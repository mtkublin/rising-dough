-- migrations/0014_v2_auth.sql
-- T-D02a: auth backend tables (ADR-0033 §1–§3 as amended by ADR-0061, ADR-0067).
--
--  1. `webauthn_credentials` — one row per registered passkey, owned by a
--     user. `credential_id` is the authenticator's raw credential id (BLOB,
--     globally unique). Soft-deleted (`deleted_at`) on manual removal or on
--     a sign-count regression (cloned authenticator, ADR-0067 §3).
--  2. `sessions` — server-side session store. `id` is the opaque random
--     cookie value (`secrets.token_urlsafe(32)`, ADR-0067 §2). Revocation
--     sets `revoked_at`; expiry is sliding via `expires_at`.
--  3. `auth_rate_limit` — fixed-window counters keyed by an opaque string
--     (e.g. `login:<ip>:<email>`). Ships empty; consumed by T-D09.
--
-- Password hashes are NOT stored here — they live on `users.password_hash`
-- (migration 0012, ADR-0061). Pure CREATE migration: no rebuilds, so it
-- runs with foreign keys ON.

CREATE TABLE webauthn_credentials (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    credential_id BLOB NOT NULL UNIQUE,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
    transports TEXT,
    label TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_used_at TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE INDEX ix_webauthn_credentials_user
ON webauthn_credentials (user_id)
WHERE deleted_at IS NULL;

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    user_agent TEXT,
    ip TEXT
);

CREATE INDEX ix_sessions_user ON sessions (user_id, revoked_at);

CREATE TABLE auth_rate_limit (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    bucket_start TIMESTAMP NOT NULL,
    count INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0)
);

CREATE UNIQUE INDEX ux_auth_rate_limit_key_bucket
ON auth_rate_limit (key, bucket_start);
