"""Tests for K9 run log (K9-0080)."""
from __future__ import annotations

import json
import pytest
from K9.engine.runner import RunResult
from K9.output.run_log import RunLog


@pytest.fixture
def filled_result() -> RunResult:
    return RunResult(
        spec_name="spx_ic_test",
        environment="holodeck",
        outcome="FILLED",
        order_id="HD-000042",
        filled_price=1.10,
        net_credit=1.10,
        expiration="2026-01-05",
        short_put_strike=5800.0,
        short_call_strike=5840.0,
        tp_order_id="HD-000043",
        tp_price=0.75,
    )


def test_run_log_write_creates_file(tmp_path, filled_result):
    log = RunLog(spec_name="spx_ic_test", log_dir=tmp_path / "logs")
    log.record(filled_result)
    path = log.write()
    assert path.exists()
    assert path.suffix == ".json"


def test_run_log_content_is_valid_json(tmp_path, filled_result):
    log = RunLog(spec_name="spx_ic_test", log_dir=tmp_path / "logs")
    log.record(filled_result)
    path = log.write()
    data = json.loads(path.read_text())
    assert data["outcome"] == "FILLED"
    assert data["filled_price"] == 1.10
    assert data["tp_price"] == 0.75
    assert data["short_put_strike"] == 5800.0
    assert data["short_call_strike"] == 5840.0


def test_run_log_skipped_outcome(tmp_path):
    result = RunResult(
        spec_name="spx_ic_test",
        environment="holodeck",
        outcome="SKIPPED",
        reason="Account below minimum.",
    )
    log = RunLog(spec_name="spx_ic_test", log_dir=tmp_path / "logs")
    log.record(result)
    path = log.write()
    data = json.loads(path.read_text())
    assert data["outcome"] == "SKIPPED"
    assert "minimum" in data["reason"]


def test_run_log_filename_includes_spec_name(tmp_path, filled_result):
    log = RunLog(spec_name="my_spec", log_dir=tmp_path / "logs")
    log.record(filled_result)
    path = log.write()
    assert "my_spec" in path.name


def test_run_log_creates_directory(tmp_path, filled_result):
    log_dir = tmp_path / "deep" / "nested" / "logs"
    log = RunLog(spec_name="spx_ic_test", log_dir=log_dir)
    log.record(filled_result)
    log.write()
    assert log_dir.exists()
