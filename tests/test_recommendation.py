import json
from contextlib import contextmanager

import pytest

from app.services.dataset import StationNode, StationUnit
from app.services.google_routes import ApiQuotaBudget, ApiQuotaBudgetExceeded
from app.services.google_routes import ComputedRoute
from app.services.quota_ledger import GoogleRoutesQuotaLedger
from app.services.recommendation import (
    QuotaProtectedRecommendationService,
    RecommendationInput,
    RecommendationQuotaError,
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


def station_node(connector="CCS2", charging_network="PUBLIC"):
    unit = StationUnit(
        source_row=2,
        province="Sulawesi Selatan",
        city="Kota Uji",
        name="SPKLU Tengah",
        address="Jalan Uji",
        latitude=0,
        longitude=0.5,
        maps_url="https://maps.app.goo.gl/uji",
        connectors=(connector,),
        charging_network=charging_network,
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


class BudgetTestRoutesClient:
    def __init__(self):
        self.active_budget = None

    @contextmanager
    def request_budget(self, **options):
        self.active_budget = ApiQuotaBudget(**options)
        try:
            yield self.active_budget
        finally:
            self.active_budget = None

    @contextmanager
    def quota_scenario(self, scenario_id):
        with self.active_budget.scenario(scenario_id):
            yield


class BudgetTestRecommendationService:
    def __init__(
        self,
        *,
        compute_routes=1,
        matrix_elements=3,
        error=None,
    ):
        self.routes_client = BudgetTestRoutesClient()
        self.compute_routes = compute_routes
        self.matrix_elements = matrix_elements
        self.error = error

    def parse_input(self, payload):
        return payload

    def recommend(self, recommendation_input):
        for _ in range(self.compute_routes):
            self.routes_client.active_budget.consume_compute_routes()
        if self.matrix_elements:
            self.routes_client.active_budget.consume_matrix_elements(
                self.matrix_elements
            )
        if self.error:
            raise self.error
        return {"api_usage": {"simulated": True}}


def protected_service(tmp_path, service, **overrides):
    ledger = GoogleRoutesQuotaLedger(tmp_path / "web-quota.json")
    options = {
        "maximum_compute_routes": 2,
        "maximum_compute_routes_per_minute": 100,
        "maximum_matrix_elements": 625,
        "maximum_matrix_elements_per_minute": 2000,
    }
    options.update(overrides)
    return (
        QuotaProtectedRecommendationService(
            service,
            quota_ledger=ledger,
            **options,
        ),
        ledger,
    )

@pytest.mark.parametrize(
    "connector",
    ("AC TYPE 2", "CCS2", "CHADEMO", "GB/T"),
)
def test_recommendation_input_supports_all_dataset_connectors(connector):
    parsed = RecommendationInput.from_payload(
        valid_payload(connector=connector), defaults=DEFAULTS
    )

    assert parsed.connector == connector
    assert parsed.parameters.minimum_soc_percent == 20
    assert parsed.parameters.target_soc_percent == 80
    assert parsed.parameters.safety_factor == 1
    assert parsed.parameters.soc_step_percent == 5
    assert parsed.corridor_radius_km == 10
    assert parsed.route_sample_step_km == 5


def test_recommendation_input_defaults_to_ccs2_when_connector_is_omitted():
    body = valid_payload()
    body["vehicle"].pop("connector")

    parsed = RecommendationInput.from_payload(body, defaults=DEFAULTS)

    assert parsed.connector == "CCS2"
    assert parsed.connectors == ("CCS2",)


def test_recommendation_input_accepts_multiple_connectors_from_checkbox_list():
    parsed = RecommendationInput.from_payload(
        valid_payload(connectors=["GB/T", "CCS2"]),
        defaults=DEFAULTS,
    )

    assert parsed.connectors == ("CCS2", "GB/T")
    assert parsed.connector == "CCS2"
    assert parsed.to_dict()["connectors"] == ["CCS2", "GB/T"]


def test_recommendation_input_accepts_multiple_additional_networks():
    body = valid_payload()
    body["options"] = {
        "additional_charging_networks": ["TOYOTA", "WULING"]
    }

    parsed = RecommendationInput.from_payload(body, defaults=DEFAULTS)

    assert parsed.additional_charging_networks == ("WULING", "TOYOTA")
    assert parsed.to_dict()["additional_charging_networks"] == [
        "WULING",
        "TOYOTA",
    ]


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
        (
            lambda body: body["vehicle"].update({"connectors": []}),
            "vehicle.connectors",
        ),
        (
            lambda body: body.update(
                {"options": {"additional_charging_networks": ["UNKNOWN"]}}
            ),
            "options.additional_charging_networks",
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
    assert result["candidate_summary"]["connector_candidate_count"] == 1
    assert result["graph"]["node_count"] == 3
    assert result["api_usage"] == {
        "compute_routes_requests": 2,
        "compute_route_matrix_requests": 1,
        "compute_route_matrix_elements": 2,
        "total_external_requests": 3,
    }
    assert len(routes_client.compute_route_calls) == 2
    assert routes_client.compute_route_calls[1][2] == ((0, 0.5),)
    assert result["route_access"]["status"] == "public"
    assert result["route_access"]["conditional"] is False


def test_dealer_station_requires_network_selection_and_marks_conditional_route():
    routes_client = PipelineRoutesClient()
    service = RecommendationService(
        spatial_index=StationSpatialIndex(
            (station_node("GB/T", "WULING"),)
        ),
        routes_client=routes_client,
        defaults=DEFAULTS,
    )
    without_network = valid_payload(connector="GB/T")

    public_only_result = service.recommend(service.parse_input(without_network))

    assert public_only_result["candidate_summary"]["connector_candidate_count"] == 1
    assert public_only_result["candidate_summary"]["corridor_candidate_count"] == 0
    assert public_only_result["optimization"]["feasible"] is False
    assert public_only_result["route_access"]["status"] == "not_applicable"

    with_network = valid_payload(connector="GB/T")
    with_network["options"] = {
        "additional_charging_networks": ["WULING"]
    }
    conditional_result = service.recommend(service.parse_input(with_network))

    assert conditional_result["optimization"]["feasible"] is True
    assert conditional_result["route_access"]["conditional"] is True
    assert conditional_result["route_access"]["conditional_stop_count"] == 1
    stop = conditional_result["optimization"]["itinerary"]["charging_stops"][0]
    assert stop["station"]["route_charging_network"] == "WULING"
    assert stop["station"]["route_access_type"] == "dealer_conditional"
    assert stop["station"]["route_compatible_connectors"] == ["GB/T"]


def test_ccs2_with_wuling_reports_zero_compatible_wuling_locations():
    routes_client = PipelineRoutesClient()
    service = RecommendationService(
        spatial_index=StationSpatialIndex(
            (
                station_node("CCS2", "PUBLIC"),
                StationNode(
                    node_id="spklu-wuling",
                    name="Wuling Uji",
                    province="Sulawesi Selatan",
                    city="Kota Uji",
                    address="Jalan Dealer",
                    latitude=0,
                    longitude=0.6,
                    maps_url="https://maps.app.goo.gl/wuling-uji",
                    connectors=("GB/T",),
                    units=(
                        StationUnit(
                            source_row=3,
                            province="Sulawesi Selatan",
                            city="Kota Uji",
                            name="Wuling Uji",
                            address="Jalan Dealer",
                            latitude=0,
                            longitude=0.6,
                            maps_url="https://maps.app.goo.gl/wuling-uji",
                            connectors=("GB/T",),
                            charging_network="WULING",
                        ),
                    ),
                ),
            )
        ),
        routes_client=routes_client,
        defaults=DEFAULTS,
    )
    body = valid_payload(connector="CCS2")
    body["options"] = {"additional_charging_networks": ["WULING"]}

    result = service.recommend(service.parse_input(body))

    compatibility = result["candidate_summary"]["network_compatibility"][0]
    assert compatibility["network"] == "WULING"
    assert compatibility["compatible_location_count"] == 0
    assert compatibility["available_connectors"] == ["GB/T"]
    assert result["candidate_summary"]["corridor_candidate_count"] == 1
    assert result["route_access"]["status"] == "public"


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


def test_web_quota_guard_records_actual_usage_and_returns_status(tmp_path):
    protected, ledger = protected_service(
        tmp_path,
        BudgetTestRecommendationService(
            compute_routes=2,
            matrix_elements=105,
        ),
    )

    result = protected.recommend({"valid": True})

    guard = result["quota_guard"]
    assert guard["compute_routes_attempt_count"] == 2
    assert guard["matrix_request_attempt_count"] == 1
    assert guard["matrix_element_attempt_count"] == 105
    assert guard["daily_compute_routes_used"] == 2
    assert guard["daily_compute_routes_remaining"] == 98
    assert guard["daily_matrix_elements_used"] == 105
    assert guard["daily_matrix_elements_remaining"] == 1895
    assert guard["compute_routes_remaining_this_minute"] == 98
    assert guard["matrix_elements_remaining_this_minute"] == 1895
    raw = json.loads(ledger.path.read_text())
    run = next(iter(raw["days"].values()))["runs"][0]
    assert run["outcome"] == "completed"


def test_web_service_keeps_public_soc_options_and_uses_backend_research_defaults(
    tmp_path,
):
    service = BudgetTestRecommendationService()
    protected, _ = protected_service(tmp_path, service)
    payload = {
        "options": {
            "minimum_soc_percent": 15,
            "target_soc_percent": 85,
            "safety_factor": 0.5,
            "soc_step_percent": 25,
            "corridor_radius_km": 99,
            "additional_charging_networks": ["WULING"],
        }
    }

    parsed = protected.parse_input(payload)

    assert parsed == {
        "options": {
            "minimum_soc_percent": 15,
            "target_soc_percent": 85,
            "additional_charging_networks": ["WULING"],
        }
    }


def test_web_quota_guard_records_failed_attempts(tmp_path):
    protected, ledger = protected_service(
        tmp_path,
        BudgetTestRecommendationService(
            compute_routes=1,
            matrix_elements=4,
            error=RuntimeError("pipeline gagal"),
        ),
    )

    with pytest.raises(RuntimeError, match="pipeline gagal"):
        protected.recommend({"valid": True})

    raw = json.loads(ledger.path.read_text())
    run = next(iter(raw["days"].values()))["runs"][0]
    assert run["outcome"] == "failed"
    assert run["compute_routes_attempt_count"] == 1
    assert run["matrix_element_attempt_count"] == 4
    assert ledger.status()["active_reservation_count"] == 0


def test_web_quota_guard_stops_before_per_request_limit(tmp_path):
    protected, ledger = protected_service(
        tmp_path,
        BudgetTestRecommendationService(
            compute_routes=3,
            matrix_elements=0,
        ),
    )

    with pytest.raises(ApiQuotaBudgetExceeded):
        protected.recommend({"valid": True})

    status = ledger.status()
    assert status["actual_compute_routes"] == 2
    assert status["actual_matrix_elements"] == 0


def test_web_quota_guard_rejects_parallel_reservation(tmp_path):
    protected, ledger = protected_service(
        tmp_path,
        BudgetTestRecommendationService(),
    )
    reservation = ledger.reserve(
        label="request-lain",
        maximum_compute_routes=2,
        maximum_matrix_elements=625,
    )

    with pytest.raises(RecommendationQuotaError, match="tidak tersedia"):
        protected.recommend({"valid": True})

    ledger.recover(
        reservation["reservation_id"],
        compute_routes_attempt_count=0,
        matrix_element_attempt_count=0,
        reason="reservasi test dibersihkan",
    )


def test_web_quota_guard_allows_sequential_request_inside_daily_capacity(
    tmp_path,
):
    protected, ledger = protected_service(
        tmp_path,
        BudgetTestRecommendationService(
            compute_routes=2,
            matrix_elements=105,
        ),
    )
    protected.recommend({"request": 1})
    protected.recommend({"request": 2})

    status = ledger.status()
    assert status["completed_or_failed_run_count"] == 2
    assert status["actual_compute_routes"] == 4
    assert status["actual_matrix_elements"] == 210
