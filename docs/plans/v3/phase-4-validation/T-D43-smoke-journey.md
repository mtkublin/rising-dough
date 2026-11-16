# T-D43: Post-deploy smoke journey

Status: written, validated locally; **production run pending** (human, after T-D27).

## Deliverables

- `tests/smoke/test_prod_smoke.py`: one long Playwright journey, marker `smoke`.
  Excluded from default runs and CI (`addopts` has `-m "not visual and not smoke"`); opt in with `-m smoke tests/smoke`.
- `GET /debug/audit-tail?n=20` (`web/routers/debug.py`, `services/audit_tail.py`): admin-only (404 for non-admins, login redirect for anonymous), `n` capped at 100, newest first, keys containing `password`/`secret`/`token`/`hash` redacted. Tests: `tests/integration/web/test_debug_audit_tail.py`.
- Runbook section "Post-deploy smoke journey" in `docs/plans/v3/runbooks/deploy.md`.

## Journey

1. Admin signs in (falls back to the new password if already rotated); rotates via `/settings/password` when forced.
2. Admin creates a non-admin user at `/settings/users` and captures the one-shot password from the toast; signs out.
3. Second user signs in, is forced to `/settings/password`, rotates.
4. Registers a passkey on `/auth/register` using a CDP virtual authenticator (ctap2, internal, resident key, user verification).
5. Creates an account and category, adds a transaction whose description is a random marker, sees it on `/ledger`; signs out.
6. Admin signs back in; the marker must NOT appear on the admin's `/ledger`.
7. `/debug/audit-tail?n=100` contains an audit row mentioning the marker and no `password_hash`.
8. Admin soft-deletes the smoke user.

## Configuration

`SMOKE_BASE_URL`, `SMOKE_ADMIN_EMAIL`, `SMOKE_ADMIN_PASSWORD`, `SMOKE_ADMIN_NEW_PASSWORD` (test skips with a reason if any is unset). Server `BUDGET_WEBAUTHN_RP_ID` / `BUDGET_WEBAUTHN_ORIGIN` must match the base URL. Locally use `http://localhost:<port>` with `BUDGET_ENV=dev` (Chromium rejects an IP rp_id; dev cookie names per ADR-0070).

## Acceptance

- Local run against a scratch DB passes (done 2026-11-03, about 25 s; second run passes via the already-rotated fallback).
- Production run passes; record date and SHA here: _pending_.
- Stays within ADR-0072 rate limits (4 password sign-ins).
