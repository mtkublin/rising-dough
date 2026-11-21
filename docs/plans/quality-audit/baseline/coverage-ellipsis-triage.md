# T-Q219 triage: statements made visible by the anchored ellipsis exclusion (Q-014, OQ-28)

`pyproject.toml` `exclude_lines` entry `"\\.\\.\\."` became `"^\\s*\\.\\.\\.$"` (stub-only lines). Measured on one full-suite run plus `coverage report` with the old and new patterns over the same `.coverage` data: statements 7818 to 8611 (793 more), total coverage 95.31 % to 95.18 % (branch coverage on; gate is 90 %). Newly visible missed statements: 38 (the audit counted 49 on an older tree; 11 are now covered). No `pragma: no cover` added, no `src/` change.

Decision (OQ-28, decided in-task): test every branch that is reachable and not in a file another work item is changing; list the rest here.

| File:lines | Branch | Disposition |
|---|---|---|
| `web/routers/accounts.py:315` | edit account with blank name re-renders form | tested (`test_update_account_blank_name_rerenders_form_with_error`) |
| `web/routers/accounts.py:487-490, 496-497` | reconcile with non-numeric category, snapshot save | tested (`test_reconcile_non_numeric_category_falls_back_and_saves_snapshot`) |
| `web/routers/budget.py:256-263` | override tier `default` | tested (`test_override_default_tier_sets_default_and_emits_trigger`) |
| `web/routers/budget.py:266-267` | override with non-numeric month | tested (`test_override_non_numeric_month_is_422`) |
| `web/routers/categories.py:176-177` | update category with invalid color | tested (`test_update_category_rejects_bad_color_and_keeps_name`) |
| `web/routers/planned.py:240, 245-246, 249` | create planned: unknown category, bad and unknown destination | tested (parametrised) |
| `web/routers/planned.py:359` | edit planned with unknown account | tested |
| `web/routers/recurring.py:839` | override for a month before the rule start | tested |
| `web/routers/transactions.py:269, 273, 279` | create transit: bad, unknown and valid destination | tested (3 tests) |
| `web/routers/transactions.py:389` | edit transaction with unknown account | tested |
| `web/routers/recurring.py:841` | "rule has no live account": the lookup uses `include_deleted=True` and `rules.account_id` is a foreign key, so `acc is None` cannot occur | dead defensive branch; list for T-Q244 (dead code) |
| `services/analytics.py:200` | `cats.get(...) is None`: `cats` is built with `include_deleted=True` and `category_id` is a foreign key | dead defensive branch; list for T-Q244 |
| `services/budget.py:627-629` | `yearly_grid` recurring-origin cell | owned by T-Q206 (budget/forecast tests) |
| `services/forecast.py:749, 758, 763, 768` | `continue` branches in forecast loops | owned by T-Q206 |
| `web/routers/ledger.py:229-232` | invalid `Direction` filter value | owned by T-Q209 (ledger tests) |

Counts (statements): 25 tested, 2 dead (for T-Q244), 11 owned elsewhere (T-Q206: 7, T-Q209: 4); total 38.
