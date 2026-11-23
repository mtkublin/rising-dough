-- Companion down migration for `migrations/0020_setup_token_consumed.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). Drops the table; the
-- consumed marker is not restorable.

DROP TABLE setup_token_consumed;
