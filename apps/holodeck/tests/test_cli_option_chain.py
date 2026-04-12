"""Tests for `holodeck option-chain` CLI command (HD-0120)."""
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


def test_option_chain_exits_zero(csv_path):
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "option-chain",
            "--date", "2026-01-05",
            "--time", "10:30",
            "--expiration", "2026-01-05",
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_option_chain_contains_atm_strike(csv_path):
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "option-chain",
            "--date", "2026-01-05",
            "--time", "10:30",
            "--expiration", "2026-01-05",
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # ATM marker should appear in output
    assert "ATM" in result.stdout


def test_option_chain_missing_expiration_exits_nonzero(csv_path):
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "option-chain",
            "--date", "2026-01-05",
            "--time", "10:30",
            # --expiration intentionally omitted
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
