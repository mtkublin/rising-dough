# T-Q285 inventory: pass-through service bindings

Found with `rg -n "^[a-z_]+ = [a-z_]+\.[a-z_]+\s*$" src/budget_planner/services` (46 bindings in 9 modules).
All are now typed `def`s; `tests/architecture/test_transaction_boundaries.py` lists zero bindings.
"Rule" is what the new function validates before its one repository mutation (row and audit row are
atomic inside the repository, so no second transaction). "Thin" is a read with no domain rule.

| Module | Name | Was bound to | Now |
|---|---|---|---|
| accounts | find_by_id, find_by_name, list_all | accounts_repo | thin, typed |
| accounts | create | accounts_repo.create | rule: `new_account_errors` (name, ISO currency, positive credit limit) |
| accounts | update | accounts_repo.update | rule: `patch_account_errors` |
| accounts | list_snapshots_for_account, list_snapshots_for_user | snapshots_repo | thin, typed |
| accounts | create_snapshot | snapshots_repo.create | thin (ownership checked by the repository, `LookupError`) |
| auth | list_active_sessions, list_passkeys | sessions_repo, webauthn_repo | thin, typed |
| budget_overrides | get_default, list_defaults | budgets_repo | thin, typed |
| budget_overrides | set_default, set_recurring, set_one_off | budgets_repo | rule: `override_errors` (amount not negative, month 1 to 12) |
| categories | find_by_id, find_by_name, list_all, list_recently_deleted | categories_repo | thin, typed |
| categories | create, update | categories_repo | rule: `new_category_errors` / `patch_category_errors` (name, colour) |
| categories | soft_delete | categories_repo.soft_delete | thin (one mutation) |
| fx | list_recent_rates | fx_repo.list_recent | thin, typed |
| planned | find_by_id, list_filtered, list_recently_deleted | planned_repo | thin, typed |
| planned | create, update | planned_repo | rule: `transactions.validate_entry` / `validate_patched_entry` |
| planned | soft_delete, undelete | planned_repo | thin (one mutation) |
| recurring (now `recurring_rules`) | find_rule, list_rules, list_overrides | recurring_repo | thin, typed |
| recurring_rules | create_rule, update_rule | recurring_repo | rule: end date, anchor day, amount, description, transit shape |
| recurring_rules | deactivate_rule, upsert_override, delete_override | recurring_repo | thin (one mutation) |
| transactions | find_by_id, list_filtered, count_filtered, list_recently_deleted | transactions_repo | thin, typed |
| transactions | create, update | transactions_repo | rule: `validate_entry` / `validate_patched_entry` (description length, positive amount except adjustments, transit shape) |
| transactions | soft_delete, undelete | transactions_repo | thin (one mutation) |

Thin reads and one-mutation writes stay as typed `def`s: they have no rule that belongs to the domain.
Deviation from the brief: ids and commands remain positional after `conn, user_id` (about 640 call
sites would change with no safety gain); flags (`include_deleted`, `active_only`, ...) stay keyword-only.

## G8 findings (multi-mutator services without a transaction)

| Function | Fix |
|---|---|
| retention.purge | wrapped in one `db_transaction` (rollback test in `test_retention.py`) |
| auth.register_passkey_finish | insert split into `_store_credential`; the spent challenge must stay spent, so deliberately not one transaction |
| reauth.verify_passkey_reauth | revoke and sign-count writes split into one-mutator helpers; the failed-attempt audit must survive |
| preferences.set_income_anchor_category_id | delete branch moved to `_clear_income_anchor` (branches are exclusive) |
| users._promote, _apply_credentials, set_user_password, create_user, edit_user | false positives (a DTO constructor was counted); the detector skips capitalised calls |
