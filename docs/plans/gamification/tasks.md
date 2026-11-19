# Savings Goals + Sourdough Starter — Tasks

> Plan: [README.md](README.md). Decisions: [ADR-0124](../../adr/0124-savings-goals-envelopes-and-net-worth.md), [ADR-0125](../../adr/0125-sourdough-starter-rules.md), [ADR-0126](../../adr/0126-gamification-design-handoff.md). Requirements: §12 (G1.x, S1.x).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-GSxx` depends on upstream task.
> Acceptance = ADR referenced in the commit + tests (TDD, coverage gate 90 %) + pre-commit green + `✅` prefix here + dated `docs/CHANGELOG.md` line. Templates, CSS or HTMX swaps touched → `frontend-visual-audit` at 1440 / 1024 / 375, both themes, before ✅.

---

## Phase 0 — Entry

### ◻ T-GS00 [S] Entry gate
- Redesign released (T-UR17 ✅).
- Decide and record the order against v4 (before or after v4 Phase 3) in README.md.
- Work branch `feat/goals` from `main`.
- Designer drop 1 status recorded (requested / delivered / accepted).

## Phase 1 — Goals backend (release 1)

### ◻ T-GS01 [S] Schema: `goals`, `goal_allocations` → T-GS00
- Migration per ADR-0124 §2, §6. Soft delete + audit (ADR-0019). User-scoped (ADR-0068 static check).
- Columns ciphertext-ready per ADR-0124 §9: if v4 Phase 3 is done, create them encrypted; otherwise plaintext, and T-GS03 adds them to the v4 plan.
- `goal_allocations.amount` signed; schema comment cites ADR-0124 §2 next to the ADR-0008 exception.

### ◻ T-GS02 [P] Domain: goal progress, free balance, projection → T-GS01
- Pure functions: `envelope_progress`, `free_balance`, `over_allocation`, `required_per_month`, `trailing_pace(90 d)`, `eta`, `reached`.
- Unit tests for FX conversion (latest rate), multi-account, release, over-allocation, zero pace, past deadline.

### ◻ T-GS03 [P] v4 alignment → T-GS01
- If goals land before v4 Phase 3: add the goal columns to ADR-0081 §1 (amendment) and to T-E08 / T-E09 / T-E12 in `docs/plans/v4/tasks.md`.
- If after: confirm the tables were created through the v4 repository helpers. Docs-only task.

### ◻ T-GS04 [S] Services + repositories: goals and allocations → T-GS02
- `services.goals`: create / edit / reorder / archive (auto-release, ADR-0124 §5) / delete; allocate / release with the write-time 422 rules (asset only, free ≥ 0, release ≤ allocated); `first_reached_at` stamping on read paths that compute progress.
- Net-worth goals: progress from `services.fortune.compute_fortune`; projection from `services.forecast` at the deadline month; deadline ≤ 60 months (422).
- `services.today.afford`: warning over the total free balance (G1.10). Existing afford tests unchanged.
- `services.accounts`: allocated / free per asset account, over-allocated flag.

### ◻ T-GS05 [P] Routes + contract tests; demo data → T-GS04
- Routes under `/plan/goals` and `/goals/*` (HTMX fragments; JSON not needed). Contract tests (ADR-0106) for every route, written before the templates exist.
- `data/scripts/build_demo_db.py`: seed demo goals and allocations matching the brief's example data. Keep the prod-basename tripwire.

## Phase 2 — Goals UI (release 1, gated on handoff drop 1)

### ◻ T-GS06 [P] Plan → Goals tab, detail, dialogs → T-GS05
- Handoff: `pages/plan/goals*`, goal detail, overlays `new-goal*`, `edit-goal*`, `allocate*`, `release*`, `archive-goal*`.
- UI-map module first (`--target=mockup`), then the per-surface loop (`docs/plans/ui-redesign/README.md`).

### ◻ T-GS07 [P] Accounts: allocated / free, over-allocated → T-GS05
- Handoff: accounts row states with allocation and over-allocation.

### ◻ T-GS08 [P] Today: goals card, afford warning variant → T-GS05
- Handoff: `today` goals card states (0 / 1–3 goals), `today--afford-free` (name per handoff).

## Phase 3 — Release 1

### ◻ T-GS09 [S] Validate and release goals → T-GS06..T-GS08
- `just ci` green in PR CI; `uv run pytest tests/e2e -q --no-cov` locally; visual audit on `/plan?tab=goals`, `/accounts`, `/today`; axe at 375 and 1440, both themes.
- Budgets (§10.2) re-measured. Release through ADR-0099 with a green `drill-gate`. CHANGELOG entry.

## Phase 4 — Starter backend (release 2)

### ◻ T-GS10 [S] Schema: starter tables, baselines, snapshot source → T-GS09
- `starter_milestones`, `starter_checkins`, `starter_state`, `budget_period_baselines` (per category: `category_id`, encrypted `amount`; ADR-0128 §4–§5), `account_snapshots.source` (default `'manual'`). ADR-0125 §4–§8, §11.

### ◻ T-GS11 [P] Domain: pure scoring → T-GS10
- `domain/starter_tuning.py` (all constants from ADR-0125 §2–§3 as amended by ADR-0128: weights, reconcile weekly cap, coverage share, nothing-to-log window, comeback bonus, hysteresis, overflowing gate).
- `domain/starter.py`: event builders (saving week, check-in day, accurate reconcile, within budget, net-worth growth at equal FX, milestones, goal reached, welcome), state signals, `starter_view(...)`, healthy-week rule.
- Scenario regression tests: port the 16 users and targets from `docs/plans/gamification/starter-sim/` onto the real `starter_view` (fixed seeds); all ADR-0128 results must hold.
- Property tests: health stays in 0–100; fade is monotone; no input increases health through spending or transaction count beyond one per day; dormancy ignores state signals.

### ◻ T-GS12 [P] Budget baseline on write paths → T-GS10
- Every budget write (default, recurring override, one-off override, year-grid cell) stores the category's pre-change resolved budget once per (category, started fiscal month); 0 when it had none (ADR-0128 §4). Cap rule tested per category: raise, decrease, new category budget, unused new budget. Existing budget contract tests unchanged.

### ◻ T-GS13 [P] Zero-delta reconcile records a snapshot → T-GS10
- ADR-0125 §7 / S1.10: replace the user-facing `NoAdjustmentNeededError` path with a `source='reconcile'` snapshot and "Already in sync". Update the reconcile contract test deliberately (behaviour change backed by S1.10).

### ◻ T-GS14 [S] `services.starter`: milestones, launch, view → T-GS11, T-GS12, T-GS13
- `sync_milestones` (idempotent detection, retro unlock for first compute, welcome event), `starter_view` assembly over the last 30 days of events + closed-period aggregates, `recent_feeds`, `last_seen_feed_at` bookkeeping.
- Hidden starter still computes (S1.9).
- Performance test: starter compute within budget at 20 000 transactions (§7.2 p95 budget if v4 is live).

### ◻ T-GS15 [P] Routes: check-ins, badge, detail; `starter-changed` trigger → T-GS14
- `POST /starter/checkins`, `DELETE /starter/checkins/{day}`, `GET /starter/badge` (badge + OOB milestone toast), `GET /starter` detail fragment.
- Feeding mutations (allocation, reconcile, transaction create / promote, check-in, budget write, goal edit) send `HX-Trigger: starter-changed`. Contract tests.
- Preferences `show_starter`, `starter_name` (ADR-0025 storage).

## Phase 5 — Starter UI (release 2, gated on handoff drop 2)

### ◻ T-GS16 [S] Accept designer drop 2 → T-GS00
- Starter SVGs (5 states, card + badge, named layers), motion spec, loaf shapes, copy deck, default name. Validator + axe clean. Record deviations in `docs/plans/ui-redesign/derived.md`.

### ◻ T-GS17 [P] Today starter card + check-in → T-GS15, T-GS16
- State, name, state line, recent feeds, check-in control (today + earlier day), dormant variant, welcome moment.

### ◻ T-GS18 [P] Rail badge, starter detail, milestone toast → T-GS15, T-GS16
- Badge in the base layout (desktop rail + phone bar per handoff), `data-state` / `data-fed`, detail overlay with milestones, toast in `#toast-root`.
- Motion per spec: CSS keyframes + a small WAAPI module (ADR-0123); `transform` / `opacity` only; reduced-motion behaviour tested.

### ◻ T-GS19 [P] Bakery shelf + Preferences → T-GS15, T-GS16
- Shelf on the Goals tab (loaf shape from goal id, `data-color` preset, focusable loaves, overflow state). Preferences toggle + name field.

## Phase 6 — Release 2

### ◻ T-GS20 [S] Validate and release the starter → T-GS17..T-GS19
- As T-GS09, plus visual audit on every page (the badge is global) and a reduced-motion pass. JS / CSS budgets re-measured.

### ◻ T-GS21 [S] Tuning review (one month after T-GS20)
- Review real health curves on the demo DB and with the user against the ADR-0128 simulation results. Retune `starter_tuning.py` constants; rerun the simulator and the scenario tests. Record the outcome as an ADR (amending ADR-0128).
