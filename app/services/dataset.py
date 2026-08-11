"""Validasi, normalisasi, dan konsolidasi dataset SPKLU Sulawesi."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


REQUIRED_COLUMNS = {
    "Provinsi": "province",
    "Kota/Kabupaten": "city",
    "Lokasi SPKLU": "name",
    "Alamat": "address",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "google maps": "maps_url",
    "Jenis Konektor": "connectors",
}

CONNECTOR_ORDER = ("AC TYPE 2", "CCS2", "CHADEMO", "GB/T")
CONNECTOR_ALIASES = {
    "ACTYPE2": "AC TYPE 2",
    "TYPE2": "AC TYPE 2",
    "CCS2": "CCS2",
    "CCSTYPE2": "CCS2",
    "CHADEMO": "CHADEMO",
    "GBT": "GB/T",
}
EXPECTED_PROVINCES = {
    "Gorontalo",
    "Sulawesi Barat",
    "Sulawesi Selatan",
    "Sulawesi Tengah",
    "Sulawesi Tenggara",
    "Sulawesi Utara",
}

# Batas persegi panjang konservatif untuk pemeriksaan awal koordinat Sulawesi.
SULAWESI_LATITUDE_RANGE = (-7.0, 3.0)
SULAWESI_LONGITUDE_RANGE = (118.0, 126.5)
COORDINATE_GROUP_PRECISION = 6


class DatasetValidationError(ValueError):
    """Menandakan satu atau lebih masalah pada dataset sumber."""

    def __init__(self, issues):
        self.issues = tuple(issues)
        message = "Dataset SPKLU tidak valid:\n- " + "\n- ".join(self.issues)
        super().__init__(message)


@dataclass(frozen=True)
class StationUnit:
    """Satu baris/unit charger yang dipertahankan dari dataset sumber."""

    source_row: int
    province: str
    city: str
    name: str
    address: str
    latitude: float
    longitude: float
    maps_url: str
    connectors: tuple[str, ...]

    def to_dict(self):
        return {
            "source_row": self.source_row,
            "name": self.name,
            "address": self.address,
            "maps_url": self.maps_url,
            "connectors": list(self.connectors),
        }


@dataclass(frozen=True)
class StationNode:
    """Satu lokasi logis yang dapat memiliki lebih dari satu unit charger."""

    node_id: str
    name: str
    province: str
    city: str
    address: str
    latitude: float
    longitude: float
    maps_url: str
    connectors: tuple[str, ...]
    units: tuple[StationUnit, ...]

    @property
    def unit_count(self):
        return len(self.units)

    def to_dict(self, include_units=True):
        payload = {
            "id": self.node_id,
            "name": self.name,
            "province": self.province,
            "city": self.city,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "maps_url": self.maps_url,
            "connectors": list(self.connectors),
            "unit_count": self.unit_count,
        }
        if include_units:
            payload["units"] = [unit.to_dict() for unit in self.units]
        return payload


@dataclass(frozen=True)
class StationCatalog:
    """Hasil pemrosesan dataset yang siap digunakan modul spasial."""

    source_path: Path
    source_columns: tuple[str, ...]
    units: tuple[StationUnit, ...]
    nodes: tuple[StationNode, ...]
    warnings: tuple[str, ...]

    @property
    def source_row_count(self):
        return len(self.units)

    @property
    def logical_node_count(self):
        return len(self.nodes)

    @property
    def multi_unit_nodes(self):
        return tuple(node for node in self.nodes if node.unit_count > 1)

    def summary(self):
        province_counts = Counter(node.province for node in self.nodes)
        connector_node_counts = Counter()
        connector_unit_counts = Counter()

        for node in self.nodes:
            connector_node_counts.update(node.connectors)
        for unit in self.units:
            connector_unit_counts.update(unit.connectors)

        return {
            "source_filename": self.source_path.name,
            "source_rows": self.source_row_count,
            "logical_nodes": self.logical_node_count,
            "multi_unit_node_count": len(self.multi_unit_nodes),
            "province_counts": dict(sorted(province_counts.items())),
            "connector_node_counts": {
                connector: connector_node_counts[connector]
                for connector in CONNECTOR_ORDER
            },
            "connector_unit_counts": {
                connector: connector_unit_counts[connector]
                for connector in CONNECTOR_ORDER
            },
            "multi_unit_nodes": [
                node.to_dict(include_units=True) for node in self.multi_unit_nodes
            ],
            "warnings": list(self.warnings),
        }


def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def _connector_key(value):
    return re.sub(r"[^A-Z0-9]", "", _normalize_text(value).upper())


def normalize_connector(value):
    """Mengubah variasi penulisan konektor menjadi label kanonis."""

    normalized = CONNECTOR_ALIASES.get(_connector_key(value))
    if normalized is None:
        raise ValueError(f"jenis konektor tidak dikenal: {value!r}")
    return normalized


def parse_connectors(value):
    """Memecah daftar konektor dan mengembalikan tuple unik terurut."""

    parts = [part for part in re.split(r"[,;|]+", str(value)) if part.strip()]
    if not parts:
        raise ValueError("jenis konektor kosong")

    normalized = {normalize_connector(part) for part in parts}
    return tuple(connector for connector in CONNECTOR_ORDER if connector in normalized)


def _is_valid_maps_url(value):
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    is_google_maps_host = (
        hostname == "maps.app.goo.gl"
        or hostname == "goo.gl"
        or hostname == "google.com"
        or hostname.endswith(".google.com")
    )
    return parsed.scheme == "https" and is_google_maps_host


def _parse_coordinate(value, label, csv_row, issues):
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        issues.append(f"Baris {csv_row}: {label} harus berupa angka.")
        return None

    if not math.isfinite(coordinate):
        issues.append(f"Baris {csv_row}: {label} harus berupa angka finite.")
        return None
    return coordinate


def _node_name(units):
    names = [unit.name for unit in units]
    bases = [re.sub(r"\s+\d+$", "", name).strip() for name in names]
    if len(units) > 1 and len({base.casefold() for base in bases}) == 1:
        return bases[0]
    return names[0]


def _node_id(latitude, longitude):
    coordinate_key = f"{latitude:.6f},{longitude:.6f}".encode("utf-8")
    digest = hashlib.sha1(coordinate_key).hexdigest()[:10]
    return f"spklu-{digest}"


def _build_nodes(units):
    grouped_units = {}
    for unit in units:
        key = (
            round(unit.latitude, COORDINATE_GROUP_PRECISION),
            round(unit.longitude, COORDINATE_GROUP_PRECISION),
        )
        grouped_units.setdefault(key, []).append(unit)

    nodes = []
    warnings = []
    for grouped in grouped_units.values():
        first = grouped[0]
        connector_set = {
            connector for unit in grouped for connector in unit.connectors
        }
        connectors = tuple(
            connector for connector in CONNECTOR_ORDER if connector in connector_set
        )

        if len(grouped) > 1:
            warnings.append(
                f"{len(grouped)} unit pada koordinat "
                f"{first.latitude:.6f}, {first.longitude:.6f} "
                f"dikonsolidasikan menjadi node '{_node_name(grouped)}'."
            )

        nodes.append(
            StationNode(
                node_id=_node_id(first.latitude, first.longitude),
                name=_node_name(grouped),
                province=first.province,
                city=first.city,
                address=first.address,
                latitude=first.latitude,
                longitude=first.longitude,
                maps_url=first.maps_url,
                connectors=connectors,
                units=tuple(grouped),
            )
        )

    return tuple(nodes), tuple(warnings)


def load_station_catalog(dataset_path):
    """Membaca CSV, memvalidasi seluruh baris, lalu membentuk node lokasi."""

    path = Path(dataset_path).expanduser().resolve()
    if not path.is_file():
        raise DatasetValidationError([f"Berkas tidak ditemukan: {path}"])

    try:
        source = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise DatasetValidationError([f"CSV tidak dapat dibaca: {exc}"]) from exc

    source.columns = [_normalize_text(column) for column in source.columns]
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in source.columns
    ]
    if missing_columns:
        raise DatasetValidationError(
            ["Kolom wajib tidak ditemukan: " + ", ".join(missing_columns)]
        )

    issues = []
    units = []
    for row_index, row in source.iterrows():
        csv_row = int(row_index) + 2
        values = {
            internal: _normalize_text(row[source_column])
            for source_column, internal in REQUIRED_COLUMNS.items()
        }

        missing_values = [
            source_column
            for source_column, internal in REQUIRED_COLUMNS.items()
            if not values[internal]
        ]
        if missing_values:
            issues.append(
                f"Baris {csv_row}: nilai kosong pada "
                + ", ".join(missing_values)
                + "."
            )
            continue

        latitude = _parse_coordinate(
            values["latitude"], "Latitude", csv_row, issues
        )
        longitude = _parse_coordinate(
            values["longitude"], "Longitude", csv_row, issues
        )
        if latitude is None or longitude is None:
            continue

        if not (
            SULAWESI_LATITUDE_RANGE[0]
            <= latitude
            <= SULAWESI_LATITUDE_RANGE[1]
        ):
            issues.append(
                f"Baris {csv_row}: Latitude {latitude} berada di luar batas Sulawesi."
            )
        if not (
            SULAWESI_LONGITUDE_RANGE[0]
            <= longitude
            <= SULAWESI_LONGITUDE_RANGE[1]
        ):
            issues.append(
                f"Baris {csv_row}: Longitude {longitude} berada di luar batas Sulawesi."
            )

        if values["province"] not in EXPECTED_PROVINCES:
            issues.append(
                f"Baris {csv_row}: Provinsi {values['province']!r} tidak dikenal."
            )

        if not _is_valid_maps_url(values["maps_url"]):
            issues.append(f"Baris {csv_row}: tautan Google Maps tidak valid.")

        try:
            connectors = parse_connectors(values["connectors"])
        except ValueError as exc:
            issues.append(f"Baris {csv_row}: {exc}.")
            continue

        units.append(
            StationUnit(
                source_row=csv_row,
                province=values["province"],
                city=values["city"],
                name=values["name"],
                address=values["address"],
                latitude=latitude,
                longitude=longitude,
                maps_url=values["maps_url"],
                connectors=connectors,
            )
        )

    if issues:
        raise DatasetValidationError(issues)
    if not units:
        raise DatasetValidationError(["Dataset tidak memiliki baris data."])

    nodes, warnings = _build_nodes(units)
    return StationCatalog(
        source_path=path,
        source_columns=tuple(source.columns),
        units=tuple(units),
        nodes=nodes,
        warnings=warnings,
    )
