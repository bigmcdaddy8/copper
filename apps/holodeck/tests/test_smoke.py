import subprocess
import sys


def test_help():
    result = subprocess.run(
        [sys.executable, "-m", "holodeck", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "holodeck" in result.stdout
