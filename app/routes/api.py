"""Endpoint API dasar aplikasi."""

from flask import Blueprint, current_app, jsonify


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
                "source_rows": catalog.source_row_count,
                "logical_nodes": catalog.logical_node_count,
            },
            "spatial_index": spatial_index.summary(),
            "graph_builder": {
                "status": "ready",
                "road_metric_provider": "adapter_required",
            },
            "optimizer": {
                "status": "ready",
                "algorithm": "dynamic_programming_soc",
                "charging_time_included": False,
            },
        },
    }

    return jsonify(response), 200


@api_bp.get("/stations/summary")
def station_summary():
    """Mengembalikan statistik dataset yang telah dinormalisasi."""

    catalog = current_app.extensions["station_catalog"]
    return jsonify({"status": "ok", "data": catalog.summary()})
