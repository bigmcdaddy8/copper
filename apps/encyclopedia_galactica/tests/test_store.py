"""Tests for report Store persistence."""
from __future__ import annotations

import pytest
from encyclopedia_galactica.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(db_path=tmp_path / "reports.db")


_STATS = {
    "count": 5,
    "pnl_count": 5,
    "total": 200.0,
    "avg": 40.0,
    "median": 35.0,
    "best": 90.0,
    "worst": -10.0,
}


def test_upsert_and_list_monthly(store):
    store.upsert_monthly("TRD", "2026-01", _STATS)
    rows = store.list_monthly("TRD")
    assert len(rows) == 1
    assert rows[0]["month"] == "2026-01"
    assert rows[0]["total_pnl"] == pytest.approx(200.0)


def test_upsert_replaces_monthly(store):
    store.upsert_monthly("TRD", "2026-01", _STATS)
    updated = {**_STATS, "total": 300.0}
    store.upsert_monthly("TRD", "2026-01", updated)
    rows = store.list_monthly("TRD")
    assert len(rows) == 1
    assert rows[0]["total_pnl"] == pytest.approx(300.0)


def test_upsert_and_list_yearly(store):
    store.upsert_yearly("TRD", "2026", _STATS)
    rows = store.list_yearly("TRD")
    assert len(rows) == 1
    assert rows[0]["year"] == "2026"


def test_reset_account(store):
    store.upsert_monthly("HD", "2026-01", _STATS)
    store.upsert_yearly("HD", "2026", _STATS)
    store.upsert_monthly("TRD", "2026-01", _STATS)
    store.reset_account("HD")
    assert store.list_monthly("HD") == []
    assert store.list_yearly("HD") == []
    assert len(store.list_monthly("TRD")) == 1


def test_list_monthly_empty(store):
    assert store.list_monthly("TRD") == []
