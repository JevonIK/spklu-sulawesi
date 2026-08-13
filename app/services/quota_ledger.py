"""Ledger lokal untuk menjaga quota Google Routes lintas eksekusi CLI."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LEDGER_SCHEMA_VERSION = 1


class QuotaLedgerError(RuntimeError):
    """Ledger rusak, tidak konsisten, atau quota tidak mencukupi."""


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} harus berupa integer positif.")
    return value


def _nonnegative_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} harus berupa integer nonnegatif.")
    return value


class GoogleRoutesQuotaLedger:
    """Mencatat penggunaan dan reservasi quota per hari kuota Google."""

    def __init__(
        self,
        path,
        *,
        timezone_name="America/Los_Angeles",
        daily_compute_routes_limit=100,
        daily_matrix_element_limit=2000,
        now_fn=None,
    ):
        self.path = Path(path).expanduser().resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Timezone ledger quota tidak valid.") from error
        self.timezone_name = timezone_name
        self.daily_compute_routes_limit = _positive_integer(
            daily_compute_routes_limit,
            "Batas harian Compute Routes",
        )
        self.daily_matrix_element_limit = _positive_integer(
            daily_matrix_element_limit,
            "Batas harian elemen Route Matrix",
        )
        self.now_fn = now_fn or (
            lambda: datetime.now(timezone.utc).astimezone(self.timezone)
        )

    def _empty(self):
        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "timezone": self.timezone_name,
            "daily_limits": {
                "compute_routes": self.daily_compute_routes_limit,
                "matrix_elements": self.daily_matrix_element_limit,
            },
            "days": {},
        }

    def _validate_metadata(self, data):
        if data.get("schema_version") != LEDGER_SCHEMA_VERSION:
            raise QuotaLedgerError("Versi schema ledger quota tidak didukung.")
        if data.get("timezone") != self.timezone_name:
            raise QuotaLedgerError("Timezone ledger berbeda dari konfigurasi.")
        expected_limits = {
            "compute_routes": self.daily_compute_routes_limit,
            "matrix_elements": self.daily_matrix_element_limit,
        }
        if data.get("daily_limits") != expected_limits:
            raise QuotaLedgerError(
                "Batas harian ledger berbeda dari konfigurasi aplikasi."
            )
        if not isinstance(data.get("days"), dict):
            raise QuotaLedgerError("Struktur hari pada ledger tidak valid.")
        return data

    def _load(self):
        if not self.path.exists():
            return self._empty()
        try:
            with self.path.open(encoding="utf-8") as ledger_file:
                data = json.load(ledger_file)
        except (OSError, json.JSONDecodeError) as error:
            raise QuotaLedgerError("Ledger quota tidak dapat dibaca.") from error
        if not isinstance(data, dict):
            raise QuotaLedgerError("Root ledger quota harus berupa objek.")
        return self._validate_metadata(data)

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(data, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _current_date(self):
        current = self.now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=self.timezone)
        return current.astimezone(self.timezone).date().isoformat()

    @staticmethod
    def _day(data, date_key):
        return data["days"].setdefault(
            date_key,
            {"runs": [], "reservations": {}, "releases": []},
        )

    def _status_from_data(self, data, date_key):
        day = data["days"].get(
            date_key,
            {"runs": [], "reservations": {}},
        )
        runs = day.get("runs", [])
        reservations = day.get("reservations", {})
        actual_compute = sum(
            run["compute_routes_attempt_count"] for run in runs
        )
        actual_matrix = sum(
            run["matrix_element_attempt_count"] for run in runs
        )
        reserved_compute = sum(
            item["maximum_compute_routes"]
            for item in reservations.values()
        )
        reserved_matrix = sum(
            item["maximum_matrix_elements"]
            for item in reservations.values()
        )
        return {
            "date": date_key,
            "timezone": self.timezone_name,
            "daily_compute_routes_limit": self.daily_compute_routes_limit,
            "actual_compute_routes": actual_compute,
            "reserved_compute_routes": reserved_compute,
            "available_compute_routes": max(
                0,
                self.daily_compute_routes_limit
                - actual_compute
                - reserved_compute,
            ),
            "daily_matrix_element_limit": self.daily_matrix_element_limit,
            "actual_matrix_elements": actual_matrix,
            "reserved_matrix_elements": reserved_matrix,
            "available_matrix_elements": max(
                0,
                self.daily_matrix_element_limit
                - actual_matrix
                - reserved_matrix,
            ),
            "completed_or_failed_run_count": len(runs),
            "active_reservation_count": len(reservations),
            "active_reservations": list(reservations.values()),
        }

    def status(self, date_key=None):
        date_key = date_key or self._current_date()
        with self._locked():
            return self._status_from_data(self._load(), date_key)

    def reserve(
        self,
        *,
        label,
        maximum_compute_routes,
        maximum_matrix_elements,
    ):
        maximum_compute_routes = _positive_integer(
            maximum_compute_routes,
            "Reservasi Compute Routes",
        )
        maximum_matrix_elements = _positive_integer(
            maximum_matrix_elements,
            "Reservasi elemen Route Matrix",
        )
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Label reservasi quota wajib diisi.")

        date_key = self._current_date()
        with self._locked():
            data = self._load()
            status = self._status_from_data(data, date_key)
            if status["active_reservation_count"]:
                raise QuotaLedgerError(
                    "Masih ada reservasi quota aktif. Jangan menjalankan "
                    "eksperimen live secara paralel; selesaikan proses atau "
                    "pulihkan reservasi yatim terlebih dahulu."
                )
            if maximum_compute_routes > status["available_compute_routes"]:
                raise QuotaLedgerError(
                    "Sisa quota harian Compute Routes tidak mencukupi: "
                    f"tersedia {status['available_compute_routes']}, "
                    f"diminta {maximum_compute_routes}."
                )
            if maximum_matrix_elements > status["available_matrix_elements"]:
                raise QuotaLedgerError(
                    "Sisa quota harian elemen Route Matrix tidak mencukupi: "
                    f"tersedia {status['available_matrix_elements']}, "
                    f"diminta {maximum_matrix_elements}."
                )

            reservation_id = uuid.uuid4().hex
            reservation = {
                "reservation_id": reservation_id,
                "label": label.strip(),
                "created_at": self.now_fn().isoformat(),
                "date": date_key,
                "maximum_compute_routes": maximum_compute_routes,
                "maximum_matrix_elements": maximum_matrix_elements,
            }
            self._day(data, date_key)["reservations"][reservation_id] = (
                reservation
            )
            self._write(data)
            return reservation

    def finalize(
        self,
        reservation_id,
        *,
        compute_routes_attempt_count,
        matrix_element_attempt_count,
        outcome,
        report_path=None,
    ):
        compute_routes_attempt_count = _nonnegative_integer(
            compute_routes_attempt_count,
            "Pemakaian Compute Routes",
        )
        matrix_element_attempt_count = _nonnegative_integer(
            matrix_element_attempt_count,
            "Pemakaian elemen Route Matrix",
        )
        if outcome not in {"completed", "failed"}:
            raise ValueError("Outcome ledger quota tidak valid.")

        with self._locked():
            data = self._load()
            found = None
            for date_key, day in data["days"].items():
                reservation = day.get("reservations", {}).get(reservation_id)
                if reservation is not None:
                    found = (date_key, day, reservation)
                    break
            if found is None:
                raise QuotaLedgerError("Reservasi quota tidak ditemukan.")
            date_key, day, reservation = found
            if (
                compute_routes_attempt_count
                > reservation["maximum_compute_routes"]
            ):
                raise QuotaLedgerError(
                    "Pemakaian Compute Routes melebihi reservasi."
                )
            if (
                matrix_element_attempt_count
                > reservation["maximum_matrix_elements"]
            ):
                raise QuotaLedgerError(
                    "Pemakaian elemen Route Matrix melebihi reservasi."
                )

            day["reservations"].pop(reservation_id)
            day["runs"].append(
                {
                    "run_id": reservation_id,
                    "label": reservation["label"],
                    "started_at": reservation["created_at"],
                    "finished_at": self.now_fn().isoformat(),
                    "outcome": outcome,
                    "compute_routes_attempt_count": (
                        compute_routes_attempt_count
                    ),
                    "matrix_element_attempt_count": (
                        matrix_element_attempt_count
                    ),
                    "report_path": str(Path(report_path).resolve())
                    if report_path
                    else None,
                    "source_sha256": None,
                }
            )
            self._write(data)
            return self._status_from_data(data, date_key)

    def import_report(self, report_path):
        report_path = Path(report_path).expanduser().resolve()
        raw_bytes = report_path.read_bytes()
        source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        try:
            report = json.loads(raw_bytes)
            execution = report["execution"]
            generated_at = datetime.fromisoformat(report["generated_at_utc"])
            compute_routes = _nonnegative_integer(
                execution["compute_routes_attempt_count"],
                "Compute Routes laporan",
            )
            matrix_elements = _nonnegative_integer(
                execution["matrix_element_attempt_count"],
                "Elemen Matrix laporan",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise QuotaLedgerError(
                "Laporan eksperimen tidak memiliki metadata quota yang valid."
            ) from error
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        date_key = generated_at.astimezone(self.timezone).date().isoformat()

        with self._locked():
            data = self._load()
            for day in data["days"].values():
                for run in day.get("runs", []):
                    if (
                        run.get("source_sha256") == source_sha256
                        or run.get("report_path") == str(report_path)
                    ):
                        return {
                            "imported": False,
                            "duplicate": True,
                            "source_sha256": source_sha256,
                            "status": self._status_from_data(data, date_key),
                        }
            status = self._status_from_data(data, date_key)
            if (
                compute_routes > status["available_compute_routes"]
                or matrix_elements > status["available_matrix_elements"]
            ):
                raise QuotaLedgerError(
                    "Pemakaian laporan melebihi sisa quota harian ledger."
                )
            day = self._day(data, date_key)
            day["runs"].append(
                {
                    "run_id": f"import-{source_sha256[:16]}",
                    "label": report.get("experiment", {}).get(
                        "id",
                        report_path.stem,
                    ),
                    "started_at": None,
                    "finished_at": generated_at.isoformat(),
                    "outcome": "imported",
                    "compute_routes_attempt_count": compute_routes,
                    "matrix_element_attempt_count": matrix_elements,
                    "report_path": str(report_path),
                    "source_sha256": source_sha256,
                }
            )
            self._write(data)
            return {
                "imported": True,
                "duplicate": False,
                "source_sha256": source_sha256,
                "status": self._status_from_data(data, date_key),
            }

    def attach_report(self, run_id, report_path):
        """Menautkan hash laporan final ke run yang sudah difinalisasi."""

        report_path = Path(report_path).expanduser().resolve()
        source_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
        with self._locked():
            data = self._load()
            for day in data["days"].values():
                for run in day.get("runs", []):
                    if run.get("run_id") != run_id:
                        continue
                    run["report_path"] = str(report_path)
                    run["source_sha256"] = source_sha256
                    self._write(data)
                    return source_sha256
        raise QuotaLedgerError("Run quota tidak ditemukan.")

    def recover(
        self,
        reservation_id,
        *,
        compute_routes_attempt_count,
        matrix_element_attempt_count,
        reason,
    ):
        """Memulihkan reservasi yatim sambil tetap mencatat pemakaiannya."""

        compute_routes_attempt_count = _nonnegative_integer(
            compute_routes_attempt_count,
            "Percobaan Compute Routes saat pemulihan",
        )
        matrix_element_attempt_count = _nonnegative_integer(
            matrix_element_attempt_count,
            "Percobaan elemen Route Matrix saat pemulihan",
        )
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Alasan pemulihan reservasi wajib diisi.")
        with self._locked():
            data = self._load()
            for date_key, day in data["days"].items():
                reservation = day.get("reservations", {}).get(
                    reservation_id,
                )
                if reservation is None:
                    continue
                if (
                    compute_routes_attempt_count
                    > reservation["maximum_compute_routes"]
                ):
                    raise QuotaLedgerError(
                        "Percobaan Compute Routes melebihi reservasi."
                    )
                if (
                    matrix_element_attempt_count
                    > reservation["maximum_matrix_elements"]
                ):
                    raise QuotaLedgerError(
                        "Percobaan elemen Route Matrix melebihi reservasi."
                    )

                day["reservations"].pop(reservation_id)
                day["runs"].append(
                    {
                        "run_id": reservation_id,
                        "label": reservation["label"],
                        "started_at": reservation["created_at"],
                        "finished_at": self.now_fn().isoformat(),
                        "outcome": "recovered_failed",
                        "compute_routes_attempt_count": (
                            compute_routes_attempt_count
                        ),
                        "matrix_element_attempt_count": (
                            matrix_element_attempt_count
                        ),
                        "report_path": None,
                        "source_sha256": None,
                        "recovery_reason": reason.strip(),
                    }
                )
                self._write(data)
                return self._status_from_data(data, date_key)
        raise QuotaLedgerError("Reservasi quota tidak ditemukan.")
