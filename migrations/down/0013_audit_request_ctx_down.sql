-- migrations/down/0013_audit_request_ctx_down.sql
-- Companion down migration for `migrations/0013_audit_request_ctx.sql`.
--
-- Forward-smoke-only. CI applies 0013 forward and then this file against a
-- scratch DB to prove the forward migration is structurally reversible.
-- Production migrations are forward-only — this file is **not** expected
-- to run against a live DB.
--
-- SQLite rejects `ALTER TABLE ... DROP COLUMN` on columns referenced by a
-- foreign key (the `user_id` column added by 0013 points at `users (id)`),
-- so we rebuild `audit_log` from scratch to drop the four request-context
-- columns in one shot. The rebuild preserves `actor_user_id` (added by
-- 0012) because 0013 did not touch it.
--
-- Runs under `PRAGMA foreign_keys = OFF` (the test harness toggles the
-- pragma outside the migration body, mirroring the forward runner).

CREATE TABLE audit_log_old (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    operation TEXT NOT NULL
    CHECK (operation IN ('create', 'update', 'delete', 'undelete')),
    prev_json TEXT,
    new_json TEXT,
    actor_user_id INTEGER REFERENCES users (id)
);

INSERT INTO audit_log_old (
    id, entity_type, entity_id, changed_at, operation,
    prev_json, new_json, actor_user_id
)
SELECT
    id,
    entity_type,
    entity_id,
    changed_at,
    operation,
    prev_json,
    new_json,
    actor_user_id
FROM audit_log;

DROP INDEX IF EXISTS ix_audit_entity;

DROP TABLE audit_log;

ALTER TABLE audit_log_old RENAME TO audit_log;

CREATE INDEX ix_audit_entity ON audit_log (entity_type, entity_id, changed_at);
