"""Application factory untuk sistem rekomendasi SPKLU Sulawesi."""

from flask import Flask

from .commands import register_commands
from .config import Config
from .routes.api import api_bp
from .routes.web import web_bp
from .security import configure_application_security
from .services.dataset import load_station_catalog
from .services.google_routes import GoogleRoutesClient
from .services.quota_ledger import GoogleRoutesQuotaLedger
from .services.recommendation import (
    QuotaProtectedRecommendationService,
    RecommendationService,
)
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

    configure_application_security(app)

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
        recommendation_service = RecommendationService(
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
                "max_total_detour_km": app.config[
                    "DEFAULT_MAX_TOTAL_DETOUR_KM"
                ],
                "route_sample_step_km": app.config[
                    "DEFAULT_ROUTE_SAMPLE_STEP_KM"
                ],
            },
        )
        quota_ledger = GoogleRoutesQuotaLedger(
            app.config["GOOGLE_QUOTA_LEDGER_PATH"],
            timezone_name=app.config["GOOGLE_QUOTA_TIMEZONE"],
            daily_compute_routes_limit=app.config[
                "GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT"
            ],
            daily_matrix_element_limit=app.config[
                "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT"
            ],
            compute_routes_per_minute_limit=app.config[
                "GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT"
            ],
            matrix_elements_per_minute_limit=app.config[
                "GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT"
            ],
        )
        app.extensions["google_routes_quota_ledger"] = quota_ledger
        app.extensions[
            "experiment_recommendation_service"
        ] = recommendation_service
        app.extensions["recommendation_service"] = (
            QuotaProtectedRecommendationService(
                recommendation_service,
                quota_ledger=quota_ledger,
                maximum_compute_routes=app.config[
                    "GOOGLE_WEB_MAX_COMPUTE_ROUTES_PER_REQUEST"
                ],
                maximum_compute_routes_per_minute=app.config[
                    "GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT"
                ],
                maximum_matrix_elements=app.config[
                    "GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST"
                ],
                maximum_matrix_elements_per_minute=app.config[
                    "GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT"
                ],
            )
        )

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    register_commands(app)

    return app
