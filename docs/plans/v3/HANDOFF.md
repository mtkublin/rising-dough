# Rising Dough v3 Phase 1 continuation

## Where we are

v3 is on origin at `3777898`. Phase 1 is mostly landed; remaining tasks and known state below.

## Branch state

- v3 HEAD: `3777898 merge(T-D08a): CSRF dev cookie fix`
- Everything below is merged into v3 unless noted.

## Landed on v3

**Phase 1 app prerequisites:**
- T-D01 `/health` + `/ready` endpoints
- T-D03 production config surface (`env`, `bind_host`, `bind_port`, `trusted_hosts`, `cookie_secret`, `session_lifetime_days`)
- T-D04 Litestream-friendly `database_url` + startup PRAGMA assertion
- T-D05 central Litestream PRAGMAs in `db/connection.py`
- T-D06 structlog JSON logging bound to `request_id`
- T-D07 `SecurityHeadersMiddleware` + CSP nonce propagation into Jinja context
- T-D08 CSRF middleware (`__Host-csrf` cookie, HTMX extension) + T-D08a dev-cookie fix (ADR-0065)
- T-D10 multi-stage non-root Dockerfile + `.dockerignore`
- T-D11 docker-compose prod-sim stack (app + caddy + litestream + minio) + `just test-prod-stack`
- T-D12 `uv.lock` frozen + lock-check CI
- T-D13 CI security scans (`pip-audit`, `trivy fs`, `trivy image`) + `.security-allowlist.yml`
- T-D14 audit log request-ctx (migration `0013_audit_request_ctx.sql`, `RequestCtx` dataclass, `get_request_ctx` dep, `write_audit(..., request_ctx=...)` kwarg)
- T-D15 graceful shutdown via lifespan + SIGTERM observer
- T-D16a multi-user migration `0012_multi_user.sql` (users grows `email`/`password_hash`/`is_admin`/`must_change_password`/`updated_at`/`deleted_at`; every user-owned table rebuilt without `DEFAULT 1` sentinel; `audit_log` gets `actor_user_id`)

**Phase 2 Terraform IaC:**
- T-D20..T-D24, T-D28 full `terraform/` tree + `.github/workflows/terraform.yml`

**Phase 3 deploy pipeline:**
- T-D30 build + cosign-sign workflow
- T-D31 deploy-drill + deploy-prod workflows
- T-D32 `terraform/cloud-init/bin/deploy-budget-planner.tpl`
- T-D34 manual rollback workflow

**Phase 4 ops artefacts:**
- T-D41 monthly restore-drill workflow
- T-D46 operational runbooks (deploy, rollback, restore, DR, user-admin, restore-log) + README
- `.github/dependabot.yml`

## Deferred / reverted

- **T-D16 repository `user_id` scoping sweep + sqlglot architecture test** — reverted after a WIP merge (`946330b`) broke the test suite. Repo + service + `web/deps.current_user_id` sweep was done but routers + ~50 test files + architecture test were not. Needs a dedicated pass. `web/deps.current_user_id(request)` dep exists on v3 today with a `return 1` fallback marked `TODO(T-D02)`.
- **T-D27 / T-D25 / T-D26 / T-D33 / T-D40 / T-D42 / T-D44 / T-D45** — human-gated (actual Scaleway apply, security scan, uptime monitor, cost alert, etc.).

## Still open on Phase 1

### T-D02 — Per-user password + passkey auth (biggest piece, nothing landed on v3)

An earlier attempt committed 6 of 10 chunks on a worktree branch that was later discarded because it diverged. The 6 chunks were sound: migration `0014`, bcrypt helper, sessions repo, webauthn repo, auth service, `AuthRequiredMiddleware`. **Treat T-D02 as a from-scratch task on current v3 head.**

Full brief:

- Migration `migrations/0014_v2_auth.sql` + `migrations/down/0014_v2_auth_down.sql`:
  - `webauthn_credentials` (id, user_id FK users.id, credential_id BLOB UNIQUE, public_key BLOB, sign_count INTEGER, transports TEXT, label TEXT, created_at)
  - `sessions` (id TEXT PRIMARY KEY — the session cookie value; user_id FK users.id; created_at, last_seen_at, expires_at, revoked_at, user_agent, ip)
  - `auth_rate_limit` (id, key TEXT, bucket_start TIMESTAMP, count INTEGER)
- Add `bcrypt` and `webauthn` to `pyproject.toml` runtime deps; `uv lock` refresh.
- `src/budget_planner/services/_passwords.py` — `hash_password(plain) -> str` (bcrypt cost 12), `verify_password(plain, hashed) -> bool`.
- `src/budget_planner/repositories/sessions.py` — frozen `Session` dataclass + `create_session`, `get_session` (None on revoked/expired), `revoke_session`, `revoke_all_user_sessions(..., except_session_id=None)`, `touch_session`. Session id = `secrets.token_urlsafe(32)`.
- `src/budget_planner/repositories/webauthn.py` — `list_credentials`, `create_credential`, `update_sign_count`. Frozen `WebAuthnCredential` dataclass.
- `src/budget_planner/services/auth.py` — `authenticate_password(conn, email, password, ip, user_agent) -> Session | None` (verifies against `users.password_hash`, creates session, writes audit via existing `write_audit(..., request_ctx=...)`), `logout(conn, session_id)`, `register_passkey_begin/finish`, `authenticate_passkey_begin/finish`. Use the `webauthn` package's ceremony helpers.
- `src/budget_planner/web/middleware/auth.py` — `AuthRequiredMiddleware` reads `__Host-session` cookie, looks up session, attaches `request.state.user = User(id=..., email=..., is_admin=...)` + `request.state.session_id`. Unauthenticated requests to protected routes → 302 to `/auth/login` (HTML) or 401 JSON (HTMX / API). Exempt paths: `/health`, `/ready`, `/auth/*`, `/static/*`. Register in `web/app.py` **after CSRF middleware**, before router dispatch.
- `src/budget_planner/web/routers/auth.py` + `web/templates/auth/{login,register,sessions}.html`:
  - `GET /auth/login` + `POST /auth/login` (password; passkey challenge; `/auth/login/finish` for passkey ceremony finish). Generic error on login failure — never reveal whether the email exists.
  - `POST /auth/logout` — revoke current session, redirect to `/auth/login`.
  - `GET /auth/register` + `POST /auth/register` + `POST /auth/register/finish` — passkey registration for the logged-in user.
  - `GET /auth/sessions` + `POST /auth/sessions/<id>/revoke` — list + revoke own sessions.
- Update `web/deps.current_user_id` to drop the `return 1` dev fallback and read `request.state.user.id`; `AuthRequiredMiddleware` provides it.
- Dev fixture: when `BUDGET_ENV=dev`, seed `admin@local.test` with password `admin` (startup hook or seed script). Test fixture provides the same.
- Tests under `tests/integration/web/`: `test_auth_login.py` (password happy path, wrong password, generic error, session cookie set), `test_auth_logout.py`, `test_auth_middleware.py` (unauth → 302 or 401 for HTMX), `test_auth_passkey.py` (webauthn ceremony with mocked public-key crypto if needed). Migration test for `0014` under `tests/integration/db/test_migrations.py`.
- Reference: `docs/adr/0033-v3-auth-single-user-passkey.md` (full spec, §1–§6), amended by `docs/adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md` (per-user password hashes live on `users.password_hash` from migration 0012).

### T-D09 — Rate limit on auth routes

- Add `slowapi` to deps.
- Apply slowapi rate limits to `/auth/login`, `/auth/register/finish`, `/auth/login/finish` per ADR-0033 §2 (e.g. 5/min + 20/hour per IP+email tuple).
- Return `429 Retry-After` on throttle.
- Backing table `auth_rate_limit` already lands with T-D02's migration 0014.
- `tests/integration/web/test_auth_rate_limit.py` — fire the limit, assert 429 + `Retry-After`.
- Reference: `docs/adr/0033-v3-auth-single-user-passkey.md` §2.

### T-D17 — `/settings/users` admin panel

- Admin-only routes under `/settings/users`: list, add (shows auto-generated password once via HTMX toast), edit (email, name, `is_admin` toggle), reset password, remove (soft-delete + session revoke in one tx).
- `AdminRequiredMiddleware` returns **404** (not 403) to non-admins to avoid admin-surface fingerprinting.
- Service invariants: last-admin cannot be deleted or demoted; email must be unique among live users (case-insensitive); creating a user seeds the two per-user system categories (`Transit`, `Reconciliation`) in the same tx.
- Auto-generated password: `secrets.token_urlsafe(16)` (~128 bits). Rendered once via HTMX toast with copy-to-clipboard. Server never persists plaintext.
- Templates: `templates/settings/users/{list,edit,_row,_password-toast}.html`.
- Audit: every mutation writes `audit_log` row with `entity_type='users'`, `entity_id=<target_user_id>`, `actor_user_id=<admin_user_id>` (`actor_user_id` column added by T-D16a).
- Reference: `docs/adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md` §4.

### T-D18 — `/settings/password` password change

- Form: current password, new password, confirm new password.
- Service: verify current with bcrypt → hash new → clear `must_change_password` → revoke all **other** sessions of the same user in the same tx (current session stays live).
- `must_change_password` flag forces redirect to `/settings/password` before any other authenticated route (integration test asserts the redirect).
- Audit row written on success AND on failed-verify attempts (both annotated with IP + user-agent via `RequestCtx`).
- Template: `templates/settings/password.html`.
- Reference: `docs/adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md` §4.

### T-D19 — Admin bootstrap on startup

- Lifespan hook calls `services.users.bootstrap_admin(conn, env)`.
- Idempotent. If any `is_admin = 1 AND deleted_at IS NULL` user exists → no-op. Else read `BUDGET_PLANNER_ADMIN_EMAIL` + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` from env; create (or promote existing matching user) with `is_admin = 1`, `password_hash = bcrypt(initial_password)`, `must_change_password = 1`.
- Logs structured line (`event="admin_bootstrap"`, `admin_email=<email>`, `action="created"|"promoted"|"noop"`); never logs the password.
- Startup fails fast (non-zero exit) if no admin exists AND either env var is missing.
- Dev fixture bootstraps `admin@local.test` / `admin` when `BUDGET_ENV=dev` (overlaps with T-D02 dev fixture; coordinate).
- Reference: `docs/adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md` §3.

### T-D43 — Playwright smoke journey (post-deploy)

- `tests/smoke/test_prod_smoke.py` — single long journey, not in CI, run manually against production hostname.
- Flow per ADR-0061 end-to-end: admin logs in with Terraform-captured password → rotates it via `/settings/password` → creates a second non-admin user via `/settings/users` (captures one-shot auto-generated password) → logs out → second user logs in → rotates password → registers a passkey → adds a transaction → sees it on `/ledger` → admin logs back in and asserts the second user's transaction is **not** visible on admin's own `/ledger` (data-isolation assertion) → verify `audit_log` row via auth-gated `/debug/audit-tail` route.
- Needs: T-D02, T-D14, T-D17, T-D18, T-D19 all landed. Depends on T-D16 for the data-isolation assertion to be meaningful (if T-D16 still deferred, note it; the test can still exercise everything else).

## Dependency ordering

Within what's left: T-D02 must land before T-D09 / T-D17 / T-D18 / T-D19 can reasonably test. T-D19 should also land before T-D17 so the admin exists for admin-panel integration tests. T-D43 is last.

T-D16 (repo scoping sweep) is still a prerequisite for proper data isolation but can be deferred to a later session without blocking the auth stack from landing.

## Known workspace hazards

- Agent isolation worktrees under `.claude/worktrees/agent-*` sometimes branch off an **outdated** v3 head. Dispatch guidance: push v3 to origin before dispatching, verify `git log <worktree-branch> --oneline -3` shows the latest merge commit as its base, else rebase before merge.
- Pre-commit hook config was repaired earlier (previous installation pointed at a deleted phase8 venv). Config now points at `.venv/bin/python`. If a worktree inherits a broken hook config, run `uv run pre-commit install --install-hooks` once from the project root.
- Pre-commit `pytest-fast` runs the full fast suite. Expect ~1–3 min per commit.
- A prior agent destroyed `data/budget.sqlite` by running `just migrate` against the default path. The CLAUDE.md "Databases" rule is now explicit and hard — no agent should touch `data/budget.sqlite` under any circumstance.

## Files worth skimming before starting

- `docs/plans/v3/implementation_plan.md` — phased plan + exit criteria
- `docs/plans/v3/tasks.md` — flat index with `✅` on done items
- `docs/plans/v3/phase-1-prerequisites/T-D02-auth-webauthn.md`, `T-D17-user-admin-panel.md`, `T-D18-password-change.md`, `T-D19-admin-bootstrap.md` — task-level deliverables + acceptance
- `docs/adr/0033-v3-auth-single-user-passkey.md`, `docs/adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md` — specs
- `src/budget_planner/web/middleware/{request_id,security_headers,csrf}.py` — existing middleware pattern
- `src/budget_planner/web/deps.py` — `current_user_id` with `TODO(T-D02)` fallback
- `src/budget_planner/domain/request_ctx.py` + `src/budget_planner/repositories/_shared.write_audit` — T-D14 audit plumbing to reuse

Hand-off ends here.
