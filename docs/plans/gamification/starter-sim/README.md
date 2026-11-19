# Starter simulation

Day-by-day simulator of the sourdough starter rules (ADR-0125, retuned by [ADR-0128](../../../adr/0128-starter-tuning-from-simulation.md)). Prototype only: plain Python, no app imports. T-GS11 ports the scenarios and targets into regression tests against the real `starter_view`.

| File | What |
|---|---|
| `engine.py` | the rules: feed events, fades, state signals, states, milestones, plus every knob tried (`BASE_TUNING` = ADR-0125 as written) |
| `scenarios.py` | 16 users (12 tuned + `s13` added in round 2 + 3 held back `h1`–`h3`) and their targets as checks |
| `tunings/*.json` | overrides per cycle: `c0` baseline, `c1`–`c5` round 1, `d1`/`d3` round 2 (final = `d3`), `d4h10` rejected |
| `run.py` | `python3 run.py d3 --holdout` runs every scenario, prints misses, writes `results/d3.json`; `SEEDS=100` for the final numbers |
| `gen_report.py` | builds `report.html` (charts per user, before/after) from `results/` |
| `predictions.md` | what I expected from the baseline before running it |

Run from this directory: `SEEDS=100 python3 run.py c0 --holdout && SEEDS=100 python3 run.py d3 --holdout && python3 gen_report.py` (the report also needs `c1`–`c5`, `d1`, `d4h10` results).

## Targets (set by the user, 2026-11-19)

| # | User | Target |
|---|---|---|
| s1 | Careful, no goals | ≥ bubbly after month 1, rising 40–70 %, never overflowing |
| s2 | Careful with goals | rising 60–80 %, overflowing 10–30 %, never below bubbly after month 1 |
| s3 | Power user | overflowing ≥ 60 %, never below rising |
| s4 | New user, clean | rising+ weeks 1–2, no sleepy weeks 3–4, rising+ from month 2 |
| s5 | New user, messy | mostly bubbly, dormant < 5 % |
| s6 | Frugal (many no-spend days) | same band as s2 ± 1 |
| s7 | Existing user at launch | awake at launch, overflowing ≤ 3 days, at s2's level within 3 weeks |
| s8 | Holiday (14 days away) | ≤ sleepy in week 1 away, dormant only near day 14, bubbly 1 day after return, rising within a week |
| s9 | Drops out | sleepy within ~3 weeks, dormant after 14 days, stays dormant |
| s10 | Diligent, always over budget | bubbly to low rising, never sleepy, never overflowing |
| s11 | Monthly catch-up | mostly sleepy/bubbly |
| s12 | Goals only | bubbly to low rising |
| s13 | Very frugal (~1 purchase a week) | same band as s2 ± 1, rising+ ≥ 60 % |
| h1 | 6 accounts | same as s2, overflowing ≤ 35 % |
| h2 | Weekend logger | at most one band below s2 |
| h3 | Point farmer | never overflowing, rising ≤ 10 % |

Every scenario also checks ≤ 1 A→B→A bounce within 3 days per 30 days (accepted miss: h2).

## Result

Baseline 27/47 tuning checks; final (`d3`, 100 seeds) 47/47, held back 7/8. Details and the cycle log: ADR-0128 and the published report.
