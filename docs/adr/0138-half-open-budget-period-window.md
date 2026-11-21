# ADR-0138: The Budget Period Is a Half-Open `[start, end)` Window Owned by `domain/periods.py`

- **Status**: Accepted
- **Date**: 2026-11-21
- **Amends**: [ADR-0041](0041-budget-period-anchor-window.md), [ADR-0064](0064-plan-default-fiscal-month.md), [ADR-0085](0085-budget-left-counts-only-budgeted-commitments.md)
- **Related**: T-Q208, Q-003 (A-05, A-14, B-05), OQ-14 (answered 2026-11-21), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md)

## Context

With an income anchor the "next income date" was an exclusive bound; the no-anchor fallback reused the same variable with the inclusive last day of the month. A committed item on the last day was dropped and the left-per-day divisor was one too small (about 9 percent inflated left-per-day on Nov 19). `account_planned` added the missing day; `budget` did not. Month bounds and month shifts existed in six copies, and the Plan router rewrote service results for other months (anchor day capped at 28).

## Decision

1. **Half-open window.** A budget period is `[start, end)`. `end` is the next income date, or, with no usable anchor, **the first day of the next month** (never the inclusive last day). `start` is the last landed anchor income, else the first of the month.
2. **One owner.** `domain/periods.py` (pure, no clock): `month_bounds` (inclusive calendar month), `next_month_start`, `shift_month`, `clamp_day`, `fiscal_window`, `days_remaining`, `window_label_month`, `PeriodWindow`. `budget._resolve_anchor`, `account_planned.resolve_window`, analytics, forecast, planned and `recurring_formula` all call it; the private copies are deleted.
3. **Days-remaining divisor** (requirements note): `days_until_next_income = max((end - today).days, 1)`, counting today. The floor of 1 stays as a guard for degenerate input only.
4. **Payday opens the new period (OQ-14.1).** The operator wording was "1, but make sure budget is reset to new period as well". On the day the anchor income is due, the period is already the new `[payday, next payday)` window: `period_start = today`, `end` = the next payday after today, so spent, committed and the divisor come from the new period and not from the old period's leftovers divided by 1. This holds whether or not the paycheck row has been promoted yet.
5. **Fiscal-month label (OQ-14.2).** A period is labelled by the calendar month holding most of its days (Dec 2 to Jan 1 is December; Nov 29 to Dec 28 is December); a tie goes to the later month. `fiscal_month_for` uses it, with the window end taken from the next anchor date, else one month after the start.
6. **Average per active month (OQ-14.3).** The "average per active month" figure keeps skipping months with no transactions. Intended; no change.
7. **Plan month picker.** The logic moves from `web/routers/plan.py` to `services/budget.resolve_picker_month` and `month_summary_for_picker`. For a non-fiscal month the period is `[anchor_day(month), anchor_day(month + 1))` with each day clamped to the month length (no cap at 28); the router only parses and renders.

## Consequences

- Left-per-day and committed totals agree between Today, Budget and Accounts for users without an income anchor.
- Entries removed from `banned_patterns`, `invariants` (INV-7, two strict xfails flipped), `thin_router` and `clones` allowlists; canonical row "Periods and month windows" is `exists`.
- The label rule changes the default Plan month when a paycheck lands late in a month (for example Jan 25 to Feb 25 is labelled February).
