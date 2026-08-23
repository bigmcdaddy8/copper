import subprocess
import sys


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "dicks_laboratory", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "dicks_laboratory" in result.stdout