"""Bangun snapshot notebook secara deterministik dari laporan live historis.

Script ini tidak melakukan request jaringan. Laporan JSON sumber harus sudah
tersedia secara lokal dan hash-nya harus cocok dengan provenance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DATA = PROJECT_ROOT / "notebooks" / "data"
PROVENANCE_PATH = NOTEBOOK_DATA / "provenance.json"

SUMMARY_COLUMNS = (
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

LEG_COLUMNS = (
    "scenario_id",
    "region",
    "sequence",
    "source_name",
    "target_name",
    "road_distance_km",
    "road_duration_minutes",
    "estimated_detour_km",
    "departure_soc_percent",
    "arrival_soc_percent",
    "consumption_soc_percent",
)

DETOUR_COLUMNS = (
    "scenario_id",
    "scenario_name",
    "region",
    "maximum_range_km",
    "current_soc_percent",
    "connectors",
    "preferred_connector",
    "minimum_soc_percent",
    "target_soc_percent",
    "safety_factor",
    "soc_step_percent",
    "corridor_radius_km",
    "route_sample_step_km",
    "max_total_detour_km",
    "status",
    "route_feasible",
    "reason",
    "soc_violation_count",
    "charging_stop_count",
    "ac_fallback_stop_count",
    "charging_stop_names",
    "base_route_distance_km",
    "recommended_route_distance_km",
    "total_detour_km",
    "final_soc_percent",
    "minimum_observed_soc_percent",
    "corridor_candidate_count",
    "graph_node_count",
    "graph_edge_count",
    "dp_processed_states",
    "dp_evaluated_transitions",
    "detour_pruned_transitions",
    "compute_routes_requests",
    "compute_route_matrix_requests",
    "compute_route_matrix_elements",
    "total_external_requests",
    "runtime_ms",
    "peak_memory_mb",
    "error_type",
    "error_message",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_verified_report(path, metadata, label):
    path = Path(path).expanduser().resolve()
    if sha256(path) != metadata["sha256"]:
        raise ValueError(f"Hash laporan {label} tidak sesuai provenance.")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema_version") != metadata["report_schema_version"]:
        raise ValueError(f"Schema laporan {label} tidak sesuai provenance.")
    source_version = report.get("execution", {}).get("app_version")
    if source_version != metadata["source_application_version"]:
        raise ValueError(f"Versi aplikasi laporan {label} tidak sesuai provenance.")
    if len(report.get("results", [])) != metadata["scenario_count"]:
        raise ValueError(f"Jumlah skenario laporan {label} tidak sesuai provenance.")
    canonical_definition = json.dumps(
        report.get("definition"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    definition_sha256 = hashlib.sha256(canonical_definition).hexdigest()
    if definition_sha256 != metadata["embedded_definition_canonical_sha256"]:
        raise ValueError(
            f"Definisi skenario tertanam laporan {label} tidak sesuai provenance."
        )
    return report


def write_csv(path, columns, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary_path = Path(destination.name)
            writer = csv.DictWriter(
                destination,
                fieldnames=columns,
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {column: row.get(column) for column in columns}
                )
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def build_snapshots(
    baseline_path,
    sensitivity_path,
    output_dir,
    detour_sensitivity_path=None,
):
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    baseline = load_verified_report(
        baseline_path,
        provenance["source_reports"]["baseline"],
        "baseline",
    )
    sensitivity = load_verified_report(
        sensitivity_path,
        provenance["source_reports"]["sensitivity"],
        "sensitivitas",
    )
    output_dir = Path(output_dir).expanduser().resolve()
    write_csv(
        output_dir / "baseline_results.csv",
        SUMMARY_COLUMNS,
        baseline["results"],
    )
    write_csv(
        output_dir / "sensitivity_results.csv",
        SUMMARY_COLUMNS,
        sensitivity["results"],
    )
    leg_rows = []
    for result in baseline["results"]:
        for leg in result.get("itinerary_legs") or []:
            leg_rows.append(
                {
                    "scenario_id": result["scenario_id"],
                    "region": result["region"],
                    **leg,
                }
            )
    write_csv(
        output_dir / "baseline_itinerary_legs.csv",
        LEG_COLUMNS,
        leg_rows,
    )
    filenames = [
        "baseline_results.csv",
        "sensitivity_results.csv",
        "baseline_itinerary_legs.csv",
    ]
    if detour_sensitivity_path is not None:
        detour = load_verified_report(
            detour_sensitivity_path,
            provenance["source_reports"]["detour_sensitivity"],
            "sensitivitas detour",
        )
        rows = []
        for result in detour["results"]:
            row = dict(result)
            row["detour_pruned_transitions"] = (
                (result.get("optimization_stats") or {}).get(
                    "detour_pruned_transitions"
                )
            )
            rows.append(row)
        write_csv(
            output_dir / "detour_sensitivity_results.csv",
            DETOUR_COLUMNS,
            rows,
        )
        filenames.append("detour_sensitivity_results.csv")
    return tuple(output_dir / filename for filename in filenames)


def main():
    parser = argparse.ArgumentParser(
        description="Bangun snapshot penelitian tanpa Google Maps API."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--sensitivity", required=True, type=Path)
    parser.add_argument("--detour-sensitivity", type=Path)
    parser.add_argument("--output-dir", type=Path, default=NOTEBOOK_DATA)
    args = parser.parse_args()
    for path in build_snapshots(
        args.baseline,
        args.sensitivity,
        args.output_dir,
        args.detour_sensitivity,
    ):
        print(f"{path.name}: {sha256(path)}")


if __name__ == "__main__":
    main()
