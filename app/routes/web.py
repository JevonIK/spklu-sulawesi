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
            "safety_factor": current_app.config["DEFAULT_SAFETY_FACTOR"],
            "corridor_radius_km": current_app.config[
                "DEFAULT_CORRIDOR_RADIUS_KM"
            ],
            "soc_step": current_app.config["DEFAULT_SOC_STEP"],
        },
        frontend_config={
            "googleMapsBrowserApiKey": current_app.config[
                "GOOGLE_MAPS_BROWSER_API_KEY"
            ],
            "googleMapsMapId": current_app.config["GOOGLE_MAPS_MAP_ID"],
            "mapsConfigured": bool(
                current_app.config["GOOGLE_MAPS_BROWSER_API_KEY"]
            ),
        },
    )
