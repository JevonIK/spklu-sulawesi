import requests
import pytest

from app.services.google_routes import (
    ApiQuotaBudgetExceeded,
    COMPUTE_ROUTE_MATRIX_URL,
    COMPUTE_ROUTES_URL,
    MATRIX_FIELD_MASK,
    ROUTE_FIELD_MASK,
    GoogleRoutesClient,
    GoogleRoutesError,
    decode_google_polyline,
)
from app.services.road_metrics import RoadMetricRequest


ENCODED_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class RecordingSession:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or ())
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def quota_options(**overrides):
    options = {
        "maximum_compute_routes": 60,
        "maximum_compute_routes_per_minute": 30,
        "maximum_compute_routes_per_scenario": 10,
        "maximum_matrix_elements": 2000,
        "maximum_matrix_elements_per_minute": 625,
    }
    options.update(overrides)
    return options


def route_payload(
    distance_meters=123_400,
    duration="7200s",
    legs=None,
):
    if legs is None:
        legs = [
            {"distanceMeters": distance_meters, "duration": duration},
        ]
    return {
        "routes": [
            {
                "distanceMeters": distance_meters,
                "duration": duration,
                "polyline": {"encodedPolyline": ENCODED_POLYLINE},
                "legs": legs,
            }
        ]
    }


def route_step(
    distance_meters,
    duration,
    start,
    end,
    *,
    maneuver="STRAIGHT",
):
    return {
        "distanceMeters": distance_meters,
        "staticDuration": duration,
        "startLocation": {
            "latLng": {"latitude": start[0], "longitude": start[1]}
        },
        "endLocation": {
            "latLng": {"latitude": end[0], "longitude": end[1]}
        },
        "navigationInstruction": {"maneuver": maneuver},
        "travelMode": "DRIVE",
    }


def road_request(request_id, origin, destination):
    return RoadMetricRequest(
        request_id=request_id,
        origin=origin,
        destination=destination,
        geodesic_distance_km=1,
    )


def test_decode_google_polyline_matches_reference_coordinates():
    coordinates = decode_google_polyline(ENCODED_POLYLINE)

    assert coordinates == (
        (38.5, -120.2),
        (40.7, -120.95),
        (43.252, -126.453),
    )


@pytest.mark.parametrize("encoded", ["", "_p~iF", "?"])
def test_invalid_polyline_is_rejected(encoded):
    with pytest.raises(ValueError, match="polyline"):
        decode_google_polyline(encoded)


def test_compute_route_uses_safe_headers_and_expected_options():
    session = RecordingSession(
        [
            FakeResponse(
                route_payload(
                    legs=[
                        {"distanceMeters": 60_000, "duration": "3600s"},
                        {"distanceMeters": 63_400, "duration": "3600s"},
                    ]
                )
            )
        ]
    )
    client = GoogleRoutesClient("server-secret", session=session)

    route = client.compute_route(
        (-5.1, 119.4),
        (-1.4, 120.7),
        intermediates=((-3.0, 120.0),),
    )

    assert route.distance_km == pytest.approx(123.4)
    assert route.duration_minutes == pytest.approx(120)
    assert len(route.coordinates) == 3
    assert [leg.distance_km for leg in route.legs] == [60, 63.4]
    url, request = session.calls[0]
    assert url == COMPUTE_ROUTES_URL
    assert "server-secret" not in url
    assert request["headers"]["X-Goog-Api-Key"] == "server-secret"
    assert request["headers"]["X-Goog-FieldMask"] == ROUTE_FIELD_MASK
    assert request["json"]["travelMode"] == "DRIVE"
    assert request["json"]["routingPreference"] == "TRAFFIC_UNAWARE"
    assert len(request["json"]["intermediates"]) == 1


def test_compute_route_can_request_ferry_avoidance():
    session = RecordingSession([FakeResponse(route_payload())])
    client = GoogleRoutesClient("key", session=session)

    client.compute_route((0, 0), (0, 1), avoid_ferries=True)

    assert session.calls[0][1]["json"]["routeModifiers"] == {
        "avoidFerries": True
    }


def test_compute_route_separates_ferry_from_energy_distance():
    session = RecordingSession(
        [
            FakeResponse(
                route_payload(
                    distance_meters=100_000,
                    duration="5400s",
                    legs=[
                        {
                            "distanceMeters": 100_000,
                            "duration": "5400s",
                            "steps": [
                                route_step(
                                    30_000,
                                    "1800s",
                                    (0, 0),
                                    (0, 0.3),
                                ),
                                route_step(
                                    60_000,
                                    "3000s",
                                    (0, 0.3),
                                    (0, 0.7),
                                    maneuver="FERRY",
                                ),
                                route_step(
                                    10_000,
                                    "600s",
                                    (0, 0.7),
                                    (0, 1),
                                ),
                            ],
                        }
                    ],
                )
            )
        ]
    )
    route = GoogleRoutesClient("key", session=session).compute_route(
        (0, 0),
        (0, 1),
    )

    leg = route.legs[0]
    assert leg.ferry_distance_km == pytest.approx(60)
    assert leg.energy_distance_km == pytest.approx(40)
    assert leg.ferry_duration_minutes == pytest.approx(50)
    assert leg.driving_duration_minutes == pytest.approx(40)
    assert len(leg.ferry_steps) == 1
    assert route.to_dict()["ferry_summary"] == {
        "contains_ferry": True,
        "segment_count": 1,
        "distance_km": 60,
        "duration_minutes": 50,
        "vehicle_access_status": "requires_operator_confirmation",
    }


def test_compute_route_rejects_incomplete_ferry_step():
    payload = route_payload(
        legs=[
            {
                "distanceMeters": 100_000,
                "duration": "5400s",
                "steps": [
                    {"navigationInstruction": {"maneuver": "FERRY"}}
                ],
            }
        ]
    )
    client = GoogleRoutesClient(
        "key",
        session=RecordingSession([FakeResponse(payload)]),
    )

    with pytest.raises(GoogleRoutesError) as captured:
        client.compute_route((0, 0), (0, 1))

    assert captured.value.code == "invalid_response"


def test_compute_route_reports_missing_route_and_invalid_payload():
    missing_session = RecordingSession([FakeResponse({"routes": []})])
    client = GoogleRoutesClient("key", session=missing_session)

    with pytest.raises(GoogleRoutesError) as missing_error:
        client.compute_route((0, 0), (0, 1))
    assert missing_error.value.code == "route_not_found"

    invalid_session = RecordingSession(
        [FakeResponse({"routes": [{"distanceMeters": 100}]})]
    )
    client = GoogleRoutesClient("key", session=invalid_session)
    with pytest.raises(GoogleRoutesError) as invalid_error:
        client.compute_route((0, 0), (0, 1))
    assert invalid_error.value.code == "invalid_response"


@pytest.mark.parametrize(
    "status_code, expected_code",
    [(400, "invalid_upstream_request"), (403, "authentication_failed"),
     (429, "quota_exceeded"), (500, "upstream_error")],
)
def test_http_errors_are_mapped_without_exposing_response(
    status_code, expected_code
):
    session = RecordingSession(
        [FakeResponse({"error": {"message": "sensitive"}}, status_code)]
    )
    client = GoogleRoutesClient("secret", session=session)

    with pytest.raises(GoogleRoutesError) as captured:
        client.compute_route((0, 0), (0, 1))

    assert captured.value.code == expected_code
    assert "sensitive" not in str(captured.value)
    assert "secret" not in str(captured.value)


def test_network_error_is_converted_to_safe_error():
    session = RecordingSession(error=requests.Timeout("secret detail"))
    client = GoogleRoutesClient("key", session=session)

    with pytest.raises(GoogleRoutesError) as captured:
        client.compute_route((0, 0), (0, 1))

    assert captured.value.code == "upstream_unavailable"
    assert "secret detail" not in str(captured.value)


def test_compute_routes_budget_stops_before_external_call_limit():
    session = RecordingSession(
        [FakeResponse(route_payload()), FakeResponse(route_payload())]
    )
    client = GoogleRoutesClient("key", session=session)

    with client.request_budget(
        **quota_options(maximum_compute_routes=1)
    ) as budget:
        with client.quota_scenario("skenario-a"):
            client.compute_route((0, 0), (0, 1))
            with pytest.raises(ApiQuotaBudgetExceeded) as captured:
                client.compute_route((0, 0), (0, 2))

    assert captured.value.code == "compute_routes_budget_exceeded"
    assert budget.compute_routes_attempt_count == 1
    assert budget.snapshot()["compute_routes_remaining"] == 0
    assert len(session.calls) == 1


def test_compute_routes_budget_counts_failed_attempt_and_resets_after_context():
    failing_session = RecordingSession(error=requests.Timeout("timeout"))
    client = GoogleRoutesClient("key", session=failing_session)

    with client.request_budget(**quota_options()) as first_budget:
        with client.quota_scenario("gagal"):
            with pytest.raises(GoogleRoutesError, match="tidak dapat dihubungi"):
                client.compute_route((0, 0), (0, 1))
    assert first_budget.compute_routes_attempt_count == 1

    client.session = RecordingSession([FakeResponse(route_payload())])
    with client.request_budget(**quota_options()) as second_budget:
        with client.quota_scenario("berhasil"):
            client.compute_route((0, 0), (0, 1))
    assert second_budget.compute_routes_attempt_count == 1


@pytest.mark.parametrize("invalid_budget", [True, 1.5, "10", 0, -1])
def test_invalid_or_nested_quota_budget_is_rejected(invalid_budget):
    client = GoogleRoutesClient("key", session=RecordingSession())

    with pytest.raises(ValueError, match="maximum_compute_routes"):
        with client.request_budget(
            **quota_options(maximum_compute_routes=invalid_budget)
        ):
            pass

    with client.request_budget(**quota_options()):
        with pytest.raises(RuntimeError, match="tidak dapat ditumpuk"):
            with client.request_budget(**quota_options()):
                pass


def test_compute_routes_per_scenario_limit_is_enforced():
    session = RecordingSession(
        [FakeResponse(route_payload()), FakeResponse(route_payload())]
    )
    client = GoogleRoutesClient("key", session=session)

    with client.request_budget(
        **quota_options(maximum_compute_routes_per_scenario=1)
    ) as budget:
        with client.quota_scenario("skenario-a"):
            client.compute_route((0, 0), (0, 1))
            with pytest.raises(ApiQuotaBudgetExceeded) as captured:
                client.compute_route((0, 0), (0, 2))

    assert captured.value.code == "compute_routes_scenario_budget_exceeded"
    assert budget.snapshot()["compute_routes_attempts_by_scenario"] == {
        "skenario-a": 1
    }
    assert len(session.calls) == 1


def test_compute_routes_rate_limit_waits_for_rolling_minute():
    clock = FakeClock()
    session = RecordingSession(
        [FakeResponse(route_payload()) for _ in range(3)]
    )
    client = GoogleRoutesClient("key", session=session)

    with client.request_budget(
        **quota_options(maximum_compute_routes_per_minute=2),
        clock=clock,
        sleeper=clock.sleep,
    ) as budget:
        with client.quota_scenario("skenario-a"):
            for longitude in (1, 2, 3):
                client.compute_route((0, 0), (0, longitude))

    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] >= 60
    assert budget.compute_routes_attempt_count == 3
    assert budget.rate_limit_wait_seconds >= 60


def test_matrix_budget_counts_elements_and_paces_rolling_minute():
    clock = FakeClock()
    session = RecordingSession([FakeResponse([]), FakeResponse([])])
    client = GoogleRoutesClient("key", session=session)

    with client.request_budget(
        **quota_options(),
        clock=clock,
        sleeper=clock.sleep,
    ) as budget:
        client._post(
            COMPUTE_ROUTE_MATRIX_URL,
            {"origins": [{}], "destinations": [{}] * 400},
            MATRIX_FIELD_MASK,
        )
        client._post(
            COMPUTE_ROUTE_MATRIX_URL,
            {"origins": [{}], "destinations": [{}] * 300},
            MATRIX_FIELD_MASK,
        )

    snapshot = budget.snapshot()
    assert snapshot["matrix_request_attempt_count"] == 2
    assert snapshot["matrix_element_attempt_count"] == 700
    assert clock.sleeps[0] >= 60


def test_matrix_total_budget_rejects_request_before_google_call():
    session = RecordingSession([FakeResponse([]), FakeResponse([])])
    client = GoogleRoutesClient("key", session=session)

    with client.request_budget(
        **quota_options(maximum_matrix_elements=500)
    ) as budget:
        client._post(
            COMPUTE_ROUTE_MATRIX_URL,
            {"origins": [{}], "destinations": [{}] * 400},
            MATRIX_FIELD_MASK,
        )
        with pytest.raises(ApiQuotaBudgetExceeded) as captured:
            client._post(
                COMPUTE_ROUTE_MATRIX_URL,
                {"origins": [{}], "destinations": [{}] * 200},
                MATRIX_FIELD_MASK,
            )

    assert captured.value.code == "matrix_elements_budget_exceeded"
    assert budget.matrix_element_attempt_count == 400
    assert len(session.calls) == 1


def test_matrix_groups_requests_by_origin_and_skips_unavailable_elements():
    first_matrix = [
        {
            "originIndex": 0,
            "destinationIndex": 1,
            "status": {},
            "condition": "ROUTE_EXISTS",
            "distanceMeters": 20_000,
            "duration": "1800s",
        },
        {
            "originIndex": 0,
            "destinationIndex": 0,
            "status": {},
            "condition": "ROUTE_EXISTS",
            "distanceMeters": 10_000,
            "duration": "900s",
        },
        {
            "originIndex": 0,
            "destinationIndex": 2,
            "status": {"code": 5},
            "condition": "ROUTE_NOT_FOUND",
        },
    ]
    second_matrix = [
        {
            "originIndex": 0,
            "destinationIndex": 0,
            "status": {},
            "condition": "ROUTE_EXISTS",
            "distanceMeters": 30_000,
            "duration": "2700s",
        }
    ]
    session = RecordingSession(
        [FakeResponse(first_matrix), FakeResponse(second_matrix)]
    )
    client = GoogleRoutesClient("key", session=session)
    requests_to_fetch = (
        road_request("a", (0, 0), (0, 0.1)),
        road_request("b", (0, 0), (0, 0.2)),
        road_request("unavailable", (0, 0), (0, 0.3)),
        road_request("c", (0, 0.1), (0, 0.4)),
    )

    batch = client.fetch(requests_to_fetch)

    assert batch.external_request_count == 2
    assert [(item.request_id, item.distance_km) for item in batch.results] == [
        ("b", 20),
        ("a", 10),
        ("c", 30),
    ]
    assert all(call[0] == COMPUTE_ROUTE_MATRIX_URL for call in session.calls)
    assert all(
        call[1]["headers"]["X-Goog-FieldMask"] == MATRIX_FIELD_MASK
        for call in session.calls
    )
    assert len(session.calls[0][1]["json"]["origins"]) == 1
    assert len(session.calls[0][1]["json"]["destinations"]) == 3


@pytest.mark.parametrize(
    "malformed_element",
    [
        {
            "originIndex": 0,
            "destinationIndex": 0,
            "status": {},
            "condition": "ROUTE_EXISTS",
            "duration": "120s",
        },
        {
            "originIndex": 0,
            "destinationIndex": 0,
            "status": {"code": 5},
            "condition": "ROUTE_EXISTS",
            "distanceMeters": 1000,
            "duration": "120s",
        },
        {
            "originIndex": 0,
            "status": {},
            "condition": "ROUTE_NOT_FOUND",
        },
        {
            "originIndex": 0,
            "destinationIndex": 0,
            "status": {},
            "condition": "CONDITION_UNSPECIFIED",
        },
    ],
)
def test_matrix_rejects_malformed_elements_instead_of_false_unavailable(
    malformed_element,
):
    client = GoogleRoutesClient(
        "key",
        session=RecordingSession([FakeResponse([malformed_element])]),
    )

    with pytest.raises(GoogleRoutesError) as captured:
        client.fetch((road_request("a", (0, 0), (0, 0.1)),))

    assert captured.value.code == "invalid_response"


def test_matrix_rejects_duplicate_destination_index():
    element = {
        "originIndex": 0,
        "destinationIndex": 0,
        "status": {},
        "condition": "ROUTE_NOT_FOUND",
    }
    client = GoogleRoutesClient(
        "key",
        session=RecordingSession([FakeResponse([element, element])]),
    )

    with pytest.raises(GoogleRoutesError, match="duplikat"):
        client.fetch((road_request("a", (0, 0), (0, 0.1)),))


def test_matrix_preflight_rejects_oversized_batch_before_any_http_call():
    requests_to_fetch = tuple(
        road_request(str(index), (0, 0), (0, 0.001 + index / 10_000))
        for index in range(626)
    )
    session = RecordingSession()
    client = GoogleRoutesClient("key", session=session)

    with client.request_budget(
        **quota_options(maximum_matrix_elements=625)
    ) as budget:
        with pytest.raises(ApiQuotaBudgetExceeded) as captured:
            client.fetch(requests_to_fetch)

    assert captured.value.code == "matrix_elements_budget_exceeded"
    assert budget.matrix_element_attempt_count == 0
    assert session.calls == []


def test_matrix_batch_size_respects_custom_per_minute_limit():
    clock = FakeClock()
    unavailable = lambda count: [
        {
            "originIndex": 0,
            "destinationIndex": index,
            "status": {"code": 5},
            "condition": "ROUTE_NOT_FOUND",
        }
        for index in range(count)
    ]
    session = RecordingSession(
        [FakeResponse(unavailable(100)), FakeResponse(unavailable(1))]
    )
    client = GoogleRoutesClient("key", session=session)
    requests_to_fetch = tuple(
        road_request(str(index), (0, 0), (0, 0.001 + index / 10_000))
        for index in range(101)
    )

    with client.request_budget(
        **quota_options(maximum_matrix_elements_per_minute=100),
        clock=clock,
        sleeper=clock.sleep,
    ):
        batch = client.fetch(requests_to_fetch)

    assert batch.external_request_count == 2
    assert [
        len(call[1]["json"]["destinations"]) for call in session.calls
    ] == [100, 1]
    assert clock.sleeps and clock.sleeps[0] >= 60


def test_empty_matrix_request_does_not_call_google():
    session = RecordingSession()
    client = GoogleRoutesClient("key", session=session)

    batch = client.fetch(())

    assert batch.results == ()
    assert batch.external_request_count == 0
    assert session.calls == []


def test_invalid_client_configuration_and_request_type_are_rejected():
    with pytest.raises(ValueError, match="API key"):
        GoogleRoutesClient("")
    with pytest.raises(ValueError, match="Timeout"):
        GoogleRoutesClient("key", timeout_seconds=0)

    client = GoogleRoutesClient("key", session=RecordingSession())
    with pytest.raises(TypeError, match="RoadMetricRequest"):
        client.fetch((object(),))
