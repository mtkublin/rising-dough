-- Companion down migration for `migrations/0016_audit_backfill_owner.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). The forward migration
-- is data-only (fills NULL audit_log.user_id); the previous NULLs are not
-- recoverable and the schema is unchanged, so this is a no-op.

SELECT 1;
