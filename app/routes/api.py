"""Endpoint API dasar aplikasi."""

from flask import Blueprint, current_app, jsonify


api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    """Mengembalikan status aplikasi dan hasil pemuatan dataset."""

    catalog = current_app.extensions["station_catalog"]

    response = {
        "status": "ok",
        "service": "spklu-sulawesi",
        "version": current_app.config["APP_VERSION"],
        "data": {
            "dataset": {
                "filename": catalog.source_path.name,
                "exists": True,
                "source_rows": catalog.source_row_count,
                "logical_nodes": catalog.logical_node_count,
            }
        },
    }

    return jsonify(response), 200


@api_bp.get("/stations/summary")
def station_summary():
    """Mengembalikan statistik dataset yang telah dinormalisasi."""

    catalog = current_app.extensions["station_catalog"]
    return jsonify({"status": "ok", "data": catalog.summary()})
