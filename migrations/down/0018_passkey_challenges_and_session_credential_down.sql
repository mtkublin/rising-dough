-- Companion down migration for
-- `migrations/0018_passkey_challenges_and_session_credential.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). Drops the index,
-- the column and the table; consumed-challenge rows are not restorable.

DROP INDEX ix_sessions_credential;

ALTER TABLE sessions DROP COLUMN credential_id;

DROP INDEX ix_passkey_challenges_consumed_at;

DROP TABLE passkey_challenges_consumed;
