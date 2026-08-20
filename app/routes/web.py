"""Route untuk halaman antarmuka aplikasi."""

from itertools import combinations

from flask import Blueprint, current_app, g, render_template

from ..services.dataset import (
    CHARGING_NETWORK_LABELS,
    DEALER_CHARGING_NETWORK_ORDER,
    PUBLIC_CHARGING_NETWORK,
)


web_bp = Blueprint("web", __name__)


def _connector_availability(catalog):
    """Jumlah node unik per konektor untuk setiap pilihan jaringan dealer."""

    availability = {}
    dealer_networks = tuple(DEALER_CHARGING_NETWORK_ORDER)
    selections = [
        selected
        for size in range(len(dealer_networks) + 1)
        for selected in combinations(dealer_networks, size)
    ]
    for connector in catalog.summary()["connector_node_counts"]:
        availability[connector] = {}
        for selected in selections:
            allowed = {PUBLIC_CHARGING_NETWORK, *selected}
            key = ",".join(selected) or "PUBLIC_ONLY"
            availability[connector][key] = sum(
                1
                for node in catalog.nodes
                if any(
                    unit.charging_network in allowed
                    and connector in unit.connectors
                    for unit in node.units
                )
            )
    return availability


@web_bp.get("/")
def index():
    catalog = current_app.extensions["station_catalog"]
    catalog_summary = catalog.summary()
    connector_availability = _connector_availability(catalog)
    connector_counts = catalog_summary["connector_node_counts"]
    connector_labels = {
        "AC TYPE 2": "AC Type 2",
        "CCS2": "CCS2",
        "CHADEMO": "CHAdeMO",
        "GB/T": "GB/T",
    }
    return render_template(
        "index.html",
        app_name=current_app.config["APP_NAME"],
        app_version=current_app.config["APP_VERSION"],
        csp_nonce=g.csp_nonce,
        connectors=[
            {
                "value": connector,
                "label": connector_labels[connector],
                "location_count": connector_availability[connector][
                    "PUBLIC_ONLY"
                ],
            }
            for connector, location_count in connector_counts.items()
            if location_count > 0
        ],
        public_location_count=catalog_summary["network_node_counts"][
            PUBLIC_CHARGING_NETWORK
        ],
        charging_networks=[
            {
                "value": network,
                "label": CHARGING_NETWORK_LABELS[network],
                "location_count": catalog_summary["network_node_counts"][
                    network
                ],
                "connector_counts": catalog_summary[
                    "network_connector_node_counts"
                ][network],
            }
            for network in DEALER_CHARGING_NETWORK_ORDER
            if catalog_summary["network_node_counts"][network] > 0
        ],
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
            "connectorAvailability": connector_availability,
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
