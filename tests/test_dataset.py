from pathlib import Path

import pytest

from app.config import BASE_DIR
from app.services.dataset import (
    DatasetValidationError,
    infer_charging_network,
    load_station_catalog,
    node_is_eligible,
    parse_additional_charging_networks,
    parse_connectors,
)


CSV_HEADER = (
    "Provinsi,Kota/Kabupaten,Lokasi SPKLU,Alamat,Latitude,Longitude,"
    "google maps,Jenis Konektor\n"
)
EXPECTED_DATASET_SHA256 = (
    "24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85"
)


def write_dataset(path: Path, rows: str):
    path.write_text(CSV_HEADER + rows, encoding="utf-8")
    return path


def test_connector_normalization():
    assert parse_connectors("ccs 2, CHAdeMO, g/bt, CCS2") == (
        "CCS2",
        "CHADEMO",
        "GB/T",
    )


def test_connector_parser_accepts_checkbox_style_list():
    assert parse_connectors(["GB/T", "ccs 2", "GB/T"]) == (
        "CCS2",
        "GB/T",
    )


def test_additional_network_parser_accepts_multiple_dealer_networks():
    assert parse_additional_charging_networks(
        ["Wuling", "Toyota/Lexus", "WULING"]
    ) == ("WULING", "TOYOTA")


def test_public_network_cannot_be_selected_as_additional_network():
    with pytest.raises(ValueError, match="selalu disertakan"):
        parse_additional_charging_networks(["PUBLIC"])


@pytest.mark.parametrize(
    "name, expected",
    [
        ("(HYUNDAI) Manado", "HYUNDAI"),
        ("(WULING) Kumala Manado", "WULING"),
        ("Kalla Toyota Kendari", "TOYOTA"),
        ("(BLUECHARGE) WISMA KALLA MAKASSAR", "PUBLIC"),
        ("SPKLU PLN ULP Uji", "PUBLIC"),
    ],
)
def test_charging_network_is_inferred_from_explicit_station_name(
    name, expected
):
    assert infer_charging_network(name) == expected


def test_real_dataset_is_valid_and_consolidates_multi_unit_location():
    catalog = load_station_catalog(BASE_DIR / "dataset_spklu_sulawesi.csv")

    assert catalog.source_row_count == 150
    assert catalog.logical_node_count == 149
    assert len(catalog.multi_unit_nodes) == 1
    assert catalog.source_sha256 == EXPECTED_DATASET_SHA256
    assert catalog.summary()["source_sha256"] == EXPECTED_DATASET_SHA256

    bolmut = catalog.multi_unit_nodes[0]
    assert bolmut.name == "SPKLU PLN KANTOR ULP BOLMUT"
    assert bolmut.unit_count == 2
    assert {unit.name for unit in bolmut.units} == {
        "SPKLU PLN KANTOR ULP BOLMUT 1",
        "SPKLU PLN KANTOR ULP BOLMUT 2",
    }
    assert bolmut.connectors == ("AC TYPE 2",)

    summary = catalog.summary()
    assert summary["network_node_counts"] == {
        "PUBLIC": 117,
        "HYUNDAI": 8,
        "WULING": 17,
        "TOYOTA": 7,
    }


def test_dealer_network_and_connector_must_both_match_same_unit():
    catalog = load_station_catalog(BASE_DIR / "dataset_spklu_sulawesi.csv")
    wuling = next(
        node for node in catalog.nodes if "WULING" in node.charging_networks
    )

    assert node_is_eligible(wuling, ("CCS2",), ("WULING",)) is False
    assert node_is_eligible(wuling, ("GB/T",), ()) is False
    assert node_is_eligible(wuling, ("GB/T",), ("WULING",)) is True


def test_unknown_connector_is_rejected(tmp_path):
    dataset = write_dataset(
        tmp_path / "unknown_connector.csv",
        "Sulawesi Selatan,Makassar,SPKLU Uji,Alamat Uji,-5.1,119.4,"
        "https://maps.app.goo.gl/uji,KONEKTOR BARU\n",
    )

    with pytest.raises(DatasetValidationError, match="jenis konektor tidak dikenal"):
        load_station_catalog(dataset)


def test_coordinate_outside_sulawesi_is_rejected(tmp_path):
    dataset = write_dataset(
        tmp_path / "outside_bounds.csv",
        "Sulawesi Selatan,Makassar,SPKLU Uji,Alamat Uji,-8.0,119.4,"
        "https://maps.app.goo.gl/uji,CCS2\n",
    )

    with pytest.raises(DatasetValidationError, match="di luar batas Sulawesi"):
        load_station_catalog(dataset)


def test_missing_required_column_is_rejected(tmp_path):
    dataset = tmp_path / "missing_column.csv"
    dataset.write_text(
        "Provinsi,Lokasi SPKLU,Latitude,Longitude\n"
        "Sulawesi Selatan,SPKLU Uji,-5.1,119.4\n",
        encoding="utf-8",
    )

    with pytest.raises(DatasetValidationError, match="Kolom wajib tidak ditemukan"):
        load_station_catalog(dataset)


def test_non_google_maps_url_is_rejected(tmp_path):
    dataset = write_dataset(
        tmp_path / "invalid_maps_url.csv",
        "Sulawesi Selatan,Makassar,SPKLU Uji,Alamat Uji,-5.1,119.4,"
        "https://example.com/uji,CCS2\n",
    )

    with pytest.raises(DatasetValidationError, match="Google Maps tidak valid"):
        load_station_catalog(dataset)


def test_unknown_province_is_rejected(tmp_path):
    dataset = write_dataset(
        tmp_path / "unknown_province.csv",
        "Sulawesi Timur,Makassar,SPKLU Uji,Alamat Uji,-5.1,119.4,"
        "https://maps.app.goo.gl/uji,CCS2\n",
    )

    with pytest.raises(DatasetValidationError, match="Provinsi .* tidak dikenal"):
        load_station_catalog(dataset)
