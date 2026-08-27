"""Orkestrasi pipeline rekomendasi SPKLU Sulawesi."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from ..constants import (
    COMBO2_CONNECTOR_POLICY,
    DEFAULT_CONNECTORS,
    connector_preference_policy,
    fallback_connectors_for,
    preferred_connector_for,
)
from .dataset import (
    CHARGING_NETWORK_LABELS,
    CONNECTOR_ORDER,
    PUBLIC_CHARGING_NETWORK,
    SULAWESI_LATITUDE_RANGE,
    SULAWESI_LONGITUDE_RANGE,
    matching_charging_networks,
    node_is_eligible,
    parse_additional_charging_networks,
    parse_connectors,
)
from .energy import EnergyParameters, SOC_TOLERANCE
from .graph import (
    ROAD_DISTANCE_ABSOLUTE_TOLERANCE_KM,
    FerryProgressInterval,
    build_travel_graph,
)
from .google_routes import (
    MAX_INTERMEDIATE_WAYPOINTS,
    GoogleRoutesError,
)
from .optimizer import optimize_itinerary
from .quota_ledger import QuotaLedgerError
from .spatial import (
    RouteGeometry,
    find_corridor_candidates,
    normalize_coordinate,
)


class RecommendationValidationError(ValueError):
    """Kesalahan input pengguna yang dapat dikembalikan sebagai HTTP 400."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


class RecommendationQuotaError(RuntimeError):
    """Budget lokal tidak mengizinkan request rekomendasi baru."""


def _ferry_progress_intervals(route_geometry, computed_route):
    """Memproyeksikan langkah feri Google ke progres polyline rute dasar."""

    intervals = []
    for leg in computed_route.legs:
        for step in leg.ferry_steps:
            start = route_geometry.project(step.start_coordinate).progress_km
            end = route_geometry.project(step.end_coordinate).progress_km
            start, end = sorted((start, end))
            if end - start <= 1e-3:
                raise GoogleRoutesError(
                    "ferry_geometry_invalid",
                    (
                        "Segmen feri terdeteksi tetapi terminalnya tidak dapat "
                        "dipetakan secara aman pada rute."
                    ),
                )
            intervals.append(
                FerryProgressInterval(
                    start_progress_km=start,
                    end_progress_km=end,
                    distance_km=step.distance_km,
                    duration_minutes=step.duration_minutes,
                    maneuver=step.maneuver,
                )
            )
    return tuple(sorted(intervals, key=lambda item: item.start_progress_km))


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


def _boolean(mapping, key, field, *, default):
    raw_value = mapping.get(key, default)
    if not isinstance(raw_value, bool):
        raise RecommendationValidationError(
            field,
            f"{field} harus berupa boolean.",
        )
    return raw_value


def _coordinate(payload, field):
    value = _mapping(payload.get(field), field)
    latitude = _number(value, "latitude", f"{field}.latitude")
    longitude = _number(value, "longitude", f"{field}.longitude")
    try:
        return normalize_coordinate((latitude, longitude))
    except ValueError as error:
        raise RecommendationValidationError(field, str(error)) from error


def validate_sulawesi_coordinate_scope(coordinate, field):
    """Menolak request publik di luar cakupan geografis penelitian."""

    if not (
        SULAWESI_LATITUDE_RANGE[0]
        <= coordinate[0]
        <= SULAWESI_LATITUDE_RANGE[1]
        and SULAWESI_LONGITUDE_RANGE[0]
        <= coordinate[1]
        <= SULAWESI_LONGITUDE_RANGE[1]
    ):
        raise RecommendationValidationError(
            field,
            f"{field} harus berada dalam cakupan wilayah Sulawesi.",
        )


@dataclass(frozen=True)
class RecommendationInput:
    origin: tuple[float, float]
    destination: tuple[float, float]
    current_soc_percent: float
    parameters: EnergyParameters
    connectors: tuple[str, ...]
    additional_charging_networks: tuple[str, ...]
    corridor_radius_km: float
    route_sample_step_km: float
    max_total_detour_km: float
    allow_ferries: bool

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

        connector_field = (
            "vehicle.connectors"
            if "connectors" in vehicle
            else "vehicle.connector"
        )
        raw_connectors = vehicle.get(
            "connectors",
            vehicle.get("connector", DEFAULT_CONNECTORS),
        )
        try:
            connectors = parse_connectors(raw_connectors)
        except ValueError as error:
            raise RecommendationValidationError(
                connector_field, str(error)
            ) from error
        try:
            additional_charging_networks = parse_additional_charging_networks(
                options.get("additional_charging_networks", ())
            )
        except ValueError as error:
            raise RecommendationValidationError(
                "options.additional_charging_networks", str(error)
            ) from error
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
        route_sample_step = _number(
            options,
            "route_sample_step_km",
            "options.route_sample_step_km",
            default=defaults["route_sample_step_km"],
        )
        max_total_detour = _number(
            options,
            "max_total_detour_km",
            "options.max_total_detour_km",
            default=defaults["max_total_detour_km"],
        )
        allow_ferries = _boolean(
            options,
            "allow_ferries",
            "options.allow_ferries",
            default=True,
        )

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
        if not 0.1 <= route_sample_step <= 100:
            raise RecommendationValidationError(
                "options.route_sample_step_km",
                "Langkah sampling rute harus berada pada rentang 0,1 sampai 100 km.",
            )
        if not 0 < max_total_detour <= 1000:
            raise RecommendationValidationError(
                "options.max_total_detour_km",
                "Batas total detour harus berada pada rentang >0 sampai 1.000 km.",
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
            connectors=connectors,
            additional_charging_networks=additional_charging_networks,
            corridor_radius_km=corridor_radius,
            route_sample_step_km=route_sample_step,
            max_total_detour_km=max_total_detour,
            allow_ferries=allow_ferries,
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
            # `connector` dipertahankan untuk kompatibilitas klien lama.
            "connector": self.connector,
            "connectors": list(self.connectors),
            "preferred_connector": self.preferred_connector,
            "fallback_connectors": list(self.fallback_connectors),
            "connector_preference_policy": self.connector_preference_policy,
            "additional_charging_networks": list(
                self.additional_charging_networks
            ),
            "corridor_radius_km": self.corridor_radius_km,
            "route_sample_step_km": self.route_sample_step_km,
            "max_total_detour_km": self.max_total_detour_km,
            "allow_ferries": self.allow_ferries,
        }

    @property
    def connector(self):
        """Konektor utama untuk kompatibilitas integrasi versi lama."""

        return self.preferred_connector or self.connectors[0]

    @property
    def preferred_connector(self):
        """Konektor utama eksplisit; ``None`` untuk kombinasi netral."""

        return preferred_connector_for(self.connectors)

    @property
    def fallback_connectors(self):
        """Konektor cadangan yang berlaku khusus profil tepat Combo 2."""

        return fallback_connectors_for(self.connectors)

    @property
    def connector_preference_policy(self):
        """Kebijakan preferensi yang dapat diaudit pada request."""

        return connector_preference_policy(self.connectors)


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

    def _network_compatibility(self, recommendation_input):
        connector_set = frozenset(recommendation_input.connectors)
        summaries = []
        for network in recommendation_input.additional_charging_networks:
            network_nodes = [
                node
                for node in self.spatial_index.nodes
                if network in node.charging_networks
            ]
            compatible_nodes = [
                node
                for node in network_nodes
                if any(
                    unit.charging_network == network
                    and not connector_set.isdisjoint(unit.connectors)
                    for unit in node.units
                )
            ]
            available_connectors = {
                connector
                for node in network_nodes
                for unit in node.units
                if unit.charging_network == network
                for connector in unit.connectors
            }
            summaries.append(
                {
                    "network": network,
                    "label": CHARGING_NETWORK_LABELS[network],
                    "total_location_count": len(network_nodes),
                    "compatible_location_count": len(compatible_nodes),
                    "available_connectors": [
                        connector
                        for connector in CONNECTOR_ORDER
                        if connector in available_connectors
                    ],
                }
            )
        return summaries

    @staticmethod
    def _station_connector_choice(station_node, recommendation_input):
        """Pilih jaringan publik dan terapkan preferensi hanya untuk Combo 2."""

        eligible_networks = matching_charging_networks(
            station_node,
            recommendation_input.connectors,
            recommendation_input.additional_charging_networks,
        )
        if not eligible_networks:
            raise RuntimeError("Station itinerary tidak lagi kompatibel.")
        route_network = (
            PUBLIC_CHARGING_NETWORK
            if PUBLIC_CHARGING_NETWORK in eligible_networks
            else eligible_networks[0]
        )
        compatible = {
            connector
            for unit in station_node.units
            if unit.charging_network == route_network
            for connector in unit.connectors
            if connector in recommendation_input.connectors
        }
        ordered_compatible = tuple(
            connector
            for connector in CONNECTOR_ORDER
            if connector in compatible
        )
        preferred_connector = recommendation_input.preferred_connector
        fallback_connectors = frozenset(
            recommendation_input.fallback_connectors
        )
        if preferred_connector in compatible:
            selected_connector = preferred_connector
        elif fallback_connectors:
            non_fallback = tuple(
                connector
                for connector in ordered_compatible
                if connector not in fallback_connectors
            )
            selected_connector = (
                non_fallback[0] if non_fallback else ordered_compatible[0]
            )
        elif len(ordered_compatible) == 1:
            selected_connector = ordered_compatible[0]
        else:
            selected_connector = None
        is_fallback = (
            selected_connector in fallback_connectors
        )
        connector_role = (
            "ac_fallback"
            if is_fallback
            else "preferred"
            if (
                recommendation_input.connector_preference_policy
                == COMBO2_CONNECTOR_POLICY
                and selected_connector == preferred_connector
            )
            else "compatible"
        )
        return {
            "eligible_networks": eligible_networks,
            "route_network": route_network,
            "compatible_connectors": ordered_compatible,
            "selected_connector": selected_connector,
            "is_fallback": is_fallback,
            "connector_role": connector_role,
        }

    def _station_preference_ranks(self, graph, recommendation_input):
        """Rank 1 membuat AC Type 2 hanya dipilih jika rute CCS2 tak feasible."""

        return {
            node.node_id: int(
                self._station_connector_choice(
                    node.station,
                    recommendation_input,
                )["is_fallback"]
            )
            for node in graph.nodes
            if node.kind == "station" and node.station is not None
        }

    @staticmethod
    def _reconcile_final_route_itinerary(
        optimization_payload,
        final_route,
        base_route,
        parameters,
        max_total_detour_km,
    ):
        """Memvalidasi ulang SOC memakai leg Compute Routes yang digambar."""

        itinerary = optimization_payload.get("itinerary")
        if not itinerary or not final_route.legs:
            optimization_payload["final_route_validation"] = {
                "status": "not_available",
                "reason": "final_route_legs_unavailable",
            }
            return
        legs = itinerary["legs"]
        if len(legs) != len(final_route.legs):
            raise GoogleRoutesError(
                "final_route_leg_mismatch",
                "Jumlah leg rute final tidak sesuai itinerary hasil optimasi.",
            )

        stops_by_node = {
            stop["node_id"]: stop
            for stop in itinerary.get("charging_stops", [])
        }
        current_soc = float(legs[0]["departure_soc_percent"])
        minimum_observed_soc = current_soc
        matrix_distance_km = sum(
            float(leg["road_distance_km"]) for leg in legs
        )
        matrix_energy_distance_km = sum(
            float(leg.get("energy_distance_km", leg["road_distance_km"]))
            for leg in legs
        )
        for leg, final_leg in zip(legs, final_route.legs):
            stop = stops_by_node.get(leg["source_id"])
            if stop is not None:
                planned_departure = float(stop["departure_soc_percent"])
                departure_soc = max(current_soc, planned_departure)
                stop["arrival_soc_percent"] = current_soc
                stop["departure_soc_percent"] = departure_soc
                stop["charged_soc_percent"] = max(
                    0.0,
                    departure_soc - current_soc,
                )
                if stop["charged_soc_percent"] <= SOC_TOLERANCE:
                    raise GoogleRoutesError(
                        "final_route_charge_not_required",
                        (
                            "Rute final Google membuat salah satu pemberhentian "
                            "tidak lagi memerlukan pengisian; rekomendasi tidak "
                            "ditampilkan."
                        ),
                    )
            else:
                departure_soc = current_soc

            arrival_soc = parameters.arrival_soc_percent(
                departure_soc,
                final_leg.energy_distance_km,
            )
            if arrival_soc + SOC_TOLERANCE < parameters.minimum_soc_percent:
                raise GoogleRoutesError(
                    "final_route_soc_violation",
                    (
                        "Rute final Google tidak lagi memenuhi batas SOC "
                        "minimum; rekomendasi tidak ditampilkan."
                    ),
                )
            leg.update(
                {
                    "matrix_road_distance_km": leg["road_distance_km"],
                    "matrix_road_duration_minutes": leg[
                        "road_duration_minutes"
                    ],
                    "road_distance_km": final_leg.distance_km,
                    "road_duration_minutes": final_leg.duration_minutes,
                    "energy_distance_km": final_leg.energy_distance_km,
                    "ferry_distance_km": final_leg.ferry_distance_km,
                    "ferry_duration_minutes": (
                        final_leg.ferry_duration_minutes
                    ),
                    "contains_ferry": bool(final_leg.ferry_steps),
                    "departure_soc_percent": departure_soc,
                    "arrival_soc_percent": arrival_soc,
                    "consumption_soc_percent": (
                        parameters.consumption_percent(
                            final_leg.energy_distance_km
                        )
                    ),
                }
            )
            current_soc = arrival_soc
            minimum_observed_soc = min(minimum_observed_soc, arrival_soc)

        itinerary["total_road_distance_km"] = sum(
            leg.distance_km for leg in final_route.legs
        )
        itinerary["total_driving_duration_minutes"] = sum(
            leg.driving_duration_minutes for leg in final_route.legs
        )
        itinerary["total_travel_duration_minutes"] = sum(
            leg.duration_minutes for leg in final_route.legs
        )
        itinerary["total_energy_distance_km"] = sum(
            leg.energy_distance_km for leg in final_route.legs
        )
        itinerary["total_ferry_distance_km"] = sum(
            leg.ferry_distance_km for leg in final_route.legs
        )
        itinerary["total_ferry_duration_minutes"] = sum(
            leg.ferry_duration_minutes for leg in final_route.legs
        )
        itinerary["contains_ferry"] = any(
            leg.ferry_steps for leg in final_route.legs
        )
        itinerary["total_detour_km"] = max(
            0.0,
            final_route.distance_km - base_route.distance_km,
        )
        if (
            itinerary["total_detour_km"]
            > max_total_detour_km + ROAD_DISTANCE_ABSOLUTE_TOLERANCE_KM
        ):
            raise GoogleRoutesError(
                "final_route_detour_violation",
                (
                    "Rute final Google melampaui batas total detour; "
                    "rekomendasi tidak ditampilkan."
                ),
            )
        itinerary["final_soc_percent"] = current_soc
        itinerary["minimum_observed_soc_percent"] = minimum_observed_soc
        optimization_payload["final_route_validation"] = {
            "status": "passed",
            "leg_count": len(final_route.legs),
            "matrix_distance_km": matrix_distance_km,
            "matrix_energy_distance_km": matrix_energy_distance_km,
            "final_route_distance_km": final_route.distance_km,
            "final_route_energy_distance_km": sum(
                leg.energy_distance_km for leg in final_route.legs
            ),
            "ferry_segment_count": sum(
                len(leg.ferry_steps) for leg in final_route.legs
            ),
            "distance_delta_km": final_route.distance_km - matrix_distance_km,
            "minimum_soc_percent": parameters.minimum_soc_percent,
            "minimum_observed_soc_percent": minimum_observed_soc,
            "max_total_detour_km": max_total_detour_km,
            "total_detour_km": itinerary["total_detour_km"],
        }

    @staticmethod
    def _annotate_route_access(
        optimization_payload,
        graph,
        recommendation_input,
        route,
    ):
        ferry_summary = route.to_dict()["ferry_summary"]
        if not optimization_payload.get("feasible"):
            return {
                "status": "not_applicable",
                "conditional": False,
                "conditional_reasons": [],
                "conditional_stop_count": 0,
                "conditional_stops": [],
                "ac_fallback_stop_count": 0,
                "ac_fallback_stops": [],
                "ferry": ferry_summary,
                "notice": (
                    "Rute dasar memuat penyeberangan feri, tetapi itinerary "
                    "belum feasible. Konfirmasi layanan kendaraan kepada "
                    "operator sebelum berangkat."
                    if ferry_summary["contains_ferry"]
                    else "Status akses tidak berlaku karena rute belum feasible."
                ),
            }

        itinerary = optimization_payload.get("itinerary")
        charging_stops = itinerary.get("charging_stops", []) if itinerary else []
        conditional_stops = []
        ac_fallback_stops = []
        for stop in charging_stops:
            station_node = graph.node(stop["node_id"]).station
            choice = RecommendationService._station_connector_choice(
                station_node,
                recommendation_input,
            )
            eligible_networks = choice["eligible_networks"]
            route_network = choice["route_network"]
            is_conditional = route_network != PUBLIC_CHARGING_NETWORK
            station_payload = stop["station"]
            station_payload["eligible_charging_networks"] = list(
                eligible_networks
            )
            station_payload["route_charging_network"] = route_network
            station_payload["route_charging_network_label"] = (
                CHARGING_NETWORK_LABELS[route_network]
            )
            station_payload["route_compatible_connectors"] = list(
                choice["compatible_connectors"]
            )
            station_payload["route_selected_connector"] = choice[
                "selected_connector"
            ]
            station_payload["route_connector_role"] = choice[
                "connector_role"
            ]
            station_payload["route_access_type"] = (
                "dealer_conditional" if is_conditional else "public"
            )
            if is_conditional:
                conditional_stops.append(
                    {
                        "node_id": stop["node_id"],
                        "name": station_node.name,
                        "network": route_network,
                        "network_label": CHARGING_NETWORK_LABELS[
                            route_network
                        ],
                    }
                )
            if choice["is_fallback"]:
                ac_fallback_stops.append(
                    {
                        "node_id": stop["node_id"],
                        "name": station_node.name,
                        "connector": choice["selected_connector"],
                    }
                )

        ferry_conditional = ferry_summary["contains_ferry"]
        conditional_reasons = []
        if conditional_stops:
            conditional_reasons.append("dealer_charger")
        if ferry_conditional:
            conditional_reasons.append("ferry")
        conditional = bool(conditional_reasons)
        notices = []
        if conditional_stops:
            notices.append(
                "Rute menggunakan charger dealer; konfirmasi izin dan "
                "ketersediaannya kepada pengelola."
            )
        if ac_fallback_stops:
            notices.append(
                "Rute memakai AC Type 2 sebagai fallback karena itinerary "
                "CCS2 penuh tidak tersedia atau tidak terpilih."
            )
        if ferry_conditional:
            notices.append(
                "Rute menggunakan feri. SOC tidak dikurangi untuk jarak "
                "pelayaran; konfirmasi jadwal, operasional, antrean, dan "
                "kemampuan kapal mengangkut mobil kepada operator."
            )
        if not notices:
            notices.append(
                "Seluruh pemberhentian pengisian pada rute menggunakan "
                "SPKLU publik."
            )
        return {
            "status": "conditional" if conditional else "public",
            "conditional": conditional,
            "conditional_reasons": conditional_reasons,
            "conditional_stop_count": len(conditional_stops),
            "conditional_stops": conditional_stops,
            "preferred_connector": recommendation_input.preferred_connector,
            "connector_preference_policy": (
                recommendation_input.connector_preference_policy
            ),
            "ac_fallback_stop_count": len(ac_fallback_stops),
            "ac_fallback_stops": ac_fallback_stops,
            "ferry": ferry_summary,
            "notice": " ".join(notices),
        }

    def recommend(self, recommendation_input):
        if not isinstance(recommendation_input, RecommendationInput):
            raise TypeError("Pipeline memerlukan RecommendationInput.")

        route_options = (
            {"avoid_ferries": True}
            if not recommendation_input.allow_ferries
            else {}
        )
        base_route = self.routes_client.compute_route(
            recommendation_input.origin,
            recommendation_input.destination,
            **route_options,
        )
        route_geometry = RouteGeometry(base_route.coordinates)
        ferry_intervals = _ferry_progress_intervals(
            route_geometry,
            base_route,
        )
        if ferry_intervals and not recommendation_input.allow_ferries:
            raise RecommendationValidationError(
                "options.allow_ferries",
                (
                    "Rute tetap memerlukan feri meskipun opsi feri "
                    "dinonaktifkan. Pilih tujuan darat lain atau izinkan feri."
                ),
            )
        connector_candidates = find_corridor_candidates(
            self.spatial_index,
            route_geometry,
            recommendation_input.corridor_radius_km,
            connector=recommendation_input.connectors,
            sample_step_km=recommendation_input.route_sample_step_km,
        )
        candidates = tuple(
            candidate
            for candidate in connector_candidates
            if node_is_eligible(
                candidate.node,
                recommendation_input.connectors,
                recommendation_input.additional_charging_networks,
            )
        )

        parameters = recommendation_input.parameters
        graph = build_travel_graph(
            origin=recommendation_input.origin,
            destination=recommendation_input.destination,
            route=route_geometry,
            candidates=candidates,
            connector=recommendation_input.connectors,
            initial_usable_range_km=parameters.usable_range_km(
                recommendation_input.current_soc_percent
            ),
            post_charge_usable_range_km=parameters.usable_range_km(
                parameters.target_soc_percent
            ),
            road_metric_provider=self.routes_client,
            ferry_intervals=ferry_intervals,
        )
        optimization = optimize_itinerary(
            graph,
            current_soc_percent=recommendation_input.current_soc_percent,
            parameters=parameters,
            station_preference_ranks=self._station_preference_ranks(
                graph,
                recommendation_input,
            ),
            max_total_detour_km=recommendation_input.max_total_detour_km,
        )

        recommended_route = None
        compute_routes_requests = 1
        if optimization.feasible:
            stop_coordinates = tuple(
                graph.node(stop.node_id).coordinate
                for stop in optimization.itinerary.charging_stops
            )
            if len(stop_coordinates) > MAX_INTERMEDIATE_WAYPOINTS:
                raise GoogleRoutesError(
                    "too_many_charging_stops",
                    (
                        "Rute memerlukan terlalu banyak pemberhentian untuk "
                        "divalidasi oleh Google Routes API."
                    ),
                )
            if stop_coordinates:
                recommended_route = self.routes_client.compute_route(
                    recommendation_input.origin,
                    recommendation_input.destination,
                    intermediates=stop_coordinates,
                    **route_options,
                )
                compute_routes_requests += 1
            else:
                recommended_route = base_route

        if (
            recommended_route is not None
            and not recommendation_input.allow_ferries
            and any(leg.ferry_steps for leg in recommended_route.legs)
        ):
            raise RecommendationValidationError(
                "options.allow_ferries",
                (
                    "Rute rekomendasi final tetap memerlukan feri meskipun "
                    "opsi feri dinonaktifkan."
                ),
            )

        optimization_payload = optimization.to_dict()
        if recommended_route is not None:
            self._reconcile_final_route_itinerary(
                optimization_payload,
                recommended_route,
                base_route,
                parameters,
                recommendation_input.max_total_detour_km,
            )
        route_access = self._annotate_route_access(
            optimization_payload,
            graph,
            recommendation_input,
            recommended_route or base_route,
        )

        return {
            "request": recommendation_input.to_dict(),
            "parameters": parameters.to_dict(),
            "base_route": base_route.to_dict(),
            "candidate_summary": {
                "corridor_candidate_count": len(candidates),
                "connector_candidate_count": len(connector_candidates),
                "compatible_connector": recommendation_input.connector,
                "compatible_connectors": list(recommendation_input.connectors),
                "preferred_connector": recommendation_input.preferred_connector,
                "fallback_connectors": list(
                    recommendation_input.fallback_connectors
                ),
                "connector_preference_policy": (
                    recommendation_input.connector_preference_policy
                ),
                "additional_charging_networks": list(
                    recommendation_input.additional_charging_networks
                ),
                "network_compatibility": self._network_compatibility(
                    recommendation_input
                ),
            },
            "graph": {
                "stats": graph.stats.to_dict(),
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            },
            "optimization": optimization_payload,
            "route_access": route_access,
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


class QuotaProtectedRecommendationService:
    """Membatasi dan mencatat pemakaian Routes API pada endpoint publik."""

    def __init__(
        self,
        service,
        *,
        quota_ledger,
        maximum_compute_routes,
        maximum_compute_routes_per_minute,
        maximum_matrix_elements,
        maximum_matrix_elements_per_minute,
    ):
        routes_client = getattr(service, "routes_client", None)
        if routes_client is None or not hasattr(
            routes_client,
            "request_budget",
        ):
            raise ValueError(
                "Service rekomendasi memerlukan client dengan budget quota."
            )
        self.service = service
        self.routes_client = routes_client
        self.quota_ledger = quota_ledger
        self.maximum_compute_routes = maximum_compute_routes
        self.maximum_compute_routes_per_minute = (
            maximum_compute_routes_per_minute
        )
        self.maximum_matrix_elements = maximum_matrix_elements
        self.maximum_matrix_elements_per_minute = (
            maximum_matrix_elements_per_minute
        )

    def parse_input(self, payload):
        if not isinstance(payload, dict):
            return self.service.parse_input(payload)

        allowed_top_level = {"origin", "destination", "vehicle", "options"}
        unknown_top_level = sorted(set(payload) - allowed_top_level)
        if unknown_top_level:
            field = unknown_top_level[0]
            raise RecommendationValidationError(
                field,
                f"Field {field} tidak dikenal pada endpoint rekomendasi.",
            )
        for coordinate_field in ("origin", "destination"):
            coordinate = payload.get(coordinate_field)
            if isinstance(coordinate, dict):
                unknown = sorted(
                    set(coordinate) - {"latitude", "longitude"}
                )
                if unknown:
                    field = f"{coordinate_field}.{unknown[0]}"
                    raise RecommendationValidationError(
                        field,
                        f"Field {field} tidak dikenal.",
                    )
        vehicle = payload.get("vehicle")
        if isinstance(vehicle, dict):
            unknown_vehicle = sorted(
                set(vehicle)
                - {
                    "maximum_range_km",
                    "current_soc_percent",
                    "connector",
                    "connectors",
                }
            )
            if unknown_vehicle:
                field = f"vehicle.{unknown_vehicle[0]}"
                raise RecommendationValidationError(
                    field,
                    f"Field {field} tidak dikenal.",
                )
            if "connector" in vehicle and "connectors" in vehicle:
                raise RecommendationValidationError(
                    "vehicle.connectors",
                    (
                        "Gunakan salah satu dari vehicle.connector atau "
                        "vehicle.connectors, bukan keduanya."
                    ),
                )

        public_payload = dict(payload)
        options = payload.get("options")
        if isinstance(options, dict):
            allowed_options = {
                "minimum_soc_percent",
                "target_soc_percent",
                "additional_charging_networks",
                "allow_ferries",
            }
            unknown_options = sorted(set(options) - allowed_options)
            if unknown_options:
                field = f"options.{unknown_options[0]}"
                raise RecommendationValidationError(
                    field,
                    (
                        f"{field} tidak tersedia pada endpoint publik; "
                        "parameter penelitian dikelola oleh backend."
                    ),
                )
            public_payload["options"] = {
                key: options[key]
                for key in allowed_options
                if key in options
            }
        recommendation_input = self.service.parse_input(public_payload)
        if isinstance(recommendation_input, RecommendationInput):
            validate_sulawesi_coordinate_scope(
                recommendation_input.origin,
                "origin",
            )
            validate_sulawesi_coordinate_scope(
                recommendation_input.destination,
                "destination",
            )
        return recommendation_input

    @staticmethod
    def _quota_payload(status, budget):
        usage = budget.snapshot()
        return {
            "date": status["date"],
            "timezone": status["timezone"],
            "compute_routes_attempt_count": usage[
                "compute_routes_attempt_count"
            ],
            "matrix_request_attempt_count": usage[
                "matrix_request_attempt_count"
            ],
            "matrix_element_attempt_count": usage[
                "matrix_element_attempt_count"
            ],
            "daily_compute_routes_used": status["actual_compute_routes"],
            "daily_compute_routes_remaining": status[
                "available_compute_routes"
            ],
            "daily_matrix_elements_used": status[
                "actual_matrix_elements"
            ],
            "daily_matrix_elements_remaining": status[
                "available_matrix_elements"
            ],
            "compute_routes_remaining_this_minute": status[
                "available_compute_routes_this_minute"
            ],
            "matrix_elements_remaining_this_minute": status[
                "available_matrix_elements_this_minute"
            ],
        }

    def recommend(self, recommendation_input):
        request_id = f"web-{uuid.uuid4().hex}"
        try:
            reservation = self.quota_ledger.reserve(
                label=request_id,
                maximum_compute_routes=self.maximum_compute_routes,
                maximum_matrix_elements=self.maximum_matrix_elements,
                enforce_per_minute_capacity=True,
            )
        except QuotaLedgerError as error:
            raise RecommendationQuotaError(
                "Quota rekomendasi sedang tidak tersedia. Coba kembali "
                "setelah request aktif selesai atau quota harian direset."
            ) from error

        budget = None
        try:
            with self.routes_client.request_budget(
                maximum_compute_routes=self.maximum_compute_routes,
                maximum_compute_routes_per_minute=(
                    self.maximum_compute_routes_per_minute
                ),
                maximum_compute_routes_per_scenario=(
                    self.maximum_compute_routes
                ),
                maximum_matrix_elements=self.maximum_matrix_elements,
                maximum_matrix_elements_per_minute=(
                    self.maximum_matrix_elements_per_minute
                ),
            ) as budget:
                with self.routes_client.quota_scenario(request_id):
                    result = self.service.recommend(recommendation_input)
        except Exception:
            usage = budget.snapshot() if budget is not None else {}
            self.quota_ledger.finalize(
                reservation["reservation_id"],
                compute_routes_attempt_count=usage.get(
                    "compute_routes_attempt_count",
                    0,
                ),
                matrix_element_attempt_count=usage.get(
                    "matrix_element_attempt_count",
                    0,
                ),
                outcome="failed",
            )
            raise

        status = self.quota_ledger.finalize(
            reservation["reservation_id"],
            compute_routes_attempt_count=budget.compute_routes_attempt_count,
            matrix_element_attempt_count=budget.matrix_element_attempt_count,
            outcome="completed",
        )
        result["quota_guard"] = self._quota_payload(status, budget)
        return result
