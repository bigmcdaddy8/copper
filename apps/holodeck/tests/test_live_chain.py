"""Tests for `holodeck live-chain` CLI command (HD-0140)."""
from __future__ import annotations
import subprocess
import sys
import pytest
from holodeck.market_data import generate_spx_minutes


@pytest.fixture
def csv_path(tmp_path):
    path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, path)
    return path


def test_live_chain_cli_smoke(csv_path):
    """live-chain exits 0 when data is exhausted at end of session."""
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "live-chain",
            "--date",       "2026-01-30",
            "--expiration", "2026-01-30",
            "--speed",      "1d",
            "--data",       csv_path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"


def test_live_chain_invalid_speed_exits_nonzero(csv_path):
    """Invalid --speed value exits 1."""
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "live-chain",
            "--date",       "2026-01-05",
            "--expiration", "2026-01-05",
            "--speed",      "99x",
            "--data",       csv_path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0


def test_live_chain_missing_expiration_exits_nonzero(csv_path):
    """Omitting --expiration exits non-zero (Typer required-option enforcement)."""
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "live-chain",
            "--date", "2026-01-05",
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
