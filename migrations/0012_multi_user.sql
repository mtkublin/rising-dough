-- migrations/0012_multi_user.sql
-- ADR-0061: activate the multi-user model.
--
--  1. Extend `users` with identity + credential columns (email, password_hash,
--     is_admin, must_change_password, updated_at, deleted_at) and a case-
--     insensitive unique index on live emails.
--  2. Rebuild every user-owned table to drop the `DEFAULT 1` sentinel on
--     `user_id`. From 0012 forward every INSERT must declare `user_id`
--     explicitly. All other columns, CHECK constraints, foreign keys, and
--     indices are preserved exactly as they stand at migration 0011.
--  3. Add a nullable `actor_user_id` column to `audit_log` so admin actions
--     against user rows carry the acting admin's id. NULL is reserved for
--     system-bootstrap writes and historical pre-0012 rows.
--
-- The runner wraps this file in `PRAGMA foreign_keys = OFF` (see
-- `db.migrate.FK_OFF_MIGRATIONS`) because every rebuilt table has incoming
-- foreign keys from siblings (e.g. `transactions.account_id → accounts.id`),
-- and SQLite's 12-step rebuild would otherwise refuse to drop the originals.
-- A `PRAGMA foreign_key_check` after the migration (performed by the runner)
-- fails fast if any FK dangles.

-------------------------------------------------------------------------------
-- 1. users — rebuild to add identity + credential columns in one shot
--
-- SQLite's `ALTER TABLE ADD COLUMN` rejects non-constant DEFAULT expressions
-- on NOT NULL columns (``updated_at TIMESTAMP NOT NULL DEFAULT (strftime(…))``
-- is a non-constant default). The 12-step rebuild sidesteps that limitation
-- and keeps the new column order consistent with the ADR §2 DDL.
-------------------------------------------------------------------------------
CREATE TABLE users_new (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    password_hash TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    must_change_password INTEGER NOT NULL DEFAULT 0
    CHECK (must_change_password IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

-- Pre-existing rows carry forward with NULL email/password_hash,
-- `is_admin = 0`, `must_change_password = 0`, and `updated_at = created_at`.
-- The admin bootstrap (ADR-0061 §3) promotes the `user_id = 1` row at first
-- boot by setting these fields explicitly.
INSERT INTO users_new (
    id, name, created_at, updated_at
)
SELECT
    id,
    name,
    created_at,
    created_at AS updated_at
FROM users;

DROP TABLE users;

ALTER TABLE users_new RENAME TO users;

CREATE UNIQUE INDEX ux_users_email_live
ON users (lower(email))
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 2. accounts — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE accounts_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    type TEXT,
    currency TEXT NOT NULL CHECK (length(currency) = 3),
    opening_balance INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP,
    is_liability INTEGER NOT NULL DEFAULT 0 CHECK (is_liability IN (0, 1)),
    credit_limit_minor INTEGER
    CHECK (credit_limit_minor IS NULL OR credit_limit_minor > 0)
);

INSERT INTO accounts_new (
    id, user_id, name, type, currency, opening_balance,
    created_at, updated_at, deleted_at, is_liability, credit_limit_minor
)
SELECT
    id,
    user_id,
    name,
    type,
    currency,
    opening_balance,
    created_at,
    updated_at,
    deleted_at,
    is_liability,
    credit_limit_minor
FROM accounts;

DROP INDEX IF EXISTS ux_accounts_user_name_live;

DROP TABLE accounts;

ALTER TABLE accounts_new RENAME TO accounts;

CREATE UNIQUE INDEX ux_accounts_user_name_live
ON accounts (user_id, name)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 3. categories — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE categories_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    direction TEXT NOT NULL
    CHECK (direction IN ('income', 'expense', 'transit', 'adjustment')),
    is_system INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP,
    color TEXT
    CHECK (color IS NULL OR color GLOB '#[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]')
);

INSERT INTO categories_new (
    id, user_id, name, direction, is_system,
    created_at, updated_at, deleted_at, color
)
SELECT
    id,
    user_id,
    name,
    direction,
    is_system,
    created_at,
    updated_at,
    deleted_at,
    color
FROM categories;

DROP INDEX IF EXISTS ux_categories_user_name_live;

DROP TABLE categories;

ALTER TABLE categories_new RENAME TO categories;

CREATE UNIQUE INDEX ux_categories_user_name_live
ON categories (user_id, name)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 4. transactions — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE transactions_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    operation_date DATE NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    dest_account_id INTEGER REFERENCES accounts (id),
    amount INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    promoted_from_planned_id INTEGER
    REFERENCES planned_transactions (id) DEFERRABLE INITIALLY DEFERRED,
    promoted_from_recurring_rule_id INTEGER
    REFERENCES recurring_rules (id) DEFERRABLE INITIALLY DEFERRED,
    promoted_from_recurring_date DATE,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP,
    CHECK (amount <> 0),
    CHECK (account_id <> dest_account_id OR dest_account_id IS NULL)
);

INSERT INTO transactions_new (
    id, user_id, operation_date, category_id, account_id, dest_account_id,
    amount, description, promoted_from_planned_id,
    promoted_from_recurring_rule_id, promoted_from_recurring_date,
    created_at, updated_at, deleted_at
)
SELECT
    id,
    user_id,
    operation_date,
    category_id,
    account_id,
    dest_account_id,
    amount,
    description,
    promoted_from_planned_id,
    promoted_from_recurring_rule_id,
    promoted_from_recurring_date,
    created_at,
    updated_at,
    deleted_at
FROM transactions;

DROP INDEX IF EXISTS ix_transactions_operation_date;
DROP INDEX IF EXISTS ix_transactions_account;
DROP INDEX IF EXISTS ix_transactions_dest_account;
DROP INDEX IF EXISTS ix_transactions_category;
DROP INDEX IF EXISTS ix_transactions_live;
DROP INDEX IF EXISTS ix_transactions_promoted_from_recurring;

DROP TABLE transactions;

ALTER TABLE transactions_new RENAME TO transactions;

CREATE INDEX ix_transactions_operation_date ON transactions (operation_date);
CREATE INDEX ix_transactions_account ON transactions (account_id);
CREATE INDEX ix_transactions_dest_account ON transactions (dest_account_id);
CREATE INDEX ix_transactions_category ON transactions (category_id);
CREATE INDEX ix_transactions_live
ON transactions (operation_date)
WHERE deleted_at IS NULL;
CREATE INDEX ix_transactions_promoted_from_recurring
ON transactions (promoted_from_recurring_rule_id, promoted_from_recurring_date);

-------------------------------------------------------------------------------
-- 5. planned_transactions — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE planned_transactions_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    operation_date DATE NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    dest_account_id INTEGER REFERENCES accounts (id),
    amount INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    recurring_rule_id INTEGER
    REFERENCES recurring_rules (id) DEFERRABLE INITIALLY DEFERRED,
    occurrence_date DATE,
    promoted_to_txn_id INTEGER REFERENCES transactions (id),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP,
    CHECK (amount <> 0),
    CHECK (account_id <> dest_account_id OR dest_account_id IS NULL)
);

INSERT INTO planned_transactions_new (
    id, user_id, operation_date, category_id, account_id, dest_account_id,
    amount, description, recurring_rule_id, occurrence_date,
    promoted_to_txn_id, created_at, updated_at, deleted_at
)
SELECT
    id,
    user_id,
    operation_date,
    category_id,
    account_id,
    dest_account_id,
    amount,
    description,
    recurring_rule_id,
    occurrence_date,
    promoted_to_txn_id,
    created_at,
    updated_at,
    deleted_at
FROM planned_transactions;

DROP INDEX IF EXISTS ix_planned_operation_date;
DROP INDEX IF EXISTS ix_planned_rule;

DROP TABLE planned_transactions;

ALTER TABLE planned_transactions_new RENAME TO planned_transactions;

CREATE INDEX ix_planned_operation_date ON planned_transactions (operation_date);
CREATE INDEX ix_planned_rule ON planned_transactions (recurring_rule_id);

-------------------------------------------------------------------------------
-- 6. recurring_rules — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE recurring_rules_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    cadence TEXT NOT NULL CHECK (cadence IN ('monthly', 'quarterly', 'yearly')),
    start_date DATE NOT NULL,
    end_date DATE,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    dest_account_id INTEGER REFERENCES accounts (id),
    default_amount INTEGER NOT NULL,
    default_description TEXT NOT NULL DEFAULT '',
    day_of_month INTEGER CHECK (day_of_month BETWEEN 1 AND 31),
    month_of_year INTEGER CHECK (month_of_year BETWEEN 1 AND 12),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    next_due DATE NOT NULL,
    last_promoted_date DATE,
    amount_formula TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP,
    CHECK (end_date IS NULL OR end_date >= start_date),
    CHECK (amount_formula IS NOT NULL OR default_amount <> 0)
);

INSERT INTO recurring_rules_new (
    id, user_id, cadence, start_date, end_date, category_id, account_id,
    dest_account_id, default_amount, default_description, day_of_month,
    month_of_year, active, next_due, last_promoted_date, amount_formula,
    created_at, updated_at, deleted_at
)
SELECT
    id,
    user_id,
    cadence,
    start_date,
    end_date,
    category_id,
    account_id,
    dest_account_id,
    default_amount,
    default_description,
    day_of_month,
    month_of_year,
    active,
    next_due,
    last_promoted_date,
    amount_formula,
    created_at,
    updated_at,
    deleted_at
FROM recurring_rules;

DROP INDEX IF EXISTS ix_recurring_active;

DROP TABLE recurring_rules;

ALTER TABLE recurring_rules_new RENAME TO recurring_rules;

CREATE INDEX ix_recurring_active ON recurring_rules (active)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 7. budget_defaults — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE budget_defaults_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

INSERT INTO budget_defaults_new (
    id, user_id, category_id, amount, created_at, updated_at, deleted_at
)
SELECT
    id,
    user_id,
    category_id,
    amount,
    created_at,
    updated_at,
    deleted_at
FROM budget_defaults;

DROP INDEX IF EXISTS ux_budget_defaults_cat_live;

DROP TABLE budget_defaults;

ALTER TABLE budget_defaults_new RENAME TO budget_defaults;

CREATE UNIQUE INDEX ux_budget_defaults_cat_live
ON budget_defaults (category_id)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 8. budget_recurring_overrides — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE budget_recurring_overrides_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

INSERT INTO budget_recurring_overrides_new (
    id, user_id, category_id, month, amount, created_at, updated_at, deleted_at
)
SELECT
    id,
    user_id,
    category_id,
    month,
    amount,
    created_at,
    updated_at,
    deleted_at
FROM budget_recurring_overrides;

DROP INDEX IF EXISTS ux_budget_recurring_cat_month_live;

DROP TABLE budget_recurring_overrides;

ALTER TABLE budget_recurring_overrides_new RENAME TO budget_recurring_overrides;

CREATE UNIQUE INDEX ux_budget_recurring_cat_month_live
ON budget_recurring_overrides (category_id, month)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 9. budget_one_off_overrides — rebuild without `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE budget_one_off_overrides_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 9999),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

INSERT INTO budget_one_off_overrides_new (
    id, user_id, category_id, year, month, amount,
    created_at, updated_at, deleted_at
)
SELECT
    id,
    user_id,
    category_id,
    year,
    month,
    amount,
    created_at,
    updated_at,
    deleted_at
FROM budget_one_off_overrides;

DROP INDEX IF EXISTS ux_budget_one_off_cat_year_month_live;

DROP TABLE budget_one_off_overrides;

ALTER TABLE budget_one_off_overrides_new RENAME TO budget_one_off_overrides;

CREATE UNIQUE INDEX ux_budget_one_off_cat_year_month_live
ON budget_one_off_overrides (category_id, year, month)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 10. user_preferences — rebuild without `DEFAULT 1` sentinel
--
-- The original table has no `DEFAULT 1` to drop (migration 0005 declared
-- `user_id INTEGER NOT NULL REFERENCES users (id)` without a default) but
-- we rebuild it anyway so the SQLite-stored `sql` of every user-owned
-- table flows through this migration — downstream tooling that greps
-- `sqlite_master` for the sentinel keeps a uniform shape.
-------------------------------------------------------------------------------
CREATE TABLE user_preferences_new (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, key)
);

INSERT INTO user_preferences_new (
    id, user_id, key, value, created_at, updated_at
)
SELECT
    id,
    user_id,
    key,
    value,
    created_at,
    updated_at
FROM user_preferences;

DROP TABLE user_preferences;

ALTER TABLE user_preferences_new RENAME TO user_preferences;

-------------------------------------------------------------------------------
-- 11. audit_log — nullable actor column for admin + system attribution
-------------------------------------------------------------------------------
ALTER TABLE audit_log
ADD COLUMN actor_user_id INTEGER REFERENCES users (id);
