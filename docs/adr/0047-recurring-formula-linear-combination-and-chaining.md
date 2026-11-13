# ADR-0047: Recurring Formula — Linear Combination of Terms + Chained Formulas

- **Status**: Accepted
- **Date**: 2026-10-28
- **Supersedes**: [ADR-0045](0045-recurring-formula-amount.md) §Decision (shape of `amount_formula`). ADR-0045's §Context, §Rounding, and the ADR-0046 soft-consume contract remain in force.
- **Composes with**: [ADR-0046](0046-recurring-override-soft-consume.md).
- **Clarified by**: [ADR-0086](0086-formula-source-overrides-honoured-in-chains.md) (formula sources honour per-occurrence overrides).

## Context

ADR-0045 shipped a single-term formula shape: `coefficient_bps × Σ(occurrence amounts of source rules in selected categories)`. Field use quickly surfaced two gaps:

1. **Only one term.** Real formulas combine multiple inputs with mixed signs — e.g. "monthly tax = 12 % of (gross income A + gross income B) minus 40 % of a deductible expense category". The single-term shape forces the user to collapse those into one category or to pre-aggregate manually.
2. **No chaining.** ADR-0045 made the dependency graph a 2-level tree (formula → fixed) and rejected formula-in-source-category at save time. Users want a formula rule F2 that references a category containing another formula rule F1 (e.g. "tax surcharge = 10 % of (base_tax)", where `base_tax` is itself a formula).

ADR-0045 §Alternatives considered the full-DSL path (tier C) and rejected it on injection + evaluator-surface grounds. The user still wants a middle-tier upgrade now, with a storage shape that **does not** have to be thrown away if we eventually move to a nested-expression (tier B) or DSL (tier C) model.

## Decision

Replace ADR-0045's single-term shape with a **linear combination of terms** (tier A), and allow source rules to themselves be formula rules (chaining) with a cycle-detection guard at the save boundary. Bake foresight hooks so a future ADR can migrate the stored shape to a nested expression tree (tier B) or a text DSL (tier C) without rewriting the compute primitives.

### Storage shape (versioned JSON)

```json
{
  "schema_version": 2,
  "terms": [
    {"sign": "+", "coefficient_bps": 1200, "source_category_ids": [5, 7]},
    {"sign": "-", "coefficient_bps": 4000, "source_category_ids": [11]}
  ]
}
```

- `schema_version: int` — explicit so future migrations bump it and the repository dispatches on the number. v1 (ADR-0045) is implicitly `1`; v2 is this ADR.
- `terms: list` — non-empty. Each term carries exactly the three fields it had in v1, plus an explicit `sign` ∈ `{"+", "-"}`. Semantics per term: `signed_coefficient × Σ(occurrence amounts in month across source rules whose category_id is in source_category_ids)`.
- The formula value is `Σ terms`. May be negative at a term level; final result is clamped at zero only when the rule's own category is `expense` and we would otherwise insert a negative amount — a 422 at promotion with a user-facing "formula resolved to a non-positive amount" error is clearer than silent clamp.

### Compute primitives (reusable across A/B/C)

Extract three helpers in `services/recurring_formula.py` so a future tier swap replaces the top-level evaluator only:

- `_sum_category_in_month(conn, category_ids, year, month, *, exclude_rule_id, in_progress) -> int` — single source of truth for "monthly sum of occurrences across a set of categories", including recursive descent into formula source rules (chaining). The `in_progress` frozenset tracks the current ancestor chain for defence-in-depth cycle protection (save-time validation is the primary guard; this is the runtime belt-and-braces).
- `_apply_coefficient(sum_minor, bps) -> int` — unchanged from ADR-0045, kept as the single rounding boundary (ROUND_HALF_UP).
- `_collect_referenced_category_ids(formula) -> set[int]` — flat scan of all terms' `source_category_ids`. Pure, no DB. Used by cycle guard and by future tier B/C's leaf-visitor.

The top-level `compute_formula_amount` becomes a thin loop over terms, delegating per-term work to the primitives above. Tier B's evaluator will walk an AST; the leaves (`SumCategoryInMonth`, `Const`, `Scale`) reuse these exact helpers. Tier C's parser compiles text → AST → tier B evaluator — no new compute code.

### Chaining semantics

`_sum_category_in_month` recurses into formula source rules:

```
for rule in active rules whose category_id ∈ category_ids and id != exclude_rule_id:
    if rule.id in in_progress:
        raise FormulaCycleError           # runtime defence
    if rule.amount_formula is None:
        total += Σ expand(rule, list_overrides_all(rule), month_start, month_end)
    else:
        total += compute_formula_amount(conn, rule.amount_formula, year, month,
                                        exclude_rule_id=rule.id,
                                        in_progress=in_progress ∪ {rule.id})
```

Memoisation: compute caches results by `(rule_id, year, month)` within a single DB read's lifetime via an optional `cache: dict` parameter threaded through recursion. Keeps O(N) across call-graphs that fan into the same child formula from multiple parents.

### Cycle detection (save boundary)

`validate_formula_sources(conn, formula, *, exclude_rule_id)` becomes a topological reachability check:

```
visited = set()
stack = [exclude_rule_id]    # the rule we're about to save
while stack:
    rid = stack.pop()
    if rid != exclude_rule_id and rid in reachable_rules(formula):
        raise FormulaCycleError
    for child in formula_rules_in_categories(_collect_referenced_category_ids(formula)):
        if child.id in visited: continue
        visited.add(child.id)
        stack.append(child.id)
```

422 at `POST /recurring` / `POST /recurring/{id}` with a specific "formula would create a cycle" error. ADR-0045's rule-level filter is **removed** — formula rules are now legitimate sources.

### Soft-consume override contract (unchanged)

ADR-0046's `list_overrides_all` is the data source for `_sum_category_in_month`'s fixed-rule branch. Historical correctness invariant from ADR-0046 holds across chaining: F2's October value remains stable even after F1 is promoted and F1's October override is soft-consumed.

### Migration path

`0010_recurring_formula_terms_schema_v2.sql` is **data-only** (SQL file is a no-op comment; the heavy lifting lives in a Python post-apply hook in `db/migrate._POST_APPLY_HOOKS`). The hook:

1. Reads every row in `recurring_rules` where `amount_formula IS NOT NULL`.
2. Parses the JSON. If `schema_version` is absent (v1), rewrites as:
   ```json
   {"schema_version": 2,
    "terms": [{"sign": "+", "coefficient_bps": <v1.coefficient_bps>,
               "source_category_ids": <v1.source_category_ids>}]}
   ```
3. Writes back.
4. Idempotent: runs again on `just migrate` after a rerun will find `schema_version == 2` and skip.

Rows born under ADR-0045 (single-term) convert to a one-term `terms` array with `sign = "+"` — numerically identical to v1.

### UI (`partials/recurring/_form.html`)

Replace the single-term pair of "Coefficient" + "Source categories" with a dynamic fieldset:

- Repeating term row: `[+ / −]` radio-ish toggle, coefficient % input, source-category checkbox grid.
- `[Add term]` button clones the row template; `[Remove]` on each row deletes it.
- At least one term required (422 at save with "formula needs at least one term").
- Edit mode prefills all persisted terms in order.

Form POST uses `terms[i][sign]`, `terms[i][coefficient_percent]`, `terms[i][source_category_ids]`. Server parses by index with sparse-safe iteration (`i` can have holes if the UI removed a row before submit).

### Ledger row chip (unchanged shape)

The `ƒ` chip retains its tooltip but now summarises multi-term: `"+12% Salary A, Salary B − 40% Deductible (2026-11)"`. Multi-line hover title; single-term rules keep the ADR-0045 single-line title.

## Consequences

- **Forward-compat with B/C.** The three primitive helpers (`_sum_category_in_month`, `_apply_coefficient`, `_collect_referenced_category_ids`) are the leaf operators of any future AST. Tier B swaps `compute_formula_amount`'s body from "loop over flat terms" to "walk tree"; the primitives are untouched. Tier C adds a parser that emits tier B's AST — no new backend code. The `AmountFormula` wrapper + repo serialisation + CHECK relaxation (ADR-0045 migration 0008) all survive.
- **Chaining opens real-world modelling.** "Base tax 12% of salary + surcharge 10% of base tax" is now expressible as two rules with no manual pre-aggregation.
- **Cycle risk is real but bounded.** Save-time check is the primary guard; runtime `in_progress` set is defence-in-depth. Diamond-shaped graphs (F3 references F1 and F2, both referencing fixed F0) compute correctly with memoisation.
- **Negative formulas allowed at term level but flagged at promotion.** `12% income − 40% deductible` yielding a negative final value raises a 422 at `POST /recurring/{id}/promote` with a clear message — we do NOT silent-clamp. Users correct the formula or the source data.
- **Snapshot `default_amount` on formula rules** stays a last-computed convenience value (same policy as ADR-0045). Live callers always recompute.
- **UI complexity grows.** Dynamic fieldset + Add/Remove is a step up from the single-term form. Keep the row template self-contained (no cross-row JS dependencies) so a future tier-B swap to a tree editor can be local.

## Alternatives Considered

- **Keep ADR-0045 single-term and introduce "compute two rules into one" external chaining.** Rejected: users would stack synthetic recurring rules to simulate multi-term semantics, polluting the Ledger with scaffolding rows.
- **Jump straight to tier B (nested AST).** Rejected now; readdressable later. The UI delta is multi-week and the 90% real-world case is already expressible with linear combination. Shipping A first validates demand for arbitrary nesting before committing to the tree-editor UI.
- **Materialise formula result into `transactions` on promote and skip chained-formula compute at runtime.** Rejected: breaks ADR-0045's "formula is live" invariant and ADR-0046's historical correctness guarantee for A's view of B's past overrides.
