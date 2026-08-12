import pytest

from app.services.dataset import StationNode, StationUnit
from app.services.google_routes import ComputedRoute
from app.services.recommendation import (
    RecommendationInput,
    RecommendationService,
    RecommendationValidationError,
)
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


def valid_payload(**vehicle_overrides):
    vehicle = {
        "maximum_range_km": 100,
        "current_soc_percent": 80,
        "connector": "CCS2",
    }
    vehicle.update(vehicle_overrides)
    return {
        "origin": {"latitude": 0, "longitude": 0},
        "destination": {"latitude": 0, "longitude": 1},
        "vehicle": vehicle,
    }


def station_node():
    unit = StationUnit(
        source_row=2,
        province="Sulawesi Selatan",
        city="Kota Uji",
        name="SPKLU Tengah",
        address="Jalan Uji",
        latitude=0,
        longitude=0.5,
        maps_url="https://maps.app.goo.gl/uji",
        connectors=("CCS2",),
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


class PipelineRoutesClient:
    def __init__(self):
        self.compute_route_calls = []
        self.matrix_requests = ()

    def compute_route(self, origin, destination, *, intermediates=()):
        self.compute_route_calls.append((origin, destination, intermediates))
        return ComputedRoute(
            distance_km=112,
            duration_minutes=120,
            encoded_polyline="encoded-for-test",
            coordinates=((0, 0), (0, 0.5), (0, 1)),
        )

    def fetch(self, requests):
        self.matrix_requests = requests
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


def test_recommendation_input_uses_defaults_and_requires_ccs2():
    parsed = RecommendationInput.from_payload(
        valid_payload(), defaults=DEFAULTS
    )

    assert parsed.connector == "CCS2"
    assert parsed.parameters.minimum_soc_percent == 20
    assert parsed.parameters.target_soc_percent == 80
    assert parsed.route_sample_step_km == 5

    with pytest.raises(RecommendationValidationError, match="hanya mendukung"):
        RecommendationInput.from_payload(
            valid_payload(connector="GB/T"), defaults=DEFAULTS
        )


@pytest.mark.parametrize(
    "mutator, expected_field",
    [
        (lambda body: body.update({"origin": None}), "origin"),
        (
            lambda body: body["destination"].update({"latitude": 91}),
            "destination",
        ),
        (
            lambda body: body.update({"destination": dict(body["origin"])}),
            "destination",
        ),
        (
            lambda body: body["vehicle"].update({"maximum_range_km": 2001}),
            "vehicle.maximum_range_km",
        ),
        (
            lambda body: body["vehicle"].update({"current_soc_percent": 20}),
            "vehicle.current_soc_percent",
        ),
        (
            lambda body: body["vehicle"].update({"connector": "unknown"}),
            "vehicle.connector",
        ),
    ],
)
def test_invalid_recommendation_input_has_field_context(
    mutator, expected_field
):
    body = valid_payload()
    mutator(body)

    with pytest.raises(RecommendationValidationError) as captured:
        RecommendationInput.from_payload(body, defaults=DEFAULTS)

    assert captured.value.field == expected_field


def test_full_recommendation_pipeline_selects_station_and_reports_api_usage():
    routes_client = PipelineRoutesClient()
    service = RecommendationService(
        spatial_index=StationSpatialIndex((station_node(),)),
        routes_client=routes_client,
        defaults=DEFAULTS,
    )
    recommendation_input = service.parse_input(valid_payload())

    result = service.recommend(recommendation_input)

    assert result["optimization"]["feasible"] is True
    stops = result["optimization"]["itinerary"]["charging_stops"]
    assert [stop["node_id"] for stop in stops] == ["spklu-tengah"]
    assert result["candidate_summary"]["corridor_candidate_count"] == 1
    assert result["graph"]["node_count"] == 3
    assert result["api_usage"] == {
        "compute_routes_requests": 2,
        "compute_route_matrix_requests": 1,
        "compute_route_matrix_elements": 2,
        "total_external_requests": 3,
    }
    assert len(routes_client.compute_route_calls) == 2
    assert routes_client.compute_route_calls[1][2] == ((0, 0.5),)


def test_direct_route_reuses_base_route_without_second_compute_call():
    routes_client = PipelineRoutesClient()
    service = RecommendationService(
        spatial_index=StationSpatialIndex((station_node(),)),
        routes_client=routes_client,
        defaults=DEFAULTS,
    )
    payload = valid_payload(maximum_range_km=300)

    result = service.recommend(service.parse_input(payload))

    assert result["optimization"]["feasible"] is True
    assert result["optimization"]["itinerary"]["charging_stop_count"] == 0
    assert result["api_usage"]["compute_routes_requests"] == 1
    assert len(routes_client.compute_route_calls) == 1
    assert result["recommended_route"] == result["base_route"]
