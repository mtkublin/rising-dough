# ADR-0038: Recurring Rules — Standalone Lifecycle with `next_due` + Direct Promotion

- **Status**: Accepted
- **Date**: 2026-10-27
- **Supersedes**: ADR-0013 (virtual-occurrence union into planned log) and ADR-0012 §scope (planned promotion flow is now one of two promotion flows, not the sole flow).

## Context

ADR-0013 modelled recurring occurrences as virtual projections of a rule and unioned them into the planned-transactions log in the UI. Field use revealed three problems:

1. **Semantic conflation.** Users think of planned (one-off intent) and recurring (standing rule) as different concepts; the UI showed them as one list. "Promote planned" and "promote recurring" are not the same operation — the first consumes a row, the second advances a schedule.
2. **No "next due" affordance.** Because occurrences were virtual, there was no persisted anchor the UI could point at ("next salary: 2026-11-01"). The Ledger Recurring row rendered `start_date` as a placeholder `next_due` (see `web/routers/ledger.py:144`), which drifts from reality after the first occurrence passes.
3. **Promotion story missing.** ADR-0012 covered planned → actual. No ADR covered recurring → actual. Users wanted a one-click "mark this month's rent paid" button on the recurring row itself.

## Decision

Treat **planned transactions** and **recurring rules** as two independent surfaces, each with its own lifecycle. Delete the virtual-union behaviour from the Ledger. Keep the per-occurrence overrides table as an edit mechanism for the *next* due occurrence.

### Schema change (migration `0006_add_recurring_next_due.sql`)

Add to `recurring_rules`:

```sql
ALTER TABLE recurring_rules ADD COLUMN next_due DATE;
ALTER TABLE recurring_rules ADD COLUMN last_promoted_date DATE;
-- Backfill: next_due = first canonical occurrence on-or-after today
--           (or start_date when start_date > today), computed once at
--           migration time via a Python-driven backfill script that
--           reuses services.recurring.generate_occurrences.
-- Post-backfill: enforce NOT NULL on next_due via a second migration
--                step inside the same file (SQLite table rebuild).
```

- `next_due` becomes the authoritative "when is the next occurrence" column. Every mutation that could shift it (`create_rule`, `promote_recurring`, `upsert_override` where `occurrence_date = next_due`, `deactivate_rule`) must keep it in sync.
- `last_promoted_date` is informational (audit, UI hint "last paid"). Nullable; untouched by overrides.

### Promotion flow (`services.recurring.promote_recurring`)

```
promote_recurring(conn, rule_id, edits: PromotionEdits) -> Transaction:
  1. Load rule; refuse if deleted / inactive.
  2. due_date = rule.next_due
  3. Load override for (rule_id, due_date) if any.
     - If state=skipped → raise CannotPromoteSkippedError (user must
       either delete the skip override or wait for next_due to advance).
     - If state=overridden → use its amount_override /
       description_override / date_override as defaults.
  4. Merge with explicit edits (same shape as PromotionEdits).
  5. Validate direction (reuse _validate_promotion from planned svc —
     factor into services.promotion_shared or duplicate; see T-118).
  6. Within one DB transaction:
     a. Insert into transactions with
        promoted_from_recurring_rule_id = rule_id,
        promoted_from_recurring_date = due_date.
     b. Advance rule.next_due via services.recurring.advance_next_due
        (pure function over cadence + due_date + end_date; returns None
        if the rule has ended).
     c. If next_due returned None, set rule.active = 0.
     d. Update rule.last_promoted_date = due_date.
     e. Delete the matching override row (if any) — it has served its
        purpose and must not re-apply next cycle.
     f. Write audit entries for the txn + rule mutation.
```

### Advancement (`services.recurring.advance_next_due`)

```
advance_next_due(cadence, from_date, end_date, day_of_month, month_of_year) -> date | None:
  Returns the next canonical occurrence strictly after from_date,
  clamped to end-of-month when day_of_month overflows the target month.
  Returns None when the advanced date would exceed end_date.
```

This is a pure function; reuse the stepping arithmetic that already lives in `services.recurring.generate_occurrences` (see `src/budget_planner/services/recurring.py:33`).

### Schema fields on `transactions`

Add to `transactions`:

```sql
ALTER TABLE transactions ADD COLUMN promoted_from_recurring_rule_id INTEGER
    REFERENCES recurring_rules (id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE transactions ADD COLUMN promoted_from_recurring_date DATE;
CREATE INDEX ix_transactions_promoted_from_recurring
    ON transactions (promoted_from_recurring_rule_id, promoted_from_recurring_date);
```

- `promoted_from_planned_id` remains for ADR-0012 planned promotions. The two columns are mutually exclusive at the application layer (service enforces XOR, no CHECK constraint — keeps the migration simple and the invariant local to the service).

### Ledger view semantics (consequence)

- **Planned tab** (`/ledger?view=planned`) lists **only persisted one-off `planned_transactions`** (`recurring_rule_id IS NULL`). No virtual rows. `services.planned.list_planned` is simplified: drop the "expand active rules + dedup" branch; remove `services.recurring.expand` from this call site. The `kind` discriminator on `PlannedView` collapses to the single value `"persisted"` and can be removed in a follow-up cleanup.
- **Recurring tab** (`/ledger?view=recurring`) lists all live `recurring_rules` with `next_due` from the column (not `start_date`), plus `Promote`, `Edit`, `Delete` (soft-delete via `deactivate_rule`), `Override next…` actions. The `Override next…` opens a slide-over pre-filled with `occurrence_date = rule.next_due` so the user can skip or tweak the next occurrence; it reuses the existing `POST /recurring/{id}/overrides` endpoint.

### Overview Upcoming (consequence)

`GET /overview/upcoming` returns the sorted union of:
- Persisted `planned_transactions` within the window where `planned_date >= today` or `planned_date < today AND promoted_to_txn_id IS NULL` (overdue).
- Active `recurring_rules` whose `next_due` falls inside the window (date rendered from `rule.next_due` + any `occurrence_date = next_due` override).

Both kinds carry a `kind` field (`"planned"` | `"recurring"`) so templates can render different affordances (promote-planned vs. promote-recurring).

## Consequences

- Rule edits still propagate instantly: next_due is recomputed only on promotion / rule mutation, not on every list query — materially faster than ADR-0013's expand-every-view model.
- Overrides table retains its sparse-exception semantics but with a tighter contract: an override only ever applies to one promotion (the one whose `due_date` matches `occurrence_date`), then self-destructs. "Skip July + September" is still two rows, both targeted at the then-current `next_due` values; the "skip" state blocks promotion and the user has to acknowledge-and-advance (see `services.recurring.skip_and_advance`, exposed via `POST /recurring/{id}/skip-next`).
- Historical rule edits that would retroactively change past occurrences are impossible — correct, because past occurrences live in `transactions` with their actual values.
- The virtual-occurrence generator (`services.recurring.expand`) is retained for the **forecast** service (ADR-0015, F5.2), which still needs to project future recurring occurrences into the fortune line. Forecast is read-only on `recurring_rules`; it does not write to `transactions`, so it has no `next_due` concern.
- `services.planned.next_planned_for_category` is replaced by `services.income.next_anchor_date(conn, category_id, after)` which composes:
  - Earliest live `planned_transactions.operation_date` for `category_id` strictly after `after` with `promoted_to_txn_id IS NULL`.
  - Earliest active `recurring_rules.next_due` for `category_id` strictly after `after` (override-applied if an override targets that date).
  - Returns the minimum of the two, or `None`.

## Alternatives Considered

- **Keep virtual-union + add "Promote next" button that materialises on click.** Rejected: still conflates two concepts in the Ledger; `next_due` still has no durable home.
- **Materialise occurrences on rule create for N years ahead.** Rejected on the same grounds as ADR-0013's rejection — arbitrary horizon, drift risk, scheduler creep.
- **Keep `next_due` virtual (compute on every query from `start_date + cadence × (promoted_count)`).** Workable but couples `transactions` + `recurring_rules` in every list query; a persisted column is cheaper and lets overrides stay sparse.

## Amendment 2026-11-21 (T-Q211, Q-006): schedule anchor and start-date boundary

- **Anchor is persisted.** The create path defaults `day_of_month` to `start_date.day` when the form leaves it blank (`services.recurring.create_rule`), so the end-of-month clamp never rewrites the anchor (Jan 31 -> Feb 28 -> Mar 31, not Mar 28).
- **`advance_next_due` takes the rule.** Signature `advance_next_due(rule, from_date)`: the next canonical occurrence strictly after `from_date` is read from the rule's own schedule, anchored on `rule.start_date` (plus `day_of_month`, `month_of_year`, `end_date`), not from a stub whose `start_date` is `from_date`. `_build_lookup_stub` is removed.
- **Start-date boundary.** `generate_occurrences` never emits an occurrence dated before `rule.start_date` (a `day_of_month` earlier than the start day skips the first month's slot).
- **Data fix.** None by default. OQ-5 (blank day-of-month after the 28th, or day-of-month earlier than start day in prod) is unanswerable without prod; default taken 2026-11-21, pending operator data check.
