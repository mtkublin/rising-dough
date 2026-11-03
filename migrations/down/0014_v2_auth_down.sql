-- Companion down migration for `migrations/0014_v2_auth.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). 0014 only creates
-- new tables + indexes, so reversing it is a plain drop in reverse order.
-- Dropping an index explicitly before its table is redundant in SQLite but
-- keeps the reversal symmetrical and reviewable.

DROP INDEX IF EXISTS ux_auth_rate_limit_key_bucket;

DROP TABLE IF EXISTS auth_rate_limit;

DROP INDEX IF EXISTS ix_sessions_user;

DROP TABLE IF EXISTS sessions;

DROP INDEX IF EXISTS ix_webauthn_credentials_user;

DROP TABLE IF EXISTS webauthn_credentials;
