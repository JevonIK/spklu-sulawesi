"""Adapter Google Routes API untuk rute dan metrik jalan."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests

from .road_metrics import RoadMetricBatch, RoadMetricRequest, RoadMetricResult
from .spatial import normalize_coordinate


COMPUTE_ROUTES_URL = (
    "https://routes.googleapis.com/directions/v2:computeRoutes"
)
COMPUTE_ROUTE_MATRIX_URL = (
    "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
)
ROUTE_FIELD_MASK = (
    "routes.distanceMeters,routes.duration,"
    "routes.polyline.encodedPolyline"
)
MATRIX_FIELD_MASK = (
    "originIndex,destinationIndex,status,condition,distanceMeters,duration"
)
MAX_MATRIX_DESTINATIONS = 625
MAX_INTERMEDIATE_WAYPOINTS = 25


class GoogleRoutesError(RuntimeError):
    """Kesalahan aman yang tidak membocorkan API key atau respons mentah."""

    def __init__(self, code, message, *, status_code=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ApiQuotaBudgetExceeded(GoogleRoutesError):
    """Salah satu hard limit quota eksperimen telah tercapai."""

    def __init__(self, code, message, limit):
        super().__init__(
            code,
            message,
        )
        self.limit = limit


@dataclass
class ApiQuotaBudget:
    """Budget terpisah untuk Compute Routes dan elemen Route Matrix."""

    maximum_compute_routes: int
    maximum_compute_routes_per_minute: int
    maximum_compute_routes_per_scenario: int
    maximum_matrix_elements: int
    maximum_matrix_elements_per_minute: int
    clock: object = field(default=time.monotonic, repr=False)
    sleeper: object = field(default=time.sleep, repr=False)
    compute_routes_attempt_count: int = 0
    matrix_request_attempt_count: int = 0
    matrix_element_attempt_count: int = 0
    rate_limit_wait_seconds: float = 0.0
    _active_scenario_id: str | None = field(default=None, init=False)
    _compute_routes_per_scenario: dict = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _compute_routes_events: list = field(
        default_factory=list,
        init=False,
        repr=False,
    )
    _matrix_element_events: list = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __post_init__(self):
        limits = {
            "maximum_compute_routes": self.maximum_compute_routes,
            "maximum_compute_routes_per_minute": (
                self.maximum_compute_routes_per_minute
            ),
            "maximum_compute_routes_per_scenario": (
                self.maximum_compute_routes_per_scenario
            ),
            "maximum_matrix_elements": self.maximum_matrix_elements,
            "maximum_matrix_elements_per_minute": (
                self.maximum_matrix_elements_per_minute
            ),
        }
        for name, value in limits.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} harus berupa integer.")
            if value <= 0:
                raise ValueError(f"{name} harus lebih besar dari nol.")

    @contextmanager
    def scenario(self, scenario_id):
        if self._active_scenario_id is not None:
            raise RuntimeError("Konteks quota skenario tidak dapat ditumpuk.")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("ID skenario quota tidak valid.")
        self._active_scenario_id = scenario_id
        try:
            yield
        finally:
            self._active_scenario_id = None

    def _wait(self, seconds):
        seconds = max(0.0, float(seconds))
        if seconds <= 0:
            return
        self.sleeper(seconds)
        self.rate_limit_wait_seconds += seconds

    def _purge_compute_routes_window(self, now):
        self._compute_routes_events = [
            timestamp
            for timestamp in self._compute_routes_events
            if now - timestamp < 60
        ]

    def _pace_compute_routes(self):
        while True:
            now = self.clock()
            self._purge_compute_routes_window(now)
            if (
                len(self._compute_routes_events)
                < self.maximum_compute_routes_per_minute
            ):
                return now
            self._wait(60 - (now - self._compute_routes_events[0]) + 0.01)

    def _purge_matrix_window(self, now):
        self._matrix_element_events = [
            event
            for event in self._matrix_element_events
            if now - event[0] < 60
        ]

    def _pace_matrix_elements(self, element_count):
        if element_count > self.maximum_matrix_elements_per_minute:
            raise ApiQuotaBudgetExceeded(
                "matrix_elements_per_minute_exceeded",
                (
                    "Satu request Route Matrix memuat lebih banyak elemen "
                    "daripada batas per menit."
                ),
                self.maximum_matrix_elements_per_minute,
            )
        while True:
            now = self.clock()
            self._purge_matrix_window(now)
            recent_elements = sum(
                count for _, count in self._matrix_element_events
            )
            if (
                recent_elements + element_count
                <= self.maximum_matrix_elements_per_minute
            ):
                return now
            self._wait(60 - (now - self._matrix_element_events[0][0]) + 0.01)

    def consume_compute_routes(self):
        if self.compute_routes_attempt_count >= self.maximum_compute_routes:
            raise ApiQuotaBudgetExceeded(
                "compute_routes_budget_exceeded",
                "Batas total Compute Routes eksperimen telah tercapai.",
                self.maximum_compute_routes,
            )
        scenario_id = self._active_scenario_id or "unscoped"
        scenario_count = self._compute_routes_per_scenario.get(scenario_id, 0)
        if scenario_count >= self.maximum_compute_routes_per_scenario:
            raise ApiQuotaBudgetExceeded(
                "compute_routes_scenario_budget_exceeded",
                "Batas Compute Routes per skenario telah tercapai.",
                self.maximum_compute_routes_per_scenario,
            )

        timestamp = self._pace_compute_routes()
        self.compute_routes_attempt_count += 1
        self._compute_routes_per_scenario[scenario_id] = scenario_count + 1
        self._compute_routes_events.append(timestamp)

    def consume_matrix_elements(self, element_count):
        if isinstance(element_count, bool) or not isinstance(element_count, int):
            raise ValueError("Jumlah elemen Route Matrix harus berupa integer.")
        if element_count <= 0:
            raise ValueError("Jumlah elemen Route Matrix harus lebih dari nol.")
        if (
            self.matrix_element_attempt_count + element_count
            > self.maximum_matrix_elements
        ):
            raise ApiQuotaBudgetExceeded(
                "matrix_elements_budget_exceeded",
                "Batas total elemen Route Matrix eksperimen akan terlampaui.",
                self.maximum_matrix_elements,
            )

        timestamp = self._pace_matrix_elements(element_count)
        self.matrix_request_attempt_count += 1
        self.matrix_element_attempt_count += element_count
        self._matrix_element_events.append((timestamp, element_count))

    def snapshot(self):
        return {
            "compute_routes_limit": self.maximum_compute_routes,
            "compute_routes_attempt_count": self.compute_routes_attempt_count,
            "compute_routes_remaining": (
                self.maximum_compute_routes - self.compute_routes_attempt_count
            ),
            "compute_routes_per_minute_limit": (
                self.maximum_compute_routes_per_minute
            ),
            "compute_routes_per_scenario_limit": (
                self.maximum_compute_routes_per_scenario
            ),
            "compute_routes_attempts_by_scenario": dict(
                self._compute_routes_per_scenario
            ),
            "matrix_element_limit": self.maximum_matrix_elements,
            "matrix_element_attempt_count": self.matrix_element_attempt_count,
            "matrix_element_remaining": (
                self.maximum_matrix_elements - self.matrix_element_attempt_count
            ),
            "matrix_elements_per_minute_limit": (
                self.maximum_matrix_elements_per_minute
            ),
            "matrix_request_attempt_count": self.matrix_request_attempt_count,
            "rate_limit_wait_seconds": round(
                self.rate_limit_wait_seconds,
                3,
            ),
        }


@dataclass(frozen=True)
class ComputedRoute:
    """Rute jalan yang dikembalikan oleh Compute Routes."""

    distance_km: float
    duration_minutes: float
    encoded_polyline: str
    coordinates: tuple[tuple[float, float], ...]

    def __post_init__(self):
        if not math.isfinite(self.distance_km) or self.distance_km <= 0:
            raise ValueError("Jarak rute harus lebih besar dari nol.")
        if not math.isfinite(self.duration_minutes) or self.duration_minutes < 0:
            raise ValueError("Durasi rute tidak boleh negatif.")
        if not self.encoded_polyline:
            raise ValueError("Polyline rute tidak boleh kosong.")
        if len(self.coordinates) < 2:
            raise ValueError("Rute harus memiliki sedikitnya dua koordinat.")

    def to_dict(self):
        return {
            "distance_km": self.distance_km,
            "duration_minutes": self.duration_minutes,
            "encoded_polyline": self.encoded_polyline,
            "coordinates": [
                {"latitude": latitude, "longitude": longitude}
                for latitude, longitude in self.coordinates
            ],
        }


def decode_google_polyline(encoded_polyline):
    """Mendekode format encoded polyline Google menjadi pasangan lat-lng."""

    if not isinstance(encoded_polyline, str) or not encoded_polyline:
        raise ValueError("Encoded polyline harus berupa teks yang tidak kosong.")

    coordinates = []
    latitude = 0
    longitude = 0
    index = 0

    def decode_component(start_index):
        result = 0
        shift = 0
        cursor = start_index
        while True:
            if cursor >= len(encoded_polyline):
                raise ValueError("Encoded polyline tidak lengkap.")
            byte = ord(encoded_polyline[cursor]) - 63
            if byte < 0:
                raise ValueError("Encoded polyline mengandung karakter tidak valid.")
            cursor += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
            if shift > 60:
                raise ValueError("Encoded polyline tidak valid.")
        delta = ~(result >> 1) if result & 1 else result >> 1
        return delta, cursor

    while index < len(encoded_polyline):
        latitude_delta, index = decode_component(index)
        longitude_delta, index = decode_component(index)
        latitude += latitude_delta
        longitude += longitude_delta
        coordinates.append((latitude / 1e5, longitude / 1e5))

    if len(coordinates) < 2:
        raise ValueError("Encoded polyline harus memuat sedikitnya dua titik.")
    return tuple(coordinates)


def _duration_minutes(raw_duration):
    if not isinstance(raw_duration, str) or not raw_duration.endswith("s"):
        raise GoogleRoutesError(
            "invalid_response",
            "Google Routes API mengembalikan format durasi yang tidak valid.",
        )
    try:
        seconds = float(raw_duration[:-1])
    except ValueError as error:
        raise GoogleRoutesError(
            "invalid_response",
            "Google Routes API mengembalikan format durasi yang tidak valid.",
        ) from error
    if not math.isfinite(seconds) or seconds < 0:
        raise GoogleRoutesError(
            "invalid_response",
            "Google Routes API mengembalikan durasi yang tidak valid.",
        )
    return seconds / 60


def _waypoint(coordinate):
    latitude, longitude = normalize_coordinate(coordinate)
    return {
        "location": {
            "latLng": {
                "latitude": latitude,
                "longitude": longitude,
            }
        }
    }


def _error_code_for_status(status_code):
    return {
        400: "invalid_upstream_request",
        401: "authentication_failed",
        403: "authentication_failed",
        429: "quota_exceeded",
    }.get(status_code, "upstream_error")


class GoogleRoutesClient:
    """Client Compute Routes sekaligus implementasi RoadMetricProvider."""

    def __init__(self, api_key, *, timeout_seconds=20, session=None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Google Maps server API key belum dikonfigurasi.")
        timeout = float(timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout Google Routes harus lebih besar dari nol.")

        self._api_key = api_key.strip()
        self.timeout_seconds = timeout
        self.session = session or requests.Session()
        self._active_request_budget = None

    @contextmanager
    def request_budget(
        self,
        *,
        maximum_compute_routes,
        maximum_compute_routes_per_minute,
        maximum_compute_routes_per_scenario,
        maximum_matrix_elements,
        maximum_matrix_elements_per_minute,
        clock=None,
        sleeper=None,
    ):
        """Menerapkan hard limit dan pacing quota selama satu eksperimen."""

        if self._active_request_budget is not None:
            raise RuntimeError("Budget quota API tidak dapat ditumpuk.")

        budget = ApiQuotaBudget(
            maximum_compute_routes=maximum_compute_routes,
            maximum_compute_routes_per_minute=(
                maximum_compute_routes_per_minute
            ),
            maximum_compute_routes_per_scenario=(
                maximum_compute_routes_per_scenario
            ),
            maximum_matrix_elements=maximum_matrix_elements,
            maximum_matrix_elements_per_minute=(
                maximum_matrix_elements_per_minute
            ),
            clock=clock or time.monotonic,
            sleeper=sleeper or time.sleep,
        )
        self._active_request_budget = budget
        try:
            yield budget
        finally:
            self._active_request_budget = None

    @contextmanager
    def quota_scenario(self, scenario_id):
        if self._active_request_budget is None:
            yield
            return
        with self._active_request_budget.scenario(scenario_id):
            yield

    def _post(self, url, payload, field_mask):
        if self._active_request_budget is not None:
            if url == COMPUTE_ROUTES_URL:
                self._active_request_budget.consume_compute_routes()
            elif url == COMPUTE_ROUTE_MATRIX_URL:
                origins = payload.get("origins", ())
                destinations = payload.get("destinations", ())
                self._active_request_budget.consume_matrix_elements(
                    len(origins) * len(destinations)
                )
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as error:
            raise GoogleRoutesError(
                "upstream_unavailable",
                "Google Routes API tidak dapat dihubungi.",
            ) from error

        if not 200 <= response.status_code < 300:
            raise GoogleRoutesError(
                _error_code_for_status(response.status_code),
                "Google Routes API menolak permintaan.",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as error:
            raise GoogleRoutesError(
                "invalid_response",
                "Google Routes API mengembalikan respons yang tidak valid.",
                status_code=response.status_code,
            ) from error

    def compute_route(self, origin, destination, *, intermediates=()):
        """Mengambil satu rute berkendara dan overview polyline."""

        origin = normalize_coordinate(origin)
        destination = normalize_coordinate(destination)
        intermediate_coordinates = tuple(
            normalize_coordinate(coordinate) for coordinate in intermediates
        )
        if len(intermediate_coordinates) > MAX_INTERMEDIATE_WAYPOINTS:
            raise ValueError(
                "Jumlah pemberhentian melebihi batas intermediate waypoint."
            )

        payload = {
            "origin": _waypoint(origin),
            "destination": _waypoint(destination),
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_UNAWARE",
            "computeAlternativeRoutes": False,
            "polylineQuality": "OVERVIEW",
            "polylineEncoding": "ENCODED_POLYLINE",
            "languageCode": "id-ID",
            "units": "METRIC",
        }
        if intermediate_coordinates:
            payload["intermediates"] = [
                _waypoint(coordinate) for coordinate in intermediate_coordinates
            ]

        response_payload = self._post(
            COMPUTE_ROUTES_URL,
            payload,
            ROUTE_FIELD_MASK,
        )
        routes = response_payload.get("routes") if isinstance(
            response_payload, dict
        ) else None
        if not routes:
            raise GoogleRoutesError(
                "route_not_found",
                "Google Routes API tidak menemukan rute berkendara.",
            )

        route = routes[0]
        try:
            distance_km = float(route["distanceMeters"]) / 1000
            duration_minutes = _duration_minutes(route["duration"])
            encoded_polyline = route["polyline"]["encodedPolyline"]
            coordinates = decode_google_polyline(encoded_polyline)
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, GoogleRoutesError):
                raise
            raise GoogleRoutesError(
                "invalid_response",
                "Google Routes API mengembalikan data rute yang tidak lengkap.",
            ) from error

        return ComputedRoute(
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            encoded_polyline=encoded_polyline,
            coordinates=coordinates,
        )

    def _fetch_origin_group(self, origin, requests_for_origin):
        payload = {
            "origins": [{"waypoint": _waypoint(origin)}],
            "destinations": [
                {"waypoint": _waypoint(request.destination)}
                for request in requests_for_origin
            ],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_UNAWARE",
            "languageCode": "id-ID",
            "units": "METRIC",
        }
        response_payload = self._post(
            COMPUTE_ROUTE_MATRIX_URL,
            payload,
            MATRIX_FIELD_MASK,
        )
        if not isinstance(response_payload, list):
            raise GoogleRoutesError(
                "invalid_response",
                "Google Routes API mengembalikan matriks yang tidak valid.",
            )

        results = []
        for element in response_payload:
            if not isinstance(element, dict):
                continue
            if element.get("originIndex", 0) != 0:
                continue
            destination_index = element.get("destinationIndex", 0)
            if not isinstance(destination_index, int) or not (
                0 <= destination_index < len(requests_for_origin)
            ):
                continue
            status = element.get("status", {})
            if status and status.get("code", 0) != 0:
                continue
            if element.get("condition") != "ROUTE_EXISTS":
                continue
            try:
                distance_km = float(element["distanceMeters"]) / 1000
                duration_minutes = _duration_minutes(element["duration"])
                result = RoadMetricResult(
                    request_id=requests_for_origin[
                        destination_index
                    ].request_id,
                    distance_km=distance_km,
                    duration_minutes=duration_minutes,
                )
            except (KeyError, TypeError, ValueError, GoogleRoutesError):
                continue
            results.append(result)
        return tuple(results)

    def fetch(self, requests_to_fetch):
        """Mengambil matriks hanya untuk pasangan edge yang telah dipangkas."""

        requests_to_fetch = tuple(requests_to_fetch)
        for request in requests_to_fetch:
            if not isinstance(request, RoadMetricRequest):
                raise TypeError("Metrik jalan memerlukan RoadMetricRequest.")
            normalize_coordinate(request.origin)
            normalize_coordinate(request.destination)

        grouped = defaultdict(list)
        for request in requests_to_fetch:
            grouped[normalize_coordinate(request.origin)].append(request)

        results = []
        external_request_count = 0
        for origin, origin_requests in grouped.items():
            for start in range(0, len(origin_requests), MAX_MATRIX_DESTINATIONS):
                batch = tuple(
                    origin_requests[start : start + MAX_MATRIX_DESTINATIONS]
                )
                results.extend(self._fetch_origin_group(origin, batch))
                external_request_count += 1

        return RoadMetricBatch(
            results=tuple(results),
            external_request_count=external_request_count,
        )
