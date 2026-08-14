import json
from pathlib import Path

import pytest

from app.services.release_audit import (
    ReleaseManifestError,
    audit_release,
    load_release_manifest,
    run_release_audit,
)


def test_project_release_manifest_passes_all_checks(app):
    report = run_release_audit(
        app.config["RELEASE_MANIFEST_PATH"],
        app_version=app.config["APP_VERSION"],
        catalog=app.extensions["station_catalog"],
        config=app.config,
    )

    assert report["status"] == "passed"
    assert report["summary"] == {
        "check_count": 21,
        "passed_count": 21,
        "failed_count": 0,
    }
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


def test_release_manifest_rejects_unknown_schema(tmp_path):
    manifest_path = tmp_path / "release_manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 99}),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseManifestError, match="schema_version"):
        load_release_manifest(manifest_path)


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
