"""Kontrak offline untuk perilaku penting antarmuka pengguna.

Tes ini sengaja tidak memuat Google Maps. Selain menjaga CI bebas quota, kontrak
berikut melindungi alur keselamatan UI yang tidak dapat dibuktikan oleh test API
Flask saja.
"""

import json
import re
from pathlib import Path


JAVASCRIPT_PATH = Path("app/static/js/app.js")
STYLESHEET_PATH = Path("app/static/css/app.css")


def _javascript():
    return JAVASCRIPT_PATH.read_text(encoding="utf-8")


def _stylesheet():
    return STYLESHEET_PATH.read_text(encoding="utf-8")


def _between(source, start, end):
    """Mengambil bagian sumber di antara dua penanda unik."""

    return source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


def _frontend_config(response):
    html = response.get_data(as_text=True)
    match = re.search(
        r'<script id="frontendConfig"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_dynamic_connector_counts_follow_selected_networks(client):
    response = client.get("/")
    config = _frontend_config(response)
    availability = config["connectorAvailability"]
    set_availability = config["connectorSetAvailability"]

    assert availability["AC TYPE 2"]["PUBLIC_ONLY"] == 92
    assert availability["AC TYPE 2"]["HYUNDAI,WULING,TOYOTA"] == 107
    assert availability["GB/T"]["PUBLIC_ONLY"] == 0
    assert availability["GB/T"]["WULING"] == 17
    assert availability["CCS2"]["WULING"] == 42
    assert set_availability["AC TYPE 2|CCS2"]["PUBLIC_ONLY"] == 114
    assert (
        set_availability["AC TYPE 2|CCS2"]["HYUNDAI,WULING,TOYOTA"]
        == 129
    )

    html = response.get_data(as_text=True)
    assert 'data-connector-count="AC TYPE 2">92 lokasi tersedia' in html
    assert 'data-connector-count="GB/T">0 lokasi tersedia' in html
    assert "114 lokasi · selalu disertakan" in html
    assert 'id="allowFerries"' in html
    assert "Izinkan feri kendaraan" in html
    assert "allow_ferries: Boolean(elements.allowFerries?.checked)" in _javascript()


def test_combo2_defaults_and_ac_fallback_are_explained(client):
    html = client.get("/").get_data(as_text=True)
    source = _javascript()

    ac_checkbox = re.search(
        r'<input[^>]+name="connectors"[^>]+value="AC TYPE 2"[^>]*>',
        html,
    )
    ccs_checkbox = re.search(
        r'<input[^>]+name="connectors"[^>]+value="CCS2"[^>]*>',
        html,
    )
    assert ac_checkbox is not None and "checked" in ac_checkbox.group(0)
    assert ccs_checkbox is not None and "checked" in ccs_checkbox.group(0)
    assert 'value="430"' in html
    assert "CCS2 diprioritaskan" in html
    assert 'id="connectorCombinationNote"' in html
    assert "function updateConnectorCombinationNote" in source
    assert '"AC Type 2 fallback"' in source
    assert "route_selected_connector" in source
    assert "waktu pengisian tidak dihitung" in source


def test_stale_recommendation_is_invalidated_on_every_input_family():
    source = _javascript()
    invalidation = _between(
        source,
        "function invalidateRecommendation",
        "function requestConnectors",
    )
    autocomplete = _between(
        source,
        "function createPlaceAutocomplete",
        "async function initializeMapsInterface",
    )
    initialization = _between(
        source,
        "async function initializeApplication",
        "\ninitializeApplication();",
    )

    assert "state.inputRevision += 1" in invalidation
    assert "elements.resultsPanel.hidden = true" in invalidation
    assert "clearMapOverlays();" in invalidation
    assert "setMapEmptyState(" in invalidation
    assert autocomplete.count("invalidateRecommendation();") >= 3
    selection_reset = "state.selectedPlaces[kind] = null"
    assert autocomplete.index(selection_reset, autocomplete.index('"gmp-select"')) < (
        autocomplete.index("await place.fetchFields")
    )
    gmp_error = autocomplete.split('"gmp-error"', maxsplit=1)[1]
    assert "invalidateRecommendation();" in gmp_error
    assert initialization.count("invalidateRecommendation();") >= 3


def test_reset_button_restores_clean_default_journey(client):
    html = client.get("/").get_data(as_text=True)
    source = _javascript()
    reset = _between(
        source,
        "function resetJourney",
        "function requestConnectors",
    )
    initialization = _between(
        source,
        "async function initializeApplication",
        "\ninitializeApplication();",
    )

    assert 'id="resetButton" class="button-secondary" type="button"' in html
    assert "Reset perjalanan" in html
    assert "elements.routeForm?.reset();" in reset
    assert "state.selectedPlaces.origin = null" in reset
    assert "state.selectedPlaces.destination = null" in reset
    assert 'autocomplete.value = ""' in reset
    assert "invalidateRecommendation({ inputChanged: false });" in reset
    assert "elements.summaryGrid?.replaceChildren();" in reset
    assert "elements.itineraryList?.replaceChildren();" in reset
    assert "elements.diagnosticList?.replaceChildren();" in reset
    assert "state.map.setCenter(SULAWESI_CENTER);" in reset
    assert "state.map.setZoom(6.1);" in reset
    assert '"Pilih lokasi awal dan tujuan"' in reset
    assert "updateConnectorAvailabilityCounts();" in reset
    assert "updateNetworkCompatibilityNote();" in reset
    assert "updateSubmitAvailability();" in reset
    assert 'elements.resetButton?.addEventListener("click", resetJourney);' in initialization


def test_active_request_is_locked_and_stale_response_is_discarded():
    source = _javascript()
    loading = _between(source, "function setLoading", "function clearMapOverlays")
    submission = _between(
        source,
        "async function submitRecommendation",
        "async function initializeApplication",
    )

    assert "if (state.isSubmitting) return" in submission
    assert "elements.routeFieldset.disabled = isLoading || !state.interfaceReady" in loading
    assert "autocomplete.disabled = isLoading || !state.interfaceReady" in loading
    assert "const requestSequence = ++state.requestSequence" in submission
    assert "const inputRevision = state.inputRevision" in submission
    assert "requestSequence !== state.requestSequence" in submission
    assert "inputRevision !== state.inputRevision" in submission
    assert "Hasil lama tidak ditampilkan" in submission
    assert submission.index("inputRevision !== state.inputRevision") < submission.index(
        "renderRecommendation(payload.data)"
    )


def test_initialization_checks_health_before_consuming_a_map_load():
    source = _javascript()
    initialization = _between(
        source,
        "async function initializeApplication",
        "\ninitializeApplication();",
    )

    health = "const health = await checkServiceHealth();"
    maps = "await initializeMapsInterface();"
    ready = 'setServiceState(\n            "ready"'
    assert health in initialization
    assert maps in initialization
    assert initialization.index(health) < initialization.index(maps)
    assert initialization.index(maps) < initialization.index(ready)
    assert "Promise.all([" not in initialization


def test_external_waits_have_bounded_timeouts_and_no_automatic_retry():
    source = _javascript()
    timeout_helper = _between(
        source,
        "async function fetchWithTimeout",
        "function initializationErrorMessage",
    )
    maps_loader = _between(
        source,
        "function loadGoogleMaps",
        "function locationToCoordinate",
    )
    submission = _between(
        source,
        "async function submitRecommendation",
        "async function initializeApplication",
    )

    assert "const HEALTH_TIMEOUT_MS = 8_000" in source
    assert "const MAPS_LOAD_TIMEOUT_MS = 20_000" in source
    assert "const RECOMMENDATION_TIMEOUT_MS = 125_000" in source
    assert "new AbortController()" in timeout_helper
    assert "controller.abort()" in timeout_helper
    assert "window.clearTimeout(timer)" in timeout_helper
    assert "MAPS_LOAD_TIMEOUT_MS" in maps_loader
    assert "window.gm_authFailure" in maps_loader
    assert "RECOMMENDATION_TIMEOUT_MS" in submission
    assert "setInterval(" not in source
    assert "while (" not in submission


def test_infeasible_is_warning_and_direct_route_needs_no_charger():
    source = _javascript()
    rendering = _between(
        source,
        "function renderRecommendation",
        "async function submitRecommendation",
    )
    summary = _between(source, "function renderSummary", "function stopByNodeId")
    css = _stylesheet()

    assert 'feasible && !conditional ? "success" : "warning"' in rendering
    assert '"Tanpa pengisian"' in rendering
    assert '"Feri kondisional"' in rendering
    assert '"Tidak perlu SPKLU"' in summary
    assert '"Jarak feri"' in summary
    assert '"Durasi feri"' in summary
    assert "SOC hanya dikurangi untuk jarak darat." in source
    assert 'ferryCard.setAttribute("role", "note")' in source
    assert ".ferry-card" in css
    assert ".form-status.is-warning" in css
    assert '"Batas total detour"' in source
    assert '"Transisi dipangkas oleh batas detour"' in source


def test_result_focus_form_descriptions_and_busy_state_are_accessible(client):
    html = client.get("/").get_data(as_text=True)
    source = _javascript()

    assert 'class="skip-link" href="#routeForm"' in html
    assert 'id="formStatus" role="status" aria-live="polite" aria-atomic="true"' in html
    assert 'id="resultsTitle" tabindex="-1"' in html
    assert 'id="map" class="map-canvas" role="region"' in html
    assert 'aria-describedby="currentSocNote"' in html
    assert 'aria-describedby="maxRangeNote"' in html
    assert 'aria-describedby="minimumSocNote"' in html
    assert 'aria-describedby="targetSocNote"' in html
    assert 'aria-busy="false"' in html
    assert 'elements.resultsTitle.focus({ preventScroll: true })' in source
    assert 'elements.routeForm?.setAttribute("aria-busy", String(isLoading))' in source
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)")' in source


def test_station_result_exposes_safe_google_maps_links():
    source = _javascript()
    info_window = _between(source, "function stationInfoContent", "function renderMap")
    itinerary = _between(source, "function renderItinerary", "function diagnosticPair")

    for section in (info_window, itinerary):
        assert "mapsLink.href = station.maps_url" in section
        assert 'mapsLink.target = "_blank"' in section
        assert 'mapsLink.rel = "noopener noreferrer"' in section
        assert 'mapsLink.textContent = "Lihat lokasi di Google Maps"' in section
    assert "stopByNodeId(itinerary.charging_stops, leg.target_id)" in itinerary


def test_primary_interface_uses_plain_language_and_valid_legal_tokens(client):
    html = client.get("/").get_data(as_text=True)
    css = _stylesheet()

    assert "Cari SPKLU di sekitar rute" in html
    assert "Periksa jangkauan" in html
    assert "Susun perjalanan aman" in html
    assert "Radius search" not in html
    assert "Graf feasible" not in html
    assert "DP berbasis SOC" not in html

    for custom_property in (
        "--surface:",
        "--surface-soft:",
        "--ink-muted:",
        "--shadow-soft:",
    ):
        assert custom_property in css
    defined_properties = set(re.findall(r"(--[\w-]+)\s*:", css))
    referenced_properties = set(re.findall(r"var\((--[\w-]+)", css))
    assert referenced_properties <= defined_properties
    assert ".service-state span:last-child" not in css
    assert 'gestureHandling: "cooperative"' in _javascript()
