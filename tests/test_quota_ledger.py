import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.quota_ledger import (
    GoogleRoutesQuotaLedger,
    QuotaLedgerError,
)


PACIFIC = ZoneInfo("America/Los_Angeles")


class FixedNow:
    def __init__(self, value=None):
        self.value = value or datetime(2026, 8, 12, 20, 0, tzinfo=PACIFIC)

    def __call__(self):
        return self.value


def ledger(tmp_path, **overrides):
    options = {
        "timezone_name": "America/Los_Angeles",
        "daily_compute_routes_limit": 100,
        "daily_matrix_element_limit": 2000,
        "now_fn": FixedNow(),
    }
    options.update(overrides)
    return GoogleRoutesQuotaLedger(tmp_path / "quota.json", **options)


def test_reservation_reduces_available_quota_and_finalize_uses_actual(tmp_path):
    quota = ledger(tmp_path)

    reservation = quota.reserve(
        label="baseline",
        maximum_compute_routes=60,
        maximum_matrix_elements=1200,
    )
    reserved = quota.status()
    finalized = quota.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=9,
        matrix_element_attempt_count=150,
        outcome="completed",
        report_path=tmp_path / "baseline.json",
    )

    assert reserved["available_compute_routes"] == 40
    assert reserved["available_matrix_elements"] == 800
    assert reserved["active_reservation_count"] == 1
    assert finalized["actual_compute_routes"] == 9
    assert finalized["actual_matrix_elements"] == 150
    assert finalized["available_compute_routes"] == 91
    assert finalized["available_matrix_elements"] == 1850
    assert finalized["active_reservation_count"] == 0


def test_parallel_reservation_is_rejected(tmp_path):
    quota = ledger(tmp_path)
    quota.reserve(
        label="run-pertama",
        maximum_compute_routes=80,
        maximum_matrix_elements=1800,
    )

    with pytest.raises(QuotaLedgerError, match="secara paralel"):
        quota.reserve(
            label="run-kedua",
            maximum_compute_routes=1,
            maximum_matrix_elements=1,
        )


def test_reservation_before_midnight_blocks_after_quota_day_reset(tmp_path):
    clock = FixedNow(
        datetime(2026, 8, 12, 23, 59, 50, tzinfo=PACIFIC)
    )
    quota = ledger(tmp_path, now_fn=clock)
    reservation = quota.reserve(
        label="lintas-hari",
        maximum_compute_routes=20,
        maximum_matrix_elements=300,
    )

    clock.value += timedelta(seconds=20)
    current_status = quota.status()

    assert current_status["date"] == "2026-08-13"
    assert current_status["active_reservation_count"] == 1
    assert current_status["reserved_compute_routes"] == 20
    with pytest.raises(QuotaLedgerError, match="secara paralel"):
        quota.reserve(
            label="run-baru",
            maximum_compute_routes=1,
            maximum_matrix_elements=1,
        )

    finalized = quota.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=4,
        matrix_element_attempt_count=30,
        outcome="completed",
    )

    assert finalized["date"] == "2026-08-13"
    assert finalized["actual_compute_routes"] == 4
    assert finalized["actual_matrix_elements"] == 30
    assert finalized["recent_compute_routes"] == 4
    assert finalized["recent_matrix_elements"] == 30
    assert quota.status("2026-08-12")["actual_compute_routes"] == 4


def test_reservation_uses_quota_day_after_waiting_for_lock_across_midnight(
    tmp_path,
):
    before_midnight = datetime(
        2026,
        8,
        12,
        23,
        59,
        59,
        999000,
        tzinfo=PACIFIC,
    )
    after_midnight = datetime(
        2026,
        8,
        13,
        0,
        0,
        0,
        1000,
        tzinfo=PACIFIC,
    )
    seeded = ledger(tmp_path, now_fn=FixedNow(after_midnight))
    seeded_reservation = seeded.reserve(
        label="quota-hari-baru-penuh",
        maximum_compute_routes=100,
        maximum_matrix_elements=2000,
    )
    seeded.finalize(
        seeded_reservation["reservation_id"],
        compute_routes_attempt_count=100,
        matrix_element_attempt_count=2000,
        outcome="completed",
    )

    clock = FixedNow(before_midnight)
    quota = ledger(tmp_path, now_fn=clock)
    original_locked = quota._locked

    @contextmanager
    def lock_crossing_midnight():
        with original_locked():
            clock.value = after_midnight
            yield

    quota._locked = lock_crossing_midnight

    with pytest.raises(QuotaLedgerError, match="quota harian Compute Routes"):
        quota.reserve(
            label="harus-memakai-hari-baru",
            maximum_compute_routes=1,
            maximum_matrix_elements=1,
        )


def test_per_minute_capacity_is_enforced_across_runs(tmp_path):
    clock = FixedNow()
    quota = ledger(
        tmp_path,
        now_fn=clock,
        compute_routes_per_minute_limit=30,
        matrix_elements_per_minute_limit=625,
    )
    reservation = quota.reserve(
        label="request-pertama",
        maximum_compute_routes=2,
        maximum_matrix_elements=625,
        enforce_per_minute_capacity=True,
    )
    quota.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=2,
        matrix_element_attempt_count=105,
        outcome="completed",
    )

    status = quota.status()
    assert status["recent_compute_routes"] == 2
    assert status["recent_matrix_elements"] == 105
    assert status["available_compute_routes_this_minute"] == 28
    assert status["available_matrix_elements_this_minute"] == 520
    with pytest.raises(QuotaLedgerError, match="per menit elemen"):
        quota.reserve(
            label="request-kedua",
            maximum_compute_routes=2,
            maximum_matrix_elements=625,
            enforce_per_minute_capacity=True,
        )
    with pytest.raises(QuotaLedgerError, match="belum bersih"):
        quota.reserve(
            label="eksperimen-cli",
            maximum_compute_routes=14,
            maximum_matrix_elements=1200,
            require_clear_per_minute_window=True,
        )

    clock.value += timedelta(seconds=61)
    next_reservation = quota.reserve(
        label="request-setelah-window",
        maximum_compute_routes=2,
        maximum_matrix_elements=625,
        enforce_per_minute_capacity=True,
    )
    assert next_reservation["label"] == "request-setelah-window"


def test_reservation_is_rejected_before_daily_quota_can_be_exceeded(tmp_path):
    quota = ledger(tmp_path)
    reservation = quota.reserve(
        label="run-pertama",
        maximum_compute_routes=80,
        maximum_matrix_elements=1800,
    )
    quota.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=80,
        matrix_element_attempt_count=1800,
        outcome="completed",
    )

    with pytest.raises(QuotaLedgerError, match="Compute Routes"):
        quota.reserve(
            label="run-kedua",
            maximum_compute_routes=21,
            maximum_matrix_elements=1,
        )
    with pytest.raises(QuotaLedgerError, match="Route Matrix"):
        quota.reserve(
            label="run-ketiga",
            maximum_compute_routes=1,
            maximum_matrix_elements=201,
        )


def test_recover_orphan_reservation_records_possible_usage(tmp_path):
    quota = ledger(tmp_path)
    reservation = quota.reserve(
        label="proses-terhenti",
        maximum_compute_routes=10,
        maximum_matrix_elements=200,
    )

    status = quota.recover(
        reservation["reservation_id"],
        compute_routes_attempt_count=4,
        matrix_element_attempt_count=30,
        reason="terminal ditutup setelah batch pertama",
    )

    assert status["active_reservation_count"] == 0
    assert status["actual_compute_routes"] == 4
    assert status["actual_matrix_elements"] == 30
    assert status["available_compute_routes"] == 96


def test_finalize_rejects_usage_above_reservation(tmp_path):
    quota = ledger(tmp_path)
    reservation = quota.reserve(
        label="terbatas",
        maximum_compute_routes=5,
        maximum_matrix_elements=10,
    )

    with pytest.raises(QuotaLedgerError, match="melebihi reservasi"):
        quota.finalize(
            reservation["reservation_id"],
            compute_routes_attempt_count=6,
            matrix_element_attempt_count=10,
            outcome="failed",
        )

    assert quota.status()["active_reservation_count"] == 1


def test_report_import_is_idempotent_by_sha256(tmp_path):
    quota = ledger(tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-13T02:30:00+00:00",
                "experiment": {"id": "baseline-enam-wilayah"},
                "execution": {
                    "compute_routes_attempt_count": 9,
                    "matrix_element_attempt_count": 150,
                },
            }
        ),
        encoding="utf-8",
    )

    first = quota.import_report(report_path)
    second = quota.import_report(report_path)

    assert first["imported"] is True
    assert second["duplicate"] is True
    assert quota.status()["actual_compute_routes"] == 9
    assert quota.status()["actual_matrix_elements"] == 150


def test_ledger_file_uses_restrictive_permissions(tmp_path):
    quota = ledger(tmp_path)
    quota.reserve(
        label="permission-test",
        maximum_compute_routes=1,
        maximum_matrix_elements=1,
    )

    assert quota.path.stat().st_mode & 0o777 == 0o600
    assert quota.lock_path.stat().st_mode & 0o777 == 0o600


def test_schema_one_ledger_is_upgraded_on_next_write(tmp_path):
    quota = ledger(tmp_path)
    quota.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timezone": "America/Los_Angeles",
                "daily_limits": {
                    "compute_routes": 100,
                    "matrix_elements": 2000,
                },
                "days": {},
            }
        ),
        encoding="utf-8",
    )

    reservation = quota.reserve(
        label="migrasi",
        maximum_compute_routes=1,
        maximum_matrix_elements=1,
    )

    upgraded = json.loads(quota.path.read_text())
    assert reservation["label"] == "migrasi"
    assert upgraded["schema_version"] == 3
    assert upgraded["per_minute_limits"] == {
        "compute_routes": 100,
        "matrix_elements": 2000,
    }


def test_schema_two_ledger_keeps_usage_when_rate_limits_change(tmp_path):
    quota = ledger(tmp_path)
    quota.path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "timezone": "America/Los_Angeles",
                "daily_limits": {
                    "compute_routes": 100,
                    "matrix_elements": 2000,
                },
                "per_minute_limits": {
                    "compute_routes": 30,
                    "matrix_elements": 625,
                },
                "days": {
                    "2026-08-12": {
                        "runs": [
                            {
                                "compute_routes_attempt_count": 9,
                                "matrix_element_attempt_count": 150,
                                "finished_at": "2026-08-12T18:00:00-07:00",
                            }
                        ],
                        "reservations": {},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = quota.status("2026-08-12")
    quota.reserve(
        label="migrasi-v2",
        maximum_compute_routes=1,
        maximum_matrix_elements=1,
    )

    upgraded = json.loads(quota.path.read_text())
    assert status["actual_compute_routes"] == 9
    assert status["actual_matrix_elements"] == 150
    assert upgraded["schema_version"] == 3
    assert upgraded["per_minute_limits"] == {
        "compute_routes": 100,
        "matrix_elements": 2000,
    }


def test_legacy_runs_without_ids_are_counted_separately_in_rolling_window(
    tmp_path,
):
    clock = FixedNow(
        datetime(2026, 8, 12, 20, 0, 30, tzinfo=PACIFIC)
    )
    quota = ledger(tmp_path, now_fn=clock)
    quota.path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "timezone": "America/Los_Angeles",
                "daily_limits": {
                    "compute_routes": 100,
                    "matrix_elements": 2000,
                },
                "per_minute_limits": {
                    "compute_routes": 30,
                    "matrix_elements": 625,
                },
                "days": {
                    "2026-08-12": {
                        "runs": [
                            {
                                "compute_routes_attempt_count": 1,
                                "matrix_element_attempt_count": 10,
                                "finished_at": (
                                    "2026-08-12T20:00:05-07:00"
                                ),
                            },
                            {
                                "compute_routes_attempt_count": 1,
                                "matrix_element_attempt_count": 10,
                                "finished_at": (
                                    "2026-08-12T20:00:10-07:00"
                                ),
                            },
                        ],
                        "reservations": {},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = quota.status()

    assert status["actual_compute_routes"] == 2
    assert status["recent_compute_routes"] == 2
    assert status["actual_matrix_elements"] == 20
    assert status["recent_matrix_elements"] == 20


def test_report_import_rejects_fractional_usage(tmp_path):
    quota = ledger(tmp_path)
    report_path = tmp_path / "invalid-usage.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-13T02:30:00+00:00",
                "execution": {
                    "compute_routes_attempt_count": 1.5,
                    "matrix_element_attempt_count": 10,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(QuotaLedgerError, match="metadata quota"):
        quota.import_report(report_path)


def test_final_report_hash_prevents_later_double_import(tmp_path):
    quota = ledger(tmp_path)
    report_path = tmp_path / "automatic.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-13T02:30:00+00:00",
                "execution": {
                    "compute_routes_attempt_count": 2,
                    "matrix_element_attempt_count": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    reservation = quota.reserve(
        label="automatic",
        maximum_compute_routes=5,
        maximum_matrix_elements=20,
    )
    quota.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=2,
        matrix_element_attempt_count=10,
        outcome="completed",
        report_path=report_path,
    )

    attached_hash = quota.attach_report(
        reservation["reservation_id"],
        report_path,
    )
    imported = quota.import_report(report_path)

    assert imported["duplicate"] is True
    assert imported["source_sha256"] == attached_hash
    assert quota.status()["actual_compute_routes"] == 2


def test_quota_cli_import_and_status_are_auditable(app, tmp_path):
    app.config["GOOGLE_QUOTA_LEDGER_PATH"] = tmp_path / "cli-quota.json"
    report_path = tmp_path / "historic.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-13T02:30:00+00:00",
                "experiment": {"id": "historic"},
                "execution": {
                    "compute_routes_attempt_count": 9,
                    "matrix_element_attempt_count": 150,
                },
            }
        ),
        encoding="utf-8",
    )
    runner = app.test_cli_runner()

    imported = runner.invoke(
        args=["quota-import-report", "--report", str(report_path)]
    )
    status = runner.invoke(args=["quota-status", "--date", "2026-08-12"])

    assert imported.exit_code == 0
    assert json.loads(imported.output)[0]["imported"] is True
    assert status.exit_code == 0
    payload = json.loads(status.output)
    assert payload["actual_compute_routes"] == 9
    assert payload["actual_matrix_elements"] == 150
    assert payload["available_compute_routes"] == 91


def test_quota_recover_cli_requires_confirmation_and_records_attempts(
    app,
    tmp_path,
):
    ledger_path = tmp_path / "recover-cli.json"
    app.config["GOOGLE_QUOTA_LEDGER_PATH"] = ledger_path
    quota = GoogleRoutesQuotaLedger(
        ledger_path,
        timezone_name=app.config["GOOGLE_QUOTA_TIMEZONE"],
        daily_compute_routes_limit=app.config[
            "GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT"
        ],
        daily_matrix_element_limit=app.config[
            "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT"
        ],
    )
    reservation = quota.reserve(
        label="cli-terhenti",
        maximum_compute_routes=10,
        maximum_matrix_elements=100,
    )
    command = [
        "quota-recover",
        "--reservation",
        reservation["reservation_id"],
        "--compute-routes-attempts",
        "3",
        "--matrix-element-attempts",
        "20",
        "--reason",
        "proses terminal berhenti",
    ]
    runner = app.test_cli_runner()

    rejected = runner.invoke(args=command)
    assert rejected.exit_code == 2
    assert quota.status()["active_reservation_count"] == 1

    recovered = runner.invoke(
        args=[*command, "--confirm-process-stopped"]
    )

    assert quota.status()["active_reservation_count"] == 0
    assert recovered.exit_code == 0
    payload = json.loads(recovered.output)
    assert payload["actual_compute_routes"] == 3
    assert payload["actual_matrix_elements"] == 20
