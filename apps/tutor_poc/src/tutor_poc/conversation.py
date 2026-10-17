"""In-memory Tutor sessions (0AC-A3): the recent conversation a model may see, and cumulative usage / cost.

One session per browser page (the page sends a random session id). Nothing is persisted: restarting the
server or reloading the page starts a new session with zero totals. Model context never includes a message
written at a later replay cutoff than the current one (the Human may step the replay back), so earlier
conversation cannot leak later market facts.
"""
from __future__ import annotations

import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from tutor_poc.providers import CONTEXT_MESSAGES, HistoryMessage, TurnResult

MAX_SESSIONS = 64
KEPT_MESSAGES = 64


@dataclass
class Totals:
    turns: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    unpriced_calls: int = 0  # calls whose usage could not be priced (counted in tokens, not in cost)

    def add(self, r: TurnResult) -> None:
        self.turns += 1
        for a in r.attempts:
            if a.reply is None:
                continue
            u = a.reply.usage
            self.model_calls += 1
            self.input_tokens += u.input_tokens or 0
            self.output_tokens += u.output_tokens or 0
            self.cached_input_tokens += u.cache_read_input_tokens or 0
            self.cache_write_input_tokens += u.cache_creation_input_tokens or 0
            if a.cost_usd is None:
                self.unpriced_calls += 1
            else:
                self.cost_usd += a.cost_usd

    def as_dict(self) -> dict:
        return {"turns": self.turns, "model_calls": self.model_calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cached_input_tokens": self.cached_input_tokens,
                "cache_write_input_tokens": self.cache_write_input_tokens,
                "total_input_tokens": self.input_tokens + self.cached_input_tokens + self.cache_write_input_tokens,
                "cost_usd": f"{self.cost_usd:.6f}", "unpriced_calls": self.unpriced_calls}


@dataclass
class _Message:
    trading_date: date
    history: HistoryMessage


@dataclass
class TutorSession:
    messages: deque = field(default_factory=lambda: deque(maxlen=KEPT_MESSAGES))
    totals: Totals = field(default_factory=Totals)

    def context(self, trading_date: date, cutoff: datetime, limit: int = CONTEXT_MESSAGES) -> tuple[HistoryMessage, ...]:
        kept = [m.history for m in self.messages if m.trading_date == trading_date
                and m.history.replay_cutoff_utc <= cutoff]
        return tuple(kept[-limit:])

    def record(self, trading_date: date, cutoff: datetime, human_text: str | None, kind: str, r: TurnResult) -> None:
        if human_text:
            self.messages.append(_Message(trading_date, HistoryMessage("student", "human", cutoff, human_text)))
        if r.accepted and r.text:
            self.messages.append(_Message(trading_date, HistoryMessage("tutor", kind, cutoff, r.text)))
        self.totals.add(r)


class SessionStore:
    """Bounded, thread-safe map session id -> TutorSession (least recently used dropped first)."""

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: OrderedDict[str, TutorSession] = OrderedDict()
        self._max = max_sessions
        self.lock = threading.Lock()

    def get(self, session_id: str | None) -> TutorSession:
        if session_id is None:
            return TutorSession()  # anonymous: no history, totals for this turn only
        with self.lock:
            s = self._sessions.pop(session_id, None) or TutorSession()
            self._sessions[session_id] = s
            while len(self._sessions) > self._max:
                self._sessions.popitem(last=False)
            return s
