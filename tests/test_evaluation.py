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
from app.services.google_routes import GoogleRoutesClient
from app.services.quota_ledger import GoogleRoutesQuotaLedger


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
            "safety_factor": 0.9,
            "soc_step_percent": 5,
            "corridor_radius_km": 10,
            "route_sample_step_km": 5,
            "additional_charging_networks": [],
        },
    }


def definition(*scenarios):
    return {
        "schema_version": 2,
        "experiment_id": "eksperimen-uji",
        "description": "Definisi eksperimen untuk pengujian.",
        "scenarios": list(scenarios or (scenario(),)),
    }


class FakeEvaluationService:
    def __init__(self, *, error=None):
        self.error = error
        self.received_payloads = []
        self.routes_client = GoogleRoutesClient("unused-test-key")

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
            "base_route": {
                "distance_km": 245,
                "duration_minutes": 290,
            },
            "recommended_route": {
                "distance_km": 250,
                "duration_minutes": 300,
            },
            "graph": {
                "node_count": 5,
                "edge_count": 6,
                "stats": {
                    "accepted_edges": 6,
                    "geodesic_pruned_pairs": 2,
                },
            },
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
                        {
                            "sequence": 1,
                            "source_name": "Awal",
                            "target_name": "SPKLU Tengah",
                            "arrival_soc_percent": 40,
                        },
                        {
                            "sequence": 2,
                            "source_name": "SPKLU Tengah",
                            "target_name": "Tujuan",
                            "arrival_soc_percent": 30,
                        },
                    ],
                    "charging_stops": [
                        {
                            "sequence": 1,
                            "node_id": "spklu-tengah",
                            "name": "SPKLU Tengah",
                            "arrival_soc_percent": 40,
                            "departure_soc_percent": 80,
                            "charged_soc_percent": 40,
                            "station": {
                                "node_id": "spklu-tengah",
                                "unit_count": 1,
                            },
                        }
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
    assert result["itinerary_leg_count"] == 2
    assert result["charging_stop_names"] == "SPKLU Tengah"
    assert result["base_route_distance_km"] == 245
    assert result["recommended_route_distance_km"] == 250
    assert result["charging_stops"][0]["node_id"] == "spklu-tengah"
    assert result["graph_build_stats"]["accepted_edges"] == 6
    assert result["safety_factor"] == pytest.approx(0.9)
    assert result["route_sample_step_km"] == pytest.approx(5)
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
    assert rows[0]["charging_stop_names"] == "SPKLU Tengah"
    assert report["definition"]["experiment_id"] == "eksperimen-uji"
    assert report["schema_version"] == 3

    with pytest.raises(FileExistsError, match="sudah ada"):
        write_experiment_report(report, tmp_path, "hasil-uji")


def test_experiment_batches_scenarios_with_minimum_minute_pause():
    waits = []
    report = run_experiment(
        FakeEvaluationService(),
        definition(
            scenario("satu"),
            scenario("dua"),
            scenario("tiga"),
            scenario("empat"),
        ),
        batch_size=2,
        batch_interval_seconds=61,
        sleep_fn=waits.append,
    )

    assert waits == [61]
    assert report["batching"] == {
        "batch_size": 2,
        "batch_interval_seconds": 61,
        "batch_wait_seconds": 61,
        "batch_count": 2,
    }


def test_experiment_allows_multibatch_without_forced_pause():
    waits = []
    report = run_experiment(
        FakeEvaluationService(),
        definition(scenario("satu"), scenario("dua")),
        batch_size=1,
        batch_interval_seconds=0,
        sleep_fn=waits.append,
    )

    assert waits == []
    assert report["batching"]["batch_wait_seconds"] == 0


def test_experiment_cli_requires_explicit_live_api_confirmation(
    app, tmp_path
):
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        json.dumps(definition(), ensure_ascii=False),
        encoding="utf-8",
    )
    fake_service = FakeEvaluationService()
    app.extensions["recommendation_service"] = fake_service
    app.extensions["experiment_recommendation_service"] = fake_service
    app.config["GOOGLE_QUOTA_LEDGER_PATH"] = tmp_path / "quota-ledger.json"
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
    assert '"compute_routes_limit": 60' in accepted.output
    assert '"matrix_element_limit": 2000' in accepted.output
    report = json.loads((tmp_path / "cli-uji.json").read_text())
    assert report["execution"] == {
            "app_version": "0.15.0",
        "live_api_confirmed": True,
        "outcome": "completed",
        "compute_routes_limit": 60,
        "compute_routes_attempt_count": 0,
        "compute_routes_remaining": 60,
        "compute_routes_per_minute_limit": 100,
        "compute_routes_per_scenario_limit": 10,
        "compute_routes_attempts_by_scenario": {},
        "matrix_element_limit": 2000,
        "matrix_element_attempt_count": 0,
        "matrix_element_remaining": 2000,
        "matrix_elements_per_minute_limit": 2000,
        "matrix_request_attempt_count": 0,
        "rate_limit_wait_seconds": 0.0,
    }
    assert report["daily_quota"]["actual_compute_routes"] == 0
    assert report["daily_quota"]["actual_matrix_elements"] == 0
    assert report["daily_quota"]["completed_or_failed_run_count"] == 1
    assert report["daily_quota"]["active_reservation_count"] == 0
    assert report["batching"]["batch_count"] == 1
    assert (tmp_path / "cli-uji.json").exists()
    assert (tmp_path / "cli-uji.csv").exists()


def test_experiment_cli_reports_scenario_errors_as_failed(app, tmp_path):
    scenario_path = tmp_path / "error-scenarios.json"
    scenario_path.write_text(
        json.dumps(definition(), ensure_ascii=False),
        encoding="utf-8",
    )
    fake_service = FakeEvaluationService(
        error=RuntimeError("upstream tidak tersedia")
    )
    app.extensions["recommendation_service"] = fake_service
    app.extensions["experiment_recommendation_service"] = fake_service
    ledger_path = tmp_path / "error-quota-ledger.json"
    app.config["GOOGLE_QUOTA_LEDGER_PATH"] = ledger_path
    runner = app.test_cli_runner()

    result = runner.invoke(
        args=[
            "experiment-run",
            "--scenarios",
            str(scenario_path),
            "--output-dir",
            str(tmp_path),
            "--label",
            "cli-error",
            "--confirm-live-api",
        ]
    )

    assert result.exit_code == 1
    assert "1 skenario error" in result.output
    assert "Laporan parsial telah disimpan" in result.output
    report = json.loads((tmp_path / "cli-error.json").read_text())
    assert report["aggregate"]["error_count"] == 1
    assert report["execution"]["outcome"] == "completed_with_errors"
    ledger = json.loads(ledger_path.read_text())
    runs = next(iter(ledger["days"].values()))["runs"]
    assert len(runs) == 1
    assert runs[0]["outcome"] == "failed"
    assert runs[0]["source_sha256"]
    assert (tmp_path / "cli-error.csv").exists()


def test_experiment_cli_uses_remaining_capacity_without_forced_wait(
    app,
    tmp_path,
):
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        json.dumps(definition(), ensure_ascii=False),
        encoding="utf-8",
    )
    fake_service = FakeEvaluationService()
    app.extensions["recommendation_service"] = fake_service
    app.extensions["experiment_recommendation_service"] = fake_service
    ledger_path = tmp_path / "shared-quota-ledger.json"
    app.config["GOOGLE_QUOTA_LEDGER_PATH"] = ledger_path
    quota = GoogleRoutesQuotaLedger(ledger_path)
    reservation = quota.reserve(
        label="web-sebelumnya",
        maximum_compute_routes=2,
        maximum_matrix_elements=625,
    )
    quota.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=1,
        matrix_element_attempt_count=25,
        outcome="completed",
    )

    result = app.test_cli_runner().invoke(
        args=[
            "experiment-run",
            "--scenarios",
            str(scenario_path),
            "--output-dir",
            str(tmp_path),
            "--label",
            "cli-setelah-web",
            "--max-matrix-elements",
            "1975",
            "--confirm-live-api",
        ]
    )

    assert result.exit_code == 0
    assert (tmp_path / "cli-setelah-web.json").exists()
    status = quota.status()
    assert status["completed_or_failed_run_count"] == 2
    assert status["actual_compute_routes"] == 1
    assert status["actual_matrix_elements"] == 25
