"""Smoke test — enc CLI entry point loads without error."""
from typer.testing import CliRunner
from encyclopedia_galactica.cli import app

runner = CliRunner()


def test_smoke_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "encyclopedia_galactica" in result.output.lower() or "enc" in result.output.lower()


def test_trades_help():
    result = runner.invoke(app, ["trades", "--help"])
    assert result.exit_code == 0


def test_pnl_help():
    result = runner.invoke(app, ["pnl", "--help"])
    assert result.exit_code == 0


def test_report_help():
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0


def test_report_trade_number_help():
    result = runner.invoke(app, ["report", "trade-number", "--help"])
    assert result.exit_code == 0


def test_report_daily_notes_help():
    result = runner.invoke(app, ["report", "daily-notes", "--help"])
    assert result.exit_code == 0


def test_report_trade_history_help():
    result = runner.invoke(app, ["report", "trade-history", "--help"])
    assert result.exit_code == 0
