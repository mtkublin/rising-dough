# Code-Quality Audit — Findings Register

> Deliverable 1. Skeleton only. Filled in during T-Q01…T-Q12.
> Schema, severity rubric and root-cause classes: [implementation_plan.md §4–§5](implementation_plan.md#4--finding-schema).
> All `path:line` references are valid at `AUDIT_SHA` only.

## Audit metadata

| Field | Value |
|---|---|
| `AUDIT_SHA` | `9fb18cbca26ef305855efc8fc106d896edc82631` (tip of `main` = tip of `audit/quality`) |
| Date | 2026-11-19 |
| Python / tool versions | Python 3.12.13; ruff 0.17.2; mypy 2.4.0; pytest 9.1.1; sqlfluff 4.4.0; djlint 1.47.0; bandit 1.9.4; detect-secrets 1.5.0 |
| LOC per package | Lines (files) under `src/budget_planner`: `domain` 1,283 (16); `services` 7,263 (32); `repositories` 3,563 (18); `web/routers` 6,114 (20); `web/templates` 6,022 (111); `web/static` 8,488 (44); `db` 752 (6); `adapters` 0 (3, empty); `cli` 155 (2). Package total (.py) 22,254 (120). `tests/` (.py) 39,158 (232). |
| `just ci` at SHA | Green: ruff, mypy (352 files) clean; 2637 passed, 17 skipped in 423.00s (pytest), 8:52.96 wall for the whole `just ci` (`PYTEST_WORKERS=2`); coverage 94.70% (gate 90%). Raw output: `baseline/ci.txt`, per-module table: `baseline/coverage.txt` |
| Scratch DB | `/tmp/audit.sqlite` (copied from `data/demo.sqlite`; migrations not needed) |
| Status | Phase 1 in progress |

## Summary

_Counts by severity × track, top 10 by risk, root-cause histogram (T-Q11)._

## Register

| ID | Severity | Confidence | Track / root cause | Title | Location(s) | Mitigation (best) |
|---|---|---|---|---|---|---|
| _Q-001_ | | | | | | |

## Details

<!-- One section per finding:

### Q-### — <title>
- **Severity / Confidence:** …
- **Track / root cause:** …
- **Location(s):** `path:line`, …
- **Description:** …
- **Evidence:** …
- **Impact:** …
- **Mitigation:** …
- **Alternatives:** (only if genuinely open)
- **Effort:** S / M / L
- **Related:** ADR-…, Q-…
-->

## Dismissed

_Findings rejected in verification, with reasons._
