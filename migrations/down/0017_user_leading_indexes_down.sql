-- Companion down migration for `migrations/0017_user_leading_indexes.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). Drops the four indexes
-- the forward migration created; no data is affected.

DROP INDEX ix_audit_user_id;

DROP INDEX ix_recurring_user_active;

DROP INDEX ix_planned_user_live_date;

DROP INDEX ix_transactions_user_live_date;
