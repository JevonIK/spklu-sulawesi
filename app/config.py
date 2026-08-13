"""Konfigurasi aplikasi yang bersumber dari environment variable."""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name, default):
    raw_value = os.getenv(name)
    return float(raw_value) if raw_value is not None else float(default)


def _env_int(name, default):
    raw_value = os.getenv(name)
    return int(raw_value) if raw_value is not None else int(default)


def _env_list(name):
    raw_value = os.getenv(name, "")
    values = [value.strip() for value in raw_value.split(",")]
    return [value for value in values if value] or None


def _resolve_project_path(raw_path):
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


class Config:
    """Konfigurasi default untuk pengembangan lokal."""

    APP_NAME = "Sistem Rekomendasi SPKLU Sulawesi"
    APP_VERSION = "0.10.1"
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    DEBUG = _env_bool("FLASK_DEBUG", default=False)
    TESTING = False
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = _env_int("MAX_CONTENT_LENGTH", 64 * 1024)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    PREFERRED_URL_SCHEME = "https" if APP_ENV == "production" else "http"
    ENABLE_HSTS = APP_ENV == "production"
    TRUSTED_HOSTS = _env_list("TRUSTED_HOSTS")
    USE_PROXY_FIX = _env_bool("USE_PROXY_FIX", default=False)

    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = _env_int("PORT", 5000)

    DATASET_PATH = _resolve_project_path(
        os.getenv("DATASET_PATH", "dataset_spklu_sulawesi.csv")
    )

    DEFAULT_SOC_MIN = _env_float("DEFAULT_SOC_MIN", 20)
    DEFAULT_SOC_TARGET = _env_float("DEFAULT_SOC_TARGET", 80)
    DEFAULT_SAFETY_FACTOR = _env_float("DEFAULT_SAFETY_FACTOR", 0.90)
    DEFAULT_CORRIDOR_RADIUS_KM = _env_float(
        "DEFAULT_CORRIDOR_RADIUS_KM", 10
    )
    DEFAULT_ROUTE_SAMPLE_STEP_KM = _env_float(
        "DEFAULT_ROUTE_SAMPLE_STEP_KM", 5
    )
    DEFAULT_SOC_STEP = _env_int("DEFAULT_SOC_STEP", 5)

    GOOGLE_MAPS_BROWSER_API_KEY = os.getenv(
        "GOOGLE_MAPS_BROWSER_API_KEY", ""
    )
    GOOGLE_MAPS_SERVER_API_KEY = os.getenv("GOOGLE_MAPS_SERVER_API_KEY", "")
    GOOGLE_MAPS_MAP_ID = os.getenv("GOOGLE_MAPS_MAP_ID", "DEMO_MAP_ID")
    GOOGLE_ROUTES_TIMEOUT_SECONDS = _env_float(
        "GOOGLE_ROUTES_TIMEOUT_SECONDS", 20
    )
    GOOGLE_QUOTA_LEDGER_PATH = _resolve_project_path(
        os.getenv(
            "GOOGLE_QUOTA_LEDGER_PATH",
            "reports/generated/google-routes-quota.json",
        )
    )
    GOOGLE_QUOTA_TIMEZONE = os.getenv(
        "GOOGLE_QUOTA_TIMEZONE",
        "America/Los_Angeles",
    )
    GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT = _env_int(
        "GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT",
        100,
    )
    GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT = _env_int(
        "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT",
        2000,
    )

    PUBLIC_CONTACT_EMAIL = os.getenv("PUBLIC_CONTACT_EMAIL", "").strip()
