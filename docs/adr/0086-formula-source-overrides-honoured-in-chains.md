# ADR-0086: Formula Sources Honour Per-Occurrence Overrides in Chains

- **Status**: Accepted
- **Date**: 2026-11-06
- **Clarifies**: [ADR-0047](0047-recurring-formula-linear-combination-and-chaining.md) (chaining), [ADR-0046](0046-recurring-override-soft-consume.md) (soft-consume visibility)

## Context

A formula rule `A` reads source rules by category. For a *fixed* source rule the source contribution goes through `services.recurring.expand` with `list_overrides_all`, so `amount_override`, `skipped` and `date_override` are honoured (ADR-0046). For a *formula* source rule, `_sum_category_in_month` instead multiplied the number of canonical occurrences in the month by the freshly computed formula value and never looked at the source's overrides. Result: overriding (or skipping) an occurrence of a formula-based source rule changed what the Budget/Ledger/Upcoming surfaces showed for that rule, but not what any rule chained over it computed.

Field case: `na osobiste` = chained formula over WYPLATA (fixed), WYPLATA VAT (formula) and two PODATKI (formula, chained). The overrides on the formula sources were invisible to the parent; error = computed default - override.

Promotion does not change this: soft-consume keeps the override row (`list_overrides_all`), but the formula-source branch never read it. In a faithful reproduction (WYPLATA fixed, WYPLATA VAT formula, both overridden and promoted; PODATKI x2 chained formula, overridden, planned) the formula-source overrides were ignored regardless of promoted/planned state; only the fixed WYPLATA override was reflected. The reported observation that WYPLATA VAT's override *was* reflected cannot be reproduced from code; the most likely explanation is that its override amount equalled its computed value (it was promoted at the formula amount), so the ignored override was numerically invisible. It could not be checked against the user's data (prod DB is off limits).

## Decision

A source rule contributes, per canonical occurrence in the month, its **effective amount**:

1. Generate the source rule's occurrences in the month (`generate_occurrences`).
2. Fixed rule: amount = `default_amount`. Formula rule: amount = the computed per-occurrence formula value (recursing with the shared `in_progress` ancestor set and `(rule_id, year, month)` cache).
3. Apply `apply_overrides(occs, list_overrides_all(...))`: an `amount_override` wins over the computed/default amount, a `skipped` occurrence contributes 0, a `date_override` only changes the occurrence's effective date (month membership is by canonical `occurrence_date`, exactly as for fixed sources).
4. Sum the resulting amounts. The result is memoised in the existing cache.

Fixed and formula sources now share one code path (differing only in the per-occurrence base amount). The formula is still evaluated only if the schedule has at least one occurrence in the month (ADR-0047 month-scope gate). Cycle detection is unchanged.

Overrides do not feed back into the source's *own* formula inputs: an override replaces the source's output for that occurrence only.

## Consequences

- Parent formula values change where a formula source has overrides/skips; this is the intended correction.
- `date_override` behaves identically for fixed and formula sources (no cross-month move of the contribution); unchanged from fixed-source behaviour.
- No schema change, no migration.
