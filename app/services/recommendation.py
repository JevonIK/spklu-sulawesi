"""Orkestrasi pipeline rekomendasi SPKLU Sulawesi."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .dataset import normalize_connector
from .energy import EnergyParameters
from .graph import build_travel_graph
from .optimizer import optimize_itinerary
from .spatial import (
    RouteGeometry,
    find_corridor_candidates,
    normalize_coordinate,
)


REQUIRED_CONNECTOR = "CCS2"


class RecommendationValidationError(ValueError):
    """Kesalahan input pengguna yang dapat dikembalikan sebagai HTTP 400."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def _mapping(value, field):
    if not isinstance(value, dict):
        raise RecommendationValidationError(field, f"{field} harus berupa objek.")
    return value


def _number(mapping, key, field, *, default=None):
    raw_value = mapping.get(key, default)
    if raw_value is None or isinstance(raw_value, bool):
        raise RecommendationValidationError(field, f"{field} wajib diisi.")
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as error:
        raise RecommendationValidationError(
            field, f"{field} harus berupa angka."
        ) from error
    if not math.isfinite(value):
        raise RecommendationValidationError(
            field, f"{field} harus berupa angka finite."
        )
    return value


def _coordinate(payload, field):
    value = _mapping(payload.get(field), field)
    latitude = _number(value, "latitude", f"{field}.latitude")
    longitude = _number(value, "longitude", f"{field}.longitude")
    try:
        return normalize_coordinate((latitude, longitude))
    except ValueError as error:
        raise RecommendationValidationError(field, str(error)) from error


@dataclass(frozen=True)
class RecommendationInput:
    origin: tuple[float, float]
    destination: tuple[float, float]
    current_soc_percent: float
    parameters: EnergyParameters
    connector: str
    corridor_radius_km: float
    route_sample_step_km: float

    @classmethod
    def from_payload(cls, payload, *, defaults):
        payload = _mapping(payload, "body")
        origin = _coordinate(payload, "origin")
        destination = _coordinate(payload, "destination")
        if origin == destination:
            raise RecommendationValidationError(
                "destination",
                "Lokasi tujuan harus berbeda dari lokasi awal.",
            )

        vehicle = _mapping(payload.get("vehicle"), "vehicle")
        options = payload.get("options", {})
        options = _mapping(options, "options")

        try:
            connector = normalize_connector(
                vehicle.get("connector", REQUIRED_CONNECTOR)
            )
        except ValueError as error:
            raise RecommendationValidationError(
                "vehicle.connector", str(error)
            ) from error
        if connector != REQUIRED_CONNECTOR:
            raise RecommendationValidationError(
                "vehicle.connector",
                "Sistem penelitian ini hanya mendukung konektor CCS2.",
            )

        maximum_range = _number(
            vehicle,
            "maximum_range_km",
            "vehicle.maximum_range_km",
        )
        current_soc = _number(
            vehicle,
            "current_soc_percent",
            "vehicle.current_soc_percent",
        )
        minimum_soc = _number(
            options,
            "minimum_soc_percent",
            "options.minimum_soc_percent",
            default=defaults["minimum_soc_percent"],
        )
        target_soc = _number(
            options,
            "target_soc_percent",
            "options.target_soc_percent",
            default=defaults["target_soc_percent"],
        )
        safety_factor = _number(
            options,
            "safety_factor",
            "options.safety_factor",
            default=defaults["safety_factor"],
        )
        soc_step = _number(
            options,
            "soc_step_percent",
            "options.soc_step_percent",
            default=defaults["soc_step_percent"],
        )
        corridor_radius = _number(
            options,
            "corridor_radius_km",
            "options.corridor_radius_km",
            default=defaults["corridor_radius_km"],
        )
        route_sample_step = float(defaults["route_sample_step_km"])

        if maximum_range > 2000:
            raise RecommendationValidationError(
                "vehicle.maximum_range_km",
                "Jangkauan maksimum tidak boleh melebihi 2.000 km.",
            )
        if not 0 < corridor_radius <= 100:
            raise RecommendationValidationError(
                "options.corridor_radius_km",
                "Radius koridor harus berada pada rentang >0 sampai 100 km.",
            )
        try:
            parameters = EnergyParameters(
                maximum_range_km=maximum_range,
                minimum_soc_percent=minimum_soc,
                target_soc_percent=target_soc,
                safety_factor=safety_factor,
                soc_step_percent=soc_step,
            )
            current_soc = parameters.validate_current_soc(current_soc)
        except ValueError as error:
            raise RecommendationValidationError("energy", str(error)) from error
        if current_soc <= parameters.minimum_soc_percent:
            raise RecommendationValidationError(
                "vehicle.current_soc_percent",
                (
                    "SOC saat ini harus lebih besar dari SOC minimum untuk "
                    "memulai perjalanan."
                ),
            )

        return cls(
            origin=origin,
            destination=destination,
            current_soc_percent=current_soc,
            parameters=parameters,
            connector=connector,
            corridor_radius_km=corridor_radius,
            route_sample_step_km=route_sample_step,
        )

    def to_dict(self):
        return {
            "origin": {
                "latitude": self.origin[0],
                "longitude": self.origin[1],
            },
            "destination": {
                "latitude": self.destination[0],
                "longitude": self.destination[1],
            },
            "current_soc_percent": self.current_soc_percent,
            "connector": self.connector,
            "corridor_radius_km": self.corridor_radius_km,
            "route_sample_step_km": self.route_sample_step_km,
        }


class RecommendationService:
    """Menjalankan rute dasar, Ball Tree, graf, DP, dan rute rekomendasi."""

    def __init__(self, *, spatial_index, routes_client, defaults):
        self.spatial_index = spatial_index
        self.routes_client = routes_client
        self.defaults = dict(defaults)

    def parse_input(self, payload):
        return RecommendationInput.from_payload(
            payload,
            defaults=self.defaults,
        )

    def recommend(self, recommendation_input):
        if not isinstance(recommendation_input, RecommendationInput):
            raise TypeError("Pipeline memerlukan RecommendationInput.")

        base_route = self.routes_client.compute_route(
            recommendation_input.origin,
            recommendation_input.destination,
        )
        route_geometry = RouteGeometry(base_route.coordinates)
        candidates = find_corridor_candidates(
            self.spatial_index,
            route_geometry,
            recommendation_input.corridor_radius_km,
            connector=recommendation_input.connector,
            sample_step_km=recommendation_input.route_sample_step_km,
        )

        parameters = recommendation_input.parameters
        graph = build_travel_graph(
            origin=recommendation_input.origin,
            destination=recommendation_input.destination,
            route=route_geometry,
            candidates=candidates,
            connector=recommendation_input.connector,
            initial_usable_range_km=parameters.usable_range_km(
                recommendation_input.current_soc_percent
            ),
            post_charge_usable_range_km=parameters.usable_range_km(
                parameters.target_soc_percent
            ),
            road_metric_provider=self.routes_client,
        )
        optimization = optimize_itinerary(
            graph,
            current_soc_percent=recommendation_input.current_soc_percent,
            parameters=parameters,
        )

        recommended_route = None
        compute_routes_requests = 1
        if optimization.feasible:
            stop_coordinates = tuple(
                graph.node(stop.node_id).coordinate
                for stop in optimization.itinerary.charging_stops
            )
            if stop_coordinates:
                recommended_route = self.routes_client.compute_route(
                    recommendation_input.origin,
                    recommendation_input.destination,
                    intermediates=stop_coordinates,
                )
                compute_routes_requests += 1
            else:
                recommended_route = base_route

        return {
            "request": recommendation_input.to_dict(),
            "parameters": parameters.to_dict(),
            "base_route": base_route.to_dict(),
            "candidate_summary": {
                "corridor_candidate_count": len(candidates),
                "compatible_connector": recommendation_input.connector,
            },
            "graph": {
                "stats": graph.stats.to_dict(),
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            },
            "optimization": optimization.to_dict(),
            "recommended_route": (
                recommended_route.to_dict() if recommended_route else None
            ),
            "api_usage": {
                "compute_routes_requests": compute_routes_requests,
                "compute_route_matrix_requests": (
                    graph.stats.external_request_count
                ),
                "compute_route_matrix_elements": graph.stats.road_metric_pairs,
                "total_external_requests": (
                    compute_routes_requests + graph.stats.external_request_count
                ),
            },
        }
