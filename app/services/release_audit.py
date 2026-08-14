"""Audit offline terhadap identitas dan batas aman kandidat rilis."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from ..constants import CHARGING_TIME_INCLUDED, REQUIRED_CONNECTOR
from .dataset import normalize_connector
from .evaluation import ExperimentDefinitionError, load_experiment_definition


RELEASE_MANIFEST_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
QUOTA_LIMIT_NAMES = frozenset(
    {
        "GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT",
        "GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT",
        "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT",
        "GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT",
        "GOOGLE_WEB_MAX_COMPUTE_ROUTES_PER_REQUEST",
        "GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST",
    }
)


class ReleaseManifestError(ValueError):
    """Manifest kandidat rilis tidak sesuai schema yang didukung."""


def _mapping(value, field):
    if not isinstance(value, dict):
        raise ReleaseManifestError(f"{field} harus berupa objek JSON.")
    return value


def _text(mapping, key, field):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReleaseManifestError(f"{field}.{key} wajib berupa teks.")
    return value.strip()


def _positive_integer(mapping, key, field):
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReleaseManifestError(
            f"{field}.{key} wajib berupa integer positif."
        )
    return value


def _relative_path(mapping, key, field):
    raw_path = _text(mapping, key, field)
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise ReleaseManifestError(
            f"{field}.{key} wajib berupa path relatif di dalam proyek."
        )
    return raw_path


def validate_release_manifest(manifest):
    """Memvalidasi schema manifest tanpa membaca dataset atau skenario."""

    manifest = _mapping(manifest, "root")
    if manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA_VERSION:
        raise ReleaseManifestError("schema_version manifest harus bernilai 1.")
    _text(manifest, "application_version", "root")

    python_versions = manifest.get("supported_python_versions")
    if (
        not isinstance(python_versions, list)
        or not python_versions
        or any(
            not isinstance(version, str) or not re.fullmatch(r"3\.\d+", version)
            for version in python_versions
        )
        or len(python_versions) != len(set(python_versions))
    ):
        raise ReleaseManifestError(
            "supported_python_versions wajib berupa daftar versi Python unik."
        )

    dataset = _mapping(manifest.get("dataset"), "root.dataset")
    _relative_path(dataset, "path", "root.dataset")
    _positive_integer(dataset, "source_rows", "root.dataset")
    _positive_integer(dataset, "logical_nodes", "root.dataset")
    if not SHA256_PATTERN.fullmatch(_text(dataset, "sha256", "root.dataset")):
        raise ReleaseManifestError("root.dataset.sha256 tidak valid.")

    algorithm = _mapping(manifest.get("algorithm"), "root.algorithm")
    _text(algorithm, "required_connector", "root.algorithm")
    if not isinstance(algorithm.get("charging_time_included"), bool):
        raise ReleaseManifestError(
            "root.algorithm.charging_time_included wajib berupa boolean."
        )

    experiments = manifest.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        raise ReleaseManifestError(
            "root.experiments wajib berupa daftar yang tidak kosong."
        )
    known_paths = set()
    for index, experiment in enumerate(experiments):
        field = f"root.experiments[{index}]"
        experiment = _mapping(experiment, field)
        path = _relative_path(experiment, "path", field)
        if path in known_paths:
            raise ReleaseManifestError(f"Path eksperimen duplikat: {path}.")
        known_paths.add(path)
        _positive_integer(experiment, "scenario_count", field)

    quota_limits = _mapping(
        manifest.get("quota_limits"),
        "root.quota_limits",
    )
    if set(quota_limits) != QUOTA_LIMIT_NAMES:
        raise ReleaseManifestError(
            "root.quota_limits tidak memuat seluruh batas wajib."
        )
    for name in sorted(QUOTA_LIMIT_NAMES):
        _positive_integer(quota_limits, name, "root.quota_limits")
    return manifest


def load_release_manifest(path):
    """Membaca manifest kandidat rilis dari JSON."""

    source_path = Path(path).expanduser().resolve()
    try:
        with source_path.open(encoding="utf-8") as source_file:
            manifest = json.load(source_file)
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseManifestError(
            "Manifest kandidat rilis tidak dapat dibaca."
        ) from error
    return validate_release_manifest(manifest)


def _add_check(checks, check_id, expected, actual):
    checks.append(
        {
            "id": check_id,
            "passed": actual == expected,
            "expected": expected,
            "actual": actual,
        }
    )


def audit_release(manifest, *, project_root, app_version, catalog, config):
    """Membandingkan source/runtime lokal dengan manifest tanpa API live."""

    validate_release_manifest(manifest)
    project_root = Path(project_root).expanduser().resolve()
    checks = []
    _add_check(
        checks,
        "application.version",
        manifest["application_version"],
        app_version,
    )
    runtime_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    _add_check(
        checks,
        "python.runtime_supported",
        True,
        runtime_python in manifest["supported_python_versions"],
    )

    dataset = manifest["dataset"]
    _add_check(
        checks,
        "dataset.path",
        str((project_root / dataset["path"]).resolve()),
        str(catalog.source_path.resolve()),
    )
    _add_check(
        checks,
        "dataset.source_rows",
        dataset["source_rows"],
        catalog.source_row_count,
    )
    _add_check(
        checks,
        "dataset.logical_nodes",
        dataset["logical_nodes"],
        catalog.logical_node_count,
    )
    _add_check(
        checks,
        "dataset.sha256",
        dataset["sha256"],
        catalog.source_sha256,
    )

    algorithm = manifest["algorithm"]
    _add_check(
        checks,
        "algorithm.required_connector",
        algorithm["required_connector"],
        REQUIRED_CONNECTOR,
    )
    _add_check(
        checks,
        "algorithm.charging_time_included",
        algorithm["charging_time_included"],
        CHARGING_TIME_INCLUDED,
    )

    for name, expected in sorted(manifest["quota_limits"].items()):
        _add_check(checks, f"quota.{name}", expected, config.get(name))

    all_scenario_ids = []
    for experiment in manifest["experiments"]:
        relative_path = experiment["path"]
        check_prefix = f"experiment.{Path(relative_path).stem}"
        try:
            definition = load_experiment_definition(project_root / relative_path)
        except (ExperimentDefinitionError, OSError) as error:
            _add_check(checks, f"{check_prefix}.valid", True, str(error))
            continue

        _add_check(checks, f"{check_prefix}.valid", True, True)
        scenarios = definition["scenarios"]
        _add_check(
            checks,
            f"{check_prefix}.scenario_count",
            experiment["scenario_count"],
            len(scenarios),
        )
        try:
            connectors = sorted(
                {
                    normalize_connector(scenario["vehicle"].get("connector"))
                    for scenario in scenarios
                }
            )
        except (KeyError, ValueError) as error:
            connectors = [f"invalid: {error}"]
        _add_check(
            checks,
            f"{check_prefix}.connectors",
            [algorithm["required_connector"]],
            connectors,
        )
        all_scenario_ids.extend(scenario["id"] for scenario in scenarios)

    _add_check(
        checks,
        "experiment.scenario_ids_unique",
        len(all_scenario_ids),
        len(set(all_scenario_ids)),
    )
    passed_count = sum(check["passed"] for check in checks)
    return {
        "schema_version": RELEASE_MANIFEST_SCHEMA_VERSION,
        "status": "passed" if passed_count == len(checks) else "failed",
        "summary": {
            "check_count": len(checks),
            "passed_count": passed_count,
            "failed_count": len(checks) - passed_count,
        },
        "checks": checks,
    }


def run_release_audit(manifest_path, *, app_version, catalog, config):
    """Memuat manifest lalu menjalankan audit dengan root yang sama."""

    manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = load_release_manifest(manifest_path)
    return audit_release(
        manifest,
        project_root=manifest_path.parent,
        app_version=app_version,
        catalog=catalog,
        config=config,
    )
