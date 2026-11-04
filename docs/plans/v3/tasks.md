# Rising Dough v3 — Tasks

> Flat index. Full detail per task lives in the matching `phase-N-*/T-Dxx-*.md` file.
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-Dxx` depends on upstream task.
> Acceptance = ADR referenced + tests + validation hook from the task file passes + `✅` prefix added here.

---

## Phase 1 — App prerequisites (local, no Scaleway yet)

Owner: application code. All tasks block Phase 2.

### ✅ T-D01 [P] Health & readiness endpoints
- `GET /health` → 200 iff process is up. No DB, no auth.
- `GET /ready` → 200 iff `PRAGMA integrity_check` returns `ok` on `/data/budget.db`; 503 otherwise. No auth.
- Mounted outside the auth middleware (ADR-0033 §5).
- File: `phase-1-prerequisites/T-D01-health-endpoints.md`. Reference: ADR-0032 §8.

### ✅ T-D02 [S] Per-user password + passkey auth → T-D16a
- Amended by ADR-0061: passwords are per-user attributes on `users.password_hash`, not a global fallback. The `/auth/fallback-login` route is retired.
- Tables (new migration `0014_v2_auth.sql`): `webauthn_credentials`, `sessions`, `auth_rate_limit`. (`auth_password` from the original plan is deleted — password hash now lives on `users.password_hash` added by migration `0012` in T-D16a.)
- Routes: `/auth/login`, `/auth/login/finish` (passkey ceremony), `/auth/register`, `/auth/register/finish` (passkey registration for the logged-in user), `/auth/logout`, `/auth/sessions`, `/auth/sessions/<id>/revoke`. Password login is handled by the same `/auth/login` form when the request body carries a `password` field.
- Middleware chain per ADR-0033 §5, with `AuthRequiredMiddleware` reading `request.state.user` as a real `User` DTO (not a `user_id=1` constant).
- Dev fixture seeds a known admin + password hash under `if settings.env == "dev"` so local tests do not need Terraform.
- `/auth/*` responses never leak whether a user exists (generic error on login failure).
- File: `phase-1-prerequisites/T-D02-auth-webauthn.md`. Reference: ADR-0033 (as amended by ADR-0061).
- Split into two work items:
  - ✅ **T-D02a** backend core — migration `0014_v2_auth.sql` (+ down), `services/_passwords.py` (bcrypt), `repositories/sessions.py`, `repositories/webauthn.py`, `repositories/auth_users.py`, `services/auth.py` (password + passkey ceremonies, stateless challenge API), `webauthn_rp_*` settings. ADR-0067.
  - ✅ **T-D02b** web layer — `AuthRequiredMiddleware` (`web/middleware/auth.py`), `/auth/*` routes (`web/routers/auth.py`) + `templates/auth/{login,register,sessions}.html`, `static/js/passkeys.js`, HMAC-signed challenge cookie + env-dependent cookie names (`web/auth_cookies.py`), `web/deps.current_user_id` from the session (dev fallback removed), Security + Sign out in the nav, authenticated test fixtures. Dev admin seeding is owned by T-D19. ADR-0070.

### ✅ T-D03 [P] Config surface for production → T-D04
- `pydantic-settings` fields added: `bind_host` (default `127.0.0.1`), `bind_port` (default `8000`), `trusted_hosts` (list), `cookie_secret`, `session_lifetime_days`.
- `.env.example` updated; `src/budget_planner/config.py` validates presence of non-defaulted secrets at startup.
- File: `phase-1-prerequisites/T-D03-config-surface.md`.

### ✅ T-D04 [P] Litestream-friendly DB config
- `database_path` → `/data/budget.db` in production (env-overridable, default stays dev-local).
- Startup assertion: `PRAGMA wal_autocheckpoint;` returns `0` when `BUDGET_PLANNER_ENV=production`.
- File: `phase-1-prerequisites/T-D04-db-config.md`. Reference: ADR-0034.

### ✅ T-D05 [S] SQLite PRAGMAs for Litestream (blocks T-D23)
- Centralise in `src/budget_planner/db/connection.py` the four PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`, `wal_autocheckpoint=0`, `busy_timeout=5000`.
- Document in module docstring that bypassing this helper is a bug.
- New unit test asserts each PRAGMA on a fresh connection.
- File: `phase-1-prerequisites/T-D05-sqlite-pragmas.md`. Reference: ADR-0034 §2.

### ✅ T-D06 [P] Structured JSON logging + request ID
- `structlog`-based config in `src/budget_planner/logging.py`.
- Request-ID middleware generates/reads `X-Request-ID`; all log lines include it.
- `uvicorn` access log replaced with JSON formatter.
- File: `phase-1-prerequisites/T-D06-structured-logging.md`.

### ✅ T-D07 [P] Security headers middleware → T-D02
- Middleware adds HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
- Reads `X-CSP-Nonce` from Caddy (ADR-0036 §3); inserts into Jinja context as `csp_nonce`.
- Integration test asserts each header on the Overview response.
- File: `phase-1-prerequisites/T-D07-security-headers.md`. Reference: ADR-0036.

### ✅ T-D08 [P] CSRF protection → T-D02
- `__Host-csrf` cookie + `X-CSRF-Token` header. HTMX extension (`htmx-csrf.js`) attached to the base template.
- Rejects POST/PUT/PATCH/DELETE without a matching token with 403.
- File: `phase-1-prerequisites/T-D08-csrf.md`. Reference: ADR-0033 §4.

### ✅ T-D08a [P] Fix: CSRF cookie rejected by browsers in dev → T-D08
- `__Host-` cookies without `Secure` are discarded by browsers, so `env=dev` had every POST/DELETE rejected with 403 `missing_cookie`.
- Dev uses cookie `csrf` (no `Secure`); other envs keep `__Host-csrf`. HTMX extension reads the token from `<meta name="csrf-token">`.
- E2E fixture stops hand-injecting the `Cookie` header; regression test for dev cookie shape.
- Reference: ADR-0065 (amends ADR-0033 §4).

### ✅ T-D09 [P] Rate limit on auth routes → T-D02
- Fixed-window counters in `auth_rate_limit` (migration 0014) via `repositories/rate_limit.py` + `services/rate_limit.py`; no `slowapi` (ADR-0072 supersedes the ADR-0033 §2 library choice).
- `POST /auth/login` (IP+email 5/min + 20/h; IP 100/h), `POST /auth/login/finish` (IP 10/min + 60/h), `POST /auth/register/finish` (user 5/min + 20/h); all configurable (`BUDGET_RATE_LIMIT_*`).
- Returns 429 with `Retry-After`; HTML login re-renders with a generic message; HTMX/JSON get `{"error": "rate_limited"}`. Throttled attempts write an `auth_event` audit row.
- Integration test fires the limit and asserts the 429 (`tests/integration/web/test_auth_rate_limit.py`).
- File: `phase-1-prerequisites/T-D09-auth-rate-limit.md`. Reference: ADR-0072.

### ✅ T-D10 [P] Dockerfile (multi-stage, non-root)
- Base `python:3.12-slim-bookworm`; `uv sync --frozen` in build stage; `COPY --from=builder` to final.
- `USER app` (uid 10001) in final.
- `HEALTHCHECK` hitting `/health`.
- `.dockerignore` excludes tests, docs, `local/`, `.claude/`.
- File: `phase-1-prerequisites/T-D10-dockerfile.md`. Reference: ADR-0032 §2.

### ✅ T-D11 [P] docker-compose.yml for prod-sim → T-D10
- Three services: `app`, `litestream`, `caddy`. MinIO-based `minio` sidecar used only in local prod-sim to simulate the Scaleway bucket.
- `just test-prod-stack` recipe boots the stack, waits for `/ready`, runs a smoke Playwright journey, tears down.
- File: `phase-1-prerequisites/T-D11-docker-compose.md`. Reference: ADR-0032 §2, ADR-0034.

### ✅ T-D12 [P] Reproducible dependency lock
- `uv.lock` committed. `just install` uses `--frozen`.
- CI verifies lock file is up to date.
- File: `phase-1-prerequisites/T-D12-reproducible-lock.md`.

### ✅ T-D13 [P] CI security scans → T-D10
- `pip-audit` on `uv.lock`, `trivy fs` on built image, `bandit` already present, `detect-secrets` already present.
- CI fails on HIGH/CRITICAL unless `.security-allowlist.yml` entry justifies.
- File: `phase-1-prerequisites/T-D13-ci-security-scans.md`.
- Delivered: `.github/workflows/security.yml` (pip-audit + trivy fs + trivy image), `.security-allowlist.yml` shape, `pip-audit` added to dev deps, `just security-scan` local recipe. Actions pinned by 40-hex SHA; least-privilege `permissions:` per job; SARIF upload gated on `secrets.CODEQL_TOKEN` presence.

### ✅ T-D14 [P] Audit log carries client IP + session user → T-D02
- `write_audit` now accepts `request_ctx: RequestCtx { ip, user_id, session_id, user_agent }`.
- `audit_log` migration `0013_audit_request_ctx.sql` adds the four columns, NULLable for pre-existing rows (companion down under `migrations/down/`).
- `RequestCtx` dataclass lives at `src/budget_planner/domain/request_ctx.py`; `RequestCtx.empty()` is the default so existing call sites keep working unchanged.
- FastAPI dependency `get_request_ctx` in `src/budget_planner/web/deps.py` extracts IP (from `request.client`), user-agent (from headers), and session user + session id (from `request.state`, populated post-T-D02).
- Scope: plumbing is additive — only `write_audit` (repo + service wrappers) threads the kwarg today. Service-layer retrofits land as follow-ups when individual services need to pass real context (gradual).
- Integration coverage: `tests/integration/web/test_audit_request_ctx.py` (POST → DB round-trip + direct-writer field persistence + default-empty NULL guarantee); migration-shape coverage: `tests/integration/db/test_migrations.py::test_0013_applies`.
- File: `phase-1-prerequisites/T-D14-audit-request-ctx.md`. Reference: ADR-0019.

### ✅ T-D15 [P] Graceful shutdown handling → T-D11
- SIGTERM handler flushes any in-flight DB connection, closes the FastAPI lifespan cleanly, and exits with code 0 so Litestream has its 30 s to flush WAL (ADR-0034 §6).
- Integration test sends SIGTERM to a subprocess and asserts clean exit.
- File: `phase-1-prerequisites/T-D15-graceful-shutdown.md`.

### ✅ T-D16a [S] Multi-user migration `0012_multi_user.sql` (blocks T-D02, T-D16, T-D19)
- Extends `users` with `email TEXT`, `is_admin INTEGER NOT NULL DEFAULT 0`, `password_hash TEXT`, `must_change_password INTEGER NOT NULL DEFAULT 0`, `updated_at`, `deleted_at`.
- Case-insensitive unique index `ux_users_email_live` on `lower(email)` where `deleted_at IS NULL`.
- Drops the `DEFAULT 1` sentinel on `user_id` across every user-owned table (`accounts`, `categories`, `transactions`, `planned_transactions`, `recurring_rules`, `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides`, `user_preferences`) via SQLite's `CREATE TABLE _new → INSERT SELECT → DROP → RENAME` idiom. Existing `user_id = 1` rows are preserved as the bootstrapped admin's own historical data.
- Adds `actor_user_id INTEGER` column to `audit_log` (nullable, FK to `users.id`) so admin actions on user rows carry the acting admin's id (ADR-0061 §5). This is additive on top of T-D14's request-context columns.
- Migration is reversible (down migration provided for completeness; CI runs it in a scratch DB).
- File: `phase-1-prerequisites/T-D16a-multi-user-migration.md`. Reference: ADR-0061 §2.

### ✅ T-D16 [S] Repository `user_id` scoping sweep + static-analysis test → T-D16a
- Every repository function against a user-owned table takes `user_id: int` as the first positional argument after `conn` and every SQL statement filters on `user_id = :user_id` (or joins through FK for `account_snapshots` / `recurring_rule_overrides`).
- Service layer passes `request.state.user.id` explicitly — no implicit "current user" global.
- New test `tests/architecture/test_user_id_filter.py` parses each repository module's SQL with `sqlglot` and fails if a SELECT/UPDATE/DELETE against a user-owned table lacks a `user_id` predicate (or an equivalent join predicate for the two FK-scoped tables).
- Call-site sweep across services + routers to thread `user_id` through. Pure mechanical change; no behavioural change for the single-user path.
- Write paths reject cross-user FK linking (`_shared.require_owned`: `account_id` / `dest_account_id` / `category_id` must belong to `user_id`, else `LookupError`).
- Checker scope, rules (joined tables, FK-scoped tables, credential-table opaque keys) and allowlist policy (`SQL_ALLOWLIST` in the test, `.user-id-filter-allowlist` for hard-coded ids): ADR-0068.
- File: `phase-1-prerequisites/T-D16-repository-user-id-scoping.md`. Reference: ADR-0022 (amended), ADR-0061 §5, ADR-0068.

### ✅ T-D17 [S] User admin panel `/settings/users` → T-D02, T-D16
- Admin-only routes per ADR-0061 §4: list, add (auto-generated password shown once), edit (email, name, `is_admin` toggle), reset password, remove (soft-delete + session revoke in one tx).
- `AdminRequiredMiddleware` returns 404 (not 403) to non-admins to avoid admin-surface fingerprinting.
- Service-layer invariants: last-admin cannot be deleted or demoted; email must be unique among live users (case-insensitive); creating a user seeds the two per-user system categories (`Transit`, `Reconciliation`) in the same transaction.
- Auto-generated password uses `secrets.token_urlsafe(16)` (~128 bits entropy). Rendered once via HTMX toast with a copy-to-clipboard button; server never persists plaintext.
- Templates: `templates/settings/users/list.html`, `edit.html`, `_row.html`, `_password-toast.html`.
- Audit: every mutation writes an `audit_log` row with `entity_type='users'`, `entity_id=target_user_id`, `actor_user_id=admin_user_id`.
- Guard placement (AuthRequired → AdminRequired → CSRF), one-shot password delivery (`Cache-Control: no-store`, `static/js/users-admin.js`), error contract (409 last-admin / self-remove, 422 invalid or duplicate email), no self-removal, `write_audit(actor_user_id=…)`: ADR-0073.
- File: `phase-1-prerequisites/T-D17-user-admin-panel.md`. Reference: ADR-0061 §4, ADR-0073.

### ✅ T-D18 [P] Password change `/settings/password` → T-D02
- Available to every logged-in user. Form fields: current password, new password, confirm new password.
- Service verifies current password with bcrypt; hashes new password; clears `must_change_password` flag; in the same transaction revokes all **other** sessions of the same user (current session stays live).
- The `must_change_password` flag forces redirect to `/settings/password` before any other authenticated route; integration test asserts the redirect.
- Audit row written on success and on failed-verify attempts (both annotated with IP + user-agent via T-D14).
- Template: `templates/settings/password.html`.
- Policy (≥12 chars, ≤72 bytes, differs from current), failed-verify audit shape, HTMX/JSON forced-rotation responses, rate limit deferred to T-D09: ADR-0074.
- File: `phase-1-prerequisites/T-D18-password-change.md`. Reference: ADR-0061 §4, ADR-0074.

### ✅ T-D18a [S] Rate-limit password change → T-D09, T-D18
- `POST /settings/password` gets the ADR-0072 limiter (scope `password_change`, per user, 5/min + 20/h); throttled → 429 + `Retry-After`, generic form error, audit row. "Change password" link on `/auth/sessions`. ADR-0074 §4 amended.

### ✅ T-D19 [S] Admin bootstrap on startup → T-D02, T-D16a
- Lifespan startup hook calls `services.users.bootstrap_admin(conn, env)`.
- Behaviour (idempotent): if any `is_admin = 1 AND deleted_at IS NULL` user exists, no-op. Else, read `BUDGET_PLANNER_ADMIN_EMAIL` + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` from env; create (or promote) the matching user with `is_admin = 1`, `password_hash = bcrypt(initial_password)`, `must_change_password = 1`.
- Logs a redacted structured line (`event="admin_bootstrap", admin_email=<email>, action="created"|"promoted"|"noop"`); never logs the password.
- Startup fails fast (process exits non-zero) if an admin does not exist **and** either env var is missing — this is the only way to recover from losing all admins without rebuilding the DB.
- Dev fixture bootstraps a known admin (`admin@local.test` / `admin`, no forced rotation) when `BUDGET_ENV=dev` and the env vars are unset — but never adopts a legacy row that owns data (`just dev` on `data/budget.sqlite` writes nothing). Test env without credentials does not open the DB. See ADR-0069.
- With no email match, the pre-v3 email-less row (`id = 1`) is adopted as the admin so v2 data stays the admin's own (ADR-0061 §2, ADR-0069 §2).
- Operator CLI `python -m budget_planner.cli.set_password` / `just set-password --db=<path> …` (explicit `--db` required) sets a user's password, email and admin flag; audit-logged (ADR-0069 §4).
- File: `phase-1-prerequisites/T-D19-admin-bootstrap.md`. Reference: ADR-0061 §3, ADR-0069.

### ✅ T-D19a [S] Apply pending migrations before the app starts (prod container) → T-D19, T-D10, T-D11, T-D23, T-D32
- Since T-D19 the production lifespan exits non-zero on an unmigrated DB (`SchemaNotMigratedError`); a fresh volume or an image upgrade carrying a new migration must therefore be migrated **before** uvicorn starts.
- Container `ENTRYPOINT` (`deploy/docker-entrypoint.sh`) runs `python -m budget_planner.db.startup_migrate` then `exec`s the CMD. Every start path (first boot, deploy, rollback, restart, DR, restore drill) goes through it; the deploy shim (T-D32) is unchanged.
- `startup_migrate`: idempotent (no-op when up to date); takes a `VACUUM INTO` pre-migration backup under `<db dir>/backups/` only when an already-initialised DB has pending migrations (keeps the newest 3); logs `event="startup_migrations"`; warns `schema_ahead_of_image` (and continues) when the DB carries versions the image does not know (rollback onto a newer schema); exits non-zero on any migration failure.
- Compose (prod template + prod-sim) gains a one-shot `litestream-restore` service (`litestream restore -if-db-not-exists -if-replica-exists`) that `app` and `litestream` wait on, so a fresh volume restores from the replica **before** the app could create an empty DB.
- Rollback policy: migrations must stay readable by the previous image (expand-only); a release that breaks N-1 compatibility is flagged in its CHANGELOG entry and rolls back via restore (pre-migration backup or Litestream PITR), not via `rollback`.
- Runbooks updated: `deploy.md`, `rollback.md`, `restore.md`, `disaster-recovery.md`. Reference: ADR-0071.

### ✅ T-D48 [P] Ledger Actual day net wrong with reconciliation entries (bug fix)
- Day-group net negated pre-signed `adjustment` amounts and summed raw minor units across currencies. Now `services/ledger_totals.py` (ADR-0008 signs, per-row FX to base per ADR-0006, transit excluded). Tests: `tests/unit/services/test_ledger_totals.py`, `tests/integration/web/test_ledger.py`.

### ✅ T-D51 [P] Liability "Available" shows 2 decimals
- Accounts page (`partials/accounts/_row.html`, `accounts/index.html`): the liability "Available" figure switches from `{:,.0f}` to `{:,.2f}` so sub-unit remainders are visible. Limit and Used are unchanged. Covered by `test_liability_available_shows_two_decimals`.

### ✅ T-D52 [P] Reconcile liability accounts by available credit
- For liability accounts with a credit limit, the reconcile slide-over asks for **Available** (prefilled with current available, 2 decimals) with helper text showing limit and implied used. Service converts `target = -(limit - available)` (`available_to_target_balance`), then runs the existing adjustment logic. Available outside `0..limit` is rejected with 422. Liabilities without a limit and assets unchanged. Reference: ADR-0011 amendment.

### ◻ T-D53 [S] Session hardening: absolute cap, step-up re-auth, hashed ids → T-D02, T-D09, T-D14, T-D17, T-D18 (UI placement: T-D47)
- Sessions get an absolute lifetime (`session_absolute_lifetime_days`, default 30) on top of the 14-day sliding expiry. Cookie `Max-Age` follows the clamped expiry.
- `sessions.id` stores `sha256(token)`. The raw token lives only in the cookie. The migration revokes all live sessions (one-time re-login) and adds `sessions.authenticated_at`.
- Step-up re-auth (`/auth/reauth`, passkey or password, 10-minute window) guards passkey add/revoke, revoking *other* sessions, and every admin `POST` under `/settings/users`. Rate-limit scope `reauth`. Audited.
- The session token rotates on re-auth and on password change, keeping `created_at` so the cap cannot be reset.
- Access/refresh tokens, periodic rotation, UA/IP binding and sign-in notifications are rejected or deferred (ADR-0076 §5).
- Split: **T-D53a ✅** hashed ids + absolute cap + migration (`0015_session_hardening`); **T-D53b** step-up re-auth + rotation (→ T-D53a).
- File: `phase-1-prerequisites/T-D53-session-hardening.md`. Reference: ADR-0076.

---

## Phase 2 — Infrastructure (Terraform + cloud-init) — Scaleway

Owner: `terraform/` directory. All tasks block Phase 3.


### ✅ T-D47 [S] Move Security + Password into Settings → Security tab → T-D02b, T-D18, T-D17
- Nav rail drops the "Security" and "Password" links (keeps email + Sign out; mobile gets a Sign out button). New Settings tab `/settings/security` (all users) with Password, Passkeys, Sessions sections. `GET /auth/sessions` and `GET /auth/register` → 303 to the tab; `GET /settings/password` → 303 unless `must_change_password` (standalone forced page, middleware exempt list unchanged). Template/CSS consolidated (`settings-security.css`). Reference: ADR-0075.

### ✅ T-D20 [S] Terraform bootstrap (state bucket, versions, providers)
- `terraform/README.md` documents the one-shot `scw object bucket create` for `budget-planner-tfstate-pl-waw`.
- `versions.tf`, `providers.tf`, `backend.tf` committed.
- `envs/prod/backend.hcl`, `envs/drill/backend.hcl`.
- File: `phase-2-infrastructure/T-D20-tf-bootstrap.md`. Reference: ADR-0035 §4.

### ✅ T-D21 [S] IAM + Object Storage modules → T-D20
- `modules/iam/`: application + policy + key.
- `modules/storage/`: bucket (versioning on, encryption on, no public access) + bucket policy.
- Outputs: `scw_access_key`, `scw_secret_key` (sensitive), `bucket_name`, `endpoint_url`.
- File: `phase-2-infrastructure/T-D21-iam-storage.md`. Reference: ADR-0035 §3, ADR-0032 §3.

### ✅ T-D22 [S] DNS module → T-D20
- `modules/dns/`: zone + A + AAAA records for `budget.<domain>`.
- Supports either a Scaleway-managed zone or an external zone (operator provisions out-of-band if external).
- File: `phase-2-infrastructure/T-D22-dns.md`.

### ✅ T-D23 [S] Cloud-init templates → T-D05, T-D10, T-D11, T-D21, T-D19
- `cloud-init/bootstrap.yaml.tpl` renders the full first-boot sequence per ADR-0035 §5.
- `compose/docker-compose.yml.tpl`, `compose/Caddyfile.tpl`, `compose/litestream.yml.tpl` with the exact shapes from ADR-0034, ADR-0036.
- Compose env now carries `BUDGET_PLANNER_ADMIN_EMAIL` (operator-supplied Terraform input var) + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` (generated by `random_password` per ADR-0061 §3). Both are passed through the compose service env; neither is written to disk outside the compose file.
- `terraform validate` + `yq -e .` + `caddy validate --config -` run on rendered output in CI.
- File: `phase-2-infrastructure/T-D23-cloud-init.md`. Reference: ADR-0035 §5, ADR-0061 §3.

### ✅ T-D24 [S] Compute module → T-D23
- `modules/compute/`: instance (`stardust1-s`, `pl-waw-1`, Ubuntu 24.04), flex IP, security group (22/80/443).
- `user_data` wired to the cloud-init template.
- File: `phase-2-infrastructure/T-D24-compute.md`.

### ◻ T-D25 [S] First apply on `drill` → T-D21, T-D22, T-D24
- `terraform apply -var-file=envs/drill/terraform.tfvars` with the operator-supplied `admin_email` input variable.
- Capture the one-time admin password from `terraform output -raw admin_initial_password` into a password manager.
- Verify admin login via `/auth/login` with that password; verify forced redirect to `/settings/password`; rotate password.
- Verify `/health` 200 via public DNS, Observatory grade ≥ A.
- File: `phase-2-infrastructure/T-D25-first-apply-drill.md`. Reference: ADR-0061 §3.

### ◻ T-D26 [S] Teardown drill
- `terraform destroy -var-file=envs/drill/terraform.tfvars` completes without manual cleanup.
- Bucket `budget-planner-drill-pl-waw` emptied as part of destroy (lifecycle policy).
- File: `phase-2-infrastructure/T-D26-teardown-drill.md`.

### ◻ T-D27 [S] First apply on `prod` → T-D25
- Prod apply with env approval. DNS points at the prod subdomain.
- Operator captures `terraform output -raw admin_initial_password` into their password manager.
- Admin logs in with that password → forced password rotation → optional passkey registration via `/auth/register`.
- Admin creates at least one non-admin user via `/settings/users` to validate the admin panel end-to-end against prod before the smoke journey (T-D43).
- File: `phase-2-infrastructure/T-D27-first-apply-prod.md`. Reference: ADR-0061.

### ✅ T-D28 [P] Terraform CI (plan on PR, apply on main w/ approval)
- `.github/workflows/terraform.yml` runs `fmt -check` + `validate` + `tflint` + `tfsec` + `plan` on PRs; `apply` on `main` after `prod` env approval.
- Plan output posted as PR comment.
- File: `phase-2-infrastructure/T-D28-terraform-ci.md`.

---

## Phase 3 — Deployment pipeline

Owner: `.github/workflows/`. All tasks block Phase 4.

### ✅ T-D30 [S] Build workflow (push image, cosign sign) → T-D10
- `.github/workflows/build.yml` builds the image on `main` push, tags `:sha-<short>`, `:main`, and `:vX.Y.Z` on release.
- cosign signs via GitHub OIDC keyless.
- Image pushed to `ghcr.io/<owner>/budget-planner`.
- File: `phase-3-deployment/T-D30-build-workflow.md`. Reference: ADR-0037 §2.

### ✅ T-D31 [S] Deploy workflow (SSH drill) → T-D27, T-D30
- `.github/workflows/deploy.yml` deploys to drill automatically on `build.yml` success.
- `prod` deploy requires manual env approval.
- Posts a GitHub Deployment status.
- File: `phase-3-deployment/T-D31-deploy-workflow.md`. Reference: ADR-0037 §1, §3.

### ✅ T-D32 [S] Deploy user command restriction + script → T-D23
- `/usr/local/bin/deploy-budget-planner` rendered by cloud-init, exact contents per ADR-0037 §3.
- `deploy` user has `/usr/sbin/nologin` shell + `command=...` restriction in `authorized_keys`.
- Audit: `ssh deploy@<host> "ls /"` returns the usage line and exits non-zero.
- File: `phase-3-deployment/T-D32-deploy-user-restriction.md`.

### ◻ T-D33 [S] Deliberate-break rollback test → T-D31, T-D32
- Push a feature-flagged "always 500 on /ready" image, confirm the deploy pipeline rolls back automatically.
- Append the result to `docs/plans/v3/runbooks/rollback.md`.
- File: `phase-3-deployment/T-D33-rollback-test.md`.

### ✅ T-D34 [S] Manual rollback workflow (`rollback.yml`) → T-D31
- `.github/workflows/rollback.yml` with `workflow_dispatch`: SSHes `deploy@<host> "rollback"`.
- One-click rollback without needing a terminal.
- File: `phase-3-deployment/T-D34-manual-rollback-workflow.md`.

---

## Phase 4 — Validation & operations

### ◻ T-D40 [S] First backup restore drill → T-D27
- Provision `drill` env from scratch, restore from the prod bucket read-only credential, verify integrity + audit count.
- Append dated row to `docs/plans/v3/runbooks/restore-log.md`.
- File: `phase-4-validation/T-D40-first-restore-drill.md`. Reference: ADR-0034 §5.

### ✅ T-D41 [S] Monthly automated restore drill → T-D40
- `.github/workflows/restore-drill.yml` scheduled monthly: `terraform apply drill` → restore → verify → `terraform destroy`.
- On failure, opens an issue titled `restore-drill-failure-YYYY-MM`.
- File: `phase-4-validation/T-D41-monthly-restore-drill.md`.

### ✅ T-D41a [S] `restore-from-prod` drill host helper → T-D41, T-D19a
- Adds the missing `/usr/local/bin/restore-from-prod` called by `restore-drill.yml`: `terraform/cloud-init/bin/restore-from-prod.tpl`, installed on the `drill` env only (via `user_data.tf` + `bootstrap.yaml.tpl`). Stops app + litestream, moves the local DB aside, `litestream restore`s from the prod replica with a read-only credential (`scw_access_key_restore` / `scw_secret_key_restore`), runs `integrity_check`, chowns to uid 10001, restarts the stack (entrypoint migrates, ADR-0071) and waits for `/ready`.
- Replication of the restored DB goes to the drill bucket only; the prod replica is only used in a restore-only config. References: ADR-0034 §5, ADR-0071.

### ◻ T-D42 [S] Security scan + external audit → T-D27
- `trivy image` on the deployed SHA, `testssl.sh` + `nikto` against the prod hostname, Mozilla Observatory check.
- Targets: Observatory ≥ A+, testssl grade A, no HIGH/CRITICAL from trivy.
- File: `phase-4-validation/T-D42-security-scan.md`.

### ◐ T-D43 [S] Smoke journey (Playwright, production) → T-D27, T-D02, T-D17
- **Status: written, validated locally; prod run pending (human, after T-D27).**
- Journey (ADR-0061 end-to-end): admin logs in with the Terraform-captured password → rotates it via `/settings/password` → creates a second non-admin user via `/settings/users` and captures the one-shot auto-generated password → logs out → second user logs in → rotates password → registers a passkey → adds a transaction → sees it on `/ledger` → admin logs back in and asserts the second user's transaction is **not** visible from the admin's own `/ledger` (data isolation assertion) → verify `audit_log` row via the auth-gated `/debug/audit-tail` route.
- Lives in `tests/smoke/test_prod_smoke.py` and is run manually post-deploy, not in CI.
- File: `phase-4-validation/T-D43-smoke-journey.md`.

### ◻ T-D44 [S] Uptime monitoring → T-D27
- UptimeRobot (or Betterstack free) checks `https://<prod-host>/health` every 5 min; alert to operator email.
- Monitor id recorded in `docs/plans/v3/runbooks/disaster-recovery.md`.
- File: `phase-4-validation/T-D44-uptime-monitor.md`.

### ◻ T-D45 [S] Cost alert
- Scaleway cost alert set at 2× expected (PLN) and verified by temporarily cutting threshold to 0.01 PLN and confirming the email arrives.
- File: `phase-4-validation/T-D45-cost-alert.md`.

### ✅ T-D49 [S] Budget override form opens inline under its row (UI fix)
- Plan → Budget: "Override" renders the form in a per-row slot (`#override-slot-<category_id>`, a full-width `<tr><td colspan>` right after the row), right-aligned; one open at a time; Cancel/Esc close it and return focus to the button; save closes it and refreshes the budget table. Static `js/budget-override.js` replaces the inline script.

### ✅ T-D46 [S] Operational runbooks → T-D33, T-D40, T-D17
- `docs/plans/v3/runbooks/deploy.md`
- `docs/plans/v3/runbooks/rollback.md`
- `docs/plans/v3/runbooks/restore.md`
- `docs/plans/v3/runbooks/disaster-recovery.md` (full re-provision + restore; includes "lost all admins → set BUDGET_PLANNER_ADMIN_EMAIL + rotate BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD via Terraform → redeploy" recovery path)
- `docs/plans/v3/runbooks/restore-log.md` (append-only drill log, seeded by T-D40)
- `docs/plans/v3/runbooks/user-admin.md` (add user / reset password / remove user / promote-admin / last-admin invariant / data-isolation note — ADR-0061)
- Each runbook has: context, step-by-step, verification, troubleshooting.
- File: `phase-4-validation/T-D46-runbooks.md`.

---

## Deferred to v3.1 or later

Explicitly out of v3 scope. Add an ADR before promoting any of these to the active plan.

- Cross-region replication of the Litestream bucket (`pl-waw` → `fr-par`).
- Centralised log store (Grafana Cloud, Loki, Datadog).
- Deeper observability (RED/USE metrics, tracing).
- CSV import from banks (deferred from v1 as well).
- Self-signup / public registration (multi-user is in scope at v3 via ADR-0061, but user creation is admin-only — no public sign-up form).
- External IdP (GitHub / Google OIDC) for login.
- Admin impersonation ("login as another user") or admin visibility into user data.
- Forgot-password email flow — admin password reset is the only recovery path in v3.
- Hard-delete flows that remove a user's underlying data rows (soft-delete only in v3).
- Per-user API tokens or programmatic access.
- CDN in front of the host (Cloudflare).
- Switching from Caddy ACME HTTP-01 to DNS-01 (`caddy-dns/scaleway`).
- Replacing SSH deploy with pull-based self-update.
