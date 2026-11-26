# Capacity and Performance

> **What**: get the app ready for each distribution stage (friends and family ≤ 10 users, invited influencers ≤ 100, open registration) with cheap serving fixes, monitoring, a measured load baseline, rehearsed resize runbooks and staged deployment and recovery improvements. Performance only; sign-up, email and GDPR are deferred.
> **Decisions**: [ADR-0151](../../adr/0151-capacity-and-scaling-strategy-per-distribution-stage.md) (strategy), [ADR-0152](../../adr/0152-python-upgrade-and-native-arm64-dev-interpreter.md) (Python upgrade, Proposed), [ADR-0153](../../adr/0153-native-hot-paths-via-pyo3.md) (PyO3 hot paths, Proposed). Requirements: [`docs/requirements.md` §13](../../requirements.md#13-capacity-and-performance-added-2026-11-26).
> **Tasks**: [`tasks.md`](tasks.md) (T-SC01…T-SC16).

## Stages and gates

| Gate | Tasks | Why |
|---|---|---|
| Now (cheap, any time) | T-SC01, T-SC02, T-SC07, T-SC08 | Serving fixes and the Python upgrade cost little and help at every stage |
| Before stage 1 (friends and family) | T-SC03, T-SC04, T-SC05, T-SC09 | Know when prod breaks; users can't reach each other's rows; a measured baseline |
| Before stage 2 (influencers) | T-SC06, T-SC10, T-SC11, T-SC15 | Fix what the profile shows; resizing is routine; shorter restores; safe migrations |
| Before v4 Phase 3 (T-E08) | T-SC12 | Postgres yes or no, before the encrypted-column rebuild |
| After the profile, if it backs them | T-SC13, T-SC14 | Native hot paths |
| Before stage 3 (open registration) | T-SC16 | Full load test, scalability plan, blue/green, warm standby, static landing |

```
now: T-SC01 T-SC02 T-SC07 → T-SC08
stage 1: T-SC03 T-SC04 T-SC09 ; T-SC05 → T-SC06 → (T-SC13 → T-SC14)
stage 2: T-SC10 → T-SC11 ; T-SC15 ; T-SC12 (before T-E08)
stage 3: T-SC16
```

## Deferred until a measurement asks for them (ADR-0151 §11)

ETag/304 conditional responses, smaller HTMX swaps, a minijinja engine switch, uvicorn workers before a bigger box, a load-triggered registration queue (last resort, ADR-0151 §8), autoscaling.

## Guardrails

- **No load or profiling against prod.** k6 and py-spy run against an explore drill (ADR-0099; one drill run at a time).
- **Numbers are measured, never assumed.** Every capacity claim cites `baseline.md` (written by T-SC05).
- **Docs first** for each stack change: ADR-0152 and ADR-0153 are accepted only when their probe or pilot passes.
