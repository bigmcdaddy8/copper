"""0W-4D: reconnect token-lifecycle correction + bounded near-expiry startup.

Deterministic reproduction of 0W-4 Attempt 1 (2026-09-21/22): a server-sent
1012 ~5h into Day 1 was recovered by a reconnect that re-requested a quote
token; the provider minted a fresh standing token, handed it to the Day-2
launch with 18,011s left, and the (correct) horizon guard refused to start.

`StandingTokenProvider` is an evidence-based model of tastytrade quote-token
issuance, not a claim about its exact rules: a still-valid token is re-issued
unchanged (0W-2C, and the 2026-09-21 Day-2 launch), a new 24h token is minted
once the current one has expired (0W-4 Days 3-5), and a request inside a
configured `mid_life_mint_windows` interval mints a new token anyway -- the
observed 2026-09-21 02:55Z reconnect, where a request produced a new token
while the prior one still had ~19h left. The provider's real rule is unknown;
the model only has to make "requesting mid-session can move the standing
token" true, because that is what happened.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest
from K9.tastytrade.dxlink import DxLinkError, DxLinkSourceEvent
from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.long_running_capture import InstrumentCaptureSpec, ReconnectPolicy, run_long_horizon_capture
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind
from dicks_laboratory.quote_token_lifecycle import (
    QUOTE_TOKEN_HORIZON_MARGIN_SECONDS,
    QuoteTokenGrant,
    QuoteTokenHorizonError,
    QuoteTokenLifecycle,
    StartupTokenPolicy,
)
from dicks_laboratory.store import LaboratoryStore

_UTC = timezone.utc
_SYMBOL = "/ESZ26:XCME"
_SPEC = InstrumentCaptureSpec(
    instrument=InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12), streamer_symbol=_SYMBOL
)
_TOKEN_LIFETIME = timedelta(seconds=86_400)
_HORIZON = 83_700.0  # production --duration
_REQUIRED = _HORIZON + QUOTE_TOKEN_HORIZON_MARGIN_SECONDS  # 84,600s

# Actual 0W-4 Attempt-1 instants.
_DAY1_LAUNCH = datetime(2026, 9, 20, 21, 55, 1, 976000, tzinfo=_UTC)  # Sun 16:55 CT; Day-1 token issued_at
_DAY1_OPEN = datetime(2026, 9, 20, 22, 0, tzinfo=_UTC)
_DAY1_1012 = datetime(2026, 9, 21, 2, 55, 11, 948328, tzinfo=_UTC)  # Sun 21:55:11.948 CT
_DAY1_RECONNECT_MINT = datetime(2026, 9, 21, 2, 55, 13, 309000, tzinfo=_UTC)
_DAY2_TOKEN_REQUEST = datetime(2026, 9, 21, 21, 55, 1, 931924, tzinfo=_UTC)  # Mon 16:55 CT


class _Clock:
    def __init__(self, start: datetime, step: timedelta = timedelta(milliseconds=1)):
        self.current = start
        self._step = step
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        value = self.current
        self.current += self._step
        return value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


class StandingTokenProvider:
    def __init__(self, clock: _Clock, mid_life_mint_windows: tuple[tuple[datetime, datetime], ...] = ()):
        self._clock = clock
        self._mint_windows = mid_life_mint_windows
        self.current: QuoteTokenGrant | None = None
        self.minted = 0
        self.requests = 0

    def _mint(self, at: datetime) -> QuoteTokenGrant:
        self.minted += 1
        self.current = QuoteTokenGrant("wss://example.invalid/dxlink", f"tok-{self.minted}", at, at + _TOKEN_LIFETIME)
        return self.current

    def request(self) -> QuoteTokenGrant:
        self.requests += 1
        moment = self._clock.now()
        if self.current is None or moment >= self.current.expires_at:
            return self._mint(moment)
        if any(start <= moment < end for start, end in self._mint_windows):
            return self._mint(moment)
        return self.current


# Any mid-session Day-1 request mints, as observed at 2026-09-21T02:55:13Z.
_DAY1_MID_SESSION = ((_DAY1_OPEN, datetime(2026, 9, 21, 21, 0, tzinfo=_UTC)),)


def _event(ts: datetime, index: int) -> DxLinkSourceEvent:
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": "NEW",
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "exchangeCode": "Q", "price": 7800.0, "size": 1.0, "bidPrice": 7799.75, "askPrice": 7800.25,
        "exchangeSaleConditions": "@", "tradeThroughExempt": "0", "aggressorSide": "BUY",
        "spreadLeg": False, "extendedTradingHours": False, "validTick": True,
    }
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


@dataclass
class _Step:
    """One `collect()` call: deliver `event_at` (if set), advance the clock to
    `drop_at`, then raise a server 1012 -- or, with `drop_at=None`, return
    cleanly after the full requested span. `connect_fails` raises before
    `on_connected` (a failed reconnect attempt)."""

    event_at: datetime | None = None
    drop_at: datetime | None = None
    connect_fails: bool = False


_SERVER_1012 = "DXLink connection error while receiving: received 1012 (service restart) Service Restart"


class _TokenRecordingCollector:
    """Fake `DxLinkSourceCollector`: records which credential each connect used."""

    def __init__(self, token: str, script: list[_Step], clock: _Clock, used_tokens: list[str]):
        self._token = token
        self._script = script
        self._clock = clock
        self._used = used_tokens

    def collect(self, streamer_symbol, event_types, duration_seconds, max_events,
                on_event=None, on_connected=None, retain_events=True):
        self._used.append(self._token)
        step = self._script.pop(0) if self._script else _Step()
        if step.connect_fails:
            raise DxLinkError("simulated reconnect connect/auth failure")
        if on_connected is not None:
            on_connected()
        if step.event_at is not None and on_event is not None:
            on_event(_event(step.event_at, len(self._used)))
        if step.drop_at is not None:
            self._clock.current = max(self._clock.current, step.drop_at)
            raise DxLinkError(_SERVER_1012)
        self._clock.sleep(duration_seconds)
        return ()


def _lifecycle(provider: StandingTokenProvider, clock: _Clock, log: list[str] | None = None, **kwargs):
    return QuoteTokenLifecycle(
        provider.request, now=clock.now, sleeper=clock.sleep,
        log=(log.append if log is not None else (lambda _m: None)), **kwargs,
    )


def _run_day(tmp_path, clock, lifecycle, script, reconnect_policy=ReconnectPolicy()):
    """Launch-guard, then run one production-shaped capture with the CLI's
    reconnect wiring (`refresh_collector` -> `grant_for_reconnect`)."""
    used: list[str] = []
    grant = lifecycle.acquire_for_launch(_HORIZON)

    def refresh_collector():
        return _TokenRecordingCollector(lifecycle.grant_for_reconnect().token, script, clock, used)

    result = run_long_horizon_capture(
        tmp_path, _SPEC, _TokenRecordingCollector(grant.token, script, clock, used), _HORIZON, 5_000_000,
        reconnect_policy=reconnect_policy, now=clock.now, sleeper=clock.sleep, refresh_collector=refresh_collector,
    )
    return result, used


def _evidence_counts(result) -> dict[str, int]:
    store = LaboratoryStore(result.database_path, read_only=True)
    try:
        values = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    finally:
        store.close()
    return {name: values.count(name) for name in set(values)}


# --- A. server 1012 with a healthy existing token --------------------------


def test_a_server_1012_reuses_healthy_token_without_new_credentials(tmp_path):
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock)
    log: list[str] = []
    lifecycle = _lifecycle(provider, clock, log)
    script = [
        _Step(event_at=_DAY1_OPEN + timedelta(seconds=1), drop_at=_DAY1_1012),
        _Step(event_at=_DAY1_1012 + timedelta(seconds=2)),
    ]
    result, used = _run_day(tmp_path, clock, lifecycle, script)

    assert used == ["tok-1", "tok-1"]  # the reconnect re-used the SAME credential
    assert provider.requests == 1 and lifecycle.fetch_count == 1  # no quote-token (hence no OAuth) request
    assert lifecycle.reuse_count == 1
    reuse_line = next(line for line in log if "quote_token_reused=true" in line)
    remaining = float(reuse_line.split("quote_token_remaining_seconds=")[1].split()[0])
    assert remaining == pytest.approx(timedelta(hours=18, minutes=59, seconds=50).total_seconds(), abs=5)
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    assert result.trading_date == date(2026, 9, 21)
    counts = _evidence_counts(result)
    assert counts["SOURCE_DISCONNECTED"] == 1
    assert counts["KNOWN_GAP"] == 1
    assert counts["SOURCE_RECONNECTED"] == 1


# --- B. several reconnects never mint new tokens ----------------------------


def test_b_multiple_reconnects_keep_reusing_one_token(tmp_path):
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock)
    lifecycle = _lifecycle(provider, clock)
    drops = [_DAY1_OPEN + timedelta(hours=h) for h in (1, 5, 9, 14, 20)]
    script = [_Step(event_at=drop - timedelta(minutes=1), drop_at=drop) for drop in drops] + [_Step()]
    result, used = _run_day(tmp_path, clock, lifecycle, script)

    assert used == ["tok-1"] * 6
    assert provider.requests == 1 and provider.minted == 1
    assert lifecycle.reuse_count == 5
    counts = _evidence_counts(result)
    assert counts["SOURCE_DISCONNECTED"] == 5
    assert counts["SOURCE_RECONNECTED"] == 5
    assert counts["KNOWN_GAP"] == 5
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED


# --- C. an existing token that genuinely cannot cover the rest of the run ---


def test_c_unknown_expiry_token_falls_back_to_fresh_request_truthfully():
    clock = _Clock(_DAY1_LAUNCH)
    grants = iter([
        QuoteTokenGrant("wss://example.invalid", "tok-unknown", None, None),
        QuoteTokenGrant("wss://example.invalid", "tok-fresh", _DAY1_1012, _DAY1_1012 + _TOKEN_LIFETIME),
    ])
    log: list[str] = []
    lifecycle = QuoteTokenLifecycle(lambda: next(grants), now=clock.now, sleeper=clock.sleep, log=log.append)
    assert lifecycle.acquire_for_launch(_HORIZON).token == "tok-unknown"  # 0W-2D: unknown expiry never blocks launch
    clock.current = _DAY1_1012
    assert lifecycle.grant_for_reconnect().token == "tok-fresh"
    assert lifecycle.fetch_count == 2 and lifecycle.reuse_count == 0
    assert any(
        "quote_token_reused=false" in line and "reason=existing_token_cannot_cover_remaining_run" in line
        and "quote_token_remaining_seconds=unknown" in line for line in log
    )


def test_c_expired_existing_token_is_not_blindly_reused():
    # e.g. a host clock step past the launch token's expiry: reusing it could
    # never re-authenticate (0W-2A), so a fresh credential is requested, logged.
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock)
    log: list[str] = []
    lifecycle = _lifecycle(provider, clock, log)
    lifecycle.acquire_for_launch(_HORIZON)
    clock.current = _DAY1_LAUNCH + _TOKEN_LIFETIME + timedelta(seconds=5)
    assert lifecycle.grant_for_reconnect().token == "tok-2"
    assert provider.requests == 2
    assert any("quote_token_reused=false" in line for line in log)


def test_c_reconnect_before_launch_is_a_programming_error():
    lifecycle = QuoteTokenLifecycle(lambda: pytest.fail("must not fetch"))
    with pytest.raises(RuntimeError):
        lifecycle.grant_for_reconnect()


# --- D/E/F/G. launch-time horizon guard + bounded near-expiry wait ----------


def test_d_fresh_token_starts_immediately():
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock)
    lifecycle = _lifecycle(provider, clock)
    grant = lifecycle.acquire_for_launch(_HORIZON)
    assert grant.remaining_seconds(clock.current) >= _REQUIRED
    assert provider.requests == 1 and clock.sleeps == []


@pytest.mark.parametrize("seconds_to_expiry", [0.044, 0.172, 3.0, 30.0])
def test_e_imminently_expiring_standing_token_waits_boundedly_then_restarts(seconds_to_expiry):
    launch = _DAY1_LAUNCH + _TOKEN_LIFETIME - timedelta(seconds=seconds_to_expiry)
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock)
    provider.request()  # yesterday's launch token, still standing
    clock.current = launch
    log: list[str] = []
    lifecycle = _lifecycle(provider, clock, log)
    grant = lifecycle.acquire_for_launch(_HORIZON)

    assert grant.token == "tok-2"
    assert grant.remaining_seconds(clock.current) >= _REQUIRED
    assert provider.requests == 3  # yesterday's + stale re-issue + one bounded re-request
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] <= StartupTokenPolicy().imminent_expiry_window_seconds + StartupTokenPolicy().post_expiry_grace_seconds
    assert any("startup_quote_token: imminent_expiry=true" in line for line in log)


def test_e_provider_lag_is_retried_but_bounded():
    clock = _Clock(_DAY1_LAUNCH)
    stale = QuoteTokenGrant("wss://example.invalid", "tok-old", _DAY1_LAUNCH - _TOKEN_LIFETIME, _DAY1_LAUNCH + timedelta(seconds=0.2))
    fresh_at = _DAY1_LAUNCH + timedelta(seconds=5)
    grants = iter([stale, stale, QuoteTokenGrant("wss://example.invalid", "tok-new", fresh_at, fresh_at + _TOKEN_LIFETIME)])
    lifecycle = QuoteTokenLifecycle(lambda: next(grants), now=clock.now, sleeper=clock.sleep)
    assert lifecycle.acquire_for_launch(_HORIZON).token == "tok-new"
    assert lifecycle.fetch_count == 3
    assert sum(clock.sleeps) < 10


def test_e_never_obtaining_a_sufficient_token_fails_closed_within_the_bound():
    clock = _Clock(_DAY1_LAUNCH)
    stale = QuoteTokenGrant("wss://example.invalid", "tok-old", None, _DAY1_LAUNCH + timedelta(seconds=10))
    policy = StartupTokenPolicy()
    lifecycle = QuoteTokenLifecycle(lambda: stale, now=clock.now, sleeper=clock.sleep, startup_policy=policy)
    with pytest.raises(QuoteTokenHorizonError):
        lifecycle.acquire_for_launch(_HORIZON)
    assert lifecycle.fetch_count == 1 + policy.max_rerequests
    worst_case = policy.imminent_expiry_window_seconds + (policy.max_rerequests * policy.post_expiry_grace_seconds)
    assert sum(clock.sleeps) <= worst_case
    # launched 16:55:00 CT -> still ~4 minutes before the 17:00 CT open
    assert clock.current < _DAY1_OPEN - timedelta(minutes=4)


def test_f_actual_day2_hours_left_token_is_refused_without_waiting():
    clock = _Clock(_DAY2_TOKEN_REQUEST)
    day2_token = QuoteTokenGrant(
        "wss://example.invalid", "tok-reconnect", _DAY1_RECONNECT_MINT, _DAY1_RECONNECT_MINT + _TOKEN_LIFETIME
    )
    lifecycle = QuoteTokenLifecycle(lambda: day2_token, now=clock.now, sleeper=clock.sleep)
    with pytest.raises(QuoteTokenHorizonError) as info:
        lifecycle.acquire_for_launch(_HORIZON)
    assert info.value.remaining_seconds == pytest.approx(18_011, abs=1)
    assert info.value.required_seconds == _REQUIRED
    assert clock.sleeps == [] and lifecycle.fetch_count == 1
    assert "insufficient" in str(info.value)


def test_g_horizon_requirement_is_unchanged_at_84600_seconds():
    assert QUOTE_TOKEN_HORIZON_MARGIN_SECONDS == 900.0
    assert _REQUIRED == 84_600.0
    for remaining, allowed in ((84_600.0, True), (84_599.0, False)):
        clock = _Clock(_DAY1_LAUNCH, step=timedelta(0))
        grant = QuoteTokenGrant("wss://example.invalid", "t", None, _DAY1_LAUNCH + timedelta(seconds=remaining))
        lifecycle = QuoteTokenLifecycle(lambda g=grant: g, now=clock.now, sleeper=clock.sleep)
        if allowed:
            lifecycle.acquire_for_launch(_HORIZON)
        else:
            with pytest.raises(QuoteTokenHorizonError):
                lifecycle.acquire_for_launch(_HORIZON)
            assert clock.sleeps == []


# --- H. reconnect accounting is unchanged under the new credential policy ---


def test_h_retry_budget_and_interrupted_semantics_unchanged(tmp_path):
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock)
    lifecycle = _lifecycle(provider, clock)
    script = [_Step(event_at=_DAY1_OPEN + timedelta(seconds=1), drop_at=_DAY1_1012)] + [
        _Step(connect_fails=True) for _ in range(3)
    ]
    result, used = _run_day(tmp_path, clock, lifecycle, script, reconnect_policy=ReconnectPolicy(max_attempts=2))
    assert result.lifecycle_state is DatasetLifecycleState.INTERRUPTED
    assert set(used) == {"tok-1"} and provider.requests == 1
    counts = _evidence_counts(result)
    assert counts["SOURCE_DISCONNECTED"] == 3  # the 1012 + two failed attempts, one episode
    assert counts["KNOWN_GAP"] == 1
    assert counts.get("SOURCE_RECONNECTED", 0) == 0


# --- 0W-4 Attempt-1 Day1 -> Day2 reproduction --------------------------------


def _day2_launch_clock(clock: _Clock) -> None:
    clock.current = _DAY2_TOKEN_REQUEST


def test_attempt1_failure_reproduced_when_reconnect_requests_a_token(tmp_path):
    """Pre-correction behaviour: the Day-1 reconnect requested a token and the
    provider minted a new one; Day 2 then gets it with 18,011s left -> refused."""
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock, _DAY1_MID_SESSION)
    _lifecycle(provider, clock).acquire_for_launch(_HORIZON)
    clock.current = _DAY1_RECONNECT_MINT
    assert provider.request().token == "tok-2"  # the old reconnect path's request at 02:55:13.309Z

    _day2_launch_clock(clock)
    day2 = _lifecycle(provider, clock)
    with pytest.raises(QuoteTokenHorizonError) as info:
        day2.acquire_for_launch(_HORIZON)
    assert info.value.remaining_seconds == pytest.approx(18_011, abs=1)
    assert clock.sleeps == []  # hard refusal, never a long wait


def test_attempt1_day1_to_day2_corrected_path_opens_day2(tmp_path):
    clock = _Clock(_DAY1_LAUNCH)
    provider = StandingTokenProvider(clock, _DAY1_MID_SESSION)

    # Day 1: fresh token, server 1012 at ~5h, reconnect, complete.
    day1 = _lifecycle(provider, clock)
    script = [
        _Step(event_at=_DAY1_OPEN + timedelta(seconds=1), drop_at=_DAY1_1012),
        _Step(event_at=_DAY1_1012 + timedelta(seconds=2)),
    ]
    result1, used1 = _run_day(tmp_path / "d1", clock, day1, script)
    assert used1 == ["tok-1", "tok-1"] and provider.minted == 1
    assert result1.trading_date == date(2026, 9, 21)
    assert _evidence_counts(result1)["KNOWN_GAP"] == 1  # the 1012 gap stays truthfully recorded

    # Day 2: the original Day-1 token expires ~44ms after the 16:55 request.
    _day2_launch_clock(clock)
    assert provider.current.expires_at - clock.current < timedelta(seconds=1)
    sleeps_before = len(clock.sleeps)
    day2 = _lifecycle(provider, clock)
    result2, used2 = _run_day(tmp_path / "d2", clock, day2, [_Step(event_at=datetime(2026, 9, 21, 22, 0, 1, tzinfo=_UTC))])

    day2_sleeps = clock.sleeps[sleeps_before:]
    assert day2_sleeps[0] < StartupTokenPolicy().imminent_expiry_window_seconds  # bounded startup wait
    assert used2 == ["tok-2"] and provider.minted == 2
    assert result2.trading_date == date(2026, 9, 22)
    assert result2.lifecycle_state is DatasetLifecycleState.FINALIZED
    assert result2.known_gap_count == 0
