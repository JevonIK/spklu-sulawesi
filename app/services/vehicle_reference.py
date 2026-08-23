"""Validasi artefak sumber baseline jangkauan kendaraan penelitian."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from urllib.parse import urlparse

from ..constants import REFERENCE_MAXIMUM_RANGE_KM, RESEARCH_CONNECTORS


VEHICLE_RANGE_REFERENCE_SCHEMA_VERSION = 1


class VehicleRangeReferenceError(ValueError):
    """Menandai artefak referensi kendaraan yang tidak dapat diaudit."""


def _finite_positive(value, field):
    if isinstance(value, bool):
        raise VehicleRangeReferenceError(f"{field} wajib berupa angka positif.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise VehicleRangeReferenceError(
            f"{field} wajib berupa angka positif."
        ) from error
    if not math.isfinite(numeric) or numeric <= 0:
        raise VehicleRangeReferenceError(f"{field} wajib berupa angka positif.")
    return numeric


def _https_url(value, field):
    if not isinstance(value, str):
        raise VehicleRangeReferenceError(f"{field} wajib berupa URL HTTPS.")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VehicleRangeReferenceError(f"{field} wajib berupa URL HTTPS.")
    return value


def _representative_value(vehicle, field):
    values = vehicle.get("wltp_range_values_km")
    if not isinstance(values, list) or not values:
        raise VehicleRangeReferenceError(
            f"{field}.wltp_range_values_km wajib berupa daftar tidak kosong."
        )
    values = [
        _finite_positive(value, f"{field}.wltp_range_values_km")
        for value in values
    ]
    rule = vehicle.get("representative_rule")
    if rule in {"single_official_variant", "single_official_model_value"}:
        if len(values) != 1:
            raise VehicleRangeReferenceError(
                f"{field} memakai aturan nilai tunggal tetapi memiliki "
                "lebih dari satu angka."
            )
        return values[0]
    if rule == "median_of_official_variants":
        return float(statistics.median(values))
    if rule == "midpoint_of_official_range_band":
        if len(values) != 2:
            raise VehicleRangeReferenceError(
                f"{field} memakai midpoint tetapi bukan dua batas."
            )
        return sum(values) / 2
    raise VehicleRangeReferenceError(
        f"{field}.representative_rule tidak dikenal."
    )


def validate_vehicle_range_reference(payload):
    """Menghitung ulang median dan memastikan baseline tidak berupa magic number."""

    if not isinstance(payload, dict):
        raise VehicleRangeReferenceError("Referensi kendaraan wajib berupa objek.")
    if payload.get("schema_version") != VEHICLE_RANGE_REFERENCE_SCHEMA_VERSION:
        raise VehicleRangeReferenceError("schema_version referensi tidak didukung.")
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise VehicleRangeReferenceError("scope wajib berupa objek.")
    if scope.get("range_standard") != "WLTP":
        raise VehicleRangeReferenceError("Sampel utama wajib memakai WLTP.")
    if tuple(scope.get("required_connectors", ())) != RESEARCH_CONNECTORS:
        raise VehicleRangeReferenceError(
            "required_connectors tidak sama dengan konfigurasi penelitian."
        )

    vehicles = payload.get("vehicles")
    if not isinstance(vehicles, list) or len(vehicles) < 5:
        raise VehicleRangeReferenceError(
            "Referensi memerlukan sedikitnya lima model-family."
        )
    representatives = []
    model_keys = set()
    for index, vehicle in enumerate(vehicles):
        field = f"vehicles[{index}]"
        if not isinstance(vehicle, dict):
            raise VehicleRangeReferenceError(f"{field} wajib berupa objek.")
        manufacturer = str(vehicle.get("manufacturer", "")).strip()
        model = str(vehicle.get("model_family", "")).strip()
        if not manufacturer or not model:
            raise VehicleRangeReferenceError(
                f"{field} wajib memuat manufacturer dan model_family."
            )
        model_key = (manufacturer.casefold(), model.casefold())
        if model_key in model_keys:
            raise VehicleRangeReferenceError(f"{field} menduplikasi model.")
        model_keys.add(model_key)
        _https_url(vehicle.get("range_source_url"), f"{field}.range_source_url")
        _https_url(
            vehicle.get("connector_source_url"),
            f"{field}.connector_source_url",
        )
        calculated = _representative_value(vehicle, field)
        recorded = _finite_positive(
            vehicle.get("representative_range_km"),
            f"{field}.representative_range_km",
        )
        if not math.isclose(calculated, recorded, abs_tol=1e-9):
            raise VehicleRangeReferenceError(
                f"{field}.representative_range_km tidak sesuai sumber angka."
            )
        representatives.append(recorded)

    calculation = payload.get("calculation")
    if not isinstance(calculation, dict):
        raise VehicleRangeReferenceError("calculation wajib berupa objek.")
    if calculation.get("rounding_rule") != "nearest_10_km_half_up":
        raise VehicleRangeReferenceError("Aturan pembulatan tidak didukung.")
    median = float(statistics.median(representatives))
    rounded = int(math.floor((median + 5) / 10) * 10)
    expected_representatives = [float(value) for value in representatives]
    recorded_representatives = [
        _finite_positive(value, "calculation.representative_ranges_km")
        for value in calculation.get("representative_ranges_km", ())
    ]
    if recorded_representatives != expected_representatives:
        raise VehicleRangeReferenceError(
            "Daftar representative_ranges_km tidak sesuai urutan kendaraan."
        )
    if calculation.get("sample_size") != len(vehicles):
        raise VehicleRangeReferenceError("sample_size tidak sesuai kendaraan.")
    if not math.isclose(
        _finite_positive(calculation.get("median_range_km"), "median_range_km"),
        median,
        abs_tol=1e-9,
    ):
        raise VehicleRangeReferenceError("median_range_km tidak sesuai data.")
    if calculation.get("selected_baseline_maximum_range_km") != rounded:
        raise VehicleRangeReferenceError(
            "Baseline jangkauan tidak sesuai median yang dibulatkan."
        )
    if rounded != REFERENCE_MAXIMUM_RANGE_KM:
        raise VehicleRangeReferenceError(
            "Baseline referensi tidak sama dengan konstanta aplikasi."
        )
    sensitivity_levels = calculation.get("sensitivity_levels_km")
    if (
        not isinstance(sensitivity_levels, list)
        or sensitivity_levels != sorted(set(sensitivity_levels))
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in sensitivity_levels
        )
        or rounded in sensitivity_levels
    ):
        raise VehicleRangeReferenceError(
            "sensitivity_levels_km harus unik, terurut, positif, dan "
            "terpisah dari baseline."
        )
    return {
        "sample_size": len(vehicles),
        "median_range_km": median,
        "selected_baseline_maximum_range_km": rounded,
        "sensitivity_levels_km": tuple(sensitivity_levels),
    }


def load_vehicle_range_reference(path):
    """Membaca dan memvalidasi referensi kendaraan dari JSON."""

    source_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VehicleRangeReferenceError(
            "Referensi kendaraan tidak dapat dibaca."
        ) from error
    return payload, validate_vehicle_range_reference(payload)
