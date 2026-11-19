# ADR-0128: Starter Tuning From Simulation

- **Status**: Accepted
- **Date**: 2026-11-19
- **Amends**: [ADR-0125](0125-sourdough-starter-rules.md) §2 (weights, reconcile cap, coverage rule, "nothing to log" rule, comeback bonus), §3 (thresholds, hysteresis, overflowing gate), §5 (per-category baseline), §6 (welcome), §11 (baseline column)
- **Relates to**: [ADR-0124](0124-savings-goals-envelopes-and-net-worth.md), [ADR-0014](0014-budget-flat-no-rollover-three-tier.md) (per-category budgets), [ADR-0041](0041-budget-period-anchor-window.md), requirements §12 (S1.1–S1.4)

## Context

- ADR-0125's weights were a guess. Before any code, we simulated them: 16 user scenarios (careful with and without goals, power user, new users clean and messy, frugal, existing user at launch, holiday, drop-out, diligent but over budget, monthly catch-up, goals only, very frugal, plus 3 held back from tuning: many accounts, weekend logger, point farmer). Each runs 6 months, day by day, with random behaviour over 20–100 seeds, scored with the ADR-0125 rules.
- The user set the targets per scenario. Key ones: a careful user with goals sits mostly in **rising** with **overflowing** peaks; a heavy daily user with many goals sits mostly in **overflowing**; overflowing is for users actively saving; effort counts even when results are bad; quiet (no-spend) days are never penalised.
- With ADR-0125 as written, 27 of 47 tuning checks passed. Findings:
  - Most users were pinned at 100. Accurate reconciles stacked per account (6 accounts or daily zero-delta reconciles alone held ~100), and the two state signals gave 30 free points.
  - **Abandoned starters woke up monthly**: a user who stops logging shows 0 spent, so the period counts as "within budget".
  - Existing users got ~14 days of overflowing at launch (recent history plus a 30-point welcome).
  - States flickered across thresholds as small feeds faded.
  - After a 2-week break, a returning user took up to a month to reach rising.
  - A new user's first month could never be "within budget": the first budget, set after the period started, wrote a 0 baseline.
  - A "point farmer" (daily "nothing to log" plus daily zero-delta reconciles, no real data) reached rising or higher.
- Simulator, scenarios, targets and results: [docs/plans/gamification/starter-sim/](../plans/gamification/starter-sim/README.md).

## Decision

### 1. Weights (replaces the ADR-0125 §2 table values)

| Signal | Points | Fade | Change vs ADR-0125 |
|---|---|---|---|
| Saving week | 10 | 14 d | 25 → 10 |
| Check-in day | 5 | 7 d | 4 → 5 |
| Accurate reconcile | 8 | 30 d | 10 → 8; **≤ 1 per ISO week across all accounts** (was ≤ 1 per account per day) |
| Accounts in sync (state) | 8 | — | 15 → 8 |
| Nothing overdue (state) | 8 | — | 15 → 8 |
| Within budget | 15 | 30 d | 30 → 15; coverage rule (§2) |
| Net-worth growth | 12 | 30 d | 20 → 12; coverage rule (§2) |
| Setup milestone | 10 | 14 d | — |
| Achievement | 30 | 30 d | — |
| Goal reached | 40 first, 20 later | 30 d | — |
| Welcome | 10 | 7 d | 30 / 14 d → 10 / 7 d |

### 2. New feed rules

- **Coverage rule.** Within-budget and net-worth-growth events need check-in days (as defined in ADR-0125 §2, after the rule below) on **≥ 50 %** of the closed period's days. A period with little recorded is not evidence of anything.
- **"Nothing to log" needs recent real data.** A "nothing to log" check-in for day D counts only if the user has a real ledger entry with `operation_date` in `[D − 13, D]`. Someone who buys once a week keeps full credit for the other days. A user with no real data gets none.
- **Comeback bonus.** When an event follows a gap of **≥ 7 days** with no events, every event dated in the **7 days** from that event is worth **× 1.5**. Welcome is ignored for gap detection. Gap detection reads all recorded check-in days, not only those still feeding. ×1.25 left 13 % of holiday returns below rising after a week; ×2 gave ~6 overflowing days after a break, which rewards absence.

### 3. States (replaces the ADR-0125 §3 thresholds)

| State | Rule |
|---|---|
| `dormant` | no event in the last 14 days (unchanged) |
| `sleepy` | health < 25 |
| `bubbly` | 25–54 |
| `rising` | 55–84 |
| `overflowing` | ≥ 85 **and** a saving-week or goal-reached event still inside its fade window; otherwise capped at `rising` |

- **Hysteresis.** A state moves up as soon as health reaches the threshold, and moves down only when health is **8** below it. `starter_view` stays pure: it replays daily health over the trailing 30 days to get the previous state.
- Event reads are bounded to the last **45 days** (30-day fades, plus the comeback window and gap), plus closed-period aggregates. This was 30 days.

### 4. Per-category budget baseline (replaces ADR-0125 §5 storage and rule)

Budgets are per category (F4.2, F4.4); the total is derived.

- `budget_period_baselines(user_id, year, month, category_id, amount, created_at)`, unique `(user_id, year, month, category_id)`. It is written **once per category** on the first budget write that changes that category's resolved budget for a fiscal month that has already started. `amount` is the resolved budget before the change (0 when the category had none).
- Cap per category: no row → the final budget; `amount > 0` → `min(amount, final)`; `amount = 0` (new budget) → `min(final, that category's spent in the period)`.
- **Met** when total expenses (all categories, base currency, as in ADR-0125 §2) ≤ Σ caps.
- Result: raising a budget mid-period still doesn't count. Adding a budget for a category that had none no longer penalises the user, and that budget can't cover overspending in other categories. A new user's first month can be met.

### 5. Encryption (amends ADR-0125 §11)

`budget_period_baselines.amount` is encrypted (it replaces `total_amount`); `category_id` is a plaintext FK.

## Results

With this tuning, 47 / 47 tuning-set checks and 7 / 8 held-back checks pass over 100 seeds. The one held-back miss is accepted: a weekend batch logger moves up and down about twice a month. Monthly catch-up users are dormant about half the time, also accepted. The feature is meant to reward regular activity.

| Scenario | Rising | Overflowing |
|---|---|---|
| Careful, no goals | 68 % | 0 % |
| Careful with goals | 70 % | 25 % |
| Power user | 20 % | 80 % |
| Diligent, always over budget | ~50 % (rest bubbly) | 0 % |

Holiday user: bubbly the day after return in every run, rising within a week in 97 %.

## Consequences

- `domain/starter_tuning.py` takes the values above; the new rules are constants there too (coverage share, nothing-to-log window, comeback gap/days/multiplier, hysteresis, overflowing gate).
- `budget_period_baselines` gains `category_id` and stores `amount` per category (T-GS10, T-GS12).
- `starter_view` replays 30 days of health for hysteresis. The render cost is ≤ 30 cheap evaluations over ≤ 45 days of events. T-GS14's performance test covers it.
- The simulator's scenarios and targets become regression tests for the real `starter_view` (T-GS11). A future retune (T-GS21) must keep them green or change a target in an ADR.
- The simulator models budget outcomes per month, not per category; §4 was checked through its effect on new users. T-GS12 tests the per-category rule directly.

## Alternatives considered

- **One-off "welcome back" bump on return.** Rejected by the user in favour of a bonus period that rewards actual activity after the break.
- **Cap "nothing to log" at 3 per week.** Rejected: it penalises people who spend rarely (a once-a-week buyer uses ~5 a week).
- **Hysteresis 10–12.** Rejected: careful users without goals stuck in rising too long, and 6 accounts pushed overflowing above 35 %.
- **Keep total-level baseline (ADR-0125 §5).** Rejected: it blocks a new user's first month and penalises budgeting a new category.
- **Count a new category budget in full.** Rejected: a large made-up category budget would cover overspending elsewhere.
