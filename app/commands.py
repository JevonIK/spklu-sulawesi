"""Perintah CLI untuk audit data dan eksperimen penelitian."""

import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext

from .services.evaluation import (
    ExperimentDefinitionError,
    experiment_report_paths,
    load_experiment_definition,
    run_experiment,
    write_experiment_report,
)
from .services.quota_ledger import GoogleRoutesQuotaLedger, QuotaLedgerError
from .services.release_audit import (
    ReleaseManifestError,
    SOURCE_SCOPE,
    compute_source_tree_sha256,
    run_release_audit,
)
from .services.graph import GEODESIC_LOWER_BOUND_MARGIN_RATIO
from .services.google_routes import (
    FERRY_MANEUVERS,
    POLYLINE_QUALITY,
    ROUTING_PREFERENCE,
    TRAVEL_MODE,
)


def _quota_ledger():
    return GoogleRoutesQuotaLedger(
        current_app.config["GOOGLE_QUOTA_LEDGER_PATH"],
        timezone_name=current_app.config["GOOGLE_QUOTA_TIMEZONE"],
        daily_compute_routes_limit=current_app.config[
            "GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT"
        ],
        daily_matrix_element_limit=current_app.config[
            "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT"
        ],
        compute_routes_per_minute_limit=current_app.config[
            "GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT"
        ],
        matrix_elements_per_minute_limit=current_app.config[
            "GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT"
        ],
    )


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _experiment_provenance(scenarios, service):
    """Merekam identitas run tanpa API key atau path home pengguna."""

    catalog = current_app.extensions["station_catalog"]
    release_manifest_path = Path(
        current_app.config["RELEASE_MANIFEST_PATH"]
    ).resolve()
    project_root = release_manifest_path.parent
    release_manifest = json.loads(
        release_manifest_path.read_text(encoding="utf-8")
    )
    constraints_path = project_root / release_manifest["dependencies"][
        "constraints_path"
    ]
    research_manifest_path = project_root / release_manifest[
        "research_manifest"
    ]["path"]
    dataset_metadata_path = project_root / release_manifest["dataset"][
        "metadata_path"
    ]
    return {
        "schema_version": 1,
        "application_version": current_app.config["APP_VERSION"],
        "source_revision": current_app.config.get("SOURCE_REVISION"),
        "source_tree": {
            "scope": SOURCE_SCOPE,
            "sha256": compute_source_tree_sha256(project_root),
        },
        "dataset": {
            "path": catalog.source_path.name,
            "sha256": catalog.source_sha256,
            "source_rows": catalog.source_row_count,
            "logical_nodes": catalog.logical_node_count,
            "metadata_path": dataset_metadata_path.name,
            "metadata_sha256": _sha256(dataset_metadata_path),
        },
        "scenario_definition": {
            "path": Path(scenarios).name,
            "sha256": _sha256(scenarios),
        },
        "dependencies": {
            "constraints_path": constraints_path.name,
            "constraints_sha256": _sha256(constraints_path),
        },
        "release_manifest": {
            "path": release_manifest_path.name,
            "sha256": _sha256(release_manifest_path),
        },
        "research_manifest": {
            "path": research_manifest_path.name,
            "sha256": _sha256(research_manifest_path),
        },
        "algorithm": {
            "defaults": dict(getattr(service, "defaults", {})),
            "travel_mode": TRAVEL_MODE,
            "routing_preference": ROUTING_PREFERENCE,
            "polyline_quality": POLYLINE_QUALITY,
            "ferry_maneuvers": sorted(FERRY_MANEUVERS),
            "ferry_distance_consumes_soc": False,
            "ferry_vehicle_access_guaranteed": False,
            "ferry_user_control": True,
            "geodesic_lower_bound_margin_ratio": (
                GEODESIC_LOWER_BOUND_MARGIN_RATIO
            ),
            "charging_time_included": False,
        },
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": sys.platform,
            "machine": platform.machine(),
        },
    }


@click.command("dataset-summary")
@with_appcontext
def dataset_summary_command():
    """Menampilkan hasil validasi dan konsolidasi dataset sebagai JSON."""

    catalog = current_app.extensions["station_catalog"]
    click.echo(json.dumps(catalog.summary(), ensure_ascii=False, indent=2))


@click.command("release-audit")
@with_appcontext
def release_audit_command():
    """Memverifikasi kandidat rilis secara offline tanpa Google Maps API."""

    try:
        report = run_release_audit(
            current_app.config["RELEASE_MANIFEST_PATH"],
            app_version=current_app.config["APP_VERSION"],
            catalog=current_app.extensions["station_catalog"],
            config=current_app.config,
        )
    except (ReleaseManifestError, OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise click.ClickException(
            f"Audit rilis gagal pada {report['summary']['failed_count']} check."
        )


@click.command("experiment-run")
@click.option(
    "--scenarios",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Berkas JSON berisi definisi skenario eksperimen.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("reports/generated"),
    show_default=True,
    help="Direktori keluaran JSON dan CSV.",
)
@click.option(
    "--label",
    type=str,
    help="Label nama berkas; default menggunakan experiment_id.",
)
@click.option(
    "--confirm-live-api",
    is_flag=True,
    help="Konfirmasi bahwa eksperimen boleh memakai kuota Google Routes API.",
)
@click.option(
    "--max-compute-routes",
    type=click.IntRange(min=1, max=60),
    default=60,
    show_default=True,
    help="Hard limit panggilan Compute Routes selama eksperimen.",
)
@click.option(
    "--max-compute-routes-per-minute",
    type=click.IntRange(min=1, max=100),
    default=100,
    show_default=True,
    help="Batas Compute Routes dalam rolling window 60 detik.",
)
@click.option(
    "--max-compute-routes-per-scenario",
    type=click.IntRange(min=1, max=10),
    default=10,
    show_default=True,
    help="Hard limit Compute Routes untuk setiap skenario.",
)
@click.option(
    "--max-matrix-elements",
    type=click.IntRange(min=1, max=2000),
    default=2000,
    show_default=True,
    help="Hard limit total elemen Compute Route Matrix.",
)
@click.option(
    "--max-matrix-elements-per-minute",
    type=click.IntRange(min=1, max=2000),
    default=2000,
    show_default=True,
    help="Batas elemen Route Matrix dalam rolling window 60 detik.",
)
@click.option(
    "--batch-size",
    type=click.IntRange(min=1, max=100),
    default=100,
    show_default=True,
    help="Jumlah skenario sebelum jeda antarbatches.",
)
@click.option(
    "--batch-interval-seconds",
    type=click.FloatRange(min=0, max=3600),
    default=0,
    show_default=True,
    help="Jeda antarbatches dalam detik.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Ganti laporan dengan label yang sama jika sudah ada.",
)
@with_appcontext
def experiment_run_command(
    scenarios,
    output_dir,
    label,
    confirm_live_api,
    max_compute_routes,
    max_compute_routes_per_minute,
    max_compute_routes_per_scenario,
    max_matrix_elements,
    max_matrix_elements_per_minute,
    batch_size,
    batch_interval_seconds,
    overwrite,
):
    """Menjalankan batch evaluasi yang dapat direproduksi."""

    if not confirm_live_api:
        raise click.UsageError(
            "Tambahkan --confirm-live-api setelah memeriksa skenario dan "
            "kuota Google Routes API."
        )
    service = current_app.extensions.get(
        "experiment_recommendation_service"
    ) or current_app.extensions.get("recommendation_service")
    if service is None:
        raise click.ClickException(
            "GOOGLE_MAPS_SERVER_API_KEY belum dikonfigurasi."
        )
    routes_client = getattr(service, "routes_client", None)
    if routes_client is None or not hasattr(routes_client, "request_budget"):
        raise click.ClickException(
            "Client Google Routes tidak mendukung budget request eksperimen."
        )

    reservation = None
    budget = None
    report = None
    report_label = None
    json_path = None
    try:
        definition = load_experiment_definition(scenarios)
        report_label = label or definition["experiment_id"]
        json_path, csv_path = experiment_report_paths(
            output_dir,
            report_label,
        )
        if not overwrite and (json_path.exists() or csv_path.exists()):
            raise FileExistsError(
                "Laporan dengan label tersebut sudah ada; gunakan "
                "--overwrite jika memang ingin menggantinya."
            )
        ledger = _quota_ledger()
        reservation = ledger.reserve(
            label=report_label,
            maximum_compute_routes=max_compute_routes,
            maximum_matrix_elements=max_matrix_elements,
            enforce_per_minute_capacity=True,
        )
        with routes_client.request_budget(
            maximum_compute_routes=max_compute_routes,
            maximum_compute_routes_per_minute=(
                max_compute_routes_per_minute
            ),
            maximum_compute_routes_per_scenario=(
                max_compute_routes_per_scenario
            ),
            maximum_matrix_elements=max_matrix_elements,
            maximum_matrix_elements_per_minute=(
                max_matrix_elements_per_minute
            ),
        ) as budget:
            report = run_experiment(
                service,
                definition,
                source_path=scenarios,
                batch_size=batch_size,
                batch_interval_seconds=batch_interval_seconds,
                progress_callback=lambda progress: click.echo(
                    (
                        f"Batch selesai: {progress['completed_scenarios']} "
                        "skenario. Menunggu "
                        f"{progress['wait_seconds']:.0f} detik sebelum "
                        "batch berikutnya..."
                    ),
                    err=True,
                ),
                provenance=_experiment_provenance(scenarios, service),
            )
        report["execution"] = {
            "app_version": current_app.config["APP_VERSION"],
            "live_api_confirmed": True,
            "outcome": (
                "completed"
                if report["aggregate"]["error_count"] == 0
                else "completed_with_errors"
            ),
            **budget.snapshot(),
        }
        json_path, csv_path = write_experiment_report(
            report,
            output_dir,
            report_label,
            overwrite=overwrite,
        )
    except Exception as error:
        if reservation is not None:
            usage = budget.snapshot() if budget is not None else {}
            ledger.finalize(
                reservation["reservation_id"],
                compute_routes_attempt_count=usage.get(
                    "compute_routes_attempt_count",
                    0,
                ),
                matrix_element_attempt_count=usage.get(
                    "matrix_element_attempt_count",
                    0,
                ),
                outcome="failed",
                report_path=(
                    json_path if json_path and json_path.exists() else None
                ),
            )
        if not isinstance(
            error,
            (ExperimentDefinitionError, QuotaLedgerError, ValueError,
             FileExistsError, OSError),
        ):
            raise
        raise click.ClickException(str(error)) from error

    scenario_error_count = report["aggregate"]["error_count"]
    daily_quota = ledger.finalize(
        reservation["reservation_id"],
        compute_routes_attempt_count=budget.compute_routes_attempt_count,
        matrix_element_attempt_count=budget.matrix_element_attempt_count,
        outcome="completed" if scenario_error_count == 0 else "failed",
        report_path=json_path,
    )
    report["daily_quota"] = daily_quota
    json_path, csv_path = write_experiment_report(
        report,
        output_dir,
        report_label,
        overwrite=True,
    )
    ledger.attach_report(reservation["reservation_id"], json_path)

    click.echo(
        json.dumps(
            {
                "aggregate": report["aggregate"],
                "execution": report["execution"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    click.echo(f"JSON: {json_path}")
    click.echo(f"CSV: {csv_path}")
    if scenario_error_count:
        raise click.ClickException(
            f"Eksperimen selesai dengan {scenario_error_count} skenario "
            "error. Laporan parsial telah disimpan dan ledger ditandai gagal."
        )


@click.command("quota-status")
@click.option(
    "--date",
    "date_key",
    type=str,
    help="Tanggal kuota Pacific Time YYYY-MM-DD; default hari ini.",
)
@with_appcontext
def quota_status_command(date_key):
    """Menampilkan pemakaian, reservasi, dan sisa quota harian."""

    if date_key:
        try:
            date_key = datetime.strptime(
                date_key,
                "%Y-%m-%d",
            ).date().isoformat()
        except ValueError as error:
            raise click.ClickException(
                "Tanggal quota harus berformat YYYY-MM-DD."
            ) from error
    try:
        status = _quota_ledger().status(date_key)
    except (QuotaLedgerError, ValueError, OSError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(status, ensure_ascii=False, indent=2))


@click.command("quota-import-report")
@click.option(
    "--report",
    "reports",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    multiple=True,
    required=True,
    help="Laporan JSON eksperimen yang akan dicatat; dapat diulang.",
)
@with_appcontext
def quota_import_report_command(reports):
    """Mengimpor pemakaian laporan lama secara idempoten."""

    ledger = _quota_ledger()
    try:
        results = [ledger.import_report(report) for report in reports]
    except (QuotaLedgerError, ValueError, OSError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(results, ensure_ascii=False, indent=2))


@click.command("quota-recover")
@click.option("--reservation", required=True, help="ID reservasi aktif.")
@click.option(
    "--compute-routes-attempts",
    type=click.IntRange(min=0),
    required=True,
    help="Percobaan Compute Routes yang sudah terjadi atau batas atas aman.",
)
@click.option(
    "--matrix-element-attempts",
    type=click.IntRange(min=0),
    required=True,
    help="Elemen Route Matrix yang sudah dicoba atau batas atas aman.",
)
@click.option("--reason", required=True, help="Alasan pemulihan reservasi.")
@click.option(
    "--confirm-process-stopped",
    is_flag=True,
    help="Konfirmasi proses pemilik reservasi sudah berhenti.",
)
@with_appcontext
def quota_recover_command(
    reservation,
    compute_routes_attempts,
    matrix_element_attempts,
    reason,
    confirm_process_stopped,
):
    """Memulihkan reservasi yatim dan mencatat pemakaian API-nya."""

    if not confirm_process_stopped:
        raise click.UsageError(
            "Tambahkan --confirm-process-stopped setelah memastikan proses "
            "eksperimen tidak lagi berjalan."
        )
    try:
        status = _quota_ledger().recover(
            reservation,
            compute_routes_attempt_count=compute_routes_attempts,
            matrix_element_attempt_count=matrix_element_attempts,
            reason=reason,
        )
    except (QuotaLedgerError, ValueError, OSError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(status, ensure_ascii=False, indent=2))


def register_commands(app):
    app.cli.add_command(dataset_summary_command)
    app.cli.add_command(release_audit_command)
    app.cli.add_command(experiment_run_command)
    app.cli.add_command(quota_status_command)
    app.cli.add_command(quota_import_report_command)
    app.cli.add_command(quota_recover_command)
