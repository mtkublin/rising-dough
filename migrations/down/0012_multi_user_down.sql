-- migrations/down/0012_multi_user_down.sql
-- Companion down migration for `migrations/0012_multi_user.sql`.
--
-- Purpose: forward-smoke-only. CI applies 0012 forward and then this file
-- against a scratch DB to prove the forward migration is structurally
-- reversible. Production migrations are forward-only — this file is **not**
-- expected to be run against a live database and does not attempt to
-- preserve orphan rows that have accumulated after 0012 (e.g. new users or
-- any row whose `user_id` is not 1).
--
-- Reverses, in order:
--   1. Drops `audit_log.actor_user_id` (via table rebuild — SQLite cannot
--      `DROP COLUMN` a column referenced by a foreign key).
--   2. Rebuilds every user-owned table with `user_id INTEGER NOT NULL
--      DEFAULT 1 REFERENCES users (id)` back in place.
--   3. Drops the live-email unique index and the identity columns added to
--      `users` (`email`, `password_hash`, `is_admin`, `must_change_password`,
--      `updated_at`, `deleted_at`).
--
-- Runs under `PRAGMA foreign_keys = OFF` (the test harness toggles the
-- pragma outside the migration body, mirroring the forward runner).

-------------------------------------------------------------------------------
-- 1. audit_log — remove `actor_user_id` via table rebuild
-------------------------------------------------------------------------------
CREATE TABLE audit_log_old (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    operation TEXT NOT NULL
    CHECK (operation IN ('create', 'update', 'delete', 'undelete')),
    prev_json TEXT,
    new_json TEXT
);

INSERT INTO audit_log_old (
    id, entity_type, entity_id, changed_at, operation, prev_json, new_json
)
SELECT
    id,
    entity_type,
    entity_id,
    changed_at,
    operation,
    prev_json,
    new_json
FROM audit_log;

DROP INDEX IF EXISTS ix_audit_entity;

DROP TABLE audit_log;

ALTER TABLE audit_log_old RENAME TO audit_log;

CREATE INDEX ix_audit_entity ON audit_log (entity_type, entity_id, changed_at);

-------------------------------------------------------------------------------
-- 2. user_preferences — restore pre-0012 shape (no default change, rebuild
-- is a no-op structurally but keeps parity with the forward migration)
-------------------------------------------------------------------------------
CREATE TABLE user_preferences_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, key)
);

INSERT INTO user_preferences_old (
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

ALTER TABLE user_preferences_old RENAME TO user_preferences;

-------------------------------------------------------------------------------
-- 3. budget_one_off_overrides — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE budget_one_off_overrides_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 9999),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

INSERT INTO budget_one_off_overrides_old (
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

ALTER TABLE budget_one_off_overrides_old RENAME TO budget_one_off_overrides;

CREATE UNIQUE INDEX ux_budget_one_off_cat_year_month_live
ON budget_one_off_overrides (category_id, year, month)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 4. budget_recurring_overrides — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE budget_recurring_overrides_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

INSERT INTO budget_recurring_overrides_old (
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

ALTER TABLE budget_recurring_overrides_old RENAME TO budget_recurring_overrides;

CREATE UNIQUE INDEX ux_budget_recurring_cat_month_live
ON budget_recurring_overrides (category_id, month)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 5. budget_defaults — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE budget_defaults_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
    category_id INTEGER NOT NULL REFERENCES categories (id),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP
);

INSERT INTO budget_defaults_old (
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

ALTER TABLE budget_defaults_old RENAME TO budget_defaults;

CREATE UNIQUE INDEX ux_budget_defaults_cat_live
ON budget_defaults (category_id)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 6. recurring_rules — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE recurring_rules_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
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

INSERT INTO recurring_rules_old (
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

ALTER TABLE recurring_rules_old RENAME TO recurring_rules;

CREATE INDEX ix_recurring_active ON recurring_rules (active)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 7. planned_transactions — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE planned_transactions_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
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

INSERT INTO planned_transactions_old (
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

ALTER TABLE planned_transactions_old RENAME TO planned_transactions;

CREATE INDEX ix_planned_operation_date ON planned_transactions (operation_date);
CREATE INDEX ix_planned_rule ON planned_transactions (recurring_rule_id);

-------------------------------------------------------------------------------
-- 8. transactions — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
-- Column order mirrors the v2 ADD COLUMN sequence:
-- 0002 defined the core columns; 0006 appended `promoted_from_recurring_rule_id`
-- and `promoted_from_recurring_date` AFTER `deleted_at`. The down must restore
-- that exact order so `PRAGMA table_info` matches the pre-0012 snapshot.
CREATE TABLE transactions_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
    operation_date DATE NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    dest_account_id INTEGER REFERENCES accounts (id),
    amount INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    promoted_from_planned_id INTEGER
    REFERENCES planned_transactions (id) DEFERRABLE INITIALLY DEFERRED,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    deleted_at TIMESTAMP,
    promoted_from_recurring_rule_id INTEGER
    REFERENCES recurring_rules (id) DEFERRABLE INITIALLY DEFERRED,
    promoted_from_recurring_date DATE,
    CHECK (amount <> 0),
    CHECK (account_id <> dest_account_id OR dest_account_id IS NULL)
);

INSERT INTO transactions_old (
    id, user_id, operation_date, category_id, account_id, dest_account_id,
    amount, description, promoted_from_planned_id,
    created_at, updated_at, deleted_at,
    promoted_from_recurring_rule_id, promoted_from_recurring_date
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
    created_at,
    updated_at,
    deleted_at,
    promoted_from_recurring_rule_id,
    promoted_from_recurring_date
FROM transactions;

DROP INDEX IF EXISTS ix_transactions_operation_date;
DROP INDEX IF EXISTS ix_transactions_account;
DROP INDEX IF EXISTS ix_transactions_dest_account;
DROP INDEX IF EXISTS ix_transactions_category;
DROP INDEX IF EXISTS ix_transactions_live;
DROP INDEX IF EXISTS ix_transactions_promoted_from_recurring;

DROP TABLE transactions;

ALTER TABLE transactions_old RENAME TO transactions;

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
-- 9. categories — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE categories_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
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

INSERT INTO categories_old (
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

ALTER TABLE categories_old RENAME TO categories;

CREATE UNIQUE INDEX ux_categories_user_name_live
ON categories (user_id, name)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 10. accounts — restore `DEFAULT 1` sentinel
-------------------------------------------------------------------------------
CREATE TABLE accounts_old (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users (id),
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

INSERT INTO accounts_old (
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

ALTER TABLE accounts_old RENAME TO accounts;

CREATE UNIQUE INDEX ux_accounts_user_name_live
ON accounts (user_id, name)
WHERE deleted_at IS NULL;

-------------------------------------------------------------------------------
-- 11. users — strip identity columns + live-email index
-------------------------------------------------------------------------------
DROP INDEX IF EXISTS ux_users_email_live;

CREATE TABLE users_old (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO users_old (id, name, created_at)
SELECT
    id,
    name,
    created_at
FROM users;

DROP TABLE users;

ALTER TABLE users_old RENAME TO users;
