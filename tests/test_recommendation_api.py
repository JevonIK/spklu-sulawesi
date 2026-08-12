from app import create_app
from app.services.google_routes import GoogleRoutesError
from app.services.recommendation import RecommendationValidationError


class FakeRecommendationService:
    def __init__(self, *, parse_error=None, recommend_error=None):
        self.parse_error = parse_error
        self.recommend_error = recommend_error
        self.received_payload = None

    def parse_input(self, payload):
        self.received_payload = payload
        if self.parse_error:
            raise self.parse_error
        return "parsed-input"

    def recommend(self, recommendation_input):
        assert recommendation_input == "parsed-input"
        if self.recommend_error:
            raise self.recommend_error
        return {"optimization": {"feasible": True}}


def test_recommendation_endpoint_returns_service_result(app, client):
    service = FakeRecommendationService()
    app.extensions["recommendation_service"] = service

    response = client.post(
        "/api/recommendations",
        json={"origin": {}, "destination": {}, "vehicle": {}},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["optimization"]["feasible"] is True
    assert service.received_payload["vehicle"] == {}


def test_recommendation_endpoint_rejects_non_json(app, client):
    app.extensions["recommendation_service"] = FakeRecommendationService()

    response = client.post(
        "/api/recommendations",
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_json"


def test_recommendation_endpoint_returns_validation_context(app, client):
    error = RecommendationValidationError(
        "vehicle.current_soc_percent", "SOC tidak valid"
    )
    app.extensions["recommendation_service"] = FakeRecommendationService(
        parse_error=error
    )

    response = client.post("/api/recommendations", json={})

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["field"] == "vehicle.current_soc_percent"


def test_recommendation_endpoint_converts_google_error(app, client):
    error = GoogleRoutesError(
        "quota_exceeded", "Google Routes API menolak permintaan."
    )
    app.extensions["recommendation_service"] = FakeRecommendationService(
        recommend_error=error
    )

    response = client.post("/api/recommendations", json={})

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "quota_exceeded"


def test_recommendation_endpoint_reports_missing_server_key():
    app = create_app(
        config_overrides={
            "TESTING": True,
            "GOOGLE_MAPS_SERVER_API_KEY": "",
        }
    )

    response = app.test_client().post("/api/recommendations", json={})

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "configuration_error"
