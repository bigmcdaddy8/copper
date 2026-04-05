import os
import subprocess
import sys

DUMMY_ARGS = [
    "--output-dir",
    "/tmp",
]


def test_run_missing_api_key():
    # Strip all Tradier vars so .env cannot inject a real key that would make the run succeed.
    strip = {"TRADIER_API_KEY", "TRADIER_SANDBOX_API_KEY", "TRADIER_ENV"}
    env = {k: v for k, v in os.environ.items() if k not in strip}
    env["TRADIER_API_KEY"] = ""  # empty — triggers the error
    env["TRADIER_SANDBOX_API_KEY"] = ""  # prevent .env from injecting sandbox key
    env["TRADIER_ENV"] = "production"  # force production code path
    r = subprocess.run(
        [sys.executable, "-m", "trade_hunter", "run"] + DUMMY_ARGS,
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 1
    assert "TRADIER_API_KEY" in r.stderr


def test_run_dry_run_summary():
    strip = {"TRADIER_API_KEY", "TRADIER_SANDBOX_API_KEY", "TRADIER_ENV"}
    env = {k: v for k, v in os.environ.items() if k not in strip}
    env["TRADIER_API_KEY"] = "test-key-123"
    env["TRADIER_SANDBOX_API_KEY"] = ""
    env["TRADIER_ENV"] = "production"
    r = subprocess.run(
        [sys.executable, "-m", "trade_hunter", "run"] + DUMMY_ARGS,
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0
    assert "TastyTrade" in r.stdout
    assert "Pipeline not yet implemented" in r.stdout
