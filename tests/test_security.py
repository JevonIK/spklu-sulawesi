import re

import pytest

from app import create_app
from app.security import ProductionConfigurationError


class ExplodingRecommendationService:
    def parse_input(self, payload):
        return payload

    def recommend(self, recommendation_input):
        raise RuntimeError("rahasia internal tidak boleh bocor")


def production_config(**overrides):
    config = {
        "APP_ENV": "production",
        "DEBUG": False,
        "SECRET_KEY": "s" * 48,
        "GOOGLE_MAPS_BROWSER_API_KEY": "browser-key",
        "GOOGLE_MAPS_SERVER_API_KEY": "server-key",
        "GOOGLE_MAPS_MAP_ID": "production-map-id",
        "TRUSTED_HOSTS": ["localhost", "127.0.0.1"],
        "PUBLIC_CONTACT_EMAIL": "pengelola@example.com",
    }
    config.update(overrides)
    return config


def test_security_headers_use_nonce_and_disable_api_cache(client):
    page_response = client.get("/")
    api_response = client.get("/api/health")
    html = page_response.get_data(as_text=True)
    nonce_match = re.search(r'<script[^>]+nonce="([^"]+)"', html)

    assert nonce_match is not None
    assert (
        f"'nonce-{nonce_match.group(1)}'"
        in page_response.headers["Content-Security-Policy"]
    )
    assert page_response.headers["X-Content-Type-Options"] == "nosniff"
    assert page_response.headers["X-Frame-Options"] == "DENY"
    assert (
        page_response.headers["Referrer-Policy"]
        == "strict-origin-when-cross-origin"
    )
    assert "geolocation=()" in page_response.headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in page_response.headers
    assert api_response.headers["Cache-Control"] == "no-store"


def test_legal_pages_are_public_and_linked_from_home(client):
    home = client.get("/")
    privacy = client.get("/privacy")
    terms = client.get("/terms")

    assert b'href="/privacy"' in home.data
    assert b'href="/terms"' in home.data
    assert privacy.status_code == 200
    assert b"Pemberitahuan privasi" in privacy.data
    assert terms.status_code == 200
    assert b"Ketentuan penggunaan" in terms.data
    assert b"Estimasi waktu pengisian tidak termasuk" in terms.data


def test_api_returns_json_for_payload_404_and_method_errors(app, client):
    app.extensions["recommendation_service"] = object()
    oversized = client.post(
        "/api/recommendations",
        json={"padding": "x" * app.config["MAX_CONTENT_LENGTH"]},
    )
    missing = client.get("/api/tidak-ada")
    wrong_method = client.get("/api/recommendations")

    assert oversized.status_code == 413
    assert oversized.get_json()["error"]["code"] == "payload_too_large"
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "not_found"
    assert wrong_method.status_code == 405
    assert wrong_method.get_json()["error"]["code"] == "method_not_allowed"


def test_unexpected_api_error_is_sanitized():
    application = create_app(
        config_overrides={"TESTING": False, "PROPAGATE_EXCEPTIONS": False}
    )
    application.extensions[
        "recommendation_service"
    ] = ExplodingRecommendationService()

    response = application.test_client().post(
        "/api/recommendations",
        json={"payload": "validasi dilewati oleh fake service"},
    )

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "internal_error"
    assert b"rahasia internal" not in response.data


def test_production_fails_fast_when_security_configuration_is_missing():
    with pytest.raises(ProductionConfigurationError) as captured:
        create_app(
            config_overrides=production_config(
                SECRET_KEY="pendek",
                GOOGLE_MAPS_BROWSER_API_KEY="",
                GOOGLE_MAPS_SERVER_API_KEY="",
                GOOGLE_MAPS_MAP_ID="DEMO_MAP_ID",
                TRUSTED_HOSTS=None,
                PUBLIC_CONTACT_EMAIL="",
            )
        )

    message = str(captured.value)
    assert "SECRET_KEY" in message
    assert "GOOGLE_MAPS_BROWSER_API_KEY" in message
    assert "GOOGLE_MAPS_SERVER_API_KEY" in message
    assert "GOOGLE_MAPS_MAP_ID" in message
    assert "TRUSTED_HOSTS" in message
    assert "PUBLIC_CONTACT_EMAIL" in message


def test_production_enforces_host_cookie_and_hsts_configuration():
    application = create_app(config_overrides=production_config())
    client = application.test_client()

    accepted = client.get("/api/health", base_url="https://localhost")
    rejected = client.get("/api/health", base_url="https://evil.example")

    assert accepted.status_code == 200
    assert (
        accepted.headers["Strict-Transport-Security"]
        == "max-age=31536000; includeSubDomains"
    )
    assert application.config["SESSION_COOKIE_SECURE"] is True
    assert application.config["PREFERRED_URL_SCHEME"] == "https"
    assert rejected.status_code == 400


@pytest.mark.parametrize("invalid_limit", [None, 0, 1023, "65536"])
def test_invalid_request_limit_is_rejected(invalid_limit):
    with pytest.raises(ProductionConfigurationError, match="MAX_CONTENT_LENGTH"):
        create_app(config_overrides={"MAX_CONTENT_LENGTH": invalid_limit})


@pytest.mark.parametrize(
    "name, value",
    [
        ("GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT", 101),
        ("GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT", 2001),
        ("GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT", 101),
        ("GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT", 2001),
        ("GOOGLE_WEB_MAX_COMPUTE_ROUTES_PER_REQUEST", 3),
        ("GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST", 626),
    ],
)
def test_google_routes_hard_limits_cannot_be_raised(name, value):
    with pytest.raises(ProductionConfigurationError, match=name):
        create_app(config_overrides={name: value})


def test_web_reservation_cannot_exceed_lower_daily_limit():
    with pytest.raises(
        ProductionConfigurationError,
        match="per request tidak boleh melebihi batas harian",
    ):
        create_app(
            config_overrides={
                "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT": 100,
                "GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST": 101,
            }
        )
