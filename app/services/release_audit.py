"""Audit offline terhadap identitas dan batas aman kandidat rilis."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from ..constants import (
    CHARGING_TIME_INCLUDED,
    FALLBACK_RESEARCH_CONNECTOR,
    DETOUR_REFERENCE_MULTIPLIER,
    DETOUR_SENSITIVITY_LEVELS_KM,
    PREFERRED_RESEARCH_CONNECTOR,
    REFERENCE_MAXIMUM_RANGE_KM,
    REFERENCE_MAX_TOTAL_DETOUR_KM,
    RESEARCH_CONNECTORS,
)
from .dataset import CONNECTOR_ORDER, parse_connectors
from .evaluation import ExperimentDefinitionError, load_experiment_definition
from .google_routes import (
    FERRY_MANEUVERS,
    POLYLINE_QUALITY,
    ROUTING_PREFERENCE,
    TRAVEL_MODE,
)
from .graph import GEODESIC_LOWER_BOUND_MARGIN_RATIO
from .vehicle_reference import (
    VehicleRangeReferenceError,
    load_vehicle_range_reference,
)


RELEASE_MANIFEST_SCHEMA_VERSION = 5
RESEARCH_MANIFEST_SCHEMA_VERSION = 1
SOURCE_SCOPE = "application-runtime-v2"
SOURCE_SUFFIXES = frozenset({".py", ".html", ".js", ".css", ".svg"})
SOURCE_ROOT_FILES = (
    "Dockerfile",
    ".dockerignore",
    ".env.example",
    ".github/workflows/ci.yml",
    "gunicorn.conf.py",
    "requirements.txt",
    "run.py",
    "wsgi.py",
)
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


def compute_source_tree_sha256(project_root):
    """Hash stabil source runtime aplikasi untuk identitas rilis."""

    project_root = Path(project_root).expanduser().resolve()
    missing_required_files = [
        relative_path
        for relative_path in SOURCE_ROOT_FILES
        if not (project_root / relative_path).is_file()
    ]
    if missing_required_files:
        raise ReleaseManifestError(
            "Berkas wajib source scope tidak ditemukan: "
            + ", ".join(missing_required_files)
            + "."
        )
    source_paths = [
        path
        for path in (project_root / "app").rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    ]
    source_paths.extend(
        project_root / relative_path
        for relative_path in SOURCE_ROOT_FILES
    )
    source_paths.sort()
    if not source_paths:
        raise ReleaseManifestError("Source Python aplikasi tidak ditemukan.")
    digest = hashlib.sha256()
    for source_path in source_paths:
        relative_path = source_path.relative_to(project_root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_release_manifest(manifest):
    """Memvalidasi schema manifest tanpa membaca dataset atau skenario."""

    manifest = _mapping(manifest, "root")
    if manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA_VERSION:
        raise ReleaseManifestError(
            "schema_version manifest harus bernilai "
            f"{RELEASE_MANIFEST_SCHEMA_VERSION}."
        )
    _text(manifest, "application_version", "root")

    source = _mapping(manifest.get("source"), "root.source")
    if _text(source, "scope", "root.source") != SOURCE_SCOPE:
        raise ReleaseManifestError(
            f"root.source.scope harus bernilai {SOURCE_SCOPE}."
        )
    if not SHA256_PATTERN.fullmatch(_text(source, "sha256", "root.source")):
        raise ReleaseManifestError("root.source.sha256 tidak valid.")

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
    _relative_path(dataset, "metadata_path", "root.dataset")
    if not SHA256_PATTERN.fullmatch(
        _text(dataset, "metadata_sha256", "root.dataset")
    ):
        raise ReleaseManifestError("root.dataset.metadata_sha256 tidak valid.")

    dependencies = _mapping(
        manifest.get("dependencies"),
        "root.dependencies",
    )
    _relative_path(
        dependencies,
        "constraints_path",
        "root.dependencies",
    )
    if not SHA256_PATTERN.fullmatch(
        _text(dependencies, "sha256", "root.dependencies")
    ):
        raise ReleaseManifestError("root.dependencies.sha256 tidak valid.")

    algorithm = _mapping(manifest.get("algorithm"), "root.algorithm")
    supported_connectors = algorithm.get("supported_connectors")
    if (
        not isinstance(supported_connectors, list)
        or not supported_connectors
        or any(
            not isinstance(connector, str) or not connector.strip()
            for connector in supported_connectors
        )
        or len(supported_connectors) != len(set(supported_connectors))
    ):
        raise ReleaseManifestError(
            "root.algorithm.supported_connectors wajib berupa daftar teks unik."
        )
    research_connectors = algorithm.get("research_connectors")
    if (
        not isinstance(research_connectors, list)
        or not research_connectors
        or tuple(research_connectors) != RESEARCH_CONNECTORS
    ):
        raise ReleaseManifestError(
            "root.algorithm.research_connectors tidak sesuai konfigurasi "
            "penelitian."
        )
    _text(algorithm, "preferred_connector", "root.algorithm")
    _text(algorithm, "fallback_connector", "root.algorithm")
    reference_range = algorithm.get("reference_maximum_range_km")
    if (
        isinstance(reference_range, bool)
        or not isinstance(reference_range, (int, float))
        or float(reference_range) <= 0
    ):
        raise ReleaseManifestError(
            "root.algorithm.reference_maximum_range_km tidak valid."
        )
    range_reference = _mapping(
        algorithm.get("range_reference"),
        "root.algorithm.range_reference",
    )
    _relative_path(range_reference, "path", "root.algorithm.range_reference")
    if not SHA256_PATTERN.fullmatch(
        _text(range_reference, "sha256", "root.algorithm.range_reference")
    ):
        raise ReleaseManifestError(
            "root.algorithm.range_reference.sha256 tidak valid."
        )
    detour_policy = _mapping(
        algorithm.get("detour_policy"),
        "root.algorithm.detour_policy",
    )
    if _text(detour_policy, "scope", "root.algorithm.detour_policy") != (
        "total_itinerary"
    ):
        raise ReleaseManifestError(
            "root.algorithm.detour_policy.scope tidak valid."
        )
    if detour_policy.get("reference_max_km") != REFERENCE_MAX_TOTAL_DETOUR_KM:
        raise ReleaseManifestError(
            "root.algorithm.detour_policy.reference_max_km tidak valid."
        )
    if detour_policy.get("corridor_multiplier") != DETOUR_REFERENCE_MULTIPLIER:
        raise ReleaseManifestError(
            "root.algorithm.detour_policy.corridor_multiplier tidak valid."
        )
    if detour_policy.get("sensitivity_levels_km") != list(
        DETOUR_SENSITIVITY_LEVELS_KM
    ):
        raise ReleaseManifestError(
            "root.algorithm.detour_policy.sensitivity_levels_km tidak valid."
        )
    if not isinstance(algorithm.get("charging_time_included"), bool):
        raise ReleaseManifestError(
            "root.algorithm.charging_time_included wajib berupa boolean."
        )
    _text(algorithm, "travel_mode", "root.algorithm")
    _text(algorithm, "routing_preference", "root.algorithm")
    _text(algorithm, "polyline_quality", "root.algorithm")
    ferry_maneuvers = algorithm.get("ferry_maneuvers")
    if (
        not isinstance(ferry_maneuvers, list)
        or not ferry_maneuvers
        or any(not isinstance(item, str) or not item for item in ferry_maneuvers)
        or len(ferry_maneuvers) != len(set(ferry_maneuvers))
    ):
        raise ReleaseManifestError(
            "root.algorithm.ferry_maneuvers wajib berupa daftar teks unik."
        )
    for name in (
        "ferry_distance_consumes_soc",
        "ferry_vehicle_access_guaranteed",
        "ferry_user_control",
    ):
        if not isinstance(algorithm.get(name), bool):
            raise ReleaseManifestError(
                f"root.algorithm.{name} wajib berupa boolean."
            )
    margin = algorithm.get("geodesic_lower_bound_margin_ratio")
    if (
        isinstance(margin, bool)
        or not isinstance(margin, (int, float))
        or not 0 <= float(margin) < 1
    ):
        raise ReleaseManifestError(
            "root.algorithm.geodesic_lower_bound_margin_ratio tidak valid."
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
        connector_sets = experiment.get("connector_sets")
        if (
            not isinstance(connector_sets, list)
            or not connector_sets
            or any(
                not isinstance(connector_set, list) or not connector_set
                for connector_set in connector_sets
            )
        ):
            raise ReleaseManifestError(
                f"{field}.connector_sets wajib berupa daftar konfigurasi."
            )
        detour_levels = experiment.get("max_total_detour_levels_km")
        if (
            not isinstance(detour_levels, list)
            or not detour_levels
            or detour_levels != sorted(set(detour_levels))
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value <= 0
                for value in detour_levels
            )
        ):
            raise ReleaseManifestError(
                f"{field}.max_total_detour_levels_km tidak valid."
            )
        if not SHA256_PATTERN.fullmatch(_text(experiment, "sha256", field)):
            raise ReleaseManifestError(f"{field}.sha256 tidak valid.")

    research_manifest = _mapping(
        manifest.get("research_manifest"),
        "root.research_manifest",
    )
    _relative_path(research_manifest, "path", "root.research_manifest")
    if not SHA256_PATTERN.fullmatch(
        _text(research_manifest, "sha256", "root.research_manifest")
    ):
        raise ReleaseManifestError("root.research_manifest.sha256 tidak valid.")

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


def validate_research_manifest(manifest):
    """Memvalidasi manifest bukti penelitian yang direferensikan rilis."""

    manifest = _mapping(manifest, "research")
    if manifest.get("schema_version") != RESEARCH_MANIFEST_SCHEMA_VERSION:
        raise ReleaseManifestError(
            "schema_version research_manifest harus bernilai "
            f"{RESEARCH_MANIFEST_SCHEMA_VERSION}."
        )

    analysis = _mapping(
        manifest.get("analysis_release"),
        "research.analysis_release",
    )
    _text(analysis, "application_version", "research.analysis_release")
    if (
        _text(analysis, "source_scope", "research.analysis_release")
        != SOURCE_SCOPE
    ):
        raise ReleaseManifestError(
            "research.analysis_release.source_scope tidak valid."
        )
    if not SHA256_PATTERN.fullmatch(
        _text(analysis, "source_sha256", "research.analysis_release")
    ):
        raise ReleaseManifestError(
            "research.analysis_release.source_sha256 tidak valid."
        )

    dataset = _mapping(manifest.get("dataset"), "research.dataset")
    _relative_path(dataset, "path", "research.dataset")
    _relative_path(dataset, "metadata_path", "research.dataset")
    for key in ("sha256", "metadata_sha256"):
        if not SHA256_PATTERN.fullmatch(
            _text(dataset, key, "research.dataset")
        ):
            raise ReleaseManifestError(
                f"research.dataset.{key} tidak valid."
            )
    _positive_integer(dataset, "source_rows", "research.dataset")
    _positive_integer(dataset, "logical_nodes", "research.dataset")
    _text(dataset, "provenance_status", "research.dataset")
    _text(dataset, "license_status", "research.dataset")

    artifacts = manifest.get("tracked_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ReleaseManifestError(
            "research.tracked_artifacts wajib berupa daftar tidak kosong."
        )
    artifact_ids = set()
    for index, artifact in enumerate(artifacts):
        field = f"research.tracked_artifacts[{index}]"
        artifact = _mapping(artifact, field)
        artifact_id = _text(artifact, "id", field)
        if artifact_id in artifact_ids:
            raise ReleaseManifestError(
                f"ID artifact penelitian duplikat: {artifact_id}."
            )
        artifact_ids.add(artifact_id)
        _text(artifact, "kind", field)
        _relative_path(artifact, "path", field)
        if not SHA256_PATTERN.fullmatch(_text(artifact, "sha256", field)):
            raise ReleaseManifestError(f"{field}.sha256 tidak valid.")
        row_count = artifact.get("row_count")
        if row_count is not None and (
            isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count < 0
        ):
            raise ReleaseManifestError(f"{field}.row_count tidak valid.")

    source_runs = manifest.get("source_runs")
    if not isinstance(source_runs, list) or not source_runs:
        raise ReleaseManifestError(
            "research.source_runs wajib berupa daftar tidak kosong."
        )
    source_run_ids = set()
    for index, source_run in enumerate(source_runs):
        field = f"research.source_runs[{index}]"
        source_run = _mapping(source_run, field)
        run_id = _text(source_run, "id", field)
        if run_id in source_run_ids:
            raise ReleaseManifestError(
                f"ID source run penelitian duplikat: {run_id}."
            )
        source_run_ids.add(run_id)
        _relative_path(source_run, "path", field)
        if not SHA256_PATTERN.fullmatch(
            _text(source_run, "sha256", field)
        ):
            raise ReleaseManifestError(f"{field}.sha256 tidak valid.")
        if not SHA256_PATTERN.fullmatch(
            _text(
                source_run,
                "embedded_definition_canonical_sha256",
                field,
            )
        ):
            raise ReleaseManifestError(
                f"{field}.embedded_definition_canonical_sha256 tidak valid."
            )
        _text(source_run, "source_application_version", field)
        _positive_integer(source_run, "report_schema_version", field)
        _text(source_run, "generated_at_utc", field)
        if source_run.get("archive_status") not in {
            "local_untracked",
            "tracked",
            "external_archive",
        }:
            raise ReleaseManifestError(f"{field}.archive_status tidak valid.")

    derivations = manifest.get("derivations")
    if not isinstance(derivations, list) or not derivations:
        raise ReleaseManifestError(
            "research.derivations wajib berupa daftar tidak kosong."
        )
    for index, derivation in enumerate(derivations):
        field = f"research.derivations[{index}]"
        derivation = _mapping(derivation, field)
        artifact_id = _text(derivation, "artifact_id", field)
        source_run_id = _text(derivation, "source_run_id", field)
        transformation_id = _text(
            derivation,
            "transformation_artifact_id",
            field,
        )
        if artifact_id not in artifact_ids:
            raise ReleaseManifestError(f"{field}.artifact_id tidak dikenal.")
        if source_run_id not in source_run_ids:
            raise ReleaseManifestError(
                f"{field}.source_run_id tidak dikenal."
            )
        if transformation_id not in artifact_ids:
            raise ReleaseManifestError(
                f"{field}.transformation_artifact_id tidak dikenal."
            )

    notes = manifest.get("limitations")
    if (
        not isinstance(notes, list)
        or not notes
        or any(not isinstance(note, str) or not note.strip() for note in notes)
    ):
        raise ReleaseManifestError(
            "research.limitations wajib berupa daftar teks tidak kosong."
        )
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
    _add_check(
        checks,
        "source.sha256",
        manifest["source"]["sha256"],
        compute_source_tree_sha256(project_root),
    )
    runtime_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    _add_check(
        checks,
        "python.runtime_supported",
        True,
        runtime_python in manifest["supported_python_versions"],
    )

    dependencies = manifest["dependencies"]
    constraints_path = (
        project_root / dependencies["constraints_path"]
    ).resolve()
    constraints_exists = constraints_path.is_file()
    _add_check(
        checks,
        "dependencies.constraints_exists",
        True,
        constraints_exists,
    )
    actual_constraints_sha256 = (
        hashlib.sha256(constraints_path.read_bytes()).hexdigest()
        if constraints_exists
        else None
    )
    _add_check(
        checks,
        "dependencies.constraints_sha256",
        dependencies["sha256"],
        actual_constraints_sha256,
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
    metadata_path = (project_root / dataset["metadata_path"]).resolve()
    metadata_exists = metadata_path.is_file()
    _add_check(checks, "dataset.metadata_exists", True, metadata_exists)
    metadata_sha256 = (
        hashlib.sha256(metadata_path.read_bytes()).hexdigest()
        if metadata_exists
        else None
    )
    _add_check(
        checks,
        "dataset.metadata_sha256",
        dataset["metadata_sha256"],
        metadata_sha256,
    )
    metadata = {}
    if metadata_exists:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        metadata_dataset = metadata.get("dataset", {})
        _add_check(
            checks,
            "dataset.metadata_dataset_sha256",
            dataset["sha256"],
            metadata_dataset.get("sha256"),
        )
        _add_check(
            checks,
            "dataset.metadata_source_rows",
            dataset["source_rows"],
            metadata_dataset.get("source_rows"),
        )
        _add_check(
            checks,
            "dataset.metadata_logical_nodes",
            dataset["logical_nodes"],
            metadata_dataset.get("logical_nodes"),
        )

    algorithm = manifest["algorithm"]
    _add_check(
        checks,
        "algorithm.supported_connectors",
        algorithm["supported_connectors"],
        list(CONNECTOR_ORDER),
    )
    _add_check(
        checks,
        "algorithm.research_connectors",
        algorithm["research_connectors"],
        list(RESEARCH_CONNECTORS),
    )
    _add_check(
        checks,
        "algorithm.preferred_connector",
        algorithm["preferred_connector"],
        PREFERRED_RESEARCH_CONNECTOR,
    )
    _add_check(
        checks,
        "algorithm.fallback_connector",
        algorithm["fallback_connector"],
        FALLBACK_RESEARCH_CONNECTOR,
    )
    _add_check(
        checks,
        "algorithm.reference_maximum_range_km",
        algorithm["reference_maximum_range_km"],
        REFERENCE_MAXIMUM_RANGE_KM,
    )
    range_reference = algorithm["range_reference"]
    range_reference_path = project_root / range_reference["path"]
    range_reference_exists = range_reference_path.is_file()
    _add_check(
        checks,
        "algorithm.range_reference_exists",
        True,
        range_reference_exists,
    )
    _add_check(
        checks,
        "algorithm.range_reference_sha256",
        range_reference["sha256"],
        (
            hashlib.sha256(range_reference_path.read_bytes()).hexdigest()
            if range_reference_exists
            else None
        ),
    )
    try:
        _, range_summary = load_vehicle_range_reference(range_reference_path)
        range_validation = True
        range_baseline = range_summary[
            "selected_baseline_maximum_range_km"
        ]
    except (OSError, VehicleRangeReferenceError):
        range_validation = False
        range_baseline = None
    _add_check(
        checks,
        "algorithm.range_reference_valid",
        True,
        range_validation,
    )
    _add_check(
        checks,
        "algorithm.range_reference_baseline",
        REFERENCE_MAXIMUM_RANGE_KM,
        range_baseline,
    )
    _add_check(
        checks,
        "algorithm.runtime_default_maximum_range",
        REFERENCE_MAXIMUM_RANGE_KM,
        config.get("DEFAULT_MAXIMUM_RANGE_KM"),
    )
    detour_policy = algorithm["detour_policy"]
    _add_check(
        checks,
        "algorithm.detour_scope",
        "total_itinerary",
        detour_policy["scope"],
    )
    _add_check(
        checks,
        "algorithm.detour_reference_max_km",
        REFERENCE_MAX_TOTAL_DETOUR_KM,
        detour_policy["reference_max_km"],
    )
    _add_check(
        checks,
        "algorithm.detour_corridor_multiplier",
        DETOUR_REFERENCE_MULTIPLIER,
        detour_policy["corridor_multiplier"],
    )
    _add_check(
        checks,
        "algorithm.detour_sensitivity_levels",
        list(DETOUR_SENSITIVITY_LEVELS_KM),
        detour_policy["sensitivity_levels_km"],
    )
    _add_check(
        checks,
        "algorithm.runtime_default_total_detour",
        REFERENCE_MAX_TOTAL_DETOUR_KM,
        config.get("DEFAULT_MAX_TOTAL_DETOUR_KM"),
    )
    _add_check(
        checks,
        "algorithm.runtime_detour_derivation",
        config.get("DEFAULT_CORRIDOR_RADIUS_KM")
        * DETOUR_REFERENCE_MULTIPLIER,
        config.get("DEFAULT_MAX_TOTAL_DETOUR_KM"),
    )
    _add_check(
        checks,
        "algorithm.charging_time_included",
        algorithm["charging_time_included"],
        CHARGING_TIME_INCLUDED,
    )
    _add_check(
        checks,
        "algorithm.travel_mode",
        algorithm["travel_mode"],
        TRAVEL_MODE,
    )
    _add_check(
        checks,
        "algorithm.routing_preference",
        algorithm["routing_preference"],
        ROUTING_PREFERENCE,
    )
    _add_check(
        checks,
        "algorithm.polyline_quality",
        algorithm["polyline_quality"],
        POLYLINE_QUALITY,
    )
    _add_check(
        checks,
        "algorithm.ferry_maneuvers",
        algorithm["ferry_maneuvers"],
        sorted(FERRY_MANEUVERS),
    )
    _add_check(
        checks,
        "algorithm.ferry_distance_consumes_soc",
        algorithm["ferry_distance_consumes_soc"],
        False,
    )
    _add_check(
        checks,
        "algorithm.ferry_vehicle_access_guaranteed",
        algorithm["ferry_vehicle_access_guaranteed"],
        False,
    )
    _add_check(
        checks,
        "algorithm.ferry_user_control",
        algorithm["ferry_user_control"],
        True,
    )
    _add_check(
        checks,
        "algorithm.geodesic_lower_bound_margin_ratio",
        algorithm["geodesic_lower_bound_margin_ratio"],
        GEODESIC_LOWER_BOUND_MARGIN_RATIO,
    )

    for name, expected in sorted(manifest["quota_limits"].items()):
        _add_check(checks, f"quota.{name}", expected, config.get(name))

    all_scenario_ids = []
    for experiment in manifest["experiments"]:
        relative_path = experiment["path"]
        check_prefix = f"experiment.{Path(relative_path).stem}"
        try:
            experiment_path = project_root / relative_path
            definition = load_experiment_definition(experiment_path)
        except (ExperimentDefinitionError, OSError) as error:
            _add_check(checks, f"{check_prefix}.valid", True, str(error))
            continue

        _add_check(checks, f"{check_prefix}.valid", True, True)
        _add_check(
            checks,
            f"{check_prefix}.sha256",
            experiment["sha256"],
            hashlib.sha256(experiment_path.read_bytes()).hexdigest(),
        )
        scenarios = definition["scenarios"]
        _add_check(
            checks,
            f"{check_prefix}.scenario_count",
            experiment["scenario_count"],
            len(scenarios),
        )
        try:
            connector_sets = sorted(
                {
                    parse_connectors(scenario["vehicle"].get("connectors"))
                    for scenario in scenarios
                }
            )
        except (KeyError, ValueError) as error:
            connector_sets = [f"invalid: {error}"]
        _add_check(
            checks,
            f"{check_prefix}.connector_sets",
            sorted(
                parse_connectors(connector_set)
                for connector_set in experiment["connector_sets"]
            ),
            connector_sets,
        )
        detour_levels = sorted(
            {
                float(scenario["options"]["max_total_detour_km"])
                for scenario in scenarios
            }
        )
        _add_check(
            checks,
            f"{check_prefix}.max_total_detour_levels_km",
            [float(value) for value in experiment[
                "max_total_detour_levels_km"
            ]],
            detour_levels,
        )
        all_scenario_ids.extend(scenario["id"] for scenario in scenarios)

    _add_check(
        checks,
        "experiment.scenario_ids_unique",
        len(all_scenario_ids),
        len(set(all_scenario_ids)),
    )
    research_manifest = manifest["research_manifest"]
    research_manifest_path = (
        project_root / research_manifest["path"]
    ).resolve()
    research_manifest_exists = research_manifest_path.is_file()
    _add_check(
        checks,
        "research_manifest.exists",
        True,
        research_manifest_exists,
    )
    _add_check(
        checks,
        "research_manifest.sha256",
        research_manifest["sha256"],
        (
            hashlib.sha256(research_manifest_path.read_bytes()).hexdigest()
            if research_manifest_exists
            else None
        ),
    )
    research = None
    if research_manifest_exists:
        try:
            research = validate_research_manifest(
                json.loads(research_manifest_path.read_text(encoding="utf-8"))
            )
            research_validation_result = True
        except (OSError, json.JSONDecodeError, ReleaseManifestError) as error:
            research_validation_result = str(error)
    else:
        research_validation_result = "research_manifest tidak ditemukan"
    _add_check(
        checks,
        "research_manifest.valid",
        True,
        research_validation_result,
    )
    if research is not None:
        analysis = research["analysis_release"]
        _add_check(
            checks,
            "research.analysis_application_version",
            manifest["application_version"],
            analysis["application_version"],
        )
        _add_check(
            checks,
            "research.analysis_source_sha256",
            manifest["source"]["sha256"],
            analysis["source_sha256"],
        )
        research_dataset = research["dataset"]
        for key in ("path", "sha256", "source_rows", "logical_nodes"):
            _add_check(
                checks,
                f"research.dataset_{key}",
                dataset[key],
                research_dataset[key],
            )
        _add_check(
            checks,
            "research.dataset_metadata_path",
            dataset["metadata_path"],
            research_dataset["metadata_path"],
        )
        _add_check(
            checks,
            "research.dataset_metadata_sha256",
            dataset["metadata_sha256"],
            research_dataset["metadata_sha256"],
        )
        metadata_provenance = metadata.get("provenance", {})
        _add_check(
            checks,
            "research.dataset_provenance_status",
            metadata_provenance.get("provenance_status"),
            research_dataset["provenance_status"],
        )
        _add_check(
            checks,
            "research.dataset_license_status",
            metadata_provenance.get("license_status"),
            research_dataset["license_status"],
        )

        for artifact in research["tracked_artifacts"]:
            artifact_id = artifact["id"]
            artifact_path = (project_root / artifact["path"]).resolve()
            artifact_exists = artifact_path.is_file()
            _add_check(
                checks,
                f"research.artifact.{artifact_id}.exists",
                True,
                artifact_exists,
            )
            _add_check(
                checks,
                f"research.artifact.{artifact_id}.sha256",
                artifact["sha256"],
                (
                    hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                    if artifact_exists
                    else None
                ),
            )
            if "row_count" in artifact:
                actual_row_count = None
                if artifact_exists:
                    with artifact_path.open(
                        encoding="utf-8",
                        newline="",
                    ) as artifact_file:
                        actual_row_count = max(
                            0,
                            sum(1 for _ in csv.reader(artifact_file)) - 1,
                        )
                _add_check(
                    checks,
                    f"research.artifact.{artifact_id}.row_count",
                    artifact["row_count"],
                    actual_row_count,
                )

        for source_run in research["source_runs"]:
            source_id = source_run["id"]
            source_path = (project_root / source_run["path"]).resolve()
            source_exists = source_path.is_file()
            source_optional = source_run["archive_status"] != "tracked"
            _add_check(
                checks,
                f"research.source_run.{source_id}.available_or_declared",
                True,
                source_exists or source_optional,
            )
            source_payload = None
            actual_source_sha = source_run["sha256"] if source_optional else None
            if source_exists:
                actual_source_sha = hashlib.sha256(
                    source_path.read_bytes()
                ).hexdigest()
                try:
                    source_payload = json.loads(
                        source_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    source_payload = {}
            _add_check(
                checks,
                f"research.source_run.{source_id}.sha256_if_available",
                source_run["sha256"],
                actual_source_sha,
            )
            execution = (source_payload or {}).get("execution", {})
            _add_check(
                checks,
                f"research.source_run.{source_id}.schema_if_available",
                source_run["report_schema_version"],
                (
                    (source_payload or {}).get("schema_version")
                    if source_exists
                    else source_run["report_schema_version"]
                ),
            )
            _add_check(
                checks,
                f"research.source_run.{source_id}.version_if_available",
                source_run["source_application_version"],
                (
                    execution.get("app_version")
                    if source_exists
                    else source_run["source_application_version"]
                ),
            )
            _add_check(
                checks,
                f"research.source_run.{source_id}.timestamp_if_available",
                source_run["generated_at_utc"],
                (
                    (source_payload or {}).get("generated_at_utc")
                    if source_exists
                    else source_run["generated_at_utc"]
                ),
            )
            actual_definition_sha = source_run[
                "embedded_definition_canonical_sha256"
            ]
            if source_exists and source_payload:
                definition = source_payload.get("definition")
                if isinstance(definition, dict):
                    canonical_definition = json.dumps(
                        definition,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    actual_definition_sha = hashlib.sha256(
                        canonical_definition
                    ).hexdigest()
                else:
                    actual_definition_sha = None
            _add_check(
                checks,
                f"research.source_run.{source_id}.definition_if_available",
                source_run["embedded_definition_canonical_sha256"],
                actual_definition_sha,
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
