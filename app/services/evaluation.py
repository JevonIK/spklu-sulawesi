"""Perangkat evaluasi terukur untuk eksperimen SPKLU Sulawesi."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import tempfile
import time
import tracemalloc
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from .dataset import (
    EXPECTED_PROVINCES,
    parse_connectors,
    parse_additional_charging_networks,
)
from .energy import EnergyParameters
from .spatial import normalize_coordinate


REPORT_SCHEMA_VERSION = 5
SCENARIO_SCHEMA_VERSION = 4
_SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

CSV_COLUMNS = (
    "scenario_id",
    "scenario_name",
    "region",
    "maximum_range_km",
    "current_soc_percent",
    "connector",
    "connectors",
    "preferred_connector",
    "minimum_soc_percent",
    "target_soc_percent",
    "safety_factor",
    "soc_step_percent",
    "corridor_radius_km",
    "route_sample_step_km",
    "max_total_detour_km",
    "additional_charging_networks",
    "status",
    "route_feasible",
    "reason",
    "soc_violation_count",
    "itinerary_leg_count",
    "charging_stop_count",
    "ac_fallback_stop_count",
    "charging_stop_names",
    "base_route_distance_km",
    "base_route_duration_minutes",
    "recommended_route_distance_km",
    "recommended_route_duration_minutes",
    "final_route_validation_status",
    "final_route_distance_delta_km",
    "total_road_distance_km",
    "total_energy_distance_km",
    "total_ferry_distance_km",
    "total_ferry_duration_minutes",
    "ferry_segment_count",
    "total_driving_duration_minutes",
    "total_travel_duration_minutes",
    "total_detour_km",
    "final_soc_percent",
    "minimum_observed_soc_percent",
    "corridor_candidate_count",
    "graph_node_count",
    "graph_edge_count",
    "dp_processed_states",
    "dp_evaluated_transitions",
    "compute_routes_requests",
    "compute_route_matrix_requests",
    "compute_route_matrix_elements",
    "total_external_requests",
    "runtime_ms",
    "peak_memory_mb",
    "error_type",
    "error_message",
)


class ExperimentDefinitionError(ValueError):
    """Menandai berkas skenario yang tidak sesuai kontrak eksperimen."""


def _require_mapping(value, field):
    if not isinstance(value, dict):
        raise ExperimentDefinitionError(f"{field} harus berupa objek JSON.")
    return value


def _require_text(mapping, key, field):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExperimentDefinitionError(f"{field}.{key} wajib berupa teks.")
    return value.strip()


def _validate_coordinate(scenario, key, field):
    coordinate = _require_mapping(scenario.get(key), f"{field}.{key}")
    _reject_unknown_fields(
        coordinate,
        {"label", "latitude", "longitude"},
        f"{field}.{key}",
    )
    _require_text(coordinate, "label", f"{field}.{key}")
    values = []
    for axis in ("latitude", "longitude"):
        value = coordinate.get(axis)
        if isinstance(value, bool):
            raise ExperimentDefinitionError(
                f"{field}.{key}.{axis} wajib berupa angka."
            )
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as error:
            raise ExperimentDefinitionError(
                f"{field}.{key}.{axis} wajib berupa angka."
            ) from error
        if not math.isfinite(numeric_value):
            raise ExperimentDefinitionError(
                f"{field}.{key}.{axis} wajib berupa angka finite."
            )
        values.append(numeric_value)
    try:
        coordinate_value = normalize_coordinate(values)
    except ValueError as error:
        raise ExperimentDefinitionError(
            f"{field}.{key} tidak valid: {error}"
        ) from error
    if not (-7 <= coordinate_value[0] <= 3 and 118 <= coordinate_value[1] <= 126.5):
        raise ExperimentDefinitionError(
            f"{field}.{key} harus berada dalam cakupan Sulawesi."
        )
    return coordinate_value


def _reject_unknown_fields(mapping, allowed, field):
    unknown = sorted(set(mapping) - set(allowed))
    if unknown:
        raise ExperimentDefinitionError(
            f"{field} memiliki field tidak dikenal: {', '.join(unknown)}."
        )


def _finite_number(mapping, key, field):
    value = mapping.get(key)
    if value is None or isinstance(value, bool):
        raise ExperimentDefinitionError(f"{field}.{key} wajib berupa angka.")
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ExperimentDefinitionError(
            f"{field}.{key} wajib berupa angka."
        ) from error
    if not math.isfinite(value):
        raise ExperimentDefinitionError(
            f"{field}.{key} wajib berupa angka finite."
        )
    return value


def _validate_vehicle_and_options(scenario, field):
    vehicle_field = f"{field}.vehicle"
    vehicle = _require_mapping(scenario.get("vehicle"), vehicle_field)
    _reject_unknown_fields(
        vehicle,
        {"maximum_range_km", "current_soc_percent", "connectors"},
        vehicle_field,
    )
    maximum_range = _finite_number(
        vehicle,
        "maximum_range_km",
        vehicle_field,
    )
    current_soc = _finite_number(
        vehicle,
        "current_soc_percent",
        vehicle_field,
    )
    if not 0 < maximum_range <= 2000:
        raise ExperimentDefinitionError(
            f"{vehicle_field}.maximum_range_km harus berada pada rentang >0 sampai 2000."
        )
    raw_connectors = vehicle.get("connectors")
    if not isinstance(raw_connectors, list) or not raw_connectors:
        raise ExperimentDefinitionError(
            f"{vehicle_field}.connectors wajib berupa daftar tidak kosong."
        )
    try:
        connectors = parse_connectors(raw_connectors)
    except ValueError as error:
        raise ExperimentDefinitionError(
            f"{vehicle_field}.connectors {error}."
        ) from error
    if len(connectors) != len(raw_connectors):
        raise ExperimentDefinitionError(
            f"{vehicle_field}.connectors tidak boleh duplikat."
        )

    options_field = f"{field}.options"
    options = _require_mapping(scenario.get("options"), options_field)
    expected_options = {
        "minimum_soc_percent",
        "target_soc_percent",
        "safety_factor",
        "soc_step_percent",
        "corridor_radius_km",
        "route_sample_step_km",
        "max_total_detour_km",
        "additional_charging_networks",
    }
    _reject_unknown_fields(options, expected_options, options_field)
    missing_options = sorted(expected_options - set(options))
    if missing_options:
        raise ExperimentDefinitionError(
            f"{options_field} belum memuat: {', '.join(missing_options)}."
        )
    minimum_soc = _finite_number(options, "minimum_soc_percent", options_field)
    target_soc = _finite_number(options, "target_soc_percent", options_field)
    safety_factor = _finite_number(options, "safety_factor", options_field)
    soc_step = _finite_number(options, "soc_step_percent", options_field)
    corridor_radius = _finite_number(options, "corridor_radius_km", options_field)
    route_sample_step = _finite_number(
        options,
        "route_sample_step_km",
        options_field,
    )
    max_total_detour = _finite_number(
        options,
        "max_total_detour_km",
        options_field,
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
        parse_additional_charging_networks(
            options["additional_charging_networks"]
        )
    except ValueError as error:
        raise ExperimentDefinitionError(
            f"{field} memiliki parameter kendaraan/energi tidak valid: {error}"
        ) from error
    if current_soc <= minimum_soc:
        raise ExperimentDefinitionError(
            f"{vehicle_field}.current_soc_percent harus lebih besar dari SOC minimum."
        )
    if not 0 < corridor_radius <= 100:
        raise ExperimentDefinitionError(
            f"{options_field}.corridor_radius_km harus berada pada rentang >0 sampai 100."
        )
    if not 0.1 <= route_sample_step <= 100:
        raise ExperimentDefinitionError(
            f"{options_field}.route_sample_step_km harus berada pada rentang 0,1 sampai 100."
        )
    if not 0 < max_total_detour <= 1000:
        raise ExperimentDefinitionError(
            f"{options_field}.max_total_detour_km harus berada pada rentang "
            ">0 sampai 1000."
        )


def _validate_sensitivity_oat(definition):
    if (
        not definition["experiment_id"].startswith("sensitivitas-")
        or definition["experiment_id"] == "sensitivitas-konektor-combo2"
    ):
        return
    scenarios = definition["scenarios"]
    baseline = next(
        (item for item in scenarios if item["id"] == "sensitivitas-baseline"),
        None,
    )
    if baseline is None:
        raise ExperimentDefinitionError(
            "Eksperimen sensitivitas wajib memuat sensitivitas-baseline."
        )
    option_factors = (
        "safety_factor",
        "corridor_radius_km",
        "soc_step_percent",
        "max_total_detour_km",
    )
    vehicle_factors = ("maximum_range_km",)
    fixed_options = {
        key: value
        for key, value in baseline["options"].items()
        if key not in option_factors
    }
    for scenario in scenarios:
        if scenario is baseline:
            continue
        if scenario["origin"] != baseline["origin"] or scenario[
            "destination"
        ] != baseline["destination"]:
            raise ExperimentDefinitionError(
                f"{scenario['id']} mengubah variabel di luar faktor sensitivitas."
            )
        if {
            key: value
            for key, value in scenario["vehicle"].items()
            if key not in vehicle_factors
        } != {
            key: value
            for key, value in baseline["vehicle"].items()
            if key not in vehicle_factors
        }:
            raise ExperimentDefinitionError(
                f"{scenario['id']} mengubah konfigurasi kendaraan tetap."
            )
        if {
            key: value
            for key, value in scenario["options"].items()
            if key not in option_factors
        } != fixed_options:
            raise ExperimentDefinitionError(
                f"{scenario['id']} mengubah parameter tetap sensitivitas."
            )
        changed_factors = [
            key
            for key in option_factors
            if scenario["options"][key] != baseline["options"][key]
        ]
        changed_factors.extend(
            key
            for key in vehicle_factors
            if scenario["vehicle"][key] != baseline["vehicle"][key]
        )
        if len(changed_factors) != 1:
            raise ExperimentDefinitionError(
                f"{scenario['id']} harus mengubah tepat satu faktor sensitivitas."
            )


def _validate_connector_sensitivity(definition):
    if definition["experiment_id"] != "sensitivitas-konektor-combo2":
        return
    scenarios = definition["scenarios"]
    if len(scenarios) != 2:
        raise ExperimentDefinitionError(
            "Sensitivitas konektor wajib memuat dua skenario."
        )
    expected_sets = {
        ("CCS2",),
        ("AC TYPE 2", "CCS2"),
    }
    actual_sets = {
        parse_connectors(scenario["vehicle"]["connectors"])
        for scenario in scenarios
    }
    if actual_sets != expected_sets:
        raise ExperimentDefinitionError(
            "Sensitivitas konektor wajib membandingkan CCS2 dengan "
            "AC Type 2 + CCS2."
        )
    baseline = scenarios[0]
    for scenario in scenarios[1:]:
        if (
            scenario["origin"] != baseline["origin"]
            or scenario["destination"] != baseline["destination"]
            or scenario["options"] != baseline["options"]
            or {
                key: value
                for key, value in scenario["vehicle"].items()
                if key != "connectors"
            }
            != {
                key: value
                for key, value in baseline["vehicle"].items()
                if key != "connectors"
            }
        ):
            raise ExperimentDefinitionError(
                "Sensitivitas konektor hanya boleh mengubah daftar konektor."
            )


def validate_experiment_definition(definition):
    """Memvalidasi struktur eksperimen tanpa melakukan panggilan API."""

    definition = _require_mapping(definition, "root")
    if definition.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ExperimentDefinitionError(
            f"schema_version skenario harus bernilai {SCENARIO_SCHEMA_VERSION}."
        )
    _reject_unknown_fields(
        definition,
        {"schema_version", "experiment_id", "description", "scenarios"},
        "root",
    )
    _require_text(definition, "experiment_id", "root")
    _require_text(definition, "description", "root")

    scenarios = definition.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ExperimentDefinitionError(
            "root.scenarios wajib berupa array yang tidak kosong."
        )

    known_ids = set()
    for index, scenario in enumerate(scenarios):
        field = f"root.scenarios[{index}]"
        scenario = _require_mapping(scenario, field)
        _reject_unknown_fields(
            scenario,
            {"id", "name", "region", "origin", "destination", "vehicle", "options"},
            field,
        )
        scenario_id = _require_text(scenario, "id", field)
        if scenario_id in known_ids:
            raise ExperimentDefinitionError(
                f"ID skenario duplikat: {scenario_id}."
            )
        known_ids.add(scenario_id)
        _require_text(scenario, "name", field)
        region = _require_text(scenario, "region", field)
        if region not in EXPECTED_PROVINCES:
            raise ExperimentDefinitionError(f"{field}.region tidak dikenal.")
        origin = _validate_coordinate(scenario, "origin", field)
        destination = _validate_coordinate(scenario, "destination", field)
        if origin == destination:
            raise ExperimentDefinitionError(
                f"{field}.destination harus berbeda dari origin."
            )
        _validate_vehicle_and_options(scenario, field)

    _validate_sensitivity_oat(definition)
    _validate_connector_sensitivity(definition)
    return definition


def load_experiment_definition(path):
    """Membaca dan memvalidasi satu berkas definisi eksperimen JSON."""

    source_path = Path(path).expanduser().resolve()
    try:
        with source_path.open(encoding="utf-8") as source_file:
            definition = json.load(source_file)
    except json.JSONDecodeError as error:
        raise ExperimentDefinitionError(
            f"JSON skenario tidak valid: {error.msg}."
        ) from error
    validate_experiment_definition(definition)
    return definition


def _service_payload(scenario):
    return {
        "origin": {
            "latitude": scenario["origin"]["latitude"],
            "longitude": scenario["origin"]["longitude"],
        },
        "destination": {
            "latitude": scenario["destination"]["latitude"],
            "longitude": scenario["destination"]["longitude"],
        },
        "vehicle": dict(scenario["vehicle"]),
        "options": dict(scenario.get("options", {})),
    }


def _result_template(scenario):
    vehicle = scenario["vehicle"]
    options = scenario.get("options", {})
    connectors = parse_connectors(vehicle.get("connectors"))
    preferred_connector = "CCS2" if "CCS2" in connectors else connectors[0]
    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "region": scenario["region"],
        "origin_label": scenario["origin"].get("label"),
        "destination_label": scenario["destination"].get("label"),
        "maximum_range_km": vehicle.get("maximum_range_km"),
        "current_soc_percent": vehicle.get("current_soc_percent"),
        "connector": preferred_connector,
        "connectors": " | ".join(connectors),
        "preferred_connector": preferred_connector,
        "minimum_soc_percent": options.get("minimum_soc_percent"),
        "target_soc_percent": options.get("target_soc_percent"),
        "safety_factor": options.get("safety_factor"),
        "soc_step_percent": options.get("soc_step_percent"),
        "corridor_radius_km": options.get("corridor_radius_km"),
        "route_sample_step_km": options.get("route_sample_step_km"),
        "max_total_detour_km": options.get("max_total_detour_km"),
        "additional_charging_networks": " | ".join(
            options.get("additional_charging_networks", [])
        ),
        "status": "error",
        "route_feasible": None,
        "reason": None,
        "soc_violation_count": None,
        "itinerary_leg_count": None,
        "charging_stop_count": None,
        "ac_fallback_stop_count": None,
        "charging_stop_names": None,
        "base_route_distance_km": None,
        "base_route_duration_minutes": None,
        "recommended_route_distance_km": None,
        "recommended_route_duration_minutes": None,
        "final_route_validation_status": None,
        "final_route_distance_delta_km": None,
        "total_road_distance_km": None,
        "total_energy_distance_km": None,
        "total_ferry_distance_km": None,
        "total_ferry_duration_minutes": None,
        "ferry_segment_count": None,
        "total_driving_duration_minutes": None,
        "total_travel_duration_minutes": None,
        "total_detour_km": None,
        "final_soc_percent": None,
        "minimum_observed_soc_percent": None,
        "corridor_candidate_count": None,
        "graph_node_count": None,
        "graph_edge_count": None,
        "dp_processed_states": None,
        "dp_evaluated_transitions": None,
        "compute_routes_requests": None,
        "compute_route_matrix_requests": None,
        "compute_route_matrix_elements": None,
        "total_external_requests": None,
        "runtime_ms": None,
        "peak_memory_mb": None,
        "error_type": None,
        "error_message": None,
        "itinerary_legs": None,
        "charging_stops": None,
        "graph_build_stats": None,
        "optimization_stats": None,
    }


def _soc_violation_count(itinerary, minimum_soc_percent):
    if itinerary is None:
        return 0
    tolerance = 1e-7
    return sum(
        1
        for leg in itinerary.get("legs", [])
        if float(leg["arrival_soc_percent"]) + tolerance
        < float(minimum_soc_percent)
    )


def _completed_result(scenario, pipeline_result):
    result = _result_template(scenario)
    optimization = pipeline_result["optimization"]
    itinerary = optimization.get("itinerary")
    optimization_stats = optimization["stats"]
    api_usage = pipeline_result["api_usage"]
    graph = pipeline_result["graph"]
    base_route = pipeline_result["base_route"]
    recommended_route = pipeline_result.get("recommended_route")
    route_access = pipeline_result.get("route_access") or {}
    ferry_summary = route_access.get("ferry") or (
        (recommended_route or base_route).get("ferry_summary") or {}
    )
    final_route_validation = optimization.get("final_route_validation") or {}
    charging_stops = itinerary.get("charging_stops", []) if itinerary else []
    itinerary_legs = itinerary.get("legs", []) if itinerary else []

    result.update(
        {
            "status": "completed",
            "route_feasible": bool(optimization["feasible"]),
            "reason": optimization["reason"],
            "soc_violation_count": _soc_violation_count(
                itinerary,
                optimization["parameters"]["minimum_soc_percent"],
            ),
            "itinerary_leg_count": len(itinerary_legs),
            "charging_stop_count": (
                itinerary["charging_stop_count"] if itinerary else 0
            ),
            "ac_fallback_stop_count": route_access.get(
                "ac_fallback_stop_count",
                0,
            ),
            "charging_stop_names": " | ".join(
                stop["name"] for stop in charging_stops
            ),
            "base_route_distance_km": base_route["distance_km"],
            "base_route_duration_minutes": base_route["duration_minutes"],
            "recommended_route_distance_km": (
                recommended_route["distance_km"]
                if recommended_route
                else None
            ),
            "recommended_route_duration_minutes": (
                recommended_route["duration_minutes"]
                if recommended_route
                else None
            ),
            "final_route_validation_status": final_route_validation.get(
                "status"
            ),
            "final_route_distance_delta_km": final_route_validation.get(
                "distance_delta_km"
            ),
            "total_road_distance_km": (
                itinerary["total_road_distance_km"] if itinerary else None
            ),
            "total_energy_distance_km": (
                itinerary.get(
                    "total_energy_distance_km",
                    itinerary["total_road_distance_km"],
                )
                if itinerary
                else None
            ),
            "total_ferry_distance_km": (
                itinerary.get("total_ferry_distance_km", 0)
                if itinerary
                else None
            ),
            "total_ferry_duration_minutes": (
                itinerary.get("total_ferry_duration_minutes", 0)
                if itinerary
                else None
            ),
            "ferry_segment_count": ferry_summary.get("segment_count", 0),
            "total_driving_duration_minutes": (
                itinerary["total_driving_duration_minutes"]
                if itinerary
                else None
            ),
            "total_travel_duration_minutes": (
                itinerary.get(
                    "total_travel_duration_minutes",
                    itinerary["total_driving_duration_minutes"],
                )
                if itinerary
                else None
            ),
            "total_detour_km": (
                itinerary["total_detour_km"] if itinerary else None
            ),
            "final_soc_percent": (
                itinerary["final_soc_percent"] if itinerary else None
            ),
            "minimum_observed_soc_percent": (
                itinerary["minimum_observed_soc_percent"]
                if itinerary
                else None
            ),
            "corridor_candidate_count": pipeline_result[
                "candidate_summary"
            ]["corridor_candidate_count"],
            "graph_node_count": graph["node_count"],
            "graph_edge_count": graph["edge_count"],
            "dp_processed_states": optimization_stats["processed_states"],
            "dp_evaluated_transitions": optimization_stats[
                "evaluated_transitions"
            ],
            "compute_routes_requests": api_usage[
                "compute_routes_requests"
            ],
            "compute_route_matrix_requests": api_usage[
                "compute_route_matrix_requests"
            ],
            "compute_route_matrix_elements": api_usage[
                "compute_route_matrix_elements"
            ],
            "total_external_requests": api_usage["total_external_requests"],
            "itinerary_legs": itinerary_legs,
            "charging_stops": [
                {
                    "sequence": stop["sequence"],
                    "node_id": stop["node_id"],
                    "name": stop["name"],
                    "arrival_soc_percent": stop["arrival_soc_percent"],
                    "departure_soc_percent": stop["departure_soc_percent"],
                    "charged_soc_percent": stop["charged_soc_percent"],
                    "station": stop.get("station"),
                }
                for stop in charging_stops
            ],
            "graph_build_stats": graph["stats"],
            "optimization_stats": optimization_stats,
        }
    )
    return result


def evaluate_scenario(service, scenario):
    """Menjalankan satu skenario dan selalu mengembalikan catatan terukur."""

    started_at = time.perf_counter()
    memory_started_here = not tracemalloc.is_tracing()
    if memory_started_here:
        tracemalloc.start()
    else:
        tracemalloc.reset_peak()

    try:
        routes_client = getattr(service, "routes_client", None)
        scenario_context = (
            routes_client.quota_scenario(scenario["id"])
            if routes_client is not None
            and hasattr(routes_client, "quota_scenario")
            else nullcontext()
        )
        with scenario_context:
            recommendation_input = service.parse_input(
                _service_payload(scenario)
            )
            pipeline_result = service.recommend(recommendation_input)
            result = _completed_result(scenario, pipeline_result)
    except Exception as error:  # Satu kegagalan tidak membatalkan batch eksperimen.
        result = _result_template(scenario)
        result["error_type"] = type(error).__name__
        result["error_message"] = str(error)
    finally:
        _, peak_bytes = tracemalloc.get_traced_memory()
        if memory_started_here:
            tracemalloc.stop()

    result["runtime_ms"] = round(
        (time.perf_counter() - started_at) * 1000,
        3,
    )
    result["peak_memory_mb"] = round(peak_bytes / (1024 * 1024), 6)
    return result


def _mean(values):
    values = [float(value) for value in values if value is not None]
    return round(sum(values) / len(values), 6) if values else None


def summarize_results(results):
    """Meringkas hasil batch dengan denominator yang eksplisit."""

    completed = [result for result in results if result["status"] == "completed"]
    feasible = [result for result in completed if result["route_feasible"]]
    return {
        "scenario_count": len(results),
        "completed_count": len(completed),
        "error_count": len(results) - len(completed),
        "feasible_count": len(feasible),
        "infeasible_count": len(completed) - len(feasible),
        "feasibility_rate_percent": (
            round(len(feasible) / len(completed) * 100, 6)
            if completed
            else None
        ),
        "total_soc_violations": sum(
            result["soc_violation_count"] or 0 for result in completed
        ),
        "mean_charging_stop_count_feasible": _mean(
            result["charging_stop_count"] for result in feasible
        ),
        "mean_runtime_ms": _mean(
            result["runtime_ms"] for result in results
        ),
        "maximum_peak_memory_mb": max(
            (result["peak_memory_mb"] for result in results),
            default=None,
        ),
        "total_external_requests": sum(
            result["total_external_requests"] or 0 for result in completed
        ),
        "total_route_matrix_elements": sum(
            result["compute_route_matrix_elements"] or 0
            for result in completed
        ),
    }


def run_experiment(
    service,
    definition,
    *,
    source_path=None,
    batch_size=None,
    batch_interval_seconds=0,
    sleep_fn=time.sleep,
    progress_callback=None,
    provenance=None,
):
    """Menjalankan semua skenario secara berurutan agar metrik dapat diaudit."""

    validate_experiment_definition(definition)
    scenarios = definition["scenarios"]
    if batch_size is None:
        batch_size = len(scenarios)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("Ukuran batch harus berupa integer.")
    if batch_size <= 0:
        raise ValueError("Ukuran batch harus lebih besar dari nol.")
    batch_interval_seconds = float(batch_interval_seconds)
    if not math.isfinite(batch_interval_seconds) or batch_interval_seconds < 0:
        raise ValueError("Jeda batch tidak valid.")
    results = []
    batch_wait_seconds = 0.0
    for index, scenario in enumerate(scenarios, start=1):
        results.append(evaluate_scenario(service, scenario))
        needs_next_batch = index < len(scenarios) and index % batch_size == 0
        if needs_next_batch and batch_interval_seconds > 0:
            if progress_callback:
                progress_callback(
                    {
                        "completed_scenarios": index,
                        "remaining_scenarios": len(scenarios) - index,
                        "wait_seconds": batch_interval_seconds,
                    }
                )
            sleep_fn(batch_interval_seconds)
            batch_wait_seconds += batch_interval_seconds
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": {
            "id": definition["experiment_id"],
            "description": definition["description"],
            "source_path": Path(source_path).name if source_path else None,
            "source_sha256": (
                hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
                if source_path
                else None
            ),
        },
        "provenance": dict(provenance) if provenance is not None else None,
        "definition": definition,
        "batching": {
            "batch_size": batch_size,
            "batch_interval_seconds": batch_interval_seconds,
            "batch_wait_seconds": batch_wait_seconds,
            "batch_count": math.ceil(len(scenarios) / batch_size),
        },
        "aggregate": summarize_results(results),
        "results": results,
    }


def experiment_report_paths(output_dir, label):
    """Memvalidasi label dan mengembalikan path laporan tanpa menulis."""

    if not isinstance(label, str) or not _SAFE_LABEL.fullmatch(label):
        raise ValueError(
            "Label keluaran hanya boleh berisi huruf kecil, angka, titik, "
            "garis bawah, dan tanda hubung."
        )
    destination = Path(output_dir).expanduser().resolve()
    return destination / f"{label}.json", destination / f"{label}.csv"


def write_experiment_report(report, output_dir, label, *, overwrite=False):
    """Mengekspor laporan yang sama ke JSON rinci dan CSV tabular."""

    json_path, csv_path = experiment_report_paths(output_dir, label)
    if not overwrite and (json_path.exists() or csv_path.exists()):
        raise FileExistsError(
            "Laporan dengan label tersebut sudah ada; gunakan --overwrite "
            "jika memang ingin menggantinya."
        )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths = []
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=json_path.parent,
            prefix=f".{json_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as json_file:
            temporary_json_path = Path(json_file.name)
            temporary_paths.append(temporary_json_path)
            json.dump(report, json_file, ensure_ascii=False, indent=2)
            json_file.write("\n")
            json_file.flush()
            os.fsync(json_file.fileno())
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=csv_path.parent,
            prefix=f".{csv_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as csv_file:
            temporary_csv_path = Path(csv_file.name)
            temporary_paths.append(temporary_csv_path)
            writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for result in report["results"]:
                writer.writerow(
                    {column: result.get(column) for column in CSV_COLUMNS}
                )
            csv_file.flush()
            os.fsync(csv_file.fileno())
        os.replace(temporary_json_path, json_path)
        temporary_paths.remove(temporary_json_path)
        os.replace(temporary_csv_path, csv_path)
        temporary_paths.remove(temporary_csv_path)
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)
    return json_path, csv_path
