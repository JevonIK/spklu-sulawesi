import pytest

from app.services.dataset import StationNode, StationUnit
from app.services.google_routes import ComputedRoute
from app.services.recommendation import RecommendationService
from app.services.road_metrics import RoadMetricBatch, RoadMetricResult
from app.services.spatial import StationSpatialIndex


DEFAULTS = {
    "minimum_soc_percent": 20,
    "target_soc_percent": 80,
    "safety_factor": 1,
    "soc_step_percent": 5,
    "corridor_radius_km": 10,
    "route_sample_step_km": 5,
}


class DeterministicRoutesClient:
    """Pengganti Google yang menjalankan pipeline tanpa trafik eksternal."""

    def compute_route(self, origin, destination, *, intermediates=()):
        return ComputedRoute(
            distance_km=112,
            duration_minutes=120,
            encoded_polyline="black-box-polyline",
            coordinates=((0, 0), (0, 0.5), (0, 1)),
        )

    def fetch(self, requests):
        return RoadMetricBatch(
            results=tuple(
                RoadMetricResult(
                    request_id=request.request_id,
                    distance_km=request.geodesic_distance_km * 1.001,
                    duration_minutes=request.geodesic_distance_km,
                )
                for request in requests
            ),
            external_request_count=1 if requests else 0,
        )


def station_node(connector="CCS2"):
    unit = StationUnit(
        source_row=1,
        province="Sulawesi Selatan",
        city="Kota Uji",
        name="SPKLU Tengah",
        address="Jalan Uji",
        latitude=0,
        longitude=0.5,
        maps_url="https://maps.example/uji",
        connectors=(connector,),
    )
    return StationNode(
        node_id="spklu-tengah",
        name=unit.name,
        province=unit.province,
        city=unit.city,
        address=unit.address,
        latitude=unit.latitude,
        longitude=unit.longitude,
        maps_url=unit.maps_url,
        connectors=unit.connectors,
        units=(unit,),
    )


def payload(maximum_range_km, connector="CCS2"):
    return {
        "origin": {"latitude": 0, "longitude": 0},
        "destination": {"latitude": 0, "longitude": 1},
        "vehicle": {
            "maximum_range_km": maximum_range_km,
            "current_soc_percent": 80,
            "connector": connector,
        },
        "options": {
            "minimum_soc_percent": 20,
            "target_soc_percent": 80,
            "safety_factor": 1,
            "soc_step_percent": 5,
            "corridor_radius_km": 10,
        },
    }


def install_real_pipeline(app, connector="CCS2"):
    app.extensions["recommendation_service"] = RecommendationService(
        spatial_index=StationSpatialIndex((station_node(connector),)),
        routes_client=DeterministicRoutesClient(),
        defaults=DEFAULTS,
    )


def test_black_box_recommendation_returns_safe_multistop_itinerary(app, client):
    install_real_pipeline(app)

    response = client.post("/api/recommendations", json=payload(100))
    result = response.get_json()["data"]

    assert response.status_code == 200
    assert result["optimization"]["feasible"] is True
    itinerary = result["optimization"]["itinerary"]
    assert itinerary["charging_stop_count"] == 1
    assert itinerary["charging_stops"][0]["node_id"] == "spklu-tengah"
    assert itinerary["minimum_observed_soc_percent"] >= 20
    assert result["recommended_route"]["encoded_polyline"] == (
        "black-box-polyline"
    )


def test_black_box_recommendation_reports_infeasible_route_without_500(
    app, client
):
    install_real_pipeline(app)

    response = client.post("/api/recommendations", json=payload(70))
    result = response.get_json()["data"]

    assert response.status_code == 200
    assert result["optimization"]["feasible"] is False
    assert result["optimization"]["reason"] == "graph_disconnected"
    assert result["optimization"]["itinerary"] is None
    assert result["recommended_route"] is None


@pytest.mark.parametrize(
    "connector",
    ("AC TYPE 2", "CCS2", "CHADEMO", "GB/T"),
)
def test_black_box_recommendation_supports_dataset_connectors(
    app, client, connector
):
    install_real_pipeline(app, connector)

    response = client.post(
        "/api/recommendations",
        json=payload(100, connector),
    )
    result = response.get_json()["data"]

    assert response.status_code == 200
    assert result["request"]["connector"] == connector
    assert result["request"]["connectors"] == [connector]
    assert result["optimization"]["feasible"] is True


def test_black_box_recommendation_matches_any_vehicle_connector(app, client):
    install_real_pipeline(app, "CHADEMO")
    request_payload = payload(100)
    request_payload["vehicle"]["connectors"] = ["CCS2", "CHADEMO"]

    response = client.post("/api/recommendations", json=request_payload)
    result = response.get_json()["data"]

    assert response.status_code == 200
    assert result["request"]["connectors"] == ["CCS2", "CHADEMO"]
    assert result["candidate_summary"]["compatible_connectors"] == [
        "CCS2",
        "CHADEMO",
    ]
    assert result["optimization"]["feasible"] is True
