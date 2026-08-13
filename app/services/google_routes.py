"""Adapter Google Routes API untuk rute dan metrik jalan."""

from __future__ import annotations

import math
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass

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


class ApiRequestBudgetExceeded(GoogleRoutesError):
    """Batas request eksternal eksperimen telah tercapai."""

    def __init__(self, limit):
        super().__init__(
            "request_budget_exceeded",
            (
                "Batas aman request Google Routes API untuk eksperimen "
                f"telah tercapai ({limit} request)."
            ),
        )
        self.limit = limit


@dataclass
class ApiRequestBudget:
    """Penghitung hard limit request HTTP aktual ke Google Routes API."""

    limit: int
    used: int = 0

    @property
    def remaining(self):
        return self.limit - self.used

    @property
    def exhausted(self):
        return self.used >= self.limit

    def consume(self):
        if self.exhausted:
            raise ApiRequestBudgetExceeded(self.limit)
        self.used += 1


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
    def request_budget(self, maximum_requests):
        """Menerapkan hard limit request aktual selama satu eksperimen."""

        if isinstance(maximum_requests, bool) or not isinstance(
            maximum_requests, int
        ):
            raise ValueError("Budget request API harus berupa integer.")
        if maximum_requests <= 0:
            raise ValueError("Budget request API harus lebih besar dari nol.")
        if self._active_request_budget is not None:
            raise RuntimeError("Budget request API tidak dapat ditumpuk.")

        budget = ApiRequestBudget(limit=maximum_requests)
        self._active_request_budget = budget
        try:
            yield budget
        finally:
            self._active_request_budget = None

    def _post(self, url, payload, field_mask):
        if self._active_request_budget is not None:
            self._active_request_budget.consume()
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
