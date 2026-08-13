"""Perintah CLI untuk audit data dan eksperimen penelitian."""

import json
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext

from .services.evaluation import (
    ExperimentDefinitionError,
    load_experiment_definition,
    run_experiment,
    write_experiment_report,
)


@click.command("dataset-summary")
@with_appcontext
def dataset_summary_command():
    """Menampilkan hasil validasi dan konsolidasi dataset sebagai JSON."""

    catalog = current_app.extensions["station_catalog"]
    click.echo(json.dumps(catalog.summary(), ensure_ascii=False, indent=2))


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
    type=click.IntRange(min=1, max=30),
    default=30,
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
    type=click.IntRange(min=1, max=625),
    default=625,
    show_default=True,
    help="Batas elemen Route Matrix dalam rolling window 60 detik.",
)
@click.option(
    "--batch-size",
    type=click.IntRange(min=1, max=100),
    default=3,
    show_default=True,
    help="Jumlah skenario sebelum jeda antarbatches.",
)
@click.option(
    "--batch-interval-seconds",
    type=click.FloatRange(min=60, max=3600),
    default=61,
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
    service = current_app.extensions.get("recommendation_service")
    if service is None:
        raise click.ClickException(
            "GOOGLE_MAPS_SERVER_API_KEY belum dikonfigurasi."
        )
    routes_client = getattr(service, "routes_client", None)
    if routes_client is None or not hasattr(routes_client, "request_budget"):
        raise click.ClickException(
            "Client Google Routes tidak mendukung budget request eksperimen."
        )

    try:
        definition = load_experiment_definition(scenarios)
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
            )
        report["execution"] = {
            "app_version": current_app.config["APP_VERSION"],
            "live_api_confirmed": True,
            **budget.snapshot(),
        }
        json_path, csv_path = write_experiment_report(
            report,
            output_dir,
            label or definition["experiment_id"],
            overwrite=overwrite,
        )
    except (ExperimentDefinitionError, ValueError, FileExistsError) as error:
        raise click.ClickException(str(error)) from error

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


def register_commands(app):
    app.cli.add_command(dataset_summary_command)
    app.cli.add_command(experiment_run_command)
