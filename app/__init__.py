"""Application factory untuk sistem rekomendasi SPKLU Sulawesi."""

from flask import Flask

from .commands import register_commands
from .config import Config
from .routes.api import api_bp
from .routes.web import web_bp
from .services.dataset import load_station_catalog


def create_app(config_object=None, config_overrides=None):
    """Membuat dan mengonfigurasi instance Flask.

    Pola application factory menjaga konfigurasi pengembangan, pengujian, dan
    deployment tetap terpisah serta memudahkan pengujian tanpa menjalankan server.
    """

    app = Flask(__name__)
    app.config.from_object(config_object or Config)

    if config_overrides:
        app.config.update(config_overrides)

    app.extensions["station_catalog"] = load_station_catalog(
        app.config["DATASET_PATH"]
    )

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    register_commands(app)

    return app
