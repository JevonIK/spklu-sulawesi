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


def _resolve_project_path(raw_path):
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


class Config:
    """Konfigurasi default untuk pengembangan lokal."""

    APP_NAME = "Sistem Rekomendasi SPKLU Sulawesi"
    APP_VERSION = "0.1.0"
    APP_ENV = os.getenv("APP_ENV", "development")

    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    DEBUG = _env_bool("FLASK_DEBUG", default=False)
    TESTING = False
    JSON_SORT_KEYS = False

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
    DEFAULT_SOC_STEP = _env_int("DEFAULT_SOC_STEP", 5)

    GOOGLE_MAPS_BROWSER_API_KEY = os.getenv(
        "GOOGLE_MAPS_BROWSER_API_KEY", ""
    )
    GOOGLE_MAPS_SERVER_API_KEY = os.getenv("GOOGLE_MAPS_SERVER_API_KEY", "")

