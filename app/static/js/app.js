"use strict";

const SULAWESI_CENTER = { lat: -2.1, lng: 121.2 };
const SULAWESI_BOUNDS = {
    south: -7,
    west: 118,
    north: 3,
    east: 126.5,
};

const elements = {
    serviceState: document.getElementById("serviceState"),
    routeForm: document.getElementById("routeForm"),
    routeFieldset: document.getElementById("routeFieldset"),
    submitButton: document.getElementById("submitButton"),
    formStatus: document.getElementById("formStatus"),
    originHost: document.getElementById("originAutocomplete"),
    destinationHost: document.getElementById("destinationAutocomplete"),
    originSelectionStatus: document.getElementById("originSelectionStatus"),
    destinationSelectionStatus: document.getElementById("destinationSelectionStatus"),
    currentSoc: document.getElementById("currentSoc"),
    maxRange: document.getElementById("maxRange"),
    minimumSoc: document.getElementById("minimumSoc"),
    targetSoc: document.getElementById("targetSoc"),
    connectorInputs: Array.from(
        document.querySelectorAll('input[name="connectors"]'),
    ),
    networkInputs: Array.from(
        document.querySelectorAll('input[name="additional_charging_networks"]'),
    ),
    networkCompatibilityNote: document.getElementById("networkCompatibilityNote"),
    resultsPanel: document.getElementById("resultsPanel"),
    resultsTitle: document.getElementById("resultsTitle"),
    resultBadge: document.getElementById("resultBadge"),
    resultMessage: document.getElementById("resultMessage"),
    summaryGrid: document.getElementById("summaryGrid"),
    itinerarySection: document.getElementById("itinerarySection"),
    itineraryList: document.getElementById("itineraryList"),
    diagnosticList: document.getElementById("diagnosticList"),
    mapElement: document.getElementById("map"),
    mapEmpty: document.getElementById("mapEmpty"),
    mapLoading: document.getElementById("mapLoading"),
};

const state = {
    config: readFrontendConfig(),
    map: null,
    mapsLibrary: null,
    AdvancedMarkerElement: null,
    infoWindow: null,
    polyline: null,
    markers: [],
    interfaceReady: false,
    isSubmitting: false,
    selectedPlaces: {
        origin: null,
        destination: null,
    },
};

function readFrontendConfig() {
    const configElement = document.getElementById("frontendConfig");
    if (!configElement) return {};
    try {
        return JSON.parse(configElement.textContent);
    } catch (error) {
        return {};
    }
}

function setFormStatus(message, type = "info") {
    if (!elements.formStatus) return;
    elements.formStatus.textContent = message;
    elements.formStatus.classList.remove("is-error", "is-success");
    if (type === "error") elements.formStatus.classList.add("is-error");
    if (type === "success") elements.formStatus.classList.add("is-success");
}

function initializationErrorMessage(error) {
    const message = error?.message || "Sistem belum siap.";
    if (message.includes("Endpoint rekomendasi")) {
        return `${message} Pastikan server API key untuk Routes API tersedia, lalu restart aplikasi.`;
    }
    if (message.includes("browser API key") || message.includes("Google Maps")) {
        return `${message} Periksa browser key, restriction referrer, Maps JavaScript API, dan Places API (New).`;
    }
    return `${message} Periksa konfigurasi Maps/Places di browser dan Routes API di backend.`;
}

function recommendationErrorMessage(response, payload) {
    const serverMessage = payload?.error?.message;
    if (response.status === 429) {
        return `${serverMessage || "Batas pemakaian atau request aktif tercapai."} Periksa sisa quota harian dan pastikan request sebelumnya sudah selesai sebelum mencoba lagi. Jangan melakukan retry berulang.`;
    }
    if (response.status === 502) {
        return `${serverMessage || "Layanan rute Google tidak dapat memproses permintaan."} Periksa Routes API, billing, restriction server key, jaringan, dan quota.`;
    }
    if (response.status === 503) {
        return `${serverMessage || "Endpoint rekomendasi belum dikonfigurasi."} Isi server API key lalu restart aplikasi.`;
    }
    return serverMessage || "Rekomendasi gagal diproses.";
}

async function checkServiceHealth() {
    if (!elements.serviceState) throw new Error("Indikator layanan tidak tersedia.");

    try {
        const response = await fetch("/api/health", {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();

        if (!response.ok || payload.status !== "ok") {
            throw new Error("Layanan belum siap");
        }

        const mapsReady = payload.data?.google_maps?.recommendation_endpoint_ready;
        if (!mapsReady) throw new Error("Endpoint rekomendasi belum siap");

        elements.serviceState.classList.remove("is-error");
        elements.serviceState.classList.add("is-ready");
        const nodeCount = payload.data?.dataset?.logical_nodes;
        elements.serviceState.querySelector("span:last-child").textContent = nodeCount
            ? `Sistem siap · ${nodeCount} lokasi`
            : "Sistem siap";
        return payload.data;
    } catch (error) {
        elements.serviceState.classList.remove("is-ready");
        elements.serviceState.classList.add("is-error");
        elements.serviceState.querySelector("span:last-child").textContent =
            "Sistem bermasalah";
        throw error;
    }
}

function updateSubmitAvailability() {
    if (!elements.submitButton) return;
    const locationsReady = Boolean(
        state.selectedPlaces.origin && state.selectedPlaces.destination,
    );
    const connectorsReady = selectedConnectorValues().length > 0;
    elements.submitButton.disabled = !state.interfaceReady
        || !locationsReady
        || !connectorsReady
        || state.isSubmitting;
}

function setPlaceSelectionStatus(kind, selected) {
    const status = kind === "origin"
        ? elements.originSelectionStatus
        : elements.destinationSelectionStatus;
    if (!status) return;
    status.classList.toggle("is-selected", selected);
    status.textContent = selected
        ? "Lokasi tersimpan dan koordinat siap digunakan."
        : "Belum dipilih dari daftar saran Google.";
}

function loadGoogleMaps(apiKey) {
    if (window.google?.maps?.importLibrary) return Promise.resolve();

    return new Promise((resolve, reject) => {
        const callbackName = `initSpkluMaps_${Date.now()}`;
        const script = document.createElement("script");
        const parameters = new URLSearchParams({
            key: apiKey,
            loading: "async",
            callback: callbackName,
            v: "weekly",
            libraries: "maps,places,marker",
            language: "id",
            region: "ID",
        });

        window[callbackName] = () => {
            delete window[callbackName];
            resolve();
        };
        script.async = true;
        script.nonce = document.querySelector("script[nonce]")?.nonce || "";
        script.src = `https://maps.googleapis.com/maps/api/js?${parameters}`;
        script.referrerPolicy = "strict-origin-when-cross-origin";
        script.onerror = () => {
            delete window[callbackName];
            reject(new Error("Google Maps JavaScript API gagal dimuat."));
        };
        document.head.append(script);
    });
}

function locationToCoordinate(location) {
    return {
        latitude: location.lat(),
        longitude: location.lng(),
    };
}

function normalizedAutocompleteValue(autocomplete) {
    return String(autocomplete.value || "").trim();
}

function createPlaceAutocomplete({ host, kind, placeholder, description }) {
    const { PlaceAutocompleteElement } = state.placesLibrary;
    const autocomplete = new PlaceAutocompleteElement({
        includedRegionCodes: ["id"],
        requestedLanguage: "id",
        requestedRegion: "id",
        placeholder,
    });
    autocomplete.description = description;
    autocomplete.locationRestriction = SULAWESI_BOUNDS;

    autocomplete.addEventListener("input", () => {
        const selectedPlace = state.selectedPlaces[kind];
        if (
            selectedPlace
            && normalizedAutocompleteValue(autocomplete)
                === selectedPlace.autocompleteValue
        ) {
            return;
        }
        state.selectedPlaces[kind] = null;
        setPlaceSelectionStatus(kind, false);
        updateSubmitAvailability();
    });
    autocomplete.addEventListener("gmp-select", async ({ placePrediction }) => {
        try {
            const place = placePrediction.toPlace();
            await place.fetchFields({
                fields: ["displayName", "formattedAddress", "location"],
            });
            if (!place.location) {
                throw new Error("Lokasi pilihan tidak memiliki koordinat.");
            }

            state.selectedPlaces[kind] = {
                ...locationToCoordinate(place.location),
                label: place.displayName || place.formattedAddress || "Lokasi pilihan",
                address: place.formattedAddress || "",
                autocompleteValue: normalizedAutocompleteValue(autocomplete),
            };
            setPlaceSelectionStatus(kind, true);
            updateSubmitAvailability();
            setFormStatus(
                "Lokasi tersimpan. Lengkapi kedua lokasi lalu jalankan rekomendasi.",
                "success",
            );
        } catch (error) {
            state.selectedPlaces[kind] = null;
            setPlaceSelectionStatus(kind, false);
            updateSubmitAvailability();
            setFormStatus(error.message || "Detail lokasi gagal dimuat.", "error");
        }
    });
    autocomplete.addEventListener("gmp-error", () => {
        state.selectedPlaces[kind] = null;
        setPlaceSelectionStatus(kind, false);
        updateSubmitAvailability();
        setFormStatus(
            "Saran lokasi Google gagal dimuat. Periksa Places API, browser key, dan quota sebelum mencoba lagi.",
            "error",
        );
    });

    host.replaceChildren(autocomplete);
    return autocomplete;
}

async function initializeMapsInterface() {
    const apiKey = state.config.googleMapsBrowserApiKey;
    if (!state.config.mapsConfigured || !apiKey) {
        throw new Error("Google Maps browser API key belum dikonfigurasi.");
    }

    await loadGoogleMaps(apiKey);
    const [mapsLibrary, placesLibrary, markerLibrary] = await Promise.all([
        google.maps.importLibrary("maps"),
        google.maps.importLibrary("places"),
        google.maps.importLibrary("marker"),
    ]);

    state.mapsLibrary = mapsLibrary;
    state.placesLibrary = placesLibrary;
    state.AdvancedMarkerElement = markerLibrary.AdvancedMarkerElement;
    state.map = new mapsLibrary.Map(elements.mapElement, {
        center: SULAWESI_CENTER,
        zoom: 6.1,
        mapId: state.config.googleMapsMapId || "DEMO_MAP_ID",
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: true,
        clickableIcons: false,
        gestureHandling: "greedy",
    });
    state.infoWindow = new mapsLibrary.InfoWindow();

    createPlaceAutocomplete({
        host: elements.originHost,
        kind: "origin",
        placeholder: "Cari lokasi awal, misalnya Makassar",
        description: "Pilih lokasi awal perjalanan",
    });
    createPlaceAutocomplete({
        host: elements.destinationHost,
        kind: "destination",
        placeholder: "Cari lokasi tujuan, misalnya Palu",
        description: "Pilih lokasi tujuan perjalanan",
    });

}

function numberValue(element) {
    return Number(element.value);
}

function selectedConnectorValues() {
    return elements.connectorInputs
        .filter((input) => input.checked)
        .map((input) => input.value);
}

function selectedChargingNetworkValues() {
    return elements.networkInputs
        .filter((input) => input.checked)
        .map((input) => input.value);
}

function networkConnectorCounts(input) {
    try {
        return JSON.parse(input.dataset.connectorCounts || "{}");
    } catch (error) {
        return {};
    }
}

function updateNetworkCompatibilityNote() {
    const note = elements.networkCompatibilityNote;
    if (!note) return;

    note.classList.remove("is-warning");
    const selectedNetworks = elements.networkInputs.filter((input) => input.checked);
    if (!selectedNetworks.length) {
        note.textContent = "Saat ini sistem hanya menggunakan SPKLU publik.";
        return;
    }

    const selectedConnectors = selectedConnectorValues();
    if (!selectedConnectors.length) {
        note.textContent = "Pilih konektor untuk memeriksa kecocokan jaringan dealer.";
        return;
    }

    const incompatible = selectedNetworks.flatMap((input) => {
        const counts = networkConnectorCounts(input);
        const compatibleCount = selectedConnectors.reduce(
            (total, connector) => total + Number(counts[connector] || 0),
            0,
        );
        if (compatibleCount > 0) return [];
        const availableConnectors = Object.entries(counts)
            .filter(([, count]) => Number(count) > 0)
            .map(([connector]) => connector);
        return [{
            label: input.dataset.label || input.value,
            availableConnectors,
        }];
    });

    if (incompatible.length) {
        note.classList.add("is-warning");
        note.textContent = incompatible.map((network) => {
            const available = network.availableConnectors.length
                ? network.availableConnectors.join(", ")
                : "tidak tercatat";
            return `${network.label} tidak memiliki lokasi yang cocok dengan ${selectedConnectors.join(", ")}. Konektor yang tersedia: ${available}.`;
        }).join(" ");
        return;
    }

    note.textContent = "Jaringan dealer yang dipilih akan disaring lagi berdasarkan konektor kendaraan.";
}

function requestConnectors(data) {
    if (Array.isArray(data.request.connectors)) return data.request.connectors;
    return data.request.connector ? [data.request.connector] : [];
}

function requestConnectorLabel(data) {
    return requestConnectors(data).join(", ");
}

function validateForm() {
    if (!elements.routeForm.checkValidity()) {
        elements.routeForm.reportValidity();
        throw new Error("Lengkapi parameter kendaraan dengan nilai yang valid.");
    }
    if (!state.selectedPlaces.origin || !state.selectedPlaces.destination) {
        throw new Error(
            "Pilih lokasi awal dan tujuan dari daftar saran Google, bukan hanya mengetik teks.",
        );
    }
    if (!selectedConnectorValues().length) {
        throw new Error("Pilih sedikitnya satu jenis konektor kendaraan.");
    }

    const currentSoc = numberValue(elements.currentSoc);
    const minimumSoc = numberValue(elements.minimumSoc);
    const targetSoc = numberValue(elements.targetSoc);
    if (currentSoc <= minimumSoc) {
        throw new Error("SOC saat ini harus lebih besar dari SOC minimum.");
    }
    if (targetSoc <= minimumSoc) {
        throw new Error("Target SOC harus lebih besar dari SOC minimum.");
    }
}

function buildRequestPayload() {
    return {
        origin: {
            latitude: state.selectedPlaces.origin.latitude,
            longitude: state.selectedPlaces.origin.longitude,
        },
        destination: {
            latitude: state.selectedPlaces.destination.latitude,
            longitude: state.selectedPlaces.destination.longitude,
        },
        vehicle: {
            maximum_range_km: numberValue(elements.maxRange),
            current_soc_percent: numberValue(elements.currentSoc),
            connectors: selectedConnectorValues(),
        },
        options: {
            minimum_soc_percent: numberValue(elements.minimumSoc),
            target_soc_percent: numberValue(elements.targetSoc),
            additional_charging_networks: selectedChargingNetworkValues(),
        },
    };
}

function setLoading(isLoading) {
    state.isSubmitting = isLoading;
    updateSubmitAvailability();
    elements.submitButton.querySelector("span").textContent = isLoading
        ? "Menghitung rekomendasi…"
        : "Cari rekomendasi SPKLU";
    elements.mapLoading.hidden = !isLoading;
}

function clearMapOverlays() {
    if (state.polyline) {
        state.polyline.setMap(null);
        state.polyline = null;
    }
    for (const marker of state.markers) marker.map = null;
    state.markers = [];
    state.infoWindow?.close();
}

function coordinateLiteral(coordinate) {
    return { lat: coordinate.latitude, lng: coordinate.longitude };
}

function markerContent(text, modifier = "") {
    const content = document.createElement("div");
    content.className = `route-marker ${modifier}`.trim();
    content.textContent = text;
    return content;
}

function addMarker({ position, title, text, modifier, onClick, zIndex }) {
    const marker = new state.AdvancedMarkerElement({
        map: state.map,
        position,
        title,
        content: markerContent(text, modifier),
        gmpClickable: Boolean(onClick),
        zIndex,
    });
    if (onClick) marker.addEventListener("gmp-click", onClick);
    state.markers.push(marker);
    return marker;
}

function stationInfoContent(stop) {
    const station = stop.station;
    const content = document.createElement("div");
    content.className = "station-info";

    const name = document.createElement("strong");
    name.textContent = station.name;
    content.append(name);

    const address = document.createElement("span");
    address.textContent = station.address;
    content.append(address);

    const charging = document.createElement("span");
    const compatibleConnectors = station.route_compatible_connectors
        || station.connectors;
    charging.textContent = `SOC ${formatPercent(stop.arrival_soc_percent)} → ${formatPercent(stop.departure_soc_percent)} · ${station.unit_count} unit · ${compatibleConnectors.join(", ")}`;
    const access = document.createElement("span");
    access.className = station.route_access_type === "dealer_conditional"
        ? "is-conditional"
        : "";
    access.textContent = station.route_access_type === "dealer_conditional"
        ? `${station.route_charging_network_label} · akses perlu dikonfirmasi`
        : "SPKLU publik";
    content.append(charging, access);
    return content;
}

function renderMap(data) {
    clearMapOverlays();
    const feasible = data.optimization.feasible;
    const route = data.recommended_route || data.base_route;
    if (!route?.coordinates?.length) return;

    const path = route.coordinates.map(coordinateLiteral);
    elements.mapEmpty.classList.add("is-hidden");
    state.polyline = new state.mapsLibrary.Polyline({
        map: state.map,
        path,
        strokeColor: feasible ? "#087f78" : "#b4433b",
        strokeOpacity: feasible ? 0.9 : 0.65,
        strokeWeight: 6,
        geodesic: true,
    });

    const origin = coordinateLiteral(data.request.origin);
    const destination = coordinateLiteral(data.request.destination);
    addMarker({
        position: origin,
        title: state.selectedPlaces.origin?.label || "Lokasi awal",
        text: "A",
        modifier: "is-origin",
        zIndex: 1000,
    });
    addMarker({
        position: destination,
        title: state.selectedPlaces.destination?.label || "Lokasi tujuan",
        text: "B",
        modifier: "is-destination",
        zIndex: 1000,
    });

    const stops = data.optimization.itinerary?.charging_stops || [];
    stops.forEach((stop, index) => {
        const station = stop.station;
        const position = {
            lat: station.latitude,
            lng: station.longitude,
        };
        let marker;
        marker = addMarker({
            position,
            title: `Pemberhentian ${index + 1}: ${station.name}`,
            text: String(index + 1),
            zIndex: 900 - index,
            onClick: () => {
                state.infoWindow.setContent(stationInfoContent(stop));
                state.infoWindow.open({ anchor: marker, map: state.map });
            },
        });
    });

    const bounds = new google.maps.LatLngBounds();
    path.forEach((position) => bounds.extend(position));
    state.map.fitBounds(bounds, 72);
    google.maps.event.addListenerOnce(state.map, "idle", () => {
        if (state.map.getZoom() > 13) state.map.setZoom(13);
    });
}

const decimalFormatter = new Intl.NumberFormat("id-ID", {
    maximumFractionDigits: 1,
});

function formatNumber(value) {
    return decimalFormatter.format(Number(value));
}

function formatDistance(value) {
    return `${formatNumber(value)} km`;
}

function formatDuration(value) {
    if (value === null || value === undefined) return "Tidak tersedia";
    const minutes = Math.round(Number(value));
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    if (!hours) return `${remainder} menit`;
    return remainder ? `${hours} jam ${remainder} menit` : `${hours} jam`;
}

function formatPercent(value) {
    return `${formatNumber(value)}%`;
}

function summaryItem(label, value) {
    const item = document.createElement("div");
    item.className = "summary-item";
    const labelElement = document.createElement("small");
    labelElement.textContent = label;
    const valueElement = document.createElement("strong");
    valueElement.textContent = value;
    item.append(labelElement, valueElement);
    return item;
}

function renderSummary(data) {
    const optimization = data.optimization;
    elements.summaryGrid.replaceChildren();
    if (optimization.feasible) {
        const itinerary = optimization.itinerary;
        elements.summaryGrid.append(
            summaryItem("Jarak berkendara", formatDistance(itinerary.total_road_distance_km)),
            summaryItem("Durasi berkendara", formatDuration(itinerary.total_driving_duration_minutes)),
            summaryItem("Pemberhentian SPKLU", String(itinerary.charging_stop_count)),
            summaryItem("SOC tiba tujuan", formatPercent(itinerary.final_soc_percent)),
            summaryItem(
                "Status akses",
                data.route_access?.conditional ? "Rute kondisional" : "Rute publik",
            ),
        );
    } else {
        elements.summaryGrid.append(
            summaryItem("Jarak rute dasar", formatDistance(data.base_route.distance_km)),
            summaryItem("Durasi rute dasar", formatDuration(data.base_route.duration_minutes)),
            summaryItem(`Kandidat ${requestConnectorLabel(data)}`, String(data.candidate_summary.corridor_candidate_count)),
            summaryItem("Status", "Tidak feasible"),
        );
    }
}

function stopByNodeId(stops, nodeId) {
    return stops.find((stop) => stop.node_id === nodeId);
}

function renderItinerary(data) {
    const itinerary = data.optimization.itinerary;
    elements.itineraryList.replaceChildren();
    if (!itinerary) return;

    itinerary.legs.forEach((leg, index) => {
        const item = document.createElement("li");
        item.className = "itinerary-item";
        const indexElement = document.createElement("span");
        indexElement.className = "itinerary-index";
        indexElement.textContent = String(index + 1);

        const copy = document.createElement("div");
        copy.className = "itinerary-copy";
        const title = document.createElement("strong");
        title.textContent = `${leg.source_name} → ${leg.target_name}`;
        const metadata = document.createElement("small");
        metadata.textContent = `${formatDistance(leg.road_distance_km)} · ${formatDuration(leg.road_duration_minutes)} · SOC ${formatPercent(leg.departure_soc_percent)} → ${formatPercent(leg.arrival_soc_percent)}`;
        copy.append(title, metadata);

        const stop = stopByNodeId(itinerary.charging_stops, leg.source_id);
        if (stop) {
            const station = stop.station;
            const stopCard = document.createElement("div");
            stopCard.className = "stop-card";
            if (station.route_access_type === "dealer_conditional") {
                stopCard.classList.add("is-conditional");
            }
            const accessLabel = station.route_access_type === "dealer_conditional"
                ? `${station.route_charging_network_label} · konfirmasi akses`
                : "SPKLU publik";
            const compatibleConnectors = station.route_compatible_connectors
                || station.connectors;
            stopCard.textContent = `Pengisian SOC ${formatPercent(stop.arrival_soc_percent)} → ${formatPercent(stop.departure_soc_percent)} (+${formatPercent(stop.charged_soc_percent)}) · ${station.unit_count} unit · ${compatibleConnectors.join(", ")} · ${accessLabel}`;
            copy.append(stopCard);
        }

        item.append(indexElement, copy);
        elements.itineraryList.append(item);
    });
}

function diagnosticPair(label, value) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = String(value);
    return [term, description];
}

function renderDiagnostics(data) {
    const graph = data.graph;
    const stats = data.optimization.stats;
    const usage = data.api_usage;
    const pairs = [
        ...diagnosticPair("Kandidat dalam koridor", data.candidate_summary.corridor_candidate_count),
        ...diagnosticPair("Kandidat sebelum filter jaringan", data.candidate_summary.connector_candidate_count),
        ...diagnosticPair("Node graf", graph.node_count),
        ...diagnosticPair("Edge graf diterima", graph.edge_count),
        ...diagnosticPair("State DP diproses", stats.processed_states),
        ...diagnosticPair("Elemen Route Matrix", usage.compute_route_matrix_elements),
        ...diagnosticPair("Total permintaan Google", usage.total_external_requests),
    ];
    if (data.quota_guard) {
        pairs.push(
            ...diagnosticPair(
                "Attempt Compute Routes request ini",
                data.quota_guard.compute_routes_attempt_count,
            ),
            ...diagnosticPair(
                "Attempt elemen Matrix request ini",
                data.quota_guard.matrix_element_attempt_count,
            ),
            ...diagnosticPair(
                "Sisa Compute Routes harian",
                data.quota_guard.daily_compute_routes_remaining,
            ),
            ...diagnosticPair(
                "Sisa elemen Matrix harian",
                data.quota_guard.daily_matrix_elements_remaining,
            ),
            ...diagnosticPair(
                "Sisa Compute Routes menit ini",
                data.quota_guard.compute_routes_remaining_this_minute,
            ),
            ...diagnosticPair(
                "Sisa elemen Matrix menit ini",
                data.quota_guard.matrix_elements_remaining_this_minute,
            ),
        );
    }
    elements.diagnosticList.replaceChildren(...pairs);
}

function renderRecommendation(data) {
    const feasible = data.optimization.feasible;
    const conditional = feasible && Boolean(data.route_access?.conditional);
    elements.resultsPanel.hidden = false;
    elements.resultBadge.classList.toggle("is-infeasible", !feasible);
    elements.resultBadge.classList.toggle("is-conditional", conditional);
    elements.resultBadge.textContent = !feasible
        ? "Tidak feasible"
        : conditional
            ? "Rute kondisional"
            : "Rute publik";
    elements.resultsTitle.textContent = feasible
        ? "Rute perjalanan ditemukan"
        : "Rute aman belum ditemukan";
    elements.resultMessage.textContent = conditional
        ? `${data.optimization.message} ${data.route_access.notice}`
        : data.optimization.message;
    elements.itinerarySection.hidden = !feasible;

    renderSummary(data);
    renderItinerary(data);
    renderDiagnostics(data);
    renderMap(data);

    setFormStatus(
        feasible
            ? conditional
                ? "Rekomendasi selesai. Rute menggunakan charger dealer yang perlu dikonfirmasi sebelum berangkat."
                : "Rekomendasi selesai. Rute publik dan rincian SOC telah diperbarui."
            : "Perhitungan selesai, tetapi tidak ditemukan rangkaian SPKLU yang memenuhi batas SOC.",
        feasible ? "success" : "error",
    );
    elements.resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function submitRecommendation(event) {
    event.preventDefault();
    try {
        validateForm();
    } catch (error) {
        setFormStatus(error.message, "error");
        return;
    }

    setLoading(true);
    setFormStatus("Mengambil rute dan menjalankan Dynamic Programming…");
    try {
        const response = await fetch("/api/recommendations", {
            method: "POST",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: JSON.stringify(buildRequestPayload()),
        });
        let payload;
        try {
            payload = await response.json();
        } catch (error) {
            throw new Error(
                "Server tidak mengembalikan respons yang dapat dibaca. Periksa terminal aplikasi dan koneksi lokal.",
            );
        }
        if (!response.ok || payload.status !== "ok") {
            throw new Error(recommendationErrorMessage(response, payload));
        }
        renderRecommendation(payload.data);
    } catch (error) {
        setFormStatus(
            error.message || "Terjadi kesalahan saat menyusun rekomendasi.",
            "error",
        );
        elements.formStatus?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } finally {
        setLoading(false);
    }
}

async function initializeApplication() {
    elements.routeForm?.addEventListener("submit", submitRecommendation);
    elements.connectorInputs.forEach((input) => {
        input.addEventListener("change", () => {
            updateSubmitAvailability();
            updateNetworkCompatibilityNote();
        });
    });
    elements.networkInputs.forEach((input) => {
        input.addEventListener("change", updateNetworkCompatibilityNote);
    });
    updateSubmitAvailability();
    updateNetworkCompatibilityNote();
    try {
        await Promise.all([
            checkServiceHealth(),
            initializeMapsInterface(),
        ]);
        state.interfaceReady = true;
        elements.routeFieldset.disabled = false;
        updateSubmitAvailability();
        setFormStatus(
            "Sistem siap. Pilih lokasi awal dan tujuan dari daftar saran Google; tombol pencarian akan aktif setelah keduanya tersimpan.",
            "success",
        );
    } catch (error) {
        state.interfaceReady = false;
        elements.routeFieldset.disabled = true;
        updateSubmitAvailability();
        setFormStatus(
            initializationErrorMessage(error),
            "error",
        );
    }
}

initializeApplication();
