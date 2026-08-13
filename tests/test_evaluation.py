import csv
import json

import pytest

from app.services.evaluation import (
    ExperimentDefinitionError,
    evaluate_scenario,
    load_experiment_definition,
    run_experiment,
    validate_experiment_definition,
    write_experiment_report,
)
from app.services.dataset import load_station_catalog


def scenario(scenario_id="skenario-uji"):
    return {
        "id": scenario_id,
        "name": "Koridor pengujian",
        "region": "Sulawesi Selatan",
        "origin": {"label": "Awal", "latitude": -5.1, "longitude": 119.4},
        "destination": {
            "label": "Tujuan",
            "latitude": -4.0,
            "longitude": 119.6,
        },
        "vehicle": {
            "maximum_range_km": 300,
            "current_soc_percent": 80,
            "connector": "CCS2",
        },
        "options": {
            "minimum_soc_percent": 20,
            "target_soc_percent": 80,
        },
    }


def definition(*scenarios):
    return {
        "schema_version": 1,
        "experiment_id": "eksperimen-uji",
        "description": "Definisi eksperimen untuk pengujian.",
        "scenarios": list(scenarios or (scenario(),)),
    }


class FakeEvaluationService:
    def __init__(self, *, error=None):
        self.error = error
        self.received_payloads = []

    def parse_input(self, payload):
        self.received_payloads.append(payload)
        return payload

    def recommend(self, recommendation_input):
        if self.error:
            raise self.error
        assert recommendation_input["vehicle"]["connector"] == "CCS2"
        return {
            "parameters": {"minimum_soc_percent": 20},
            "candidate_summary": {"corridor_candidate_count": 3},
            "graph": {"node_count": 5, "edge_count": 6},
            "optimization": {
                "feasible": True,
                "reason": "feasible",
                "parameters": {"minimum_soc_percent": 20},
                "stats": {
                    "processed_states": 8,
                    "evaluated_transitions": 12,
                },
                "itinerary": {
                    "legs": [
                        {"arrival_soc_percent": 40},
                        {"arrival_soc_percent": 30},
                    ],
                    "charging_stop_count": 1,
                    "total_road_distance_km": 250,
                    "total_driving_duration_minutes": 300,
                    "total_detour_km": 4.5,
                    "final_soc_percent": 30,
                    "minimum_observed_soc_percent": 30,
                },
            },
            "api_usage": {
                "compute_routes_requests": 2,
                "compute_route_matrix_requests": 1,
                "compute_route_matrix_elements": 6,
                "total_external_requests": 3,
            },
        }


def test_baseline_file_covers_all_six_research_regions():
    loaded = load_experiment_definition(
        "experiments/scenarios_baseline.json"
    )

    assert len(loaded["scenarios"]) == 6
    assert {item["region"] for item in loaded["scenarios"]} == {
        "Sulawesi Selatan",
        "Sulawesi Tengah",
        "Sulawesi Tenggara",
        "Sulawesi Utara",
        "Sulawesi Barat",
        "Gorontalo",
    }
    assert all(
        item["vehicle"]["connector"] == "CCS2"
        for item in loaded["scenarios"]
    )
    catalog = load_station_catalog("dataset_spklu_sulawesi.csv")
    dataset_coordinates = {
        (round(node.latitude, 8), round(node.longitude, 8))
        for node in catalog.nodes
    }
    scenario_endpoints = {
        (
            round(float(item[endpoint]["latitude"]), 8),
            round(float(item[endpoint]["longitude"]), 8),
        )
        for item in loaded["scenarios"]
        for endpoint in ("origin", "destination")
    }
    assert scenario_endpoints <= dataset_coordinates


def test_sensitivity_file_changes_one_parameter_at_a_time():
    loaded = load_experiment_definition(
        "experiments/scenarios_sensitivity.json"
    )
    options = [item["options"] for item in loaded["scenarios"]]

    assert len(options) == 7
    assert {item["safety_factor"] for item in options} == {0.8, 0.9, 1.0}
    assert {item["corridor_radius_km"] for item in options} == {5, 10, 15}
    assert {item["soc_step_percent"] for item in options} == {2.5, 5, 10}


def test_definition_rejects_duplicate_scenario_id():
    duplicate = definition(scenario("sama"), scenario("sama"))

    with pytest.raises(ExperimentDefinitionError, match="duplikat"):
        validate_experiment_definition(duplicate)


def test_scenario_records_metrics_and_soc_safety():
    service = FakeEvaluationService()

    result = evaluate_scenario(service, scenario())

    assert result["status"] == "completed"
    assert result["route_feasible"] is True
    assert result["soc_violation_count"] == 0
    assert result["charging_stop_count"] == 1
    assert result["safety_factor"] is None
    assert result["total_driving_duration_minutes"] == 300
    assert result["total_external_requests"] == 3
    assert result["runtime_ms"] >= 0
    assert result["peak_memory_mb"] >= 0
    assert "label" not in service.received_payloads[0]["origin"]


def test_scenario_error_is_isolated_from_experiment_batch():
    service = FakeEvaluationService(error=RuntimeError("gagal terukur"))

    report = run_experiment(service, definition(scenario("gagal")))

    assert report["aggregate"]["completed_count"] == 0
    assert report["aggregate"]["error_count"] == 1
    assert report["aggregate"]["feasibility_rate_percent"] is None
    assert report["results"][0]["error_type"] == "RuntimeError"
    assert report["results"][0]["error_message"] == "gagal terukur"


def test_experiment_summary_and_json_csv_export(tmp_path):
    report = run_experiment(
        FakeEvaluationService(),
        definition(scenario("satu"), scenario("dua")),
    )

    json_path, csv_path = write_experiment_report(
        report,
        tmp_path,
        "hasil-uji",
    )

    assert report["aggregate"]["feasibility_rate_percent"] == 100
    assert report["aggregate"]["total_soc_violations"] == 0
    assert report["aggregate"]["total_external_requests"] == 6
    assert json.loads(json_path.read_text(encoding="utf-8"))[
        "aggregate"
    ] == report["aggregate"]
    with csv_path.open(encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert [row["scenario_id"] for row in rows] == ["satu", "dua"]
    assert rows[0]["total_driving_duration_minutes"] == "300"
    assert rows[0]["minimum_soc_percent"] == "20"
    assert report["definition"]["experiment_id"] == "eksperimen-uji"

    with pytest.raises(FileExistsError, match="sudah ada"):
        write_experiment_report(report, tmp_path, "hasil-uji")


def test_experiment_cli_requires_explicit_live_api_confirmation(
    app, tmp_path
):
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        json.dumps(definition(), ensure_ascii=False),
        encoding="utf-8",
    )
    app.extensions["recommendation_service"] = FakeEvaluationService()
    runner = app.test_cli_runner()

    rejected = runner.invoke(
        args=["experiment-run", "--scenarios", str(scenario_path)]
    )
    accepted = runner.invoke(
        args=[
            "experiment-run",
            "--scenarios",
            str(scenario_path),
            "--output-dir",
            str(tmp_path),
            "--label",
            "cli-uji",
            "--confirm-live-api",
        ]
    )

    assert rejected.exit_code == 2
    assert "--confirm-live-api" in rejected.output
    assert accepted.exit_code == 0
    assert '"feasible_count": 1' in accepted.output
    assert (tmp_path / "cli-uji.json").exists()
    assert (tmp_path / "cli-uji.csv").exists()
