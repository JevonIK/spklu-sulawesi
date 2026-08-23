import copy
import json
from pathlib import Path

import pytest

from app.services.vehicle_reference import (
    VehicleRangeReferenceError,
    load_vehicle_range_reference,
    validate_vehicle_range_reference,
)


REFERENCE_PATH = Path("research/vehicle_range_reference.json")


def reference_payload():
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def test_vehicle_reference_recomputes_scientific_baseline():
    payload, summary = load_vehicle_range_reference(REFERENCE_PATH)

    assert len(payload["vehicles"]) == 7
    assert summary == {
        "sample_size": 7,
        "median_range_km": 433.0,
        "selected_baseline_maximum_range_km": 430,
        "sensitivity_levels_km": (200, 300, 400, 500),
    }


@pytest.mark.parametrize(
    "mutator, message",
    [
        (
            lambda payload: payload["vehicles"][0].update(
                {"representative_range_km": 999}
            ),
            "tidak sesuai sumber angka",
        ),
        (
            lambda payload: payload["calculation"].update(
                {"median_range_km": 300}
            ),
            "median_range_km tidak sesuai",
        ),
        (
            lambda payload: payload["calculation"].update(
                {"selected_baseline_maximum_range_km": 300}
            ),
            "Baseline jangkauan tidak sesuai",
        ),
        (
            lambda payload: payload["scope"].update(
                {"range_standard": "NEDC"}
            ),
            "wajib memakai WLTP",
        ),
    ],
)
def test_vehicle_reference_rejects_untraceable_numbers(mutator, message):
    payload = copy.deepcopy(reference_payload())
    mutator(payload)

    with pytest.raises(VehicleRangeReferenceError, match=message):
        validate_vehicle_range_reference(payload)


@pytest.mark.parametrize(
    "mutator, message",
    [
        (
            lambda payload: payload.update({"schema_version": 99}),
            "schema_version",
        ),
        (
            lambda payload: payload.update({"scope": None}),
            "scope wajib",
        ),
        (
            lambda payload: payload["scope"].update(
                {"required_connectors": ["CCS2"]}
            ),
            "required_connectors",
        ),
        (
            lambda payload: payload.update(
                {"vehicles": payload["vehicles"][:4]}
            ),
            "sedikitnya lima",
        ),
        (
            lambda payload: payload["vehicles"][1].update(
                {
                    "manufacturer": payload["vehicles"][0]["manufacturer"],
                    "model_family": payload["vehicles"][0]["model_family"],
                }
            ),
            "menduplikasi model",
        ),
        (
            lambda payload: payload["vehicles"][0].update(
                {"range_source_url": "http://tidak-aman.example"}
            ),
            "URL HTTPS",
        ),
        (
            lambda payload: payload["vehicles"][0].update(
                {"wltp_range_values_km": []}
            ),
            "daftar tidak kosong",
        ),
        (
            lambda payload: payload["vehicles"][0].update(
                {"representative_rule": "random"}
            ),
            "tidak dikenal",
        ),
        (
            lambda payload: payload["calculation"].update(
                {"sensitivity_levels_km": [300, 200]}
            ),
            "sensitivity_levels_km",
        ),
    ],
)
def test_vehicle_reference_rejects_invalid_contract(mutator, message):
    payload = copy.deepcopy(reference_payload())
    mutator(payload)

    with pytest.raises(VehicleRangeReferenceError, match=message):
        validate_vehicle_range_reference(payload)
