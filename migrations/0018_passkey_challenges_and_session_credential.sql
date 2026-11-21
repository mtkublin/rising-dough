-- 0018_passkey_challenges_and_session_credential - T-Q253, Q-062 (ADR-0067 amendment 2026-11-21).
--
-- 1. `passkey_challenges_consumed` - sha256(challenge) of every passkey
--    challenge a `*_finish` call has used. The primary key makes the first
--    attempt win atomically, so a challenge is single-use (replay of a
--    captured assertion fails). Old rows are pruned by the repository.
-- 2. `sessions.credential_id` - `webauthn_credentials.id` a passkey login
--    used (NULL for password sessions and rows from before this migration).
--    Revoking a passkey ends the sessions that carry it.
--
-- Expand-only (one new table, one nullable column): N-1 images keep working.

CREATE TABLE passkey_challenges_consumed (
    challenge_hash TEXT PRIMARY KEY,
    consumed_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_passkey_challenges_consumed_at
ON passkey_challenges_consumed (consumed_at);

ALTER TABLE sessions ADD COLUMN credential_id INTEGER;

CREATE INDEX ix_sessions_credential
ON sessions (credential_id)
WHERE credential_id IS NOT NULL;
