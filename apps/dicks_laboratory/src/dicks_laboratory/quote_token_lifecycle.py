"""0W-4D — DXLink quote-token lifecycle for ONE collector process.

0W-4 Attempt 1 root cause (see FULL_SESSION_MULTIDAY_SOAK_REPORT.md §0W-4):
a server-sent 1012 "Service Restart" at ~5h into the 2026-09-21 run was
recovered by a reconnect path that re-requested a quote token. The provider
minted a NEW standing token (expiry pushed ~5h forward), which it then handed
to the NEXT day's launch with only 18,011s left -- so the (correct) startup
horizon guard refused to open trading date 2026-09-22 at all.

This module separates *transport reconnection* from *credential renewal*:

- `acquire_for_launch` requests a token once at process start and enforces the
  unchanged horizon guard (capture horizon + `QUOTE_TOKEN_HORIZON_MARGIN_SECONDS`).
  The only relaxation is a tiny, bounded wait when the token handed out is a
  standing token expiring within `StartupTokenPolicy.imminent_expiry_window_seconds`
  (the daily 16:55 launch lands within ~±0.2s of the prior day's token expiry);
  it then re-requests a bounded number of times. A token with minutes-to-hours
  left (e.g. the actual Day-2 18,011s) is still refused immediately.
- `grant_for_reconnect` re-uses the launch token whenever it still outlasts the
  whole remaining run by the same margin -- which a guard-passing launch token
  always does -- so an ordinary socket drop never touches OAuth or mints a new
  standing token. Only a token that genuinely cannot cover the rest of the run
  (or whose expiry is unknown) falls back to requesting a fresh one: the 0W-2A
  path, justified because an expired token can never re-authenticate.

Safe evidence only: timestamps, seconds, counts. Never the token itself.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

# The DXLink quote token lives ~24h (0W-2C measured 86,400s) and one ES
# trading-date run is 83,700s, so a genuinely fresh token has ~1,800s of
# natural slack. The launch guard (0W-2D) requires horizon + this margin; the
# reconnect reuse check applies the same margin to the remaining run.
QUOTE_TOKEN_HORIZON_MARGIN_SECONDS = 900.0


@dataclass(frozen=True)
class QuoteTokenGrant:
    """A quote token plus its non-secret lifetime metadata."""

    dxlink_url: str
    token: str = field(repr=False)
    issued_at: datetime | None
    expires_at: datetime | None

    def remaining_seconds(self, now: datetime) -> float | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - now).total_seconds()


@dataclass(frozen=True)
class StartupTokenPolicy:
    """Bounded handling of a standing token that expires *imminently* at launch.

    Launch is 16:55:00 CT (systemd `AccuracySec=1s`; observed 16:55:00.86-.96
    every day of 0W-4) and the session opens 17:00:00 CT, so there are ~300s
    of pre-open slack and a normal connect takes ~1-2s. Observed boundary
    offsets between a launch's token request and the prior token's expiry were
    -0.172s..+0.069s. A 30s window covers that race with >100x headroom; the
    worst case (30s wait + 2s grace + 2 further 2s re-requests ~= 36s, plus
    request latency) still starts well before 16:56 CT, leaving ~4 minutes
    before the 17:00 open.
    """

    imminent_expiry_window_seconds: float = 30.0
    post_expiry_grace_seconds: float = 2.0
    max_rerequests: int = 3

    def __post_init__(self) -> None:
        if self.imminent_expiry_window_seconds < 0 or self.post_expiry_grace_seconds < 0:
            raise ValueError("StartupTokenPolicy windows must be non-negative.")
        if self.max_rerequests < 0:
            raise ValueError("max_rerequests must be non-negative.")


class QuoteTokenHorizonError(RuntimeError):
    """The launch token cannot outlast the intended capture: refuse to start."""

    def __init__(self, remaining_seconds: float, horizon_seconds: float, margin_seconds: float) -> None:
        self.remaining_seconds = remaining_seconds
        self.required_seconds = horizon_seconds + margin_seconds
        super().__init__(
            "DXLink quote-token lifetime is insufficient for the intended capture: "
            f"{remaining_seconds:.0f}s remaining < {self.required_seconds:.0f}s required "
            f"(horizon {horizon_seconds:.0f}s + margin {margin_seconds:.0f}s). The token was almost "
            "certainly minted early (e.g. a pre-arm preflight or a prior mid-session reissue); "
            "obtain it at collector startup instead. Refusing to open a misleading full-session capture."
        )


class QuoteTokenLifecycle:
    """Owns the quote token for one collector process (launch + reconnects)."""

    def __init__(
        self,
        fetch_grant: Callable[[], QuoteTokenGrant],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleeper: Callable[[float], None] | None = None,
        log: Callable[[str], None] = lambda _message: None,
        horizon_margin_seconds: float = QUOTE_TOKEN_HORIZON_MARGIN_SECONDS,
        startup_policy: StartupTokenPolicy = StartupTokenPolicy(),
    ) -> None:
        self._fetch_grant = fetch_grant
        self._now = now
        self._sleeper = sleeper or time.sleep
        self._log = log
        self._margin = horizon_margin_seconds
        self._policy = startup_policy
        self._grant: QuoteTokenGrant | None = None
        self._run_deadline: datetime | None = None
        self.fetch_count = 0
        self.reuse_count = 0

    def _fetch(self) -> QuoteTokenGrant:
        self.fetch_count += 1
        return self._fetch_grant()

    def acquire_for_launch(self, horizon_seconds: float) -> QuoteTokenGrant:
        """Obtain the launch token and enforce the unchanged horizon guard.

        A token whose expiry is unknown is accepted (pre-existing 0W-2D
        behaviour: observability never blocks a launch it cannot evaluate).
        """
        required = horizon_seconds + self._margin
        grant = self._fetch()
        rerequests = 0
        while True:
            moment = self._now()
            remaining = grant.remaining_seconds(moment)
            if remaining is None or remaining >= required:
                break
            imminent = remaining <= self._policy.imminent_expiry_window_seconds
            if not imminent or rerequests >= self._policy.max_rerequests:
                raise QuoteTokenHorizonError(remaining, horizon_seconds, self._margin)
            wait_seconds = max(0.0, remaining) + self._policy.post_expiry_grace_seconds
            rerequests += 1
            self._log(
                "startup_quote_token: imminent_expiry=true "
                f"remaining_seconds={remaining:.3f} wait_seconds={wait_seconds:.3f} "
                f"rerequest={rerequests}/{self._policy.max_rerequests}"
            )
            self._sleeper(wait_seconds)
            grant = self._fetch()
        self._grant = grant
        self._run_deadline = moment + timedelta(seconds=horizon_seconds)
        return grant

    def grant_for_reconnect(self) -> QuoteTokenGrant:
        """Credential for a transport reconnect: reuse unless genuinely insufficient."""
        if self._grant is None or self._run_deadline is None:
            raise RuntimeError("acquire_for_launch() must succeed before any reconnect.")
        moment = self._now()
        remaining = self._grant.remaining_seconds(moment)
        required = max(0.0, (self._run_deadline - moment).total_seconds()) + self._margin
        if remaining is not None and remaining >= required:
            self.reuse_count += 1
            self._log(
                "reconnect_credentials: quote_token_reused=true quote_token_requested=false "
                f"quote_token_remaining_seconds={remaining:.0f} required_seconds={required:.0f}"
            )
            return self._grant
        remaining_text = f"{remaining:.0f}" if remaining is not None else "unknown"
        self._log(
            "reconnect_credentials: quote_token_reused=false "
            "reason=existing_token_cannot_cover_remaining_run quote_token_requested=true "
            f"quote_token_remaining_seconds={remaining_text} required_seconds={required:.0f}"
        )
        self._grant = self._fetch()
        return self._grant
