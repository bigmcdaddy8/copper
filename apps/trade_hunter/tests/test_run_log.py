"""Unit tests for RunLog."""

import re
from datetime import datetime

import pytest

from trade_hunter.output.run_log import RunLog

_RUN_START = datetime(2025, 3, 19, 14, 30, 22)
_EXPECTED_FILENAME = "run_log_20250319_143022.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path, verbose: bool = False, **kwargs) -> tuple[object, str]:
    """Create a RunLog, apply kwargs (warn/info/add_warnings), write, return (path, content)."""
    log = RunLog(run_start=_RUN_START, verbose=verbose)
    for method, args in kwargs.items():
        if method == "warn":
            for msg in args:
                log.warn(msg)
        elif method == "info":
            for msg in args:
                log.info(msg)
        elif method == "add_warnings":
            log.add_warnings(args)
    path = log.write(tmp_path)
    return path, path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_runlog_creates_file(tmp_path):
    log = RunLog(run_start=_RUN_START)
    path = log.write(tmp_path)
    assert path.exists()


def test_runlog_filename_format(tmp_path):
    log = RunLog(run_start=_RUN_START)
    path = log.write(tmp_path)
    assert path.name == _EXPECTED_FILENAME
    assert re.match(r"run_log_\d{8}_\d{6}\.txt", path.name)


def test_runlog_warn_in_file(tmp_path):
    _, content = _write(tmp_path, warn=["something went wrong"])
    assert "[WARN] something went wrong" in content


def test_runlog_info_in_file(tmp_path):
    _, content = _write(tmp_path, info=["run date: 2025-03-19"])
    assert "[INFO] run date: 2025-03-19" in content


def test_runlog_add_warnings(tmp_path):
    log = RunLog(run_start=_RUN_START)
    log.add_warnings(["[WARN] alpha skipped", "[WARN] beta skipped"])
    _, content = log.write(tmp_path), (tmp_path / _EXPECTED_FILENAME).read_text(encoding="utf-8")
    assert "[WARN] alpha skipped" in content
    assert "[WARN] beta skipped" in content


def test_runlog_summary_in_file(tmp_path):
    log = RunLog(run_start=_RUN_START)
    path = log.write(tmp_path, summary={"Loaded (BULL)": 10, "Scored (BULL)": 8})
    content = path.read_text(encoding="utf-8")
    assert "Summary" in content
    assert "Loaded (BULL):" in content
    assert "10" in content


def test_runlog_summary_omitted_when_none(tmp_path):
    log = RunLog(run_start=_RUN_START)
    path = log.write(tmp_path, summary=None)
    content = path.read_text(encoding="utf-8")
    assert "Summary" not in content


def test_runlog_empty_log_produces_file(tmp_path):
    log = RunLog(run_start=_RUN_START)
    path = log.write(tmp_path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "trade_hunter run log" in content


def test_runlog_creates_output_dir(tmp_path):
    subdir = tmp_path / "nested" / "logs"
    assert not subdir.exists()
    log = RunLog(run_start=_RUN_START)
    path = log.write(subdir)
    assert subdir.exists()
    assert path.exists()


# ---------------------------------------------------------------------------
# Verbose mode — warn() and add_warnings() print to stdout when verbose=True
# ---------------------------------------------------------------------------


def test_warn_prints_to_stdout_when_verbose(tmp_path, capsys):
    log = RunLog(run_start=_RUN_START, verbose=True)
    log.warn("ticker XYZ filtered — bid too low")
    log.write(tmp_path)
    captured = capsys.readouterr()
    assert "[WARN] ticker XYZ filtered — bid too low" in captured.out


def test_warn_silent_when_not_verbose(tmp_path, capsys):
    log = RunLog(run_start=_RUN_START, verbose=False)
    log.warn("ticker XYZ filtered — bid too low")
    log.write(tmp_path)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_warn_still_written_to_file_when_verbose(tmp_path, capsys):
    _, content = _write(tmp_path, verbose=True, warn=["something bad happened"])
    assert "[WARN] something bad happened" in content


def test_add_warnings_prints_to_stdout_when_verbose(tmp_path, capsys):
    log = RunLog(run_start=_RUN_START, verbose=True)
    log.add_warnings(["[BULL] 'AAPL' excluded — active open trade", "[BEAR] 'MSFT' not in Universal Data Set — skipped"])
    log.write(tmp_path)
    captured = capsys.readouterr()
    assert "[BULL] 'AAPL' excluded — active open trade" in captured.out
    assert "[BEAR] 'MSFT' not in Universal Data Set — skipped" in captured.out


def test_add_warnings_silent_when_not_verbose(tmp_path, capsys):
    log = RunLog(run_start=_RUN_START, verbose=False)
    log.add_warnings(["[BULL] 'AAPL' excluded — active open trade"])
    log.write(tmp_path)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_add_warnings_still_written_to_file_when_verbose(tmp_path):
    log = RunLog(run_start=_RUN_START, verbose=True)
    log.add_warnings(["[BULL] 'XYZ' filtered — open interest 5 < 10"])
    path = log.write(tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "[BULL] 'XYZ' filtered — open interest 5 < 10" in content
