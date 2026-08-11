"""Endpoint API dasar aplikasi."""

from pathlib import Path

from flask import Blueprint, current_app, jsonify


api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    """Mengembalikan status aplikasi dan ketersediaan berkas dataset."""

    dataset_path = Path(current_app.config["DATASET_PATH"])
    dataset_exists = dataset_path.is_file()
    status = "ok" if dataset_exists else "degraded"

    response = {
        "status": status,
        "service": "spklu-sulawesi",
        "version": current_app.config["APP_VERSION"],
        "data": {
            "dataset": {
                "filename": dataset_path.name,
                "exists": dataset_exists,
            }
        },
    }

    return jsonify(response), 200 if dataset_exists else 503

