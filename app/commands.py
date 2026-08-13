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
    "--max-api-requests",
    type=click.IntRange(min=1, max=1000),
    default=100,
    show_default=True,
    help="Hard limit request HTTP aktual selama satu batch eksperimen.",
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
    max_api_requests,
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
        with routes_client.request_budget(max_api_requests) as budget:
            report = run_experiment(
                service,
                definition,
                source_path=scenarios,
            )
        report["execution"] = {
            "live_api_confirmed": True,
            "api_request_budget": budget.limit,
            "api_request_attempt_count": budget.used,
            "api_request_budget_remaining": budget.remaining,
            "api_request_budget_exhausted": budget.exhausted,
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
