import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        config_overrides={
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "GOOGLE_MAPS_BROWSER_API_KEY": "test-browser-key",
            "GOOGLE_MAPS_SERVER_API_KEY": "test-server-key",
            "GOOGLE_MAPS_MAP_ID": "test-map-id",
            "GOOGLE_QUOTA_LEDGER_PATH": tmp_path / "quota-ledger.json",
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()
