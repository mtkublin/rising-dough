# ADR-0064: Plan / Today / Overview Default Landing Month Follows the Fiscal Cycle, Not the Calendar

- **Status**: Accepted
- **Date**: 2026-11-01
- **Amends**: [ADR-0041](0041-budget-period-anchor-window.md); surfaces [F4.6](../requirements.md)
- **Related**: [ADR-0025](0025-user-preferences-and-income-anchor.md), [ADR-0031](0031-budget-page-composition-v2.md), [ADR-0051](0051-v2-information-architecture-rising-dough.md)

## Context

ADR-0041 shifted the Budget `spent_minor` window from the calendar month to the paycheck window `[last_anchor_date, today]`, where `last_anchor_date` is the operation date of the most recent **promoted** anchor-category transaction with `operation_date <= today`. The "monthly budget" tier resolution ([ADR-0014](0014-budget-flat-no-rollover-three-tier.md)) still keys on `(year, month)`, and ADR-0041 §29 defines each monthly budget as the budget "for the cycle anchored in that month."

The `/plan`, `/today`, and legacy `/` routers currently default `(year, month)` to `today.year, today.month`. On the first day(s) of a calendar month, before that month's anchor paycheck has landed, this default picks the **next** cycle's budget while `_resolve_period_start` keeps `spent_minor` anchored to the **previous** paycheck. The result on the Budget hero is a Nov-budget-vs-Oct-7→Nov-1-spent chimera that the user sees as "wrong number."

Concrete example (observed 2026-11-01): last `WYPŁATA` (anchor) landed Oct 7; next scheduled Nov 7. Today is Nov 1. Plan defaults to November, pulling Nov `budget_defaults` / overrides, while `_resolve_period_start` returns Oct 7 — so `remaining = Nov_budget − (Oct7..Nov1 spent)` and `committed` sums the Nov 1..Nov 7 window. The three totals describe two different cycles.

## Decision

Introduce a derived `fiscal_month_for(conn, today) → (year, month)` helper and use it as the default landing month on every surface that renders a "current cycle" summary:

- `/plan` (`tab=budget` and `tab=analytics` — both are month-scoped).
- `/today`.
- `/` (legacy Overview; still live until the Phase 7 redirect).

### Resolution rules for `fiscal_month_for`

1. **Anchor configured + promoted anchor-category transaction on-or-before `today` exists** → `(last_anchor_date.year, last_anchor_date.month)`, where `last_anchor_date` is defined exactly as in ADR-0041 (max `operation_date` across live promoted transactions in the anchor category with `operation_date <= today`).
2. **No anchor configured** → `(today.year, today.month)`.
3. **Anchor configured but no promoted anchor-category transaction yet** → `(today.year, today.month)`.

The helper lives in `services/budget.py` next to `_resolve_period_start` to keep the paycheck-window logic co-located. It uses the same `transactions_repo.list_filtered` call shape (same filter: `date_to=today, category_ids=(anchor.id,), directions=(Direction.INCOME,)`), so there is a single source of truth for "last promoted anchor on-or-before today."

### What stays unchanged

- The explicit `?year=&month=` picker in `/plan` still wins over the default (the Plan period selector navigates prev/next from whatever month the user picked).
- `budget_service.month_summary` signature and internals (`period_window` override, `_resolve_period_start`, `_resolve_anchor`, committed-window math) are unchanged.
- ADR-0041 fallbacks (`budgeted_total == 0`, missing anchor, no prior anchor transaction) still produce month-start-based windows inside `month_summary`.
- The `is_current` branch in `/plan` (`tab=budget`) that applies the calendar-month `period_window` override to non-current months now compares against the **fiscal** month instead of the calendar month, so landing on the fiscal month renders real anchor-window math rather than the clamp.

### Routing precedence summary

| Query | Behavior |
|-------|----------|
| `/plan?tab=budget` (no `year`/`month`) | Default to `fiscal_month_for(today)`. |
| `/plan?tab=budget&year=…&month=…` | Honor explicit params (existing behavior). |
| `/today` | Default to `fiscal_month_for(today)`. |
| `/` (legacy Overview) | Default to `fiscal_month_for(today)`. |

## Consequences

- On Nov 1 (last anchor Oct 7, next Nov 7), the Budget hero now shows the October budget with the Oct 7 → today window of spent, matching the user's mental model of "the cycle I'm still in."
- Immediately after a paycheck is promoted, the fiscal month snaps forward in the same tick as `spent_minor` resets to zero (both derive from the same `last_anchor_date`).
- Pre-first-paycheck users keep calendar-month defaults — identical to today's behavior.
- Non-anchor users (no `income_anchor_category_id`) also keep calendar-month defaults.
- No schema change. No new indexes required (the `transactions(operation_date)` + `category_id` indexes already satisfy the lookup, same as ADR-0041).
- The Plan picker's `prev` / `next` arrows still shift by one calendar month — the fiscal default only picks the initial landing month.

## Alternatives Considered

- **Default to the month containing `next_anchor_date − 1 day`.** Rejected — mirrors a scheduled row instead of a promoted one. If the user drifts the next paycheck via override, or the recurring rule's `next_due` has been bumped administratively but no money has landed, the cycle picker would advance before the budget actually rolls (contradicting ADR-0041's "promoted money only" rule).
- **Add a dedicated "cycle" picker separate from the month picker.** Rejected for the same reason ADR-0041 rejected it — the user asks one question of the Budget page, and the month picker already exists.
- **Prorate the budget across cycle-straddling months.** Rejected — same objection as ADR-0041 §Alternatives: ambiguates `budget_one_off_overrides` and the Yearly grid.

## Non-goals

- Changing `month_summary` internals.
- Changing the Yearly grid, Forecast table, or Analytics windows.
- Changing the Plan picker's prev/next step (still one calendar month).
- Introducing a user-visible "fiscal month" label — the hero already shows `period_start → next_income_date`; nothing new is surfaced.
