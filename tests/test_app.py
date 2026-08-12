import json


def test_index_is_available(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"SPKLU Sulawesi" in response.data
    assert b"State of Charge" in response.data


def test_health_endpoint_reports_dataset(client):
    response = client.get("/api/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "spklu-sulawesi"
    assert payload["data"]["dataset"]["exists"] is True
    assert payload["data"]["dataset"]["filename"] == "dataset_spklu_sulawesi.csv"
    assert payload["data"]["dataset"]["source_rows"] == 150
    assert payload["data"]["dataset"]["logical_nodes"] == 149
    assert payload["data"]["spatial_index"]["index_type"] == "BallTree"
    assert payload["data"]["spatial_index"]["metric"] == "haversine"
    assert payload["data"]["spatial_index"]["indexed_nodes"] == 149
    assert payload["data"]["graph_builder"]["status"] == "ready"
    assert (
        payload["data"]["graph_builder"]["road_metric_provider"]
        == "adapter_required"
    )
    assert payload["data"]["optimizer"]["status"] == "ready"
    assert (
        payload["data"]["optimizer"]["algorithm"]
        == "dynamic_programming_soc"
    )
    assert payload["data"]["optimizer"]["charging_time_included"] is False


def test_station_summary_endpoint(client):
    response = client.get("/api/stations/summary")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["data"]["multi_unit_node_count"] == 1
    assert payload["data"]["connector_unit_counts"]["GB/T"] == 17


def test_dataset_summary_cli(app):
    result = app.test_cli_runner().invoke(args=["dataset-summary"])
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["source_rows"] == 150
    assert payload["logical_nodes"] == 149
