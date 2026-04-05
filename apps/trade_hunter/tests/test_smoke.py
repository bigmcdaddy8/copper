import subprocess
import sys


def test_help():
    r = subprocess.run(
        [sys.executable, "-m", "trade_hunter", "run", "--help"], capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "Usage" in r.stdout or "usage" in r.stdout
