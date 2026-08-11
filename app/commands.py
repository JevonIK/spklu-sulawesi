"""Perintah CLI untuk audit data penelitian."""

import json

import click
from flask import current_app
from flask.cli import with_appcontext


@click.command("dataset-summary")
@with_appcontext
def dataset_summary_command():
    """Menampilkan hasil validasi dan konsolidasi dataset sebagai JSON."""

    catalog = current_app.extensions["station_catalog"]
    click.echo(json.dumps(catalog.summary(), ensure_ascii=False, indent=2))


def register_commands(app):
    app.cli.add_command(dataset_summary_command)

