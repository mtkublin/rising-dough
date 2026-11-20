"""T-Q06 repro: clock/time-format edges. Pure stdlib + sqlite3, no app DB.

Run: uv run python docs/plans/quality-audit/repro/C/repro_clock.py
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo

print("== K1: date.today() follows the PROCESS tz, not settings.display_timezone ==")
instant = dt.datetime(2026, 6, 30, 22, 30, tzinfo=dt.UTC)  # 00:30 on 1 July in Warsaw
ts = instant.timestamp()
for tz in ("UTC", "Europe/Warsaw"):
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", f"import datetime as d; print(d.date.fromtimestamp({ts}))"],
        env={**os.environ, "TZ": tz},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"TZ={tz:14} date.fromtimestamp(22:30Z)={out}  (date.today() uses the same rule)")
print("display tz says   :", instant.astimezone(ZoneInfo("Europe/Warsaw")).date())
print("=> on a UTC process, naive date.today() lags Warsaw by one day from 00:00 to 01:00/02:00 local")

print("\n== K2: soft-delete retention window compares 'T' timestamps with datetime('now') ==")
db = sqlite3.connect(":memory:")
cutoff = db.execute("SELECT datetime('2026-11-19 12:00:00', '-90 days')").fetchone()[0]
deleted_at = "2026-08-21T00:00:01.000Z"  # stored format: strftime('%Y-%m-%dT%H:%M:%fZ','now')
print("cutoff (datetime(...,'-90 days')):", cutoff)
print("deleted_at                       :", deleted_at)
print("deleted_at > cutoff ->", db.execute("SELECT ? > ?", (deleted_at, cutoff)).fetchone()[0],
      "(row is 90d 12h old and still listed: 'T' sorts after ' ')")

print("\n== K3: mixed timestamp precision (SQL %f = ms, Python %f = us) ==")
a = db.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', '2026-11-19 10:00:00.123')").fetchone()[0]
b = dt.datetime(2026, 11, 19, 10, 0, 0, 123456, tzinfo=dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
print("sql   :", a)
print("python:", b)
print("sql > python as strings:", a > b, "(10:00:00.123 < 10:00:00.123456 in time)")
