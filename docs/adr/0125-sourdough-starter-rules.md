# ADR-0125: The Sourdough Starter — Feed Signals, Health Score, Milestones, Shelf

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: [ADR-0011](0011-derived-balance-snapshots-reconciliation.md) (a zero-delta reconcile records a snapshot instead of failing; F2.5)
- **Relates to**: [ADR-0124](0124-savings-goals-envelopes-and-net-worth.md) (goals, allocations), [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md) (animation stack), [ADR-0126](0126-gamification-design-handoff.md) (art and UI source), [ADR-0019](0019-soft-delete-and-audit-log.md), [ADR-0021](0021-functional-style-no-oop.md), [ADR-0025](0025-user-preferences-and-income-anchor.md) (preferences), [ADR-0041](0041-budget-period-anchor-window.md) / [ADR-0064](0064-plan-default-fiscal-month.md) (fiscal period), [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md), requirements §12

## Context

- §12 describes a Tamagotchi-style sourdough starter fed by good money habits, on top of savings goals (ADR-0124). The product is *Rising Dough*, and the redesign is sourdough-themed.
- Money and guilt mix badly: people who feel bad about their finances stop opening the app. The mechanic must reward the right behaviour (consistency, accuracy, saving) and never spending, transaction volume or daily compulsion.
- A no-spend day has nothing to log. A logging habit must not punish it.
- v4 has no background jobs that see decrypted data while the user is offline, so all state must be computable at render time during a session.

## Decision

### 1. Derived health, rolling score

Health is computed by a pure function at render time:

```
starter_view(events, state_signals, today) -> StarterView(health, state, recent_feeds)
```

- Every **feed event** has a date, a kind and points. Its contribution fades **linearly to 0** over the kind's fade window, counted from the event date.
- **State signals** add a constant while true.
- `health = min(100, Σ live event points + Σ true state signals)`.
- Constants live in one module (`domain/starter_tuning.py`). The values below are the **starting tuning**, to be revisited after about a month of real use.

### 2. Feed signals (starting tuning)

| Signal | Type | Points | Fade | Definition |
|---|---|---|---|---|
| Saving week | event, ≤ 1 per ISO week | 25 | 14 d | Net Σ of the week's allocation events (ADR-0124), valued in base currency at today's FX, is > 0. Dated at the week's last allocation. Amount-agnostic. |
| Check-in day | event, ≤ 1 per day | 4 | 7 d | Day D has any user ledger entry with `operation_date = D` (created or promoted; system reconciliation adjustments excluded), **or** a "nothing to log" check-in row for D. Counted by operation date whenever it was recorded; backfilled days older than the fade window contribute nothing. |
| Accurate reconcile | event, ≤ 1 per account per day | 10 | 30 d | A reconcile whose `abs(delta) ≤ 1 %` of the actual balance, including a zero-delta reconcile (§7). |
| Accounts in sync | state | 15 | — | Every active, non-liability account has `last_checked` within 30 days (existing `services.accounts` semantics). False when there are no such accounts. |
| Nothing overdue | state | 15 | — | No unpromoted planned row and no active recurring `next_due` older than today − 3 days. |
| Within budget | event, ≤ 1 per fiscal period | 30 | 30 d | Closed fiscal period (ADR-0041) with total budget > 0 and total expenses (base currency) ≤ `min(baseline, final total)` (§5). Total, not per category. Dated at period end. |
| Net-worth growth | event, ≤ 1 per fiscal period | 20 | 30 d | Closed fiscal period whose net worth at end > at start, **both valued at the period-end FX rates** (strips currency swings). All users. Dated at period end. |
| Setup milestone | event | 10 | 14 d | §4, milestones 1–10. |
| Achievement | event | 30 | 30 d | §4, milestones 12–14. |
| Goal reached | event | 40 first ever, 20 later | 30 d | `goals.first_reached_at` (ADR-0124). First goal reached is also milestone 11. |
| Welcome | event, once | 30 | 14 d | §6. |

Nothing feeds on spending, on transaction counts beyond one per day, or on amounts saved.

### 3. States

| State | Rule |
|---|---|
| `dormant` | no **event** in the last 14 days, regardless of score (state signals alone cannot keep it awake) |
| `sleepy` | health < 25 |
| `bubbly` | 25–49 |
| `rising` | 50–79 |
| `overflowing` | ≥ 80 |

There is no death and no negative event. Any event ends dormancy. A user doing everything sits around 80–90.

### 4. Milestones

One-time, per user, **persisted** in `starter_milestones(user_id, milestone, unlocked_at, retro, announced_at)` (plaintext enum and timestamps, soft delete + audit), so deleting the source row does not revoke a milestone.

- Setup: (1) first account, (2) first own (non-system) category, (3) first ledger entry, (4) first recurring rule, (5) first planned payment, (6) first budget set, (7) first reconciliation, (8) first goal, (9) first allocation, (10) passkey added.
- Achievements: (11) first goal reached, (12) first fiscal period within budget (§5 rule), (13) first "nothing to log" check-in, (14) four consecutive healthy ISO weeks. A week is *healthy* when it holds events of at least three distinct signal kinds; this is computable from history without replaying state signals.
- **Detection** runs at render (`services.starter.sync_milestones`): conditions satisfied by current data and not yet persisted are written once. Idempotent, unique `(user_id, milestone)`.

### 5. Budget baseline (anti-gaming)

- Raising the budget after a period has started must not let it be "met".
- `budget_period_baselines(user_id, year, month, total_amount, created_at)`, unique `(user_id, year, month)`, written **once**: on any budget write (default, recurring override, one-off override) that changes the resolved total of a fiscal month whose period has already started, the service first stores the pre-change total if no baseline exists.
- Met means `spent ≤ min(baseline, final total)`. No mid-period edit means no row, and the final total stands. Decreases always count, because `min`.
- The alternative of rebuilding the start-of-period total from `audit_log` was rejected as fragile; v4 also encrypts audit payloads.

### 6. Existing users at launch

- On a user's first starter compute (`starter_state` row absent): milestones already satisfied by data are unlocked **retroactively** with their original dates (`retro = true`, 0 points), plus one **welcome** event (+30) so the starter starts awake.
- `starter_state(user_id, launched_at, welcomed_at, last_seen_feed_at)` holds UI bookkeeping only, never health.

### 7. Zero-delta reconcile (amends ADR-0011, F2.5)

A reconcile where `actual == derived` no longer raises `NoAdjustmentNeededError` to the user. It records an `account_snapshots` row with the new plaintext column `source = 'reconcile'` (existing rows: `'manual'`). The UI says "Already in sync". `last_checked` already counts snapshots.

### 8. Check-in

- `starter_checkins(user_id, day, created_at, deleted_at)`, unique live `(user_id, day)`. `POST /starter/checkins` with `day ≤ today` (any past day; points follow §2 fade). Undo via soft delete. Audited.
- The check-in control shows "done" for a day already covered by a ledger entry.

### 9. Bakery shelf

Every goal with `first_reached_at` gets a loaf (goal colour, shape picked deterministically from the goal id), kept even if the goal is archived or later drops below target. Soft-deleting a goal removes its loaf. No other progression: no levels, no jar growth.

### 10. Placement, feedback, opt-out

- `/today` starter card: state, name, state line, recent feeds (from the same events), the check-in control.
- Rail badge on every full page: a small state glyph linking to the starter detail (milestones, longer feed list).
- Mutations that can feed (allocation, reconcile, transaction create/promote, check-in, budget write, goal edit) send `HX-Trigger: starter-changed`. The badge refetches `GET /starter/badge`, which syncs milestones and returns the badge with `data-fed` when an event newer than `last_seen_feed_at` exists. Unannounced milestones come back as an out-of-band toast, and `announced_at` is set. Routine feeds animate only and never toast.
- Preferences (ADR-0025): `show_starter` (default on) hides card, badge and toasts. Goals and the shelf stay. Health and milestones keep computing while hidden. `starter_name` holds the user's name for it (designer supplies the default; the value is encrypted under v4 like every preference value).
- Animation follows ADR-0123 (CSS/SVG/WAAPI, transform and opacity, reduced motion). Art comes from the handoff (ADR-0126).

### 11. Encryption and isolation

- Encrypted: `budget_period_baselines.total_amount`, `user_preferences.value` (already). Everything else in this ADR is plaintext metadata (enums, dates, timestamps, FKs).
- If the starter lands before v4 Phase 3, `budget_period_baselines.total_amount` joins T-E08/T-E09/T-E12.
- All tables are per user and user-scoped (ADR-0061, ADR-0068 static check).

## Rationale

- A fading-points score is forgiving and smooth, and one rule covers habits and milestones. Recent feeds make it legible.
- Counting check-in days by operation date with a short fade is lenient for real use, and still makes backfilling a whole month worthless.
- Total-budget adherence with a write-once baseline rewards the real habit and closes the "raise it mid-month" loophole without storing derived state.
- Comparing net worth at the same FX rewards accumulation, not currency luck.
- Persisting only milestones, check-ins, baselines and UI bookkeeping keeps everything else derived: no backfill jobs, no drift, and corrections show up automatically.

## Consequences

- New tables: `starter_milestones`, `starter_checkins`, `starter_state`, `budget_period_baselines`; new column `account_snapshots.source`.
- New `domain/starter*.py` (pure scoring), `services.starter`, `/starter/*` routes, a badge in the base layout, a Today card, preferences.
- Budget write paths gain the baseline step; reconcile gains the zero-delta branch (F2.5 text updated).
- The badge adds a starter compute to every full-page render. It must stay within the §10.2 and v4 render budgets. Events read are bounded to the last 30 days, plus closed-period aggregates.
- Weights will change after tuning. They are constants, not schema.

## Alternatives considered

- **Hunger clock (time since last feed).** Rejected: every feed is worth the same, and it pushes daily interaction.
- **Weekly checklist.** Rejected: monthly signals fit badly and the state jumps at week boundaries.
- **Logging on N distinct days by creation day.** Rejected: punishes no-spend days and real-life backdating.
- **Starter levels / jar growth.** Rejected: rewards grind over outcomes. The shelf ties progression to reached goals.
- **Retro milestones with full points.** Rejected: a meaningless two-week "overflowing" burst at launch.
- **Net-worth growth only for users with a net-worth goal.** Rejected: users without envelopes would lose their only saving-like signal.
