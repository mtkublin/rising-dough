-- Companion down migration for `migrations/0015_session_hardening.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). Drops the added
-- column. The session revocations done by the forward migration are data
-- and are not (and cannot be) restored.

ALTER TABLE sessions DROP COLUMN authenticated_at;
