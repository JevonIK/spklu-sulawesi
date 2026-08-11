"""Route untuk halaman antarmuka aplikasi."""

from flask import Blueprint, current_app, render_template


web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    return render_template(
        "index.html",
        app_name=current_app.config["APP_NAME"],
        app_version=current_app.config["APP_VERSION"],
        defaults={
            "soc_min": current_app.config["DEFAULT_SOC_MIN"],
            "soc_target": current_app.config["DEFAULT_SOC_TARGET"],
        },
    )

