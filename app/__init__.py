"""Application factory untuk sistem rekomendasi SPKLU Sulawesi."""

from flask import Flask

from .commands import register_commands
from .config import Config
from .routes.api import api_bp
from .routes.web import web_bp
from .services.dataset import load_station_catalog
from .services.google_routes import GoogleRoutesClient
from .services.recommendation import RecommendationService
from .services.spatial import StationSpatialIndex


def create_app(config_object=None, config_overrides=None):
    """Membuat dan mengonfigurasi instance Flask.

    Pola application factory menjaga konfigurasi pengembangan, pengujian, dan
    deployment tetap terpisah serta memudahkan pengujian tanpa menjalankan server.
    """

    app = Flask(__name__)
    app.config.from_object(config_object or Config)

    if config_overrides:
        app.config.update(config_overrides)

    station_catalog = load_station_catalog(
        app.config["DATASET_PATH"]
    )
    app.extensions["station_catalog"] = station_catalog
    spatial_index = StationSpatialIndex(
        station_catalog.nodes
    )
    app.extensions["station_spatial_index"] = spatial_index

    server_api_key = app.config["GOOGLE_MAPS_SERVER_API_KEY"]
    if server_api_key:
        routes_client = GoogleRoutesClient(
            server_api_key,
            timeout_seconds=app.config["GOOGLE_ROUTES_TIMEOUT_SECONDS"],
        )
        app.extensions["google_routes_client"] = routes_client
        app.extensions["recommendation_service"] = RecommendationService(
            spatial_index=spatial_index,
            routes_client=routes_client,
            defaults={
                "minimum_soc_percent": app.config["DEFAULT_SOC_MIN"],
                "target_soc_percent": app.config["DEFAULT_SOC_TARGET"],
                "safety_factor": app.config["DEFAULT_SAFETY_FACTOR"],
                "soc_step_percent": app.config["DEFAULT_SOC_STEP"],
                "corridor_radius_km": app.config[
                    "DEFAULT_CORRIDOR_RADIUS_KM"
                ],
                "route_sample_step_km": app.config[
                    "DEFAULT_ROUTE_SAMPLE_STEP_KM"
                ],
            },
        )

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    register_commands(app)

    return app
