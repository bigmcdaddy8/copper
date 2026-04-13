"""Smoke tests for K9 CLI (K9-0000 / K9-0010)."""
import subprocess
import sys


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "K9", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "K9" in result.stdout


def test_enter_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "K9", "enter", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "trade-spec" in result.stdout


def test_enter_missing_spec_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "K9", "enter", "--trade-spec", "nonexistent_xyz_abc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
