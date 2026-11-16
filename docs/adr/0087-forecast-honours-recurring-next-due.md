# ADR-0087: Forecast Honours Recurring `next_due` (No Re-Projection of Promoted Occurrences)

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0043](0043-forecast-tab-monthly-horizon-and-table.md)

## Context

Forecast flows (`_month_flow_sums`) and the daily event builder (`_collect_events`) expanded recurring rules from the canonical schedule over `[today+1, end]` and ignored `rule.next_due`. Promoting an occurrence early (e.g. salary due 11-07 promoted on 11-06) creates a transaction and advances `next_due` to 12-07, but the 11-07 occurrence is still `>= today+1`, so it was projected again: the current month's Income showed 29,517 instead of the ~700 still to come, and the EOM / net-worth chain double-counted it. Budget and `_committed_future_for_category` already clamp to `max(rule.next_due, window_start)`.

## Decision

Forecast flows and daily events expand a rule from `max(rule.next_due, today+1)`. The filter is on the **canonical** `occurrence_date` (`generate_occurrences` range start), never on the effective / `date_override` date, so a date override can neither resurrect a promoted occurrence nor drop an unpromoted one. Consequently the current-month row's Income is the remaining not-yet-received income only (received money is already in the starting balance).

## Consequences

- Current-row Income and the daily/EOM chain no longer double-count early-promoted occurrences.
- Skipped occurrences keep being excluded (skip advances `next_due` / carries a skip override).
- No schema change; `services/budget.py` and `recurring_formula.py` untouched.

## Amendment (T-FIX4): linked planned rows suppress their occurrence everywhere

A persisted, **unpromoted** planned row with `(recurring_rule_id, occurrence_date)` represents that recurring occurrence wherever it lives. The dedup key set is therefore built from **all** such rows for the user, not only those inside the consumer's window, so re-dating a linked row outside the window still suppresses the virtual occurrence. One shared helper (`recurring.linked_occurrence_keys`) feeds Budget `committed` (previously not deduped at all, so it double-counted), Forecast (`_collect_events`, `_month_flow_sums`) and Accounts planned net (`_collect_legs`). Promoted linked rows need no handling: `next_due` already excludes their occurrences. Unlinked planned rows never suppress anything. No `src/` path currently creates linked rows (only the repository accepts the fields), so this closes a latent double-count.
