import subprocess
import sys


def test_help():
    r = subprocess.run(
        [sys.executable, "-m", "tradier_sniffer", "--help"], capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "tradier_sniffer" in r.stdout
