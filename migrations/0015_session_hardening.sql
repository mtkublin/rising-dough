-- 0015_session_hardening — T-D53a, ADR-0076 §1/§3.
--
-- 1. `sessions.authenticated_at` — when the session holder last proved a
--    credential (login / re-auth / password change). NULL (rows from before
--    this migration) is read as `created_at` by the repository.
-- 2. `sessions.id` now stores sha256(cookie token) hex instead of the raw
--    token. SQLite has no built-in sha256, so existing raw ids cannot be
--    rehashed here: every live session is revoked and users sign in once.
--
-- Expand-only (one nullable column + an UPDATE), so N-1 images still run;
-- an N-1 image looks raw cookie values up against hashed ids, finds
-- nothing, and sends users to login (ADR-0071 §4, ADR-0076 §3).

ALTER TABLE sessions ADD COLUMN authenticated_at TIMESTAMP;

UPDATE sessions
SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE revoked_at IS NULL;
