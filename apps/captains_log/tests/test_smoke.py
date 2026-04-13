"""Smoke tests for captains_log CLI."""
from __future__ import annotations

import subprocess
import sys


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "captains_log", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "list" in result.stdout.lower() or "trade" in result.stdout.lower()
