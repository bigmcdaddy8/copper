"""0AC-A1 API boundary: approved dates only, server-cut snapshots, Globex semantics, clamped replay."""
from __future__ import annotations

from datetime import date, datetime

import pytest
import test_replay as fx_mod  # on sys.path via conftest (shared Laboratory fixture)
from fastapi.testclient import TestClient

from tutor_poc import dev_sessions
from tutor_poc.api import create_app
from tutor_poc.dev_sessions import DevSession

CUR, ct = fx_mod.CUR, fx_mod.ct
SEALED = date(2026, 10, 12)


@pytest.fixture(scope="module")
def client(fx_timeline):
    registry = (DevSession(CUR, "synthetic.sqlite3", fx_timeline.database_sha256, True),
                DevSession(date(2026, 9, 29), "unused.sqlite3", "0" * 64, False),
                # a sealed campaign date wrongly added to the registry must still never be served
                DevSession(SEALED, "campaign.sqlite3", "0" * 64, True))
    loaded = []

    def load(s):
        loaded.append(s.trading_date)
        assert s.trading_date == CUR
        return fx_timeline

    c = TestClient(create_app(registry, load, web_dist=None))
    c.loaded = loaded
    return c


def _snap(client, cutoff=None, action=None, **kw):
    params = {k: v for k, v in (("cutoff", cutoff), ("action", action)) if v is not None} | kw
    r = client.get(f"/api/sessions/{CUR}/snapshot", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_discovery_lists_approved_dates_and_never_the_campaign(client):
    body = client.get("/api/sessions").json()
    dates = [s["trading_date"] for s in body["sessions"]]
    assert body["instrument"] == "/ES" and body["default"] == CUR.isoformat()
    assert SEALED.isoformat() not in dates and dates == [CUR.isoformat(), "2026-09-29"]


@pytest.mark.parametrize("d", ["2026-10-12", "2026-11-06", "2026-10-20", "2026-09-29", "2026-09-01", "not-a-date"])
def test_only_an_enabled_approved_date_is_served(client, d):
    for path in ("snapshot", "replay"):
        assert client.get(f"/api/sessions/{d}/{path}").status_code == 404
    assert all(x == CUR for x in client.loaded)


def test_real_registry_seals_the_campaign():
    assert all(not dev_sessions.is_sealed(s.trading_date) for s in dev_sessions.APPROVED)
    for d in (date(2026, 10, 12), date(2026, 11, 6)):
        with pytest.raises(dev_sessions.SealedDateError):
            dev_sessions.approved_session(d)
    assert [s.trading_date for s in dev_sessions.APPROVED if s.enabled] == [date(2026, 9, 30)]


@pytest.mark.parametrize("hh,mm", [(8, 0), (9, 0), (10, 0), (12, 0)])
def test_snapshot_contains_nothing_after_the_cutoff(client, hh, mm):
    cutoff = ct(CUR, hh, mm)
    s = _snap(client, cutoff.isoformat())
    end = int(cutoff.timestamp())
    assert s["replay"]["cutoff_utc"] == cutoff.isoformat()
    assert s["candles"] and all(c["end_time"] <= end for c in s["candles"])
    assert max(c["time"] for c in s["candles"]) <= end - 300  # bars are non-empty 5m bars; none open past the cutoff
    ids = {x["id"] for x in s["series"]}
    assert ids == {"vwap", "upper_1sd", "lower_1sd", "upper_2sd", "lower_2sd"}
    for x in s["series"]:
        assert [p["time"] for p in x["points"]] == [c["time"] for c in s["candles"]]
        assert all(p["time"] + 300 <= end for p in x["points"])


def test_future_bars_exist_but_are_not_returned(client, fx_timeline):
    s = _snap(client, ct(CUR, 10, 0).isoformat())
    full = len(fx_timeline.positions[-1].bars)
    assert len(s["candles"]) < full


def test_snapshot_reports_globex_vwap_semantics(client, fx_timeline):
    s = _snap(client)
    assert s["study"] == {"vwap_anchor": "GLOBEX", "band_policy": "VWAP_BANDS_GLOBEX_V1",
                          "anchor_utc": ct(date(2026, 10, 4), 17, 0).isoformat(), "bar_interval": "5m"}
    assert s["study"]["anchor_utc"] == fx_timeline.anchor_utc.isoformat()
    assert client.get(f"/api/sessions/{CUR}/snapshot", params={"vwap_anchor": "CASH"}).status_code == 422


def test_initial_position_is_0900_ct_with_future_hidden(client):
    r = client.get(f"/api/sessions/{CUR}/replay").json()
    assert r["initial_cutoff_utc"] == ct(CUR, 9, 0).isoformat()
    assert r["first_cutoff_utc"] == ct(date(2026, 10, 4), 17, 5).isoformat()
    assert r["last_cutoff_utc"] == ct(CUR, 16, 0).isoformat() and r["count"] == 276
    s = _snap(client)
    assert s["replay"]["cutoff_utc"] == ct(CUR, 9, 0).isoformat() and not s["replay"]["at_end"]


def test_replay_stepping_at_ordinary_positions(client):
    at = ct(CUR, 10, 0).isoformat()
    assert _snap(client, at, "next")["replay"]["cutoff_utc"] == ct(CUR, 10, 5).isoformat()
    assert _snap(client, at, "plus5m")["replay"]["cutoff_utc"] == ct(CUR, 10, 5).isoformat()
    prev = _snap(client, at, "previous")
    assert prev["replay"]["cutoff_utc"] == ct(CUR, 9, 55).isoformat()
    assert len(prev["candles"]) == len(_snap(client, at)["candles"]) - 1  # the newly-future candle disappears


def test_replay_stepping_clamps_at_session_bounds(client):
    first, last = ct(date(2026, 10, 4), 17, 5).isoformat(), ct(CUR, 16, 0).isoformat()
    s = _snap(client, first, "previous")
    assert s["replay"]["cutoff_utc"] == first and s["replay"]["at_start"]
    for action in ("next", "plus5m"):
        s = _snap(client, last, action)
        assert s["replay"]["cutoff_utc"] == last and s["replay"]["at_end"]


def test_off_grid_cutoff_is_rejected(client):
    for bad in (ct(CUR, 10, 1).isoformat(), "yesterday", ct(CUR, 16, 5).isoformat()):
        assert client.get(f"/api/sessions/{CUR}/snapshot", params={"cutoff": bad}).status_code == 422


def test_snapshot_values_are_the_laboratory_values(client, fx_timeline):
    at = ct(CUR, 12, 0)
    s = _snap(client, at.isoformat())
    bars = next(p for p in fx_timeline.positions if p.cutoff_utc == at).bars
    series = {x["id"]: x["points"] for x in s["series"]}
    assert [c["close"] for c in s["candles"]] == [float(b.close) for b in bars]
    assert [p["value"] for p in series["vwap"]] == [float(b.vwap) for b in bars]
    assert [p["value"] for p in series["lower_2sd"]] == [float(b.lower_2sd) for b in bars]
    assert isinstance(datetime.fromisoformat(s["replay"]["cutoff_utc"]), datetime)
