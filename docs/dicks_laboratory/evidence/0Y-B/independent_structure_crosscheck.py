"""0Y-B independent cross-check: one-TPO zones and extremes for TD 2026-09-30, stdlib only.

Same rules as the design doc (30-min periods from 13:30Z, contiguous low..high at
0.25, one TPO per period per price), recomputed straight from SQLite without any
Laboratory code. Usage: python independent_structure_crosscheck.py <db>
"""
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal

con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
start = datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)
lo, hi = {}, {}
for ts, price in con.execute("SELECT event_timestamp, price FROM trade_observations"):
    sec = (datetime.fromisoformat(ts.replace("Z", "+00:00")) - start).total_seconds()
    if 0 <= sec < 390 * 60:
        p, tick = int(sec // 1800), int(Decimal(price) / Decimal("0.25"))
        lo[p], hi[p] = min(lo.get(p, tick), tick), max(hi.get(p, tick), tick)
letters = {}
for p in sorted(lo):
    for tick in range(lo[p], hi[p] + 1):
        letters[tick] = letters.get(tick, "") + "ABCDEFGHIJKLM"[p]
q = Decimal("0.25")
rows = range(min(letters), max(letters) + 1)
singles = [t for t in rows if len(letters.get(t, "")) == 1]
zones, run = [], []
for t in singles:
    if run and t != run[-1] + 1:
        zones.append(run)
        run = []
    run.append(t)
if run:
    zones.append(run)
print("one_tpo_levels", len(singles))
for z in zones:
    print("zone", z[0] * q, z[-1] * q, "rows", len(z), "letters", "".join(sorted({letters[t] for t in z})))
top, bottom = max(letters), min(letters)
print("high", top * q, "letters", letters[top], "low", bottom * q, "letters", letters[bottom])
