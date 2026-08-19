"""Perangkat evaluasi terukur untuk eksperimen SPKLU Sulawesi."""

from __future__ import annotations

import csv
import json
import math
import re
import time
import tracemalloc
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path


REPORT_SCHEMA_VERSION = 2
SCENARIO_SCHEMA_VERSION = 1
_SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

CSV_COLUMNS = (
    "scenario_id",
    "scenario_name",
    "region",
    "maximum_range_km",
    "current_soc_percent",
    "connector",
    "minimum_soc_percent",
    "target_soc_percent",
    "safety_factor",
    "soc_step_percent",
    "corridor_radius_km",
    "status",
    "route_feasible",
    "reason",
    "soc_violation_count",
    "itinerary_leg_count",
    "charging_stop_count",
    "charging_stop_names",
    "base_route_distance_km",
    "base_route_duration_minutes",
    "recommended_route_distance_km",
    "recommended_route_duration_minutes",
    "total_road_distance_km",
    "total_driving_duration_minutes",
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


def validate_experiment_definition(definition):
    """Memvalidasi struktur eksperimen tanpa melakukan panggilan API."""

    definition = _require_mapping(definition, "root")
    if definition.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ExperimentDefinitionError(
            "schema_version skenario harus bernilai 1."
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
        scenario_id = _require_text(scenario, "id", field)
        if scenario_id in known_ids:
            raise ExperimentDefinitionError(
                f"ID skenario duplikat: {scenario_id}."
            )
        known_ids.add(scenario_id)
        _require_text(scenario, "name", field)
        _require_text(scenario, "region", field)
        _validate_coordinate(scenario, "origin", field)
        _validate_coordinate(scenario, "destination", field)
        _require_mapping(scenario.get("vehicle"), f"{field}.vehicle")
        if "options" in scenario:
            _require_mapping(scenario["options"], f"{field}.options")

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
    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "region": scenario["region"],
        "origin_label": scenario["origin"].get("label"),
        "destination_label": scenario["destination"].get("label"),
        "maximum_range_km": vehicle.get("maximum_range_km"),
        "current_soc_percent": vehicle.get("current_soc_percent"),
        "connector": vehicle.get("connector"),
        "minimum_soc_percent": options.get("minimum_soc_percent"),
        "target_soc_percent": options.get("target_soc_percent"),
        "safety_factor": options.get("safety_factor"),
        "soc_step_percent": options.get("soc_step_percent"),
        "corridor_radius_km": options.get("corridor_radius_km"),
        "status": "error",
        "route_feasible": None,
        "reason": None,
        "soc_violation_count": None,
        "itinerary_leg_count": None,
        "charging_stop_count": None,
        "charging_stop_names": None,
        "base_route_distance_km": None,
        "base_route_duration_minutes": None,
        "recommended_route_distance_km": None,
        "recommended_route_duration_minutes": None,
        "total_road_distance_km": None,
        "total_driving_duration_minutes": None,
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
            "total_road_distance_km": (
                itinerary["total_road_distance_km"] if itinerary else None
            ),
            "total_driving_duration_minutes": (
                itinerary["total_driving_duration_minutes"]
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
            "source_path": str(Path(source_path).resolve())
            if source_path
            else None,
        },
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

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(report, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for result in report["results"]:
            writer.writerow({column: result.get(column) for column in CSV_COLUMNS})
    return json_path, csv_path
