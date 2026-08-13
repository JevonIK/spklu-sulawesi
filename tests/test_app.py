import json


def test_index_is_available(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"SPKLU Sulawesi" in response.data
    assert b"State of Charge" in response.data
    assert b'id="routeForm"' in response.data
    assert b'id="map"' in response.data
    assert b"CCS2" in response.data


def test_index_exposes_only_browser_configuration():
    from app import create_app

    application = create_app(
        config_overrides={
            "TESTING": True,
            "GOOGLE_MAPS_BROWSER_API_KEY": "public-browser-key",
            "GOOGLE_MAPS_SERVER_API_KEY": "private-server-key",
            "GOOGLE_MAPS_MAP_ID": "test-map-id",
        }
    )

    response = application.test_client().get("/")

    assert response.status_code == 200
    assert b"public-browser-key" in response.data
    assert b"test-map-id" in response.data
    assert b"private-server-key" not in response.data


def test_health_endpoint_reports_dataset(client):
    response = client.get("/api/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "spklu-sulawesi"
    assert payload["version"] == "0.11.0"
    assert payload["data"]["dataset"]["exists"] is True
    assert payload["data"]["dataset"]["filename"] == "dataset_spklu_sulawesi.csv"
    assert payload["data"]["dataset"]["sha256"] == (
        "24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85"
    )
    assert payload["data"]["dataset"]["source_rows"] == 150
    assert payload["data"]["dataset"]["logical_nodes"] == 149
    assert payload["data"]["spatial_index"]["index_type"] == "BallTree"
    assert payload["data"]["spatial_index"]["metric"] == "haversine"
    assert payload["data"]["spatial_index"]["indexed_nodes"] == 149
    assert payload["data"]["graph_builder"]["status"] == "ready"
    assert (
        payload["data"]["graph_builder"]["road_metric_provider"]
        == "google_routes_api"
    )
    assert payload["data"]["optimizer"]["status"] == "ready"
    assert (
        payload["data"]["optimizer"]["algorithm"]
        == "dynamic_programming_soc"
    )
    assert payload["data"]["optimizer"]["charging_time_included"] is False
    assert payload["data"]["google_maps"]["browser_key_configured"] is True
    assert payload["data"]["google_maps"]["server_key_configured"] is True
    assert (
        payload["data"]["google_maps"]["recommendation_endpoint_ready"]
        is True
    )


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
