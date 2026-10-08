"""0Y-A independent cross-check: recompute the 2026-09-30 TPO facts straight from SQLite.

Uses only the stdlib (no Laboratory code): canonical trades in
[2026-09-30T13:30Z, 20:00Z), 30-minute periods, contiguous low..high occupancy at
0.25. The 2026-09-30 dataset has 0 corrections/cancels, so canonical == effective.
Usage: python independent_crosscheck.py <es_20260930_9ac5a21e.sqlite3>
"""
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal

con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
start = datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)
lo, hi = {}, {}
for ts, price in con.execute("SELECT event_timestamp, price FROM trade_observations"):
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    sec = (t - start).total_seconds()
    if not (0 <= sec < 390 * 60):
        continue
    p, tick = int(sec // 1800), int(Decimal(price) / Decimal("0.25"))
    lo[p], hi[p] = min(lo.get(p, tick), tick), max(hi.get(p, tick), tick)
counts = {}
for p in lo:
    for tick in range(lo[p], hi[p] + 1):
        counts[tick] = counts.get(tick, 0) + 1
q = Decimal("0.25")
best = max(counts.values())
mid = (min(counts) + max(counts)) / 2
poc = min((t for t in counts if counts[t] == best), key=lambda t: (abs(t - mid), t))
ib_hi, ib_lo = max(hi[0], hi[1]), min(lo[0], lo[1])
print("periods", len(lo), "total_tpos", sum(counts.values()), "poc", poc * q, "poc_tpos", best)
print("high", max(counts) * q, "low", min(counts) * q, "ib_high", ib_hi * q, "ib_low", ib_lo * q)
