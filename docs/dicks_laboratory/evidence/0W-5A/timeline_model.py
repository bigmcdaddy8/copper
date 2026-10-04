"""0W-5A event-driven writer timeline model for the 2026-09-30 burst (evidence script).

Usage: python timeline_model.py <path/to/es_20260930_9ac5a21e.sqlite3>

Replays the authentic per-event arrival times (received_at, 19:30-20:40Z) with
the 19:59-20:01Z window optionally scaled 1.5x/2x. The writer takes
min(queued, cap) per batch; commit time = CPU 0.23 ms/event + device writes at
603 IOPS, where writes/event vs batch size is interpolated from the measured
benchmark points in bench_*.json (DELETE journal, synchronous=FULL). The last
block models the WAL commit path (bench_c8) with checkpoints kept off the burst.
"""

import sqlite3
import bisect
import math
import json
import sys
from datetime import datetime

c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)


def ts(s):
    return datetime.fromisoformat(s).timestamp()


base = [
    ts(r[0])
    for r in c.execute(
        "SELECT received_at FROM observation_source_provenance WHERE received_at>='2026-09-30T19:30' AND received_at<'2026-09-30T20:40' ORDER BY source_order"
    )
]
W = (ts("2026-09-30T19:59:00+00:00"), ts("2026-09-30T20:01:00+00:00"))


def scaled(a, f):
    out = []
    carry = 0.0
    for t in a:
        if W[0] <= t < W[1]:
            carry += f
            k = int(carry)
            carry -= k
            out.extend([t] * k)
        else:
            out.append(t)
    return out


# measured burst-phase device writes/event vs average batch size (DELETE journal, synchronous=FULL)
PTS = [(250, 2.7234), (1978, 2.366), (8063, 1.6433), (14973, 1.2154), (26203, 0.6874)]


def w_per_event(n):
    if n <= PTS[0][0]:
        return PTS[0][1]
    for (n0, w0), (n1, w1) in zip(PTS, PTS[1:]):
        if n <= n1:
            f = (math.log(n) - math.log(n0)) / (math.log(n1) - math.log(n0))
            return w0 + f * (w1 - w0)
    return PTS[-1][1]


IOPS = 603
CPU = 0.00023
FIXED = 8


def service(n):
    return CPU * n + max(FIXED, w_per_event(n) * n) / IOPS


def sim(a, cap, interval=0.1):
    i = 0
    n = len(a)
    t = a[0]
    qmax = 0
    lagmax = 0
    sizes = []
    while i < n:
        t = max(t, a[i])
        avail = bisect.bisect_right(a, t, lo=i) - i
        if avail <= 1:  # idle: timer window collects arrivals for `interval`
            j = bisect.bisect_right(a, t + interval, lo=i)
            j = min(max(j, i + 1), i + cap)
            start = max(t, a[j - 1])
        else:
            j = i + min(avail, cap)
            start = t
        qmax = max(qmax, bisect.bisect_right(a, start, lo=i) - i)
        end = start + service(j - i)
        lagmax = max(lagmax, end - a[i])
        sizes.append(j - i)
        i = j
        t = end
    return qmax, lagmax, max(sizes)


for f in (1.0, 1.5, 2.0):
    a = scaled(base, f)
    for cap in (250, 2000, 10000, 20000, 50000):
        q, lag, m = sim(a, cap)
        print(
            json.dumps(
                {
                    "scale": f,
                    "cap": cap,
                    "queue_peak": q,
                    "pct_of_50k": round(100 * q / 50000, 1),
                    "max_lag_s": round(lag, 1),
                    "largest_batch": m,
                    "overload": q >= 50000,
                }
            )
        )
print(
    "--- WAL commit path (checkpoint deferred off-burst): per event CPU 0.17 ms + 10.5 KB at 100 MB/s; 3 fsyncs x 5 ms per commit"
)


def service_wal(n):
    return n * (0.00017 + 10.5e3 / 100e6) + 0.015


def sim2(a, cap, svc, interval=0.1):
    i = 0
    n = len(a)
    t = a[0]
    qmax = 0
    lagmax = 0
    while i < n:
        t = max(t, a[i])
        avail = bisect.bisect_right(a, t, lo=i) - i
        if avail <= 1:
            j = bisect.bisect_right(a, t + interval, lo=i)
            j = min(max(j, i + 1), i + cap)
            start = max(t, a[j - 1])
        else:
            j = i + min(avail, cap)
            start = t
        qmax = max(qmax, bisect.bisect_right(a, start, lo=i) - i)
        end = start + svc(j - i)
        lagmax = max(lagmax, end - a[i])
        i = j
        t = end
    return qmax, lagmax


for f in (1.0, 1.5, 2.0):
    q, lag = sim2(scaled(base, f), 2000, service_wal)
    print(
        json.dumps(
            {
                "scale": f,
                "wal_cap": 2000,
                "queue_peak": q,
                "pct_of_50k": round(100 * q / 50000, 1),
                "max_lag_s": round(lag, 1),
            }
        )
    )
