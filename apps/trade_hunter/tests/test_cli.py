import os
import subprocess
import sys

DUMMY_ARGS = [
    "--output-dir",
    "/tmp",
    # Pass explicit non-existent paths so loaders fail immediately (FileNotFoundError)
    # rather than scanning the default OneDrive mount directory.
    "--tastytrade-file",
    "/tmp/nonexistent_tastytrade.csv",
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


def test_run_prints_summary_before_pipeline():
    """Config summary is always printed before pipeline execution.

    With a valid API key but no input files at the default paths, the run
    exits with code 1 after printing the summary (FileNotFoundError from loader).
    """
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
    # Pipeline exits non-zero because no input files exist at the default paths
    assert r.returncode == 1
    # Config summary is still printed to stdout before the pipeline attempts to load files
    assert "TastyTrade" in r.stdout
    # Error message is printed to stderr
    assert "Error" in r.stderr
