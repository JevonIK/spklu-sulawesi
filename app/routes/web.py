"""Route untuk halaman antarmuka aplikasi."""

from flask import Blueprint, current_app, g, render_template


web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    return render_template(
        "index.html",
        app_name=current_app.config["APP_NAME"],
        app_version=current_app.config["APP_VERSION"],
        csp_nonce=g.csp_nonce,
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


@web_bp.get("/privacy")
def privacy():
    """Menampilkan pemberitahuan privasi prototipe penelitian."""

    return render_template(
        "privacy.html",
        app_name=current_app.config["APP_NAME"],
        contact_email=current_app.config["PUBLIC_CONTACT_EMAIL"],
        csp_nonce=g.csp_nonce,
    )


@web_bp.get("/terms")
def terms():
    """Menampilkan ketentuan penggunaan dan batasan rekomendasi."""

    return render_template(
        "terms.html",
        app_name=current_app.config["APP_NAME"],
        contact_email=current_app.config["PUBLIC_CONTACT_EMAIL"],
        csp_nonce=g.csp_nonce,
    )
