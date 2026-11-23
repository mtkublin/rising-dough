-- 0020_setup_token_consumed - T-UR32 (ADR-0134 section 9, ADR-0148).
--
-- `setup_token_consumed` - the one-time setup token marker. The app stores no
-- token (only the operator-supplied hash in config); this row records that
-- first-run setup has been completed (the created admin is in the audit row).
-- `id = 1` keeps it a
-- single-row table: a second consume violates the primary key.
--
-- Expand-only (one new table): N-1 images keep working.

CREATE TABLE setup_token_consumed (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    consumed_at TIMESTAMP NOT NULL
);
