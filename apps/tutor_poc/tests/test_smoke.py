"""Smoke: the CLI entry point and the app factory are callable."""
from typer.testing import CliRunner

from tutor_poc.api import create_app
from tutor_poc.cli import app


def test_cli_help():
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0 and "prepare" in r.output and "serve" in r.output


def test_prepare_refuses_a_campaign_date():
    r = CliRunner().invoke(app, ["prepare", "--date", "2026-10-12"])
    assert r.exit_code != 0


def test_app_factory_without_frontend():
    assert create_app(web_dist=None).title
