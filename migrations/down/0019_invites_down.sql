-- Companion down migration for `migrations/0019_invites.sql`.
--
-- Forward-smoke-only (see migrations/down/README.md). Drops the indexes and
-- the table; invite rows are not restorable.

DROP INDEX ix_invites_email_live;

DROP INDEX ux_invites_token_hash;

DROP TABLE invites;
