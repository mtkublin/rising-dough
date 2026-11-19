"""python run.py <cycle> — runs all scenarios with tunings/<cycle>.json, writes results/<cycle>.json."""

from __future__ import annotations

import copy
import json
import os
import statistics
import sys
from pathlib import Path

from engine import BASE_TUNING, RANK, STATES, simulate
from scenarios import SCENARIOS, checks_for, mean_band


SEEDS = int(os.environ.get("SEEDS", 20))
HERE = Path(__file__).parent


def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))]


def run(cycle: str, include_holdout: bool):
    tfile = HERE / "tunings" / f"{cycle}.json"
    tuning = deep_merge(BASE_TUNING, json.loads(tfile.read_text()) if tfile.exists() else {})
    runs = {}
    for sc in SCENARIOS:
        if sc.holdout and not include_holdout:
            continue
        runs[sc.key] = [simulate(sc, tuning, s) for s in range(SEEDS)]
    out = {"cycle": cycle, "tuning": tuning, "scenarios": {}}
    total = passed = 0
    for sc in SCENARIOS:
        if sc.key not in runs:
            continue
        rs = runs[sc.key]
        days = len(rs[0]["health"])
        med_h = [statistics.median(r["health"][d] for r in rs) for d in range(days)]
        p10_h = [pct([r["health"][d] for r in rs], 0.1) for d in range(days)]
        p90_h = [pct([r["health"][d] for r in rs], 0.9) for d in range(days)]
        share = {s: statistics.mean(sum(1 for x in r["states"][30:] if x == s) / (days - 30) for r in rs) for s in STATES}
        res = []
        for label, fn, lo, hi, agg in checks_for(sc.key):
            if agg.startswith("cmp"):
                ref = agg.split(":")[1]
                a = statistics.median(mean_band(r["states"], 30) for r in rs)
                b = statistics.median(mean_band(r["states"], 30) for r in runs[ref])
                val = (b - a) if agg.startswith("cmpsigned") else abs(a - b)
            else:
                vals = [fn(r) for r in rs]
                val = {"med": statistics.median, "p90": lambda v: pct(v, 0.9), "p10": lambda v: pct(v, 0.1)}[agg](vals)
            ok = lo - 1e-9 <= val <= hi + 1e-9
            total += 1
            passed += ok
            res.append({"label": label, "value": round(val, 3), "lo": lo, "hi": hi, "agg": agg, "ok": ok})
        out["scenarios"][sc.key] = {
            "title": sc.title, "holdout": sc.holdout, "median_health": med_h, "p10": p10_h, "p90": p90_h,
            "share": share, "checks": res,
            "example_states": rs[0]["states"],
        }
    out["passed"], out["total"] = passed, total
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{cycle}.json").write_text(json.dumps(out))
    return out


def report(out):
    print(f"== cycle {out['cycle']}: {out['passed']}/{out['total']} checks pass")
    for key, s in out["scenarios"].items():
        sh = " ".join(f"{k[:4]}={v:.0%}" for k, v in s["share"].items())
        mh = statistics.mean(s["median_health"][30:])
        print(f"{key:4} {s['title'][:30]:30} meanH={mh:5.1f}  {sh}")
        for c in s["checks"]:
            if not c["ok"]:
                print(f"      FAIL {c['label']}: {c['value']} not in [{c['lo']}, {c['hi']}] ({c['agg']})")


if __name__ == "__main__":
    cycle = sys.argv[1]
    report(run(cycle, include_holdout="--holdout" in sys.argv))
