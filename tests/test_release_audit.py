import json
from pathlib import Path

import pytest

from app.services.release_audit import (
    ReleaseManifestError,
    audit_release,
    compute_source_tree_sha256,
    load_release_manifest,
    run_release_audit,
    validate_release_manifest,
    validate_research_manifest,
)


def test_project_release_manifest_passes_all_checks(app):
    report = run_release_audit(
        app.config["RELEASE_MANIFEST_PATH"],
        app_version=app.config["APP_VERSION"],
        catalog=app.extensions["station_catalog"],
        config=app.config,
    )

    assert report["status"] == "passed"
    assert report["summary"]["check_count"] >= 50
    assert report["summary"]["passed_count"] == report["summary"][
        "check_count"
    ]
    assert report["summary"]["failed_count"] == 0
    assert all(check["passed"] for check in report["checks"])


def test_release_audit_reports_version_and_quota_mismatch(app):
    manifest_path = Path(app.config["RELEASE_MANIFEST_PATH"])
    manifest = load_release_manifest(manifest_path)
    changed_config = dict(app.config)
    changed_config["GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT"] = 99

    report = audit_release(
        manifest,
        project_root=manifest_path.parent,
        app_version="9.9.9",
        catalog=app.extensions["station_catalog"],
        config=changed_config,
    )

    failed_ids = {
        check["id"] for check in report["checks"] if not check["passed"]
    }
    assert report["status"] == "failed"
    assert report["summary"]["failed_count"] == 2
    assert failed_ids == {
        "application.version",
        "quota.GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT",
    }


def test_release_audit_detects_constraints_hash_mismatch(app):
    manifest_path = Path(app.config["RELEASE_MANIFEST_PATH"])
    manifest = load_release_manifest(manifest_path)
    manifest["dependencies"]["sha256"] = "0" * 64

    report = audit_release(
        manifest,
        project_root=manifest_path.parent,
        app_version=app.config["APP_VERSION"],
        catalog=app.extensions["station_catalog"],
        config=app.config,
    )

    failed = [check for check in report["checks"] if not check["passed"]]
    assert [check["id"] for check in failed] == [
        "dependencies.constraints_sha256"
    ]


def test_release_audit_detects_ferry_energy_policy_mismatch(app):
    manifest_path = Path(app.config["RELEASE_MANIFEST_PATH"])
    manifest = load_release_manifest(manifest_path)
    manifest["algorithm"]["ferry_distance_consumes_soc"] = True

    report = audit_release(
        manifest,
        project_root=manifest_path.parent,
        app_version=app.config["APP_VERSION"],
        catalog=app.extensions["station_catalog"],
        config=app.config,
    )

    failed_ids = [
        check["id"] for check in report["checks"] if not check["passed"]
    ]
    assert failed_ids == ["algorithm.ferry_distance_consumes_soc"]


def test_release_manifest_rejects_unreviewed_detour_policy_change():
    manifest = json.loads(Path("release_manifest.json").read_text())
    manifest["algorithm"]["detour_policy"]["reference_max_km"] = 25

    with pytest.raises(
        ReleaseManifestError,
        match="detour_policy.reference_max_km",
    ):
        validate_release_manifest(manifest)


def test_release_manifest_rejects_missing_connector_preference_policy():
    manifest = json.loads(Path("release_manifest.json").read_text())
    del manifest["algorithm"]["neutral_multi_connector_policy"]

    with pytest.raises(
        ReleaseManifestError,
        match="neutral_multi_connector_policy",
    ):
        validate_release_manifest(manifest)


def test_release_manifest_rejects_missing_experiment_range_levels():
    manifest = json.loads(Path("release_manifest.json").read_text())
    del manifest["experiments"][0]["maximum_range_levels_km"]

    with pytest.raises(
        ReleaseManifestError,
        match="maximum_range_levels_km",
    ):
        validate_release_manifest(manifest)


@pytest.mark.parametrize(
    "relative_path",
    [
        "requirements.txt",
        ".dockerignore",
        ".env.example",
        ".github/workflows/ci.yml",
    ],
)
def test_source_hash_detects_release_and_deployment_input_changes(
    tmp_path,
    relative_path,
):
    required_files = [
        "Dockerfile",
        ".dockerignore",
        ".env.example",
        ".github/workflows/ci.yml",
        "gunicorn.conf.py",
        "requirements.txt",
        "run.py",
        "wsgi.py",
    ]
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text(
        "APP_VERSION = 'test'\n",
        encoding="utf-8",
    )
    for required_path in required_files:
        path = tmp_path / required_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture: {required_path}\n", encoding="utf-8")

    original_hash = compute_source_tree_sha256(tmp_path)
    changed_path = tmp_path / relative_path
    changed_path.write_text(
        changed_path.read_text(encoding="utf-8") + "perubahan\n",
        encoding="utf-8",
    )

    assert compute_source_tree_sha256(tmp_path) != original_hash


def test_source_hash_rejects_missing_required_release_input(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")

    with pytest.raises(
        ReleaseManifestError,
        match="Berkas wajib source scope tidak ditemukan",
    ):
        compute_source_tree_sha256(tmp_path)


def test_docker_context_keeps_v2_integrity_inputs():
    patterns = {
        line.strip()
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".env*" in patterns
    assert "!.env.example" in patterns
    assert ".github" not in patterns
    assert "docs" not in patterns
    assert "docs/*" in patterns
    assert "!docs/parameter_rationale.md" in patterns


def test_container_tmpfs_keeps_runtime_report_directory_accessible():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert (
        "--tmpfs /app/reports/generated:rw,noexec,nosuid,size=16m,mode=1777"
        in workflow
    )


def test_release_manifest_rejects_unknown_schema(tmp_path):
    manifest_path = tmp_path / "release_manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 99}),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseManifestError, match="schema_version"):
        load_release_manifest(manifest_path)


def test_research_manifest_rejects_invalid_artifact_hash():
    manifest = json.loads(Path("research_manifest.json").read_text())
    manifest["tracked_artifacts"][0]["sha256"] = "tidak-valid"

    with pytest.raises(ReleaseManifestError, match="sha256"):
        validate_research_manifest(manifest)


def test_release_audit_cli_outputs_json(app):
    result = app.test_cli_runner().invoke(args=["release-audit"])
    report = json.loads(result.output)

    assert result.exit_code == 0
    assert report["status"] == "passed"
    assert report["summary"]["failed_count"] == 0


def test_release_audit_cli_exits_nonzero_on_mismatch(app):
    app.config["APP_VERSION"] = "9.9.9"

    result = app.test_cli_runner().invoke(args=["release-audit"])

    assert result.exit_code == 1
    assert '"status": "failed"' in result.output
    assert "Audit rilis gagal pada 1 check" in result.output
