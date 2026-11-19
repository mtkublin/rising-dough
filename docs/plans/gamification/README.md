# Savings goals + sourdough starter (gamification)

> **What**: savings goals (envelope allocations and net-worth goals), then a sourdough starter that rewards good money habits, with a bakery shelf of reached goals.
> **Requirements**: [`docs/requirements.md` §12](../../requirements.md#12-savings-goals--sourdough-starter-added-2026-11-17-scoped-2026-11-18).
> **Decisions**: [ADR-0124](../../adr/0124-savings-goals-envelopes-and-net-worth.md) (goals), [ADR-0125](../../adr/0125-sourdough-starter-rules.md) (starter), [ADR-0126](../../adr/0126-gamification-design-handoff.md) (designer handoff), [ADR-0129](../../adr/0129-goals-starter-handoff-vendored-standalone.md) (handoff vendored standalone, one drop), [ADR-0123](../../adr/0123-frontend-stays-server-rendered-no-spa-framework.md) (stack, no SPA).
> **Designer brief**: [`docs/design/gamification-brief.md`](../../design/gamification-brief.md) (shared with the designer as a page).
> **Designer handoff**: [`docs/design/rising-dough-goals-starter/`](../../design/rising-dough-goals-starter/index.html) (both drops, delivered 2026-11-19; acceptance at T-GS00 / T-GS16).
> **Tasks**: [`tasks.md`](tasks.md) (T-GS00…T-GS21).
> **Status**: scoped 2026-11-18. Not started. Designer handoff for both releases delivered and vendored 2026-11-19 (not yet accepted).

## Sequencing

```
redesign released (T-UR17) ─┬─ R1 goals backend ── R1 goals UI ── R1 release ─┬─ R2 starter backend ── R2 starter UI ── R2 release
                            │                         ▲                         │                           ▲
designer: brief ─ drops 1 + 2 delivered together 2026-11-19 (ADR-0129); accepted per release ───────────────────┘
v4: before or after, either way (schema is v4-ready; see "Encryption" below)
```

- Code starts after the redesign is released (§10.4 freezes features during the migration).
- The order against v4 is open. If goals land before v4 Phase 3, the goal columns are added to T-E08 / T-E09 / T-E12 (task T-GS03 records that in the v4 plan).
- Backend tasks are not gated on the designer. UI tasks wait for the accepted handoff drop (ADR-0126 §7); both drops arrived as one folder, accepted per release (ADR-0129 §3).

## Phases

| Phase | Tasks | What | Gate |
|---|---|---|---|
| 0 — Entry | T-GS00 | preconditions, branch, handoff drop status | redesign released |
| 1 — Goals backend | T-GS01..T-GS05 | schema, domain, services, afford warning, routes + contract tests | contract tests green |
| 2 — Goals UI | T-GS06..T-GS08 | Goals tab and dialogs, Accounts + Today additions | handoff drop 1 accepted |
| 3 — R1 release | T-GS09 | validation, release | `drill-gate` green |
| 4 — Starter backend | T-GS10..T-GS15 | tables, pure scoring, milestones, baseline, zero-delta reconcile, check-in + badge routes | contract tests green |
| 5 — Starter UI | T-GS16..T-GS19 | starter card, badge + detail, shelf, preferences, motion | handoff drop 2 accepted |
| 6 — R2 release | T-GS20..T-GS21 | tuning hooks, validation, release | `drill-gate` green |

## Design summary

### Goals (ADR-0124)

- **Kinds**: `envelope` (earmark money in real asset accounts, many goals per account, many accounts per goal) and `net_worth` (the existing fortune `net_base`).
- **Allocations**: dated event ledger, + allocate / − release, soft delete + audit. Rejected if they would make an account's free balance negative. Later shortfalls are flagged ("over-allocated", "unbacked"), never auto-shrunk.
- **Currency**: goal currency, latest FX.
- **Projection**: net worth from the fortune forecast at the deadline (≤ 60 months); envelopes from required pace and the trailing 90-day pace / ETA.
- **Lifecycle**: reached is derived (first reach persisted); archive releases remaining allocations; no recurring allocations.
- **Placement**: Plan → Goals tab, Today card, allocated/free on Accounts, afford warning over free balance.

### Starter (ADR-0125)

- **Health** 0–100 from fading feed events + state signals, computed at render. Tuning from simulation (ADR-0128) in `domain/starter_tuning.py`; simulator and scenarios in [`starter-sim/`](starter-sim/README.md).
- **Signals**: saving week, check-in day (entry or "nothing to log"), accurate reconcile, all accounts in sync, nothing overdue, within total budget (baseline-protected), net-worth growth at equal FX, milestones, goal reached, welcome.
- **States**: dormant / sleepy / bubbly / rising / overflowing (overflowing only while actively saving). Hysteresis, comeback bonus. No death.
- **Persisted**: milestones, check-ins, budget baselines, starter UI bookkeeping. Everything else is derived.
- **Feedback**: `HX-Trigger: starter-changed` → badge refetch → `data-fed` animation; milestone toasts only.
- **Opt-out**: hide toggle, user-named starter.

### Encryption (v4, §7.2)

| Table | Encrypted | Plaintext |
|---|---|---|
| `goals` | `name`, `target_amount`, `note` (+ `name_bidx` blind index) | ids, `kind`, `currency`, `color`, `deadline`, `sort_order`, `first_reached_at`, `archived_at`, timestamps |
| `goal_allocations` | `amount` | ids, FKs, `op_date`, timestamps |
| `budget_period_baselines` | `amount` | ids, `category_id`, `year`, `month`, timestamps |
| `starter_milestones`, `starter_checkins`, `starter_state` | — | all (enums, dates, timestamps) |
| `account_snapshots.source` | — | enum |
| preferences `show_starter`, `starter_name` | `value` (as all preferences) | key |

## Guardrails

- **Docs first** (CLAUDE.md): any change to a rule here goes through ADR-0124/0125 (amend or supersede) before code.
- **UI from the handoff only** (ADR-0126, ADR-0107). Never invent markup or art; missing states go back to the designer.
- **Contract tests first** for every new route; the redesign's per-surface loop for every new screen.
- **Never reward spending or volume.** Any new signal must be reviewed against ADR-0125's principles in an ADR amendment.
- **Prod DB hands off.** Scratch DBs or `data/demo.sqlite` only. The demo builder (`data/scripts/build_demo_db.py`) gets goals and allocations so demos have data (T-GS05).
- **Frontend validation**: `frontend-visual-audit` at 1440 / 1024 / 375 on every touched route, both themes.
- **Release** only through the ADR-0099 pipeline; each release needs a green `drill-gate`.
- **Orchestrator mode** (ADR-0066) is optional for Phases 1 and 4 (`[P]` tasks are conflict-free).

## Open items (not blocking)

- Weights and thresholds are tuned by simulation (ADR-0128); T-GS21 records the first review after a month of R2 use.
- Order against v4: decide when the redesign ships.
- Designer handoff delivered 2026-11-19; acceptance (validator + axe) tracked in T-GS00 (goals) and T-GS16 (starter).
