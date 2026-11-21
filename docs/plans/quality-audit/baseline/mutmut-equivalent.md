# T-Q03b - Mutmut equivalent mutants

Survivors that cannot change observable behaviour. Same row format as the real-gap file (`fn#N` = mutmut id).

Total: 50 mutants.

| Module:line | Function and mutants | What changed | Reason |
|---|---|---|---|
| money:254 | `format_money` #18 | `whole, _, frac = f"{value:,.{decimals}f}".partitio` -> `whole, _, frac = f"{value:,.{decimals}f}".partitio` | partition on a never-matching separator leaves whole in whole; reassembly identical for every input |
| forecast:240 | `_convert_native_to_base` #23, #25 | `return int(converted.quantize(Decimal("1"), roundi` -> `return int(converted.quantize(Decimal("1"), roundi` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| forecast:412 | `_distribute_overlay` #8, #10 | `Decimal("1"), rounding=ROUND_HALF_EVEN` -> `Decimal("1"), rounding=None` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| forecast:685 | `_planned_budget_per_month` #4, #7 | `for c in categories_repo.list_all(conn, user_id, i` -> `for c in categories_repo.list_all(conn, user_id, i` | include_deleted default is False; None/omitted is falsy -> identical |
| recurring:249 | `_build_lookup_stub` #1, #2 | `now = dt.datetime.now(dt.UTC)` -> `now = None` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:251 | `_build_lookup_stub` #3, #36 | `id=0,` -> `id=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:252 | `_build_lookup_stub` #4, #37 | `user_id=0,` -> `user_id=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:255 | `_build_lookup_stub` #7 | `end_date=end_date,` -> `end_date=None,` | end_date already bounds the range via range_end/hard_end; stub copy is redundant |
| recurring:256 | `_build_lookup_stub` #8, #38 | `category_id=0,` -> `category_id=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:257 | `_build_lookup_stub` #9, #39 | `account_id=0,` -> `account_id=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:259 | `_build_lookup_stub` #10, #40 | `default_amount=0,` -> `default_amount=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:260 | `_build_lookup_stub` #11 | `default_description="",` -> `default_description=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:264 | `_build_lookup_stub` #15 | `next_due=start_date,` -> `next_due=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:266 | `_build_lookup_stub` #16 | `created_at=now,` -> `created_at=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:267 | `_build_lookup_stub` #17 | `updated_at=now,` -> `updated_at=None,` | placeholder stub field never read by generate_occurrences for occurrence_date lookup |
| recurring:292 | `advance_next_due` #4 | `end_date=end_date,` -> `end_date=None,` | end_date already bounds the range via range_end/hard_end; stub copy is redundant |
| recurring:297 | `advance_next_due` #16 | `if hard_end <= from_date:` -> `if hard_end < from_date:` | hard_end == from_date: generator range (from+1..hard_end) is empty -> None either way |
| users:112 | `_assert_schema` #3 | `cols = {row["name"] for row in conn.execute("PRAGM` -> `cols = {row["NAME"] for row in conn.execute("PRAGM` | sqlite3.Row column lookup is case-insensitive |
| accounts:47 | `_latest_snapshot_by_account` #8 | `if row["taken_at"] is None:` -> `if row["TAKEN_AT"] is None:` | sqlite3.Row column lookup is case-insensitive |
| accounts:49 | `_latest_snapshot_by_account` #13, #20 | `out[row["account_id"]] = dt.datetime.fromisoformat` -> `out[row["ACCOUNT_ID"]] = dt.datetime.fromisoformat` | sqlite3.Row column lookup is case-insensitive |
| accounts:74 | `_latest_reconcile_by_account` #16 | `if row["d"] is None:` -> `if row["D"] is None:` | sqlite3.Row column lookup is case-insensitive |
| accounts:76 | `_latest_reconcile_by_account` #21, #24 | `out[row["account_id"]] = dt.date.fromisoformat(row` -> `out[row["ACCOUNT_ID"]] = dt.date.fromisoformat(row` | sqlite3.Row column lookup is case-insensitive |
| budget:243 | `_mean_minor` #6, #8 | `quantised = (Decimal(total) / Decimal(count)).quan` -> `quantised = (Decimal(total) / Decimal(count)).quan` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| budget:270 | `_committed_by_category` #5 | `if start is not None and end <= start:` -> `if start is not None and end < start:` | end == start: inclusive_end = start-1 so every rule/planned filter is empty -> same empty result |
| budget:586 | `month_summary` #283, #285 | `Decimal("1"), rounding=ROUND_HALF_EVEN` -> `Decimal("1"), rounding=None` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| export:79 | `export_csv` #24 | `return buf.getvalue().encode("utf-8")` -> `return buf.getvalue().encode("UTF-8")` | codec alias: "UTF-8" == "utf-8" |
| today:50 | `_div_round_half_even` #6, #8 | `(Decimal(numerator) / Decimal(denominator)).quanti` -> `(Decimal(numerator) / Decimal(denominator)).quanti` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| _passwords:35 | `_encode` #4 | `raw = plain.encode("utf-8")` -> `raw = plain.encode("UTF-8")` | codec alias: "UTF-8" == "utf-8" |
| analytics:141 | `_mean_minor` #6, #8 | `quantised = (Decimal(total) / Decimal(months)).qua` -> `quantised = (Decimal(total) / Decimal(months)).qua` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| fx:142 | `convert` #33, #35 | `quantised = converted.quantize(Decimal("1"), round` -> `quantised = converted.quantize(Decimal("1"), round` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| fx:164 | `convert_cached` #37, #39 | `return int(converted.quantize(Decimal("1"), roundi` -> `return int(converted.quantize(Decimal("1"), roundi` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |
| balance:118 | `_mean` #10, #12 | `quantised = (total / count).quantize(Decimal("1"),` -> `quantised = (total / count).quantize(Decimal("1"),` | quantize rounding=None uses default context = ROUND_HALF_EVEN (no setcontext in src) |

## T-Q222 - `services/recurring_formula` after the kill tests (2026-11-21)

Survivors in this module: 141 (baseline, `mutmut.txt`; 71 real-gap rows 234-304) -> 20 survivors + 2 timeouts (infinite-loop kills) after `tests/unit/services/test_recurring_formula_mutants.py` (59 tests). All 20 are equivalent:

| Function and mutants | Reason |
|---|---|
| `parse_percent_to_bps` #34 | `_BPS_MIN / 101` formats to `0.01` under `:.2f`, same message |
| `build_formula` #8 | dropping `schema_version=` falls back to the identical dataclass default `FORMULA_SCHEMA_VERSION` |
| `_sum_category_in_month` #12, #15, #16 | `active_only` is redundant: `generate_occurrences` returns `()` for an inactive rule, so it contributes 0 either way |
| `validate_formula_sources` #3 | sentinel `-1` vs `-2`: no rule has a negative id |
| `validate_formula_sources` #40 | `next(..., None)` default unreachable: `rid` always comes from `all_rules` |
| `compute_savable_amount` #25, #31 | `exclude_rule_id` only matters when the excluded rule sits in a referenced category, which `validate_formula_sources` rejects first |
| `preview` #48-#55 | `except FormulaError` around `build_formula` is unreachable (terms are non-empty by then) |
| `preview` #78, #84 | same as `compute_savable_amount` #25: a self-referencing draft raises in validate before compute |
