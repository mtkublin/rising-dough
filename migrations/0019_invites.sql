-- 0019_invites - T-UR30 (ADR-0134 section 1 and 10, ADR-0148).
--
-- `invites`: an admin invites a person by email and role. Only the sha256 of
-- the token is stored (never the token). Lifecycle columns: `used_at` (the
-- invitee accepted), `revoked_at` (final), `expires_at` (7 days from create or
-- resend, set by the service). Soft delete via `deleted_at`; every mutation is
-- audited by the repository. `invited_by` is the admin who created it.
--
-- Expand-only (one new table, two indexes): N-1 images keep working.

CREATE TABLE invites (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    invited_by INTEGER NOT NULL REFERENCES users (id),
    token_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    revoked_at TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE UNIQUE INDEX ux_invites_token_hash
ON invites (token_hash);

CREATE INDEX ix_invites_email_live
ON invites (lower(email))
WHERE deleted_at IS NULL;
