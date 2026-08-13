"""Endpoint API dasar aplikasi."""

from flask import Blueprint, current_app, jsonify, request

from ..services.google_routes import GoogleRoutesError
from ..services.recommendation import RecommendationValidationError


api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    """Mengembalikan status aplikasi dan hasil pemuatan dataset."""

    catalog = current_app.extensions["station_catalog"]
    spatial_index = current_app.extensions["station_spatial_index"]

    response = {
        "status": "ok",
        "service": "spklu-sulawesi",
        "version": current_app.config["APP_VERSION"],
        "data": {
            "dataset": {
                "filename": catalog.source_path.name,
                "exists": True,
                "sha256": catalog.source_sha256,
                "source_rows": catalog.source_row_count,
                "logical_nodes": catalog.logical_node_count,
            },
            "spatial_index": spatial_index.summary(),
            "graph_builder": {
                "status": "ready",
                "road_metric_provider": "google_routes_api",
            },
            "optimizer": {
                "status": "ready",
                "algorithm": "dynamic_programming_soc",
                "charging_time_included": False,
            },
            "google_maps": {
                "browser_key_configured": bool(
                    current_app.config["GOOGLE_MAPS_BROWSER_API_KEY"]
                ),
                "server_key_configured": bool(
                    current_app.config["GOOGLE_MAPS_SERVER_API_KEY"]
                ),
                "recommendation_endpoint_ready": (
                    "recommendation_service" in current_app.extensions
                ),
            },
        },
    }

    return jsonify(response), 200


@api_bp.get("/stations/summary")
def station_summary():
    """Mengembalikan statistik dataset yang telah dinormalisasi."""

    catalog = current_app.extensions["station_catalog"]
    return jsonify({"status": "ok", "data": catalog.summary()})


@api_bp.post("/recommendations")
def create_recommendation():
    """Menyusun rekomendasi rute pengisian dari parameter perjalanan."""

    service = current_app.extensions.get("recommendation_service")
    if service is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": {
                        "code": "configuration_error",
                        "message": (
                            "Google Maps server API key belum dikonfigurasi."
                        ),
                    },
                }
            ),
            503,
        )

    payload = request.get_json(silent=True)
    if payload is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": {
                        "code": "invalid_json",
                        "message": "Body permintaan harus berupa JSON.",
                    },
                }
            ),
            400,
        )

    try:
        recommendation_input = service.parse_input(payload)
        result = service.recommend(recommendation_input)
    except RecommendationValidationError as error:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": {
                        "code": "validation_error",
                        "field": error.field,
                        "message": str(error),
                    },
                }
            ),
            400,
        )
    except GoogleRoutesError as error:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": {
                        "code": error.code,
                        "message": str(error),
                    },
                }
            ),
            502,
        )

    return jsonify({"status": "ok", "data": result}), 200
