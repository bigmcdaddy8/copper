"""Smoke test for the discover sub-command — verifies it exits 0 against sandbox."""

import subprocess
import sys


def test_discover_exits_0():
    """discover must exit 0 when sandbox credentials are present in .env."""
    r = subprocess.run(
        [sys.executable, "-m", "tradier_sniffer", "discover"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"discover exited {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "discover complete" in r.stdout
