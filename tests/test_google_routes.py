import requests
import pytest

from app.services.google_routes import (
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


def route_payload(distance_meters=123_400, duration="7200s"):
    return {
        "routes": [
            {
                "distanceMeters": distance_meters,
                "duration": duration,
                "polyline": {"encodedPolyline": ENCODED_POLYLINE},
            }
        ]
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
    session = RecordingSession([FakeResponse(route_payload())])
    client = GoogleRoutesClient("server-secret", session=session)

    route = client.compute_route(
        (-5.1, 119.4),
        (-1.4, 120.7),
        intermediates=((-3.0, 120.0),),
    )

    assert route.distance_km == pytest.approx(123.4)
    assert route.duration_minutes == pytest.approx(120)
    assert len(route.coordinates) == 3
    url, request = session.calls[0]
    assert url == COMPUTE_ROUTES_URL
    assert "server-secret" not in url
    assert request["headers"]["X-Goog-Api-Key"] == "server-secret"
    assert request["headers"]["X-Goog-FieldMask"] == ROUTE_FIELD_MASK
    assert request["json"]["travelMode"] == "DRIVE"
    assert request["json"]["routingPreference"] == "TRAFFIC_UNAWARE"
    assert len(request["json"]["intermediates"]) == 1


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
