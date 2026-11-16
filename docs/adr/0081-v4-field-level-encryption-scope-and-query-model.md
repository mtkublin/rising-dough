# ADR-0081: v4 Field-Level Encryption — Column Scope, Query Model, Feature Preservation

- **Status**: Proposed
- **Date**: 2026-11-04
- **Amends**: [ADR-0022](0022-repository-layer-soft-delete-audit-discipline.md) (repositories read and write ciphertext; aggregates move to services), [ADR-0068](0068-user-scoping-static-check-policy.md) (static check extended to encrypted columns), [ADR-0019](0019-soft-delete-and-audit-log.md) (audit payloads encrypted), [ADR-0071](0071-production-startup-migrations.md) (expand/contract for encrypted columns; per-user data migrations)
- **Related**: [ADR-0079](0079-v4-threat-model-and-data-protection-goals.md), [ADR-0080](0080-v4-envelope-encryption-key-hierarchy-and-sessions.md), [ADR-0008](0008-transaction-amount-sign-and-direction.md) (amounts), [ADR-0006](0006-multi-currency-model.md) (FX)

## Context

ADR-0080 defines the keys. This ADR decides which columns become ciphertext, which stay plaintext and why, and how every existing feature keeps working once SQL can no longer see amounts or names. That's requirement R2 from ADR-0079.

The schema was inventoried on 2026-11-04 from migrations 0001–0014. The code inventory found:

- SQL aggregates (`SUM`, `GROUP BY`, `TOTAL`) in `repositories/transactions.py` and in the services `accounts`, `analytics`, `balance`, `budget` (5), `categories`, `forecast` (3) and `recurring_formula`: about 18 sites in total.
- A `description LIKE ?` search in `repositories/transactions.py`.
- Live-row `UNIQUE` indexes on `(user_id, name)` for accounts and categories.

No background job reads user-owned data without a logged-in user. Recurring and planned promotion is request-triggered (`batch_promote_due` from routers), and `fx_rates` is global.

## Decision

### 1. Column classification

**Encrypted** (ciphertext `BLOB`, ADR-0080 §5 envelope):

| Table | Columns |
|---|---|
| `accounts` | `name`, `opening_balance`, `credit_limit_minor` |
| `categories` | `name` (incl. `is_system` rows, for uniformity) |
| `transactions` | `amount`, `description` |
| `planned_transactions` | `amount`, `description` |
| `recurring_rules` | `default_amount`, `default_description`, `amount_formula` |
| `recurring_rule_overrides` | `amount_override`, `description_override` |
| `account_snapshots` | `balance`, `note` |
| `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides` | `amount` |
| `user_preferences` | `value` (covers the income anchor, ADR-0025) |
| `audit_log` | `prev_json`, `new_json` for rows whose entity belongs to a user (key: the owner's DEK) |
| `webauthn_credentials` | `label` |

**Plaintext**, needed by SQL or by pre-login code:

| Data | Why it stays plaintext |
|---|---|
| `id`, `user_id`, all FKs (`account_id`, `category_id`, `dest_account_id`, `rule_id`, `promoted_*`) | ownership scoping (ADR-0068), joins |
| Dates (`operation_date`, `occurrence_date`, `start_date`, `end_date`, `next_due`, `taken_at`, budget `year`/`month`) | range filters, month bucketing, indexes, recurrence |
| Enums and flags (`direction`, `type`, `cadence`, `state`, `is_liability`, `is_system`, `active`, `day_of_month`, `month_of_year`) | control flow, filters |
| `accounts.currency` | FX lookup key; low sensitivity |
| `categories.color` | presentation; not personal |
| `created_at`, `updated_at`, `deleted_at` | soft delete, audit ordering |
| `users.email`, `users.name` | login lookup and admin panel run without a user key. These are erased on RTBF (ADR-0083). |
| Auth tables (`sessions`, `webauthn_credentials` other than `label`, `auth_rate_limit`) | auth runs before keys exist; they hold no financial data |
| `fx_rates` | global public data |

**Blind-index columns** (ADR-0080 §6): `accounts.name_bidx` and `categories.name_bidx`. The existing `ux_accounts_user_name_live` and `ux_categories_user_name_live` are rebuilt on `(user_id, name_bidx) WHERE deleted_at IS NULL`, which keeps the "no duplicate names" rule enforced in SQL.

### 2. Query model

- **Repositories** keep issuing SQL for selection: ownership, date ranges, FKs, soft-delete state. Encrypted columns come back as `bytes`. Repositories decrypt into the existing frozen domain dataclasses through `crypto.decrypt_*` with the caller's `UserKeys`, so the domain types (`Transaction.amount: int`, …) **don't change**. The same holds on write: domain value in, ciphertext out.
- **Aggregates** (`SUM` / `GROUP BY` over amounts) are rewritten as pure Python reductions over decrypted rows. The rows are selected by plaintext SQL predicates, so the row set stays as narrow as today. The functional-first convention (ADR-0021) fits: `sum_by(rows, key=…)` helpers in `domain/money.py`.
- **Sorting** by name or amount moves to Python (`sorted(…, key=…)`) after selection. Sorting by date or id stays in SQL.
- **Text search** (`description LIKE`): SQL narrows by owner, date range and filters, then Python applies a case-insensitive substring match on the decrypted description. Same user-visible semantics.
- **Pagination** that depends on an encrypted sort key happens after the Python sort, over the SQL-filtered set. Per-user volumes (thousands of rows) make this cheap.
- **FX conversion** (ADR-0006) is unchanged. It already runs in Python on decrypted amounts using plaintext rates.

### 3. Performance budget

- Target: p95 server render time for `/today`, `/ledger`, `/budget`, `/overview`, `/accounts`, `/forecast` increases by **≤ 50 ms** versus v3, on a synthetic user with 20 000 transactions, 30 accounts and 60 categories on a Stardust1-S-equivalent container.
- If exceeded, the sanctioned mitigation is a **request-scoped** decrypted-row memo, shared across the services of one request. A cross-request plaintext cache is **not** allowed, because it would hold plaintext beyond the session request (ADR-0079 A3).
- A benchmark test (`tests/perf/test_encrypted_render_budget.py`, marker `perf`, run in `just ci-perf`) guards the budget.

### 4. Metadata leakage controls

- Text plaintexts are **padded to 32-byte buckets** (length-prefixed, then zero-padded) before encryption, so names and descriptions leak only a coarse length class.
- Amounts are fixed-width int64, so they leak no magnitude.
- Accepted leaks, also published on the "What the operator can see" page (ADR-0079): row counts per table and date; dates; the FK graph (which account or category a row uses); timestamps of edits; currency per account; category colour; whether a category is system; email and display name.

### 5. Schema migration (expand, then contract)

Follows the ADR-0071 N-1 rule.

1. **Expand** (v4.0 migration). Add `<col>_ct BLOB` (and `name_bidx`) next to each plaintext column, plus the `user_key_wraps` table, `sessions.wrapped_umk` and `users.key_state` (ADR-0082). Old images ignore the new columns.
2. **Backfill per user** (ADR-0082 §2). In one transaction per user: encrypt every plaintext value into `_ct`, then set the plaintext column to `NULL`. Plaintext columns are made nullable in the expand step through the ADR-0061 table-rebuild pattern.
3. **Contract** (a later release, gated on `SELECT count(*) FROM users WHERE key_state = 'plaintext'` being `0` on prod). Drop the plaintext columns, rename `_ct` to the original names, and rebuild indexes. Then a `VACUUM` with `secure_delete` (ADR-0078 §6) followed by a fresh Litestream generation, so no plaintext page survives in the live file. Old generations expire under the 37-day ceiling (ADR-0078 §4).
4. **Per-user data migrations.** Any future migration that must *transform* encrypted values (not just schema) can't run at boot. It's registered in a `user_data_migrations` registry and applied lazily at the user's next unlock, tracked per user in `users.data_migration_version`. Boot-time `startup_migrate` stays schema-only.

### 6. Guardrails

- **Static check** (extends ADR-0068): CI parses repository SQL and fails if an encrypted column appears in `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING`, an aggregate function, or a `LIKE`. It also fails if any module outside `budget_planner.crypto` imports `cryptography` or `argon2`.
- **Round-trip property tests** (Hypothesis): every encrypted column's encode → encrypt → decrypt → decode is the identity, including negative reconciliation amounts, Unicode, empty strings and maximum-length strings.
- **"No plaintext at rest" test**: after a full journey on a scratch DB, a byte-scan of the DB and WAL files finds none of the journey's sentinel strings or amounts.
- **AAD tamper tests**: moving a ciphertext to another user, column or table fails with `DecryptionError`.

### 7. Feature preservation (R2)

| Feature | Mechanism after v4 |
|---|---|
| Ledger list, filters (account, category, date, direction) | unchanged SQL predicates on plaintext metadata |
| Ledger description search | SQL pre-filter + Python substring match (§2) |
| Day / month sums, Today hero, pace tag, Overview | Python reductions (§2) |
| Budget (defaults, recurring and one-off overrides, monthly summary) | Python reductions; same domain types |
| Forecast, recurring formulas (ADR-0047) | formulas decrypted per rule; evaluation unchanged |
| Accounts balances, liability available (T-D51), reconciliation (ADR-0011) | Python over decrypted snapshots and amounts |
| Duplicate-name prevention | blind-index unique indexes (§1) |
| Sorting by name or amount | Python sort |
| Multi-currency aggregates | unchanged (Python already) |
| CSV / Parquet export | decrypt in session; unchanged output |
| Admin panel | uses plaintext `email`/`name` only; unchanged |
| Audit log (own history) | decrypt own payloads; others' payloads unreadable (ADR-0078 §1 becomes cryptographic) |
| Demo DB build, smoke journey, restore drill | see ADR-0083 §6 |

## Consequences

- SQL keeps doing what it's good at on plaintext metadata. Value-dependent logic lives in Python, consistent with "thin web, fat services".
- About 18 aggregate sites and 1 search site are rewritten, each covered by existing behaviour tests that must pass unchanged. That's the regression net for R2.
- The metadata leaks are explicit and published rather than implicit.
- A second release (contract) is needed after every user has been backfilled. Until then, plaintext columns exist but are `NULL` for migrated users.
