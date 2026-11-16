-- migrations/0013_audit_request_ctx.sql
-- T-D14: attach request-context columns to `audit_log` (ADR-0019, ADR-0061 §5).
--
-- Every mutation in the service layer will carry a `RequestCtx` captured from
-- the FastAPI dependency. The request's client IP, acting session user id,
-- opaque session id, and user-agent string are persisted alongside the audit
-- row so forensic reads can reconstruct "who did what from where" even for
-- rows that pre-date T-D02 (the auth bootstrap).
--
-- All four columns are nullable:
--   * historical rows (pre-0013) survive with NULL on every new column;
--   * system-bootstrap writes (seed scripts, migrations) have no request;
--   * `user_id` is NULL until T-D02 wires sessions through.
--
-- `user_id` is the acting-session user (the person who clicked the button);
-- it is intentionally distinct from `actor_user_id` (added in 0012), which
-- records the admin issuing a privileged mutation against another user's row.
-- When both are present and equal the mutation is self-driven; when they
-- differ the session user is operating on behalf of (or against) the actor.
--
-- No table rebuild — `ALTER TABLE ... ADD COLUMN` is sufficient here because
-- (a) every new column is nullable and (b) none of them participate in a
-- CHECK that references another column.

ALTER TABLE audit_log ADD COLUMN ip TEXT;

ALTER TABLE audit_log ADD COLUMN user_id INTEGER REFERENCES users (id);

ALTER TABLE audit_log ADD COLUMN session_id TEXT;

ALTER TABLE audit_log ADD COLUMN user_agent TEXT;
