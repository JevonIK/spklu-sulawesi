import json
from pathlib import Path

from app.services.recommendation import (
    QuotaProtectedRecommendationService,
    RecommendationService,
)


def test_index_is_available(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"SPKLU Sulawesi" in response.data
    assert b"State of Charge" in response.data
    assert b'id="routeForm"' in response.data
    assert b'id="map"' in response.data
    assert b'id="originSelectionStatus"' in response.data
    assert b'id="destinationSelectionStatus"' in response.data
    assert b'name="connectors"' in response.data
    assert response.data.count(b'type="checkbox"') == 8
    assert b'name="additional_charging_networks"' in response.data
    assert b'value="HYUNDAI"' in response.data
    assert b'value="WULING"' in response.data
    assert b'value="TOYOTA"' in response.data
    assert b"SPKLU publik" in response.data
    assert b'value="AC TYPE 2"' in response.data
    assert b'value="CCS2"' in response.data
    assert b'value="CHADEMO"' in response.data
    assert b'value="GB/T"' in response.data
    assert b'id="safetyFactor"' not in response.data
    assert b'id="corridorRadius"' not in response.data
    assert b'id="socStep"' not in response.data


def test_places_autocomplete_uses_sulawesi_bounds_not_invalid_large_radius():
    source = Path("app/static/js/app.js").read_text(encoding="utf-8")

    assert "autocomplete.locationRestriction = SULAWESI_BOUNDS" in source
    assert "INDONESIA_BIAS_RADIUS_METERS" not in source
    assert "1_000_000" not in source


def test_map_render_uses_global_bounds_and_hides_empty_overlay_first():
    source = Path("app/static/js/app.js").read_text(encoding="utf-8")

    hide_overlay = 'elements.mapEmpty.classList.add("is-hidden")'
    create_bounds = "new google.maps.LatLngBounds()"
    assert "state.mapsLibrary.LatLngBounds" not in source
    assert create_bounds in source
    assert source.index(hide_overlay) < source.index(create_bounds)


def test_autocomplete_forces_readable_light_color_scheme():
    source = Path("app/static/css/app.css").read_text(encoding="utf-8")

    autocomplete_rule = source.split(
        ".autocomplete-host gmp-place-autocomplete {",
        maxsplit=2,
    )[-1].split("}", maxsplit=1)[0]
    assert "color-scheme: light" in autocomplete_rule
    assert "--gmp-mat-color-on-surface: #102a3a" in autocomplete_rule


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
    assert payload["version"] == "0.15.0"
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
    assert payload["data"]["google_maps"]["quota_guard"] == {
        "enabled": True,
        "maximum_compute_routes_per_request": 2,
        "maximum_matrix_elements_per_request": 625,
    }


def test_station_summary_endpoint(client):
    response = client.get("/api/stations/summary")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["data"]["multi_unit_node_count"] == 1
    assert payload["data"]["connector_unit_counts"]["GB/T"] == 17
    assert payload["data"]["network_node_counts"] == {
        "PUBLIC": 117,
        "HYUNDAI": 8,
        "WULING": 17,
        "TOYOTA": 7,
    }
    assert payload["data"]["network_connector_node_counts"]["WULING"] == {
        "AC TYPE 2": 0,
        "CCS2": 0,
        "CHADEMO": 0,
        "GB/T": 17,
    }


def test_dataset_summary_cli(app):
    result = app.test_cli_runner().invoke(args=["dataset-summary"])
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["source_rows"] == 150
    assert payload["logical_nodes"] == 149


def test_app_separates_web_quota_guard_from_experiment_service(app):
    assert isinstance(
        app.extensions["recommendation_service"],
        QuotaProtectedRecommendationService,
    )
    assert isinstance(
        app.extensions["experiment_recommendation_service"],
        RecommendationService,
    )
