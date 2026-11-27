# Faster CI

> **What**: cut CI and local check time with parallel tests, slow-test fixes, and change-based checks in the inner loop, while every gate keeps running the full suite.
> **Decision**: [ADR-0108](../../adr/0108-faster-ci-parallel-tests-and-change-based-inner-loop.md). Requirements: [`docs/requirements.md` §11](../../requirements.md#11-faster-ci-added-2026-11-16).
> **Tasks**: [`tasks.md`](tasks.md) (T-CS01…T-CS09; proposed T-CS10…T-CS17 from the [2026-11-27 check audit](check-audit-2026-11-27.md)). Local gate policy: [ADR-0120](../../adr/0120-pre-commit-is-the-local-gate.md). Required checks: [ADR-0121](../../adr/0121-path-filtered-workflows-are-not-required-checks.md).

## When

After v3 ships and **before the quality audit pins its commit** (T-Q01), so the audit reviews the new test and CI setup, and every later effort (audit remediation, UI test harness, redesign) gets the speed-up.

```
v3 ships ─ faster CI (T-CS01..T-CS06) ─ quality audit ─┬─ [pre-v4-P3] remediation ─┐
                                                       └─ UI test harness ─────────┴─ redesign ─ v4 Phase 2
```

## Baseline (2026-11-16)

| Measure | Value |
|---|---|
| GitHub `ci` job | about 5 min, of which the `just ci` step about 4 min 40 s and setup about 15 s |
| Tests collected | 2,006 (16 deselected) |
| xdist | installed, unused |
| Developer machine | 8 cores |

T-CS01 re-measures these, plus local `just ci`, the pre-commit hook and a typical item-agent check, as the reference for T-CS06.

## Targets

| Measure | Target |
|---|---|
| GitHub `ci` job | under 2 min |
| Local full `just ci` (8 cores, idle) | at least 3× faster than baseline |
| Pre-commit hook on a small diff | under 15 s |
| `just test-changed` on a one-module diff | under 30 s |
| Coverage gate | unchanged: 90%, measured on the full suite |

## Guardrails

- **The full gate is PR CI** (ADR-0120, amending ADR-0108 §4). Locally, the pre-commit hooks are the gate: affected tests across the whole suite, the full suite for changes testmon cannot see.
- **Tools' own mechanisms first** (pre-commit `--from-ref`, mypy cache, testmon, xdist). Custom code is limited to the fallback path list and recipe glue in the `justfile`.
- **No behaviour changes in `src/`.** Test speed-ups that need a production-code hook (for example a configurable hasher cost) go through settings that default to production values, with a test proving the default.
- **Prod DB hands off.** Profiling and test runs use the existing temp DBs only.
- Each task records before/after timings in its handoff.
