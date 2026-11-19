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
### ✅ T-D50 [S] Retire legacy home page → T-D47
- `/` (GET/HEAD) → 303 `/today`; post-login, post-rotation and `safe_next` fallback = `DEFAULT_LANDING` (`/today`). Legacy home router, `templates/home/**`, `/overview/upcoming` and the home nav/palette entries removed; shared Today data helpers moved to `web/today_data.py`. Reference: ADR-0077.

### ✅ T-D51 [P] Liability "Available" shows 2 decimals
- Accounts page (`partials/accounts/_row.html`, `accounts/index.html`): the liability "Available" figure switches from `{:,.0f}` to `{:,.2f}` so sub-unit remainders are visible. Limit and Used are unchanged. Covered by `test_liability_available_shows_two_decimals`.

### ✅ T-D52 [P] Reconcile liability accounts by available credit
- For liability accounts with a credit limit, the reconcile slide-over asks for **Available** (prefilled with current available, 2 decimals) with helper text showing limit and implied used. Service converts `target = -(limit - available)` (`available_to_target_balance`), then runs the existing adjustment logic. Available outside `0..limit` is rejected with 422. Liabilities without a limit and assets unchanged. Reference: ADR-0011 amendment.

### ✅ T-D53 [S] Session hardening: absolute cap, step-up re-auth, hashed ids → T-D02, T-D09, T-D14, T-D17, T-D18 (UI placement: T-D47)
- Sessions get an absolute lifetime (`session_absolute_lifetime_days`, default 30) on top of the 14-day sliding expiry. Cookie `Max-Age` follows the clamped expiry.
- `sessions.id` stores `sha256(token)`. The raw token lives only in the cookie. The migration revokes all live sessions (one-time re-login) and adds `sessions.authenticated_at`.
- Step-up re-auth (`/auth/reauth`, passkey or password, 10-minute window) guards passkey add/revoke, revoking *other* sessions, and every admin `POST` under `/settings/users`. Rate-limit scope `reauth`. Audited.
- The session token rotates on re-auth and on password change, keeping `created_at` so the cap cannot be reset.
- Access/refresh tokens, periodic rotation, UA/IP binding and sign-in notifications are rejected or deferred (ADR-0076 §5).
- Split: **T-D53a ✅** hashed ids + absolute cap + migration (`0015_session_hardening`); **T-D53b ✅** step-up re-auth + rotation (→ T-D53a).
- File: `phase-1-prerequisites/T-D53-session-hardening.md`. Reference: ADR-0076.

### ✅ T-VIS3 [P] /today mobile overflow + visual baseline refresh → T-VIS2
- `/today` at 375px: the Upcoming panel header (`.rd-panel__head`, flex without wrap) pushed the filter buttons ("Promote all due", "+ Planned", "+ Recurring") past the viewport, and the mobile row grid (`1fr` + `auto` actions column) squeezed the description to a few pixels. Header now wraps; rows use `minmax(0, 1fr)` with actions on their own row. `/budget` yearly table (1440) sits inside `.ledger-scroll`, so it scrolls in its own container and does not widen the page (no change). `mobile___today.png` baseline refreshed (375px wide). `rising-dough.css` cache-bust `rd3` → `rd4`.

### ✅ T-FIX1 [S] Budget "left" counts only budgeted-category commitments → T-VIS3
- Bug: promoting the income-anchor planned payment one day early moved `next_income_date` a month out, so `committed_in_window` subtracted a month of unbudgeted bills (rent, subs) and left showed -9,824.01 with 0 spent. `committed_minor` now counts only planned + recurring expenses in categories with a resolved budget; new `unbudgeted_committed_minor` renders as an informational sub-line on /budget and Plan · Budget and never affects left. Forecast current row Expenses = committed + unbudgeted. Reference: ADR-0085 (amends ADR-0039).

### ✅ T-FIX2 [P] Formula source rules honour per-occurrence overrides in chains → T-VIS3
- `_sum_category_in_month` ignored `amount_override` / `skipped` / `date_override` of *formula* source rules (fixed sources were fine), so a chained formula (e.g. `na osobiste` over PODATKI) did not see overrides on its formula sources. Formula sources now contribute effective per-occurrence amounts (override, else computed; skip = 0). Reference: ADR-0086 (clarifies ADR-0046/0047); requirements F3.6/F3.11.

### ✅ T-VIS4 [P] /plan budget period bar clipped at 375px → T-VIS3
- `.rd-period-bar` (Plan · Budget only) used `auto 1fr auto` columns, so the right column (per-day figure, committed meta, T-FIX1 "not counted" line) sized to its max-content and overflowed at 375px (5 overflowing elements). Columns are now `auto minmax(0,1fr) minmax(0,auto)` with `min-width: 0` and wrapping text; at <=640px the bar stacks into one column. `rising-dough.css` cache-bust `rd4` → `rd5`.

### ✅ T-FIX3 [P] Forecast must not re-project promoted recurring occurrences
- Early promotion (salary 11-07 promoted 11-06) left the 11-07 occurrence in the forecast window, so current-row Income showed 29,517 instead of ~700 and EOM double-counted. Forecast flows + daily events now expand from `max(next_due, today+1)` by canonical date. Reference: ADR-0087 (amends ADR-0043); requirements F5.5.

### ✅ T-ACC1 [M] Accounts tab: planned net per account + projected end-of-period balance
- Sub-line under Balance on `/accounts`: signed net of unpromoted planned + recurring payments (incl. overdue, all categories, transfer legs) in `[period_start, next income)` and the projected balance `balance + net`; hidden at 0; hero "Planned" total over base-currency accounts. Reference: ADR-0089; requirements F2.6.

### ✅ T-VIS5 [S] Refresh drifting visual-regression baselines (frozen test clock)
- Root cause: `data/demo.sqlite` ends 2026-10-31 but pages key off the wall clock (fiscal period, days left, overdue tint, "next 7 days"), so today/accounts/budget drifted daily; plus intentional UI changes (T-FIX1, T-VIS4, T-ACC1). The app has no clock hook, so the visual server now starts via `tests/visual/frozen_server.py`, which pins `datetime.date.today()`/`datetime.now()` to 2026-10-31 for that test process only (opt-in env `BUDGET_VISUAL_FROZEN_DATE`; nothing in `src/` references it, so prod is unaffected; no ADR needed). Playwright browser clock pinned to the same instant. Baselines refreshed; `/plan` snapshots added (15 total).

### ✅ T-ACC1b [S] Accounts planned net must not crash on archived categories
- `compute_accounts_planned` looked up category direction among live categories only, so archiving a category that still had unpromoted planned rows or active recurring rules raised `KeyError` (500 on `/accounts` and account create/update/reconcile). Direction lookup now includes archived categories, matching forecast/budget. Test also pins canonical-date window membership for recurring `date_override`. Reference: ADR-0089, ADR-0087.

### ✅ T-FIX4 [P] Budget `committed` dedups planned rows linked to recurring occurrences → T-FIX1
- `services/budget.py` `_committed_by_category` sums unpromoted planned rows and `rt_expand` occurrences independently; forecast (`_collect_events`, `_month_flow_sums`) and `services/account_planned.py` dedup by `(recurring_rule_id, occurrence_date)`. If a persisted planned row linked to a not-yet-promoted recurring occurrence exists, budget "left" double-counts it while Forecast/Accounts count it once. Latent (no current `src/` path found that creates such rows). Fix: apply the same dedup (ideally a shared helper) or document + assert such rows are never created. Add regression test. Found in code review 2026-11-06. Reference: ADR-0085, ADR-0087, ADR-0089. Outcome: latent, no current `src/` path creates linked rows; Budget, Forecast and Accounts now share `recurring.linked_occurrence_keys` (window-independent, so a re-dated linked row still suppresses its occurrence); ADR-0087 amendment.

### ✅ T-FIX5 [S] Budget `committed` mixes account currencies → T-FIX1
- `services/budget.py` `_committed_by_category` adds planned/recurring amounts as raw minor units regardless of account currency; a planned expense on a EUR account counts as PLN in `remaining_minor`, `left_daily_spend`, `unbudgeted_committed_minor`, and (via T-FIX1) Forecast current-row Expenses. Pre-existing, widened by T-FIX1. Decision needed (ADR first): convert to `base_currency` via the FX service (ADR-0006, historical/cached rates) vs. document single-currency limitation in ADR-0085. Found in code review 2026-11-06. Reference: ADR-0006, ADR-0008, ADR-0085.
- **Outcome**: converted to base currency ([ADR-0095](../../adr/0095-budget-committed-converts-to-base-currency.md)): latest cached rate on/before today via `fx.convert_cached`, missing rate degrades to native amount (as Today account rows). Same helper fixes the Forecast overlay `_committed_future_for_category`. `account_planned` untouched.

### ✅ T-FIX6 [S] Budget per-category `spent` ignores account currency → T-FIX5
- `services/budget.py` per-category posted `spent_minor` was a raw sum of minor units across accounts of any currency, mixing with the base-currency `committed` from T-FIX5 in `remaining`/left/`left_daily_spend`.
- **Outcome**: each posted expense converts to `base_currency` at the latest cached rate on/before its own `operation_date` (ADR-0006 historical rates; [ADR-0095](../../adr/0095-budget-committed-converts-to-base-currency.md) amendment); missing rate falls back to native amount + warning; base-currency transactions untouched. No template/CSS changes.

### ✅ T-VIS6 [P] /accounts table clipped on mobile (375) → T-ACC1, T-VIS5
- At 375 the Accounts table is horizontally clipped (Checked column cut, Balance not visible without sideways scroll inside `.rd-table-scroll`). Determine whether it predates T-ACC1 (compare v3 before merge 142cde3); decide mobile layout (e.g. hide Trend/Checked/Txns columns or stacked rows) so Balance + planned sub-line are visible without horizontal scroll. Run `frontend-visual-audit` at 1440/1024/375 and refresh `/accounts` visual baselines. Reference: ADR-0051 §6, ADR-0089. Outcome: predated T-ACC1 (the `.rd-table-scroll .rd-table { min-width: 36rem }` rule); Trend/Checked/Txns hidden at <=640px, planned sub-line and pill wrap, Reconcile stacks over kebab; table fits at 343px with no sideways scroll; desktop/tablet unchanged.

### ✅ T-JPY [S] Native-currency amounts honour the currency exponent (JPY/KRW = 0 decimals)
- Finding: the domain already has a per-currency exponent (`domain/money.py` `currency_decimals`; JPY/KRW = 0) and input parsing (`to_minor_units`) stores JPY "1000" as 1000 minor units (ADR-0006, ADR-0008). Several native-currency templates formatted `minor / 100.0` with 2 decimals regardless, so a 1000 JPY balance rendered as "10.00 JPY". Base-currency (PLN) aggregates keep the 2-decimal format (base is 2-decimal; non-2-decimal base currencies remain out of scope).
- Fix: new `money_num` Jinja filter (`format_money` sibling, number only, optional sign/force decimals) used for account balances, planned-net sub-line, credit limit/available, reconcile modal, recently-deleted rows, `amount` macro. Tests: unit + rendered JPY account. No ADR needed (applies ADR-0006/0008 as written). Reference: ADR-0006, ADR-0008.

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
- `modules/compute/`: instance (`stardust1-s`, `pl-waw-2`, Ubuntu 24.04 `ubuntu_noble`), flex IP, security group (80/443; port 22 closed, SSH over Tailscale per ADR-0094). Zone + image per ADR-0084 (T-D62).
- `user_data` wired to the cloud-init template.
- File: `phase-2-infrastructure/T-D24-compute.md`.

### ✅ T-D62 [P] Compute zone `pl-waw-2` + `ubuntu_noble` image default → T-D24
- Stardust1-S is sold out in `pl-waw-1` (operator decision D1). The `scaleway_zone` default, both `envs/*/terraform.tfvars.example` files and `SCW_DEFAULT_ZONE` in `restore-drill.yml` move to `pl-waw-2`.
- Compute module `image` default `ubuntu_jammy` (22.04) → `ubuntu_noble` (24.04), matching ADR-0032/0035. Plain Ubuntu only, no InstantApps (they conflict with cloud-init's Docker packages).
- Re-check Stardust stock before T-D25 / T-D27. Override `scaleway_zone` in tfvars if needed.
- Reference: ADR-0084.

### ✅ T-D63 [S] DNS zone owned outside env state → T-D22
- `modules/dns` no longer creates `scaleway_domain_zone`. The zone (created by Scaleway Domains at registration) is referenced by name in `scaleway_domain_record.dns_zone`. Each env state owns only its own A/AAAA records (`budget`, `drill.budget`), so `terraform destroy` on drill (T-D26, T-D41) cannot touch the zone or prod records.
- `managed_dns_zone = true` now means "zone exists at Scaleway DNS, manage this env's records". `false` (external zone, no records) still works.
- Reference: ADR-0088 (amends ADR-0035).

### ✅ T-D64 [P] Terraform >= 1.10 + CI pin 1.17.1 → T-D20
- Floor is `>= 1.10.0` (native S3 lockfile for `use_lockfile = true`). CI pins and `.terraform-version` are `1.17.1`, matching the operator. Reference: ADR-0090.

### ✅ T-D65 [P] DNS AAAA record count known at plan time → T-D63
- `scaleway_domain_record.aaaa` count was `managed_zone && instance_ipv6 != null`, which fails first plan ("Invalid count argument", address unknown until apply). Compute always creates the IPv6 IP, so count is now `managed_zone ? 1 : 0` and `instance_ipv6` is required. Reference: ADR-0088.

### ✅ T-D68 [S] Bucket policy explicit allow-list + per-env isolation + drill force_destroy → T-D21
- The `2023-04-17` policy had only a `Deny`, which locks out every non-owner (Litestream got 403). Replaced by an Allow-only policy (`modules/bucket_policy`): the env's own IAM application (Litestream actions), optional `bucket_admin_principals` (operator, `s3:*`), optional `bucket_readonly_principals` (prod: the restore key's application).
- Per-env isolation: drill and prod share a project; the allow-list stops a drill key touching the prod bucket.
- `force_destroy` is a module variable: `true` on drill, `false` on prod.
- Operator must fill `bucket_admin_principals` (both envs) and prod `bucket_readonly_principals` (see operator checklist).
- Reference: ADR-0091 (amends ADR-0035 §3, ADR-0032 §3).

### ✅ T-D69 [S] Drill in its own Scaleway project → T-D68
- Drill resources go to project `rising-dough-drill`; prod stays in `rising-dough`. `scaleway_project_id` is per-env tfvar and feeds provider + IAM scope.
- DNS records of both envs are created in the zone's (prod) project via new `dns_zone_project_id` -> `scaleway_domain_record.project_id`.
- Prod state creates a stable read-only `restore-reader` IAM application + key (`ObjectStorageReadOnly`, prod project) and adds it to the prod bucket policy; its key feeds the `drill` environment secrets `PROD_REPLICA_RO_*`.
- Reference: ADR-0092 (supersedes ADR-0091 shared-project assumption).

### ✅ T-D67 [S] SSH only over Tailscale → T-D24, T-D31
- Security group drops inbound 22 (80/443 tcp + 443 udp stay). The VM joins the tailnet in cloud-init with a single-use, tag-bound `tailscale_tailnet_key` (ephemeral on drill) minted by the `tailscale` Terraform provider (OAuth client). No Tailscale SSH; sshd and users unchanged.
- Tailnet ACL is NOT in env state; intended policy in `runbooks/tailscale-acl.hujson`, procedure + break-glass in `runbooks/tailscale-ssh.md`.
- `deploy.yml`, `rollback.yml`, `restore-drill.yml` join the tailnet (`tailscale/github-action`, `tag:ci`) before SSH; SSH targets are `budget-planner-drill` / `budget-planner-prod`; restore drill waits for the drill host on the tailnet. `terraform.yml` plan receives `TF_VAR_tailscale_oauth_*`.
- Operator: checklist A9. Reference: ADR-0094.

### ✅ T-D72 [S] Terraform state bootstrap stack replaces script → T-D20
- `terraform/bootstrap/` (local state, committed after the operator's first apply): versioned private `scaleway_object_bucket` with `prevent_destroy`, 90-day noncurrent expiry, no bucket policy. `terraform/scripts/bootstrap-state.sh` deleted; docs and operator checklist A7 updated.
- CI: `terraform.yml` runs fmt/tflint recursively and init `-backend=false` + validate on the bootstrap dir. Test: `tests/unit/deploy/test_state_bootstrap.py`. Reference: ADR-0096 (amends ADR-0035 §4).

### ✅ T-D71 [S] ufw SSH only on tailscale0 → T-D67
- `bootstrap.yaml.tpl`: `ufw allow 22/tcp` replaced by `ufw allow in on tailscale0 to any port 22 proto tcp`; 80/443 unchanged; rules precede `ufw --force enable`. Matches the SG that closes 22 publicly.
- Test: `tests/unit/deploy/test_tailscale_ssh.py`. Reference: ADR-0094 (amended).

### ✅ T-D70 [S] CI Terraform inputs via TF_VAR_* secrets → T-D28
- `terraform.yml` and `restore-drill.yml` no longer pass `-var-file` (the tfvars are gitignored and absent in CI). Every root variable is `TF_VAR_<name>` from GitHub secrets, environment-scoped (`drill`, `prod`, ungated `prod-plan` for the PR plan's prod leg) with identical secret names. No tfvars committed.
- `terraform/scripts/check_tf_vars.py` fails fast listing empty required inputs; all terraform commands use `-input=false`. Test: `tests/architecture/test_ci_terraform_inputs.py`.
- Reference: ADR-0093 (amends ADR-0092 §4, ADR-0078 §3).

### ✅ T-D73 [S] Tailscale OAuth client owns tag:automation → T-D67
- The OAuth client carries only `tag:automation` (scope Auth Keys: write). `tagOwners` makes `tag:automation` own `tag:prod`, `tag:drill` and `tag:ci`. Before this, single-tag auth keys failed with `requested tags [tag:drill] are invalid or not permitted (400)`.
- Docs only: `runbooks/tailscale-acl.hujson`, checklist A9, `runbooks/tailscale-ssh.md`, and the Tailscale comments in `terraform/providers.tf` and `terraform/variables.tf`. The Terraform code and the workflows are unchanged.
- Reference: ADR-0094 (amendment 2026-11-06).

### ✅ T-D25 [S] First apply on `drill` → T-D21, T-D22, T-D24, T-D63, T-D69
- `terraform apply -var-file=envs/drill/terraform.tfvars` with the operator-supplied `admin_email` input variable.
- Capture the one-time admin password from `terraform output -raw admin_initial_password` into a password manager.
- Verify admin login via `/auth/login` with that password; verify forced redirect to `/settings/password`; rotate password.
- Verify `/health` 200 via public DNS, Observatory grade ≥ A.
- File: `phase-2-infrastructure/T-D25-first-apply-drill.md`. Reference: ADR-0061 §3.
- Done 2026-11-07 (laptop bring-up, verified end to end); drills now run through `drill.yml` (ADR-0101).

### ✅ T-D26 [S] Teardown drill
- `terraform destroy -var-file=envs/drill/terraform.tfvars` completes without manual cleanup.
- Bucket `budget-planner-drill-pl-waw` emptied as part of destroy (lifecycle policy).
- File: `phase-2-infrastructure/T-D26-teardown-drill.md`.
- Done 2026-11-07 (16 resources destroyed, state empty); since then every gate drill tears down through `drill.yml`.

### ✅ T-D27 [S] First apply on `prod` → T-D25
- Prod apply with env approval. DNS points at the prod subdomain.
- Operator captures `terraform output -raw admin_initial_password` into their password manager.
- Admin logs in with that password → forced password rotation → optional passkey registration via `/auth/register`.
- Admin creates at least one non-admin user via `/settings/users` to validate the admin panel end-to-end against prod before the smoke journey (T-D43).
- File: `phase-2-infrastructure/T-D27-first-apply-prod.md`. Reference: ADR-0061.
- Done 2026-11-07 (laptop exception, ADR-0099 (a)); prod live at `budget.rising-dough.eu`.

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

### ✅ T-D33 [S] Deliberate-break rollback test → T-D31, T-D32
- Push a feature-flagged "always 500 on /ready" image, confirm the deploy pipeline rolls back automatically.
- Append the result to `docs/plans/v3/runbooks/rollback.md`.
- 2026-11-16 partial run: see T-D129e (bad image detected as unhealthy, rollback applied in place; `failed` state and reconvergence not observed). Repeat on the next explore drill.
- Re-scoped 2026-11-16 (ADR-0111): there is no deploy pipeline any more. On a kept explore drill, apply an image from a throwaway branch whose `/ready` returns 503; the host agent must report `failed` (`ready_timeout`), and `rollback.yml env=drill` must converge back. The automatic rollback step in `terraform.yml` is prod-only (the apply runner is not on the tailnet), so the drill proves detection and the rollback workflow, not that step.
- File: `phase-3-deployment/T-D33-rollback-test.md`.
- 2026-11-18 (T-D139-FIX): `rollback.yml env=drill` must keep the drill hostname (reuses the run id recorded in state); verify on the drill that the hostname is unchanged after the rollback.
- DRILL-2 2026-11-18 (explore drill 44356288331, sha-bd4c4c3): PASS both ways. Rollback run 44360554182 (`target=v3.0.2`) converged to v3.0.2 and the app was healthy, but renamed the host (fixed by T-D139-FIX). Repair run 44362948854 rolled forward to sha-bd4c4c3 with the name restored (TLS, `/ready`, replication 200). Runs 44364434084 (rollback to v3.0.2) and 44365282708 (roll forward) kept `budget-planner-drill-44356288331`. The `failed` (`ready_timeout`) transition on a break image was not recorded in DRILL-2; it is still unobserved (see T-D129e).

### ✅ T-D34 [S] Manual rollback workflow (`rollback.yml`) → T-D31
- `.github/workflows/rollback.yml` with `workflow_dispatch`: SSHes `deploy@<host> "rollback"`.
- One-click rollback without needing a terminal.
- File: `phase-3-deployment/T-D34-manual-rollback-workflow.md`.

---

## Phase 4 — Validation & operations

### ✅ T-D40 [S] First backup restore drill → T-D27
- Provision `drill` env from scratch, restore from the prod bucket read-only credential, verify integrity + audit count.
- Append dated row to `docs/plans/v3/runbooks/restore-log.md`.
- File: `phase-4-validation/T-D40-first-restore-drill.md`. Reference: ADR-0034 §5.
- Status 2026-11-18, before the green run below (superseded): never run. Prod went live without it, although the task file names it as a gate before go-live. `restore-log.md` has no entries, so no backup has ever been restored from the prod replica. RPO/RTO and the `restore-reader` credential are unproven.
- Plan: after the first good release through the host agent (T-D129f), the operator dispatches `restore-drill.yml` from `main` and watches the run. That run is the first restore-log entry. It closes this task, the first-run gap in T-D41, and the T-D56 drill acceptance. It must also show that `restore-from-prod` (written before ADR-0111, T-D41a) still works on an agent-managed drill host: the agent must not restart or overwrite the restored stack mid-restore.
- Readiness review and restore-log entry template (2026-11-18): `phase-4-validation/T-D40-first-restore-drill.md`.
- Run 44330551119 (2026-11-18) restored fine but failed the `/ready` probe in `restore-from-prod` (probed `localhost`, which Caddy has no cert for, and expected `status:"ok"` instead of `status:"ready"` + `db:"ok"`). Fixed (T-D40-FIX): probe by host name with verified TLS, check `ready`/`ok`, log failures. Still ◻ until a green re-run.
- Run 44340976282 (2026-11-18): restore, integrity and ready all ok; failed on a RETURN-trap bug (`cfg: unbound variable` after `main` returned). Fixed (T-D40-FIX2): temp config cleaned by the EXIT trap. Still ◻ until a green re-run.
- Run 44346338885 (2026-11-18): restore, ready and integrity green; the T-D57 check found `budget.db.tmp-wal`/`-shm` left by `litestream restore`. Fixed (T-D40-FIX3): the script removes them (fails if the tmp-wal is non-empty). Still ◻ until a green re-run.
- **Done 2026-11-18**: run 44351020259 (https://github.com/mtkublin/rising-dough/actions/runs/44351020259, `docs/v3-remaining` at 9257b5b) is green: generation `2901fbd3873a6696` restored in 19s, `integrity_check=ok`, `/ready` ready/ok, no extra DB copies, about 6 min to green. First entry in `runbooks/restore-log.md`. Audit row counts were not collected (no count step yet; T-D41 adds it).

### ✅ T-D41 [S] Monthly automated restore drill → T-D40
- `.github/workflows/restore-drill.yml` scheduled monthly: `terraform apply drill` → restore → verify → `terraform destroy`.
- On failure, opens an issue titled `restore-drill-failure-YYYY-MM`.
- File: `phase-4-validation/T-D41-monthly-restore-drill.md`.
- Status 2026-11-18 (was ✅): the workflow was written but had never run before the dispatched green run 44351020259 (2026-11-18), and it was not on `main` for the 2026-11-01 cron. Still unproven as a scheduled run. The first scheduled run is 2026-12-01 03:00 UTC and would be unattended. It picks the newest release, so a good release must exist before then.
- Done when: the first scheduled or dispatched run posts its entry to the `restore-log` issue.
- 2026-11-18 (closeout): still ◐. Remaining: dispatch `restore-drill.yml` from `main` in the next drill window and confirm its entry posts to the `restore-log` issue. The scheduled run (2026-12-01) stays unattended until then.
- 2026-11-18 (T-D138 lock-conflict proof, ✅): the negative case is observed. A kept explore drill (run 44381760469, VM `budget-planner-drill-vm`, tailnet node `budget-planner-drill-44381760469`, expires 2026-11-18T20:38:49Z) was up. `drill.yml mode=gate` dispatched from `main` (run 44383745599): job `drill lock` failed with `drill lock held: drill VM budget-planner-drill-vm is up until 2026-11-18T20:38:49Z (created 2026-11-18T19:39:55.358837+00:00) (kept explore drill?); run drill-destroy.yml or wait` and `drill lock held: tailnet node budget-planner-drill-44381760469 (tag:drill) is online; a drill VM is running; run drill-destroy.yml or wait`. All other jobs were skipped (ci, build, apply, smoke, teardown, tailnet removal); only `gate status (result)` ran and posted on main's SHA. The explore drill was untouched and its tailnet node stayed online. The positive path was already proven (gate run 44366621363 and others).
- 2026-11-18 (T-D41-LOG): user decision, no commit from CI (`main` is protected). `restore-drill.yml` writes the entry to the job summary and posts it as a comment on the single `restore-log` issue on every run, failures included (`restore-log` job, `scripts/ci/restore_log_entry.py`). It also collects the restored `audit_log` count, max id and max `changed_at` over SSH, read-only. Prod counts are recorded as `n/a (prod not queried)`. Not yet proven by a run.
- 2026-11-18 (T-D41 proof, ✅): first automated restore-log post, from `main`. `restore-drill.yml` run 44387134093 (dispatched from `main` at b018739) went green on every job (drill lock, Resolve app image, terraform apply drill, Restore → verify, Post restore-log entry, terraform destroy drill, remove drill tailnet node, Verify drill environment destroyed); "Open issue on failure" was skipped. The entry was posted as a comment on the `restore-log` issue #28 (https://github.com/mtkublin/rising-dough/issues/28) and copied into `runbooks/restore-log.md`. Source generation `2901fbd3873a6696`, snapshot index 0, WAL index 0..10, restored at 2026-11-18T20:09:55Z. Restored `audit_log`: 293 rows, max_id=293, max_changed_at=2026-11-18T11:58:26.101Z (prod not queried). `integrity_check` ok, recovery point latest, result pass. Duration 5m26s (run start to green /ready). App image v3.0.3. The scheduled run (2026-12-01) is the remaining unattended check.

### ✅ T-D41a [S] `restore-from-prod` drill host helper → T-D41, T-D19a
- Adds the missing `/usr/local/bin/restore-from-prod` called by `restore-drill.yml`: `terraform/cloud-init/bin/restore-from-prod.tpl`, installed on the `drill` env only (via `user_data.tf` + `bootstrap.yaml.tpl`). Stops app + litestream, moves the local DB aside, `litestream restore`s from the prod replica with a read-only credential (`scw_access_key_restore` / `scw_secret_key_restore`), runs `integrity_check`, chowns to uid 10001, restarts the stack (entrypoint migrates, ADR-0071) and waits for `/ready`.
- Replication of the restored DB goes to the drill bucket only; the prod replica is only used in a restore-only config. References: ADR-0034 §5, ADR-0071.

### ✅ T-D66 [S] Restore drill always destroys drill env → T-D41
- `restore-drill.yml` runs `terraform destroy` `if: always()` (also after partial apply / cancel), preceded on failure by best-effort evidence capture uploaded as the `restore-drill-evidence` artifact, and followed by a verification step that fails the job loudly if destroy failed. Failure issue text updated. Operator decision 2026-11-06 (cost bound ~EUR 0.01/run). ADR-0034 §5 addendum.

### ✅ T-D42 [S] Security scan + external audit → T-D27
- `trivy image` on the deployed SHA, `testssl.sh` + `nikto` against the prod hostname, Mozilla Observatory check.
- Targets: Observatory ≥ A+, testssl grade A, no HIGH/CRITICAL from trivy.
- **Done 2026-11-18** on `v3.0.1`: Observatory **A+ (130)**, testssl **A+**, trivy 0 HIGH/CRITICAL (CI policy), F1 (CSP) closed. Details in `runbooks/security-audit-log.md`.
- Residual, not blocking: nikto still cannot finish a pass (the host refuses TLS handshakes during the scan; F2, LOW). The CAA record (F4) is in `terraform/modules/dns` (Let's Encrypt + Sectigo for the ZeroSSL fallback, prod only) and is live on prod DNS since 2026-11-18 (`0 issue "letsencrypt.org"`, `0 issue "sectigo.com"`, `0 issuewild ";"`), so F4 is closed; re-check testssl's `DNS CAA RR`.
- File: `phase-4-validation/T-D42-security-scan.md` (never created; the audit log is the record).

### ✅ T-D43 [S] Smoke journey (Playwright, drill) → T-D27, T-D02, T-D17, T-D135
- **Status: done 2026-11-18 (DRILL-2, explore drill 44356288331, run 3 green on sha-bd4c4c3).**
- Re-scoped 2026-11-18 (user decision): the journey runs on a drill, never on prod. On prod it would sign in as the real admin, create users and data, and use up auth rate-limit budget. The drill runs the same image and host config, so it proves the same thing. Target: `https://budget-planner-drill.<tailnet>.ts.net` on a kept explore drill, signed in as the drill admin. The smoke user dies with the drill. Proposed: an opt-in job in `drill.yml` (the runner is already on the tailnet and the drill environment holds the admin password), so no human step is needed. Blocked by T-D135: the passkey step needs the WebAuthn RP settings on the host. T-D135 is live on prod (2026-11-18), so the drill run is the next step (operator checklist step 5).
- Journey (ADR-0061 end-to-end): admin logs in with the Terraform-captured password → rotates it via `/settings/password` → creates a second non-admin user via `/settings/users` and captures the one-shot auto-generated password → logs out → second user logs in → rotates password → registers a passkey → adds a transaction → sees it on `/ledger` → admin logs back in and asserts the second user's transaction is **not** visible from the admin's own `/ledger` (data isolation assertion) → verify `audit_log` row via the auth-gated `/debug/audit-tail` route.
- Lives in `tests/smoke/test_prod_smoke.py` and is run manually post-deploy, not in CI.
- File: `phase-4-validation/T-D43-smoke-journey.md`.
- DRILL-2 helper and checklist (2026-11-18): `scripts/drill/passkey_check.py`, `phase-4-validation/DRILL-2-checklist.md`.
- 2026-11-18: second drill run found the leak check matched the admin's own users audit rows; scoped to non-users entries (T-D43-FIX2). The smoke user's email carries the marker, and the admin's `users` create/delete rows legitimately show it.
- 2026-11-18: first drill run (44356288331) found the audit entity_type mismatch in the test; fixed (`entity_type` is `"transaction"`, singular). Steps 1–10 passed on that run.
- 2026-11-18 DRILL-2: run 3 passed (1 passed, 11.85 s). Run 1 failed on a test bug (entity_type `transactions` vs `transaction`, T-D43-FIX); run 2 on a test bug (leak check matched the admin's own users audit rows, T-D43-FIX2). Follow-up: T-D145 (audit attribution NULL).

### ✅ T-D44 [S] Uptime monitoring → T-D27
- Done 2026-11-18 (user decision): UptimeRobot (external, 5 min, `/health`, test alert received) is the only uptime alarm. `uptime.yml` and its test removed. Host-down detection covered by the external check. See `phase-4-validation/T-D44-uptime-monitor.md`.
- ~~UptimeRobot (or Betterstack free)~~ Decision 2026-11-16 (user): a scheduled GitHub Actions workflow `uptime.yml` checks `/health` and the host agent status every 5 min; a failed run emails the operator and opens one issue, the next green run closes it. Test `tests/unit/deploy/test_uptime_workflow.py`. Described in `docs/plans/v3/runbooks/disaster-recovery.md`.
- Note 2026-11-18 (cadence): the workflow is on `main` since 2026-11-17 07:52 UTC; `gh run list` shows only 3 runs, all `schedule` and green (17:06, 23:49 UTC on 11-17; 04:44 on 11-18), roughly 5 to 7 hours apart instead of every 5 minutes (~330 expected). Not a config fault: cron `*/5 * * * *` and the `on:` block are valid, the workflow is `active`, the repo is public with recent pushes (so no 60-day auto-disable), and `concurrency: cancel-in-progress` cannot explain it (no cancelled or skipped runs are listed). Cause: GitHub schedule events are best effort and are delayed or dropped under load; `*/5` is the most contended cron and new or low-activity repos get the worst treatment. Effective detection latency is hours, so the check is not fit for purpose: status changed from done to partial (◐).
  - Options: (1) external free monitor (UptimeRobot, Better Stack, Healthchecks.io) hitting `/health` every 1 to 5 min with email alerts: simplest, independent of GitHub outages (recommended; keep `uptime.yml` as a slow backup or drop it); (2) a different cron (off-peak minutes such as `7,22,37,52 * * * *`) only reduces drops, no guarantee; (3) Scaleway-side check (Cockpit/alert on a probe) adds platform cost and shares fate with the host; (4) host-side dead-man's switch pinging Healthchecks.io from `bp-converge`.
  - Recommendation: option 1 (plus 4 if host-down detection is wanted). Needs a user decision and, per the change policy, a task/ADR update before any workflow change; none made here.
- 2026-11-18 (operator): an external UptimeRobot monitor for https://budget.rising-dough.eu is set up and is the primary alarm. Superseded by the closure above: the 5 min interval and the test alert are recorded, and `uptime.yml` is removed. See `phase-4-validation/T-D44-uptime-monitor.md`.
- File: `phase-4-validation/T-D44-uptime-monitor.md`.

### ✅ T-D45 [S] Cost alert
- Scaleway cost alert set at 2× expected (PLN) and verified by temporarily cutting threshold to 0.01 PLN and confirming the email arrives.
- Done 2026-11-18 by the operator (Scaleway console).
- File: `phase-4-validation/T-D45-cost-alert.md`.

### ✅ T-D49 [S] Budget override form opens inline under its row (UI fix)
- Plan → Budget: "Override" renders the form in a per-row slot (`#override-slot-<category_id>`, a full-width `<tr><td colspan>` right after the row), right-aligned; one open at a time; Cancel/Esc close it and return focus to the button; save closes it and refreshes the budget table. Static `js/budget-override.js` replaces the inline script.

### ✅ T-D49a [S] No gaps between budget rows when override slots are closed (UI regression fix of T-D49)
- Empty per-row slot rows (`tr.rd-override-slot-row`) are `display: none` via CSS (`:not(:has(.rd-override))`) at every viewport; a row appears only while its override form is swapped in. Open-form behaviour unchanged.

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

## Phase 5 — Data-protection quick wins (added 2026-11-04; ADR-0078)

Owner: app + `terraform/`. Down-payment on the v4 data-protection plan (`docs/plans/v4/`, ADR-0079..0083). No key management, no schema redesign. Detail: `phase-5-data-protection/`.

### ✅ T-D54 [P] Audit tail is owner-scoped → T-D43
- `/debug/audit-tail` returns `prev`/`new` only for the caller's own rows; other users' rows show metadata + `"[other-user]"`. Closes the one confirmed ADR-0061 leak (admin saw every user's audit payloads). Smoke journey asserts presence, not payload.
- File: `phase-5-data-protection/T-D54-audit-tail-owner-scoped.md`. Reference: ADR-0078 §1.

### ✅ T-D55 [P] `no-store` on authenticated responses; logout clears site data → T-D02b, T-D07
- Middleware sets `Cache-Control: no-store` on every authenticated response (not `/static/`); logout adds `Clear-Site-Data: "cache", "storage"`. Back button after logout never shows cached financial pages.
- File: `phase-5-data-protection/T-D55-no-store-authenticated-responses.md`. Reference: ADR-0078 §2.

### ✅ T-D56 [S] Litestream replica encryption (age) + version alignment → T-D21, T-D23, T-D41a
- **Status: code done; prod-sim + drill acceptance pending (needs Docker / drill env).** Verified: age is absent in Litestream 0.5.x (rejected since v0.5.1), so everything pins `litestream/litestream:0.3.14` (see ADR-0078 §3 addendum).
- One exact Litestream tag for prod + prod-sim (today `0.3` vs `0.5.x`), chosen for verified age support. Replicas encrypted to an operator-held age identity (0600 on host). Cut-over: new generation → restore drill → delete plaintext generations.
- Order (2026-11-18): the restore drill in the cut-over is the T-D40 run, and no restore has been proven yet (superseded: run 44351020259 is green, see below). Delete the plaintext generations only after that run is green against the encrypted replica.
- 2026-11-18: `litestream-plaintext-cleanup.yml` (prod-gated, dry run by default, ADR-0112) and `scripts/ci/litestream_cleanup.py` written and unit-tested. Stays ◐ until the drill is green and the real cleanup has run with the operator's approval. Closed by T-D136 (✅): `age.identities` is now in the replicate config.
- 2026-11-18: the drill gate of the cleanup (a green `restore-log.md` entry on or after the first encrypted snapshot day) is satisfied by the T-D40 entry (run 44351020259). Re-run the cleanup dry run once this lands on `main`; it should pass the restore-log check.
- 2026-11-18 (closeout, supersedes the status line above): dry run of `litestream-plaintext-cleanup.yml` from `main`, run 44372136946: 83 encrypted objects, 0 plaintext to delete, 0 kept. The restore-log gate passed on `main` (T-D40 entry). No delete run is needed, since there is nothing to delete. T-D56 is ✅.
- File: `phase-5-data-protection/T-D56-litestream-age-encryption.md`. Reference: ADR-0078 §3.

### ✅ T-D57 [S] Maximum copy age 37 days → T-D56, T-D19a
- Bucket noncurrent expiry 30 → 7 d; pre-migration backups pruned by age (≤30 d) and count; drill copies deleted per run. Setting `backup_max_age_days = 37`.
- Done 2026-11-06. Single knob: Terraform variable `backup_max_age_days` (default 37), passed to the app container as `BUDGET_BACKUP_MAX_AGE_DAYS` via the compose template (app default 37 applies to dev/prod-sim only). Litestream `retention: 720h` unchanged; drill acceptance (no extra `*.db*` after a run) is asserted by the workflow and verified on the next drill.
- File: `phase-5-data-protection/T-D57-backup-copy-age-ceiling.md`. Reference: ADR-0078 §4.

### ✅ T-D58 [P] `PRAGMA secure_delete = ON` → T-D05
- Deleted content zeroed on disk. File: `phase-5-data-protection/T-D58-sqlite-secure-delete.md`. Reference: ADR-0078 §6.

### ✅ T-D59 [P] Log hygiene → T-D06, T-D23
- Structlog redaction processor (value-bearing keys); Caddy access log drops query strings; logrotate 14 d; sentinel test proves search terms never hit logs.
- File: `phase-5-data-protection/T-D59-log-redaction.md`. Reference: ADR-0078 §5.

### ✅ T-D60 [P] IP / user-agent retention purge (90 d) → T-D14, T-D19a
- Null `audit_log.ip`/`user_agent` and delete ended `sessions` older than `retention_personal_days` (default 90, 7..3650); runs at container start (entrypoint, non-fatal, `python -m budget_planner.db.retention`) + every 24 h on the app lifespan task. Audit rows are never deleted. Logs `event="retention_purge"` counts only. No migration.
- File: `phase-5-data-protection/T-D60-ip-user-agent-retention-purge.md`. Reference: ADR-0078 §7. Tests: `tests/unit/services/test_retention.py`, `tests/integration/startup/test_startup_migrate.py`.

### ✅ T-D61 [S] Data inventory + "what the operator can see in v3" → T-D54..T-D60
- `runbooks/data-inventory.md`: every location of user data/secrets with protection + retention; honest operator-visibility statement.
- File: `phase-5-data-protection/T-D61-data-inventory-runbook.md`. Reference: ADR-0078 §8.
- Done 2026-11-16: `runbooks/data-inventory.md` (15 user-data and 17 secret locations, operator-visibility statement, quarterly check). Includes ADR-0111: every host secret is also in instance metadata. Its open-items list tracks what the repo cannot verify (provider disk encryption, journald retention, encrypted Litestream generation).

---

## Deferred to v3.1 or later

Explicitly out of v3 scope. Add an ADR before promoting any of these to the active plan.

- Cross-region replication of the Litestream bucket (`pl-waw` → `fr-par`).
- Centralised log store (Grafana Cloud, Loki, Datadog).
- Deeper observability (RED/USE metrics, tracing).
- CSV import from banks (deferred from v1 as well).
- Self-signup / public registration (multi-user is in scope at v3 via ADR-0061, but user creation is admin-only — no public sign-up form).
- External IdP (GitHub / Google OIDC) for login.
- Admin impersonation ("login as another user") or admin visibility into user data. (Cryptographic isolation from the admin/operator is planned for v4 — `docs/plans/v4/`, ADR-0079.)
- Forgot-password email flow — admin password reset is the only recovery path in v3.
- Hard-delete flows that remove a user's underlying data rows (soft-delete only in v3). (Right to be forgotten planned for v4 — ADR-0083.)
- Per-user API tokens or programmatic access.
- CDN in front of the host (Cloudflare).
- Switching from Caddy ACME HTTP-01 to DNS-01 (`caddy-dns/scaleway`).
- Replacing SSH deploy with pull-based self-update.
- Periodic session token rotation (e.g. daily). Needs a grace window so concurrent HTMX requests don't race the cookie swap (ADR-0076 §5).
- Binding sessions to user agent or IP, including a soft "unrecognised device" flag (ADR-0076 §5).
- New-sign-in notifications. Needs a notification channel, and v3 has none (ADR-0076 §5).

### ✅ T-D74 [S] Pin IAM API key default project, ignore provider-set expiry → T-D69
- `scaleway_iam_api_key.app`: `default_project_id = var.scaleway_project_id` (the drill key no longer defaults to the prod project) and `lifecycle { ignore_changes = [expires_at] }` (Scaleway's 1-year default expiry no longer forces replacement on every plan). New root output `scw_app_key_expires_at`.
- Docs: ADR-0092 amendment; deploy runbook "Rotate the Litestream API key"; checklist F reminder. Test: `tests/unit/deploy/test_iam_api_key.py`.

### ✅ T-D75 [S] `#cloud-config` must be the first line of user-data → T-D23, T-D25
- `terraform/cloud-init/bootstrap.yaml.tpl`: `#cloud-config` moved to line 1. cloud-init only treats user-data as cloud-config when line 1 is exactly that header; with the NOTE lines above it, the first real drill boot (2026-11-06) ignored the whole payload (no packages, no Tailscale, no Docker, ports closed). Nothing else in the template changed.
- Other user-data inputs checked: the compose, Caddyfile, Litestream and bin templates are embedded as `write_files` content, not user-data, so no header change was needed.
- Test: `tests/unit/deploy/test_cloud_init_header.py`. Re-drill on `drill` is pending (T-D25).

### ✅ T-D76 [S] Build the app image on `v3` pushes for pre-merge drills → T-D75, T-D25
- `.github/workflows/build.yml`: push trigger is now `branches: [main, v3]` (temporary, marked with a comment to remove after v3 merges). Tag rules unchanged: `sha-<short>` on every build, `main` only when `is_default_branch`, semver on tags. No step-level `if:` gates the push, so no other change was needed.
- The drill sets `app_image_tag = "sha-<short>"` of the pushed `v3` commit (checklist D, T-D25).
- Test: `tests/unit/deploy/test_build_workflow.py`.

### ✅ T-D77 [S] Offline render + cloud-init schema check of user-data → T-D75
- Why: the first drill boot (2026-11-06) silently ignored the user-data and we cannot SSH to a failed boot, so first-boot bugs must be caught before a VM boot.
- `terraform/tests/render/` fixture root calls the real `modules/compute` with dummy values (no credentials). `terraform/tests/render.tftest.hcl` (`mock_provider "scaleway"`, `command = plan`) asserts `#cloud-config` is line 1. `render_check.py` plans the fixture, extracts the rendered user-data, and checks line 1, YAML parse and `cloud-init schema`. New sensitive module output `compute.user_data` (used only by the fixture).
- Wiring: `just tf-render-check`; new steps in `.github/workflows/terraform.yml` (`terraform test`, install cloud-init, render + schema with `--require-schema`). Docs: `terraform/README.md`. Test: `tests/unit/deploy/test_render_check.py`.

### ✅ T-D78 [S] Read-only Terraform preflight → T-D67, T-D70, T-D73
- `terraform/scripts/preflight.py` (stdlib only, frozen-dataclass results) plus `just tf-preflight <env>` and `just drill-preflight`. Checks the things that broke or nearly broke the first drill apply (2026-11-06): required inputs set, not placeholders, right prefixes; `SCW_DEFAULT_PROJECT_ID` equals `scaleway_project_id`; app image exists on GHCR; the Tailscale OAuth client can mint a key for the env tag (test key deleted in `finally`; 400 gives the `tag:automation` hint, T-D73); state bucket reachable (SigV4 `HEAD`). Never prints secret values.
- Docs: `terraform/README.md` Preflight section; operator checklist D. Test: `tests/unit/deploy/test_preflight.py`.

### ✅ T-D79 [S] Align module `required_version` with root (>= 1.10) → ADR-0090
- Five modules (`compute`, `dns`, `iam`, `restore_reader`, `storage`) still declared `required_version = ">= 1.9.0"`, so a 1.9 binary could plan them without state locking. All module and bootstrap `versions.tf` now match the root `>= 1.10.0`. Provider constraints unchanged (already compatible).
- Test: `tests/unit/deploy/test_tf_versions.py` asserts the root floor is 1.10.0 and every module's `required_version` equals the root's.
- Docs: ADR-0090 amendment (2026-11-06); CHANGELOG 2026-11-06.

### ✅ T-D80 [S] Per-batch CI policy for orchestrator mode; fast pre-commit pytest → ADR-0097
- Item agents run scoped checks plus pre-commit only; the orchestrator runs one full `just ci` per merge batch (skipped for docs-only batches). `ci.yml` stays the safety net. Single-agent work keeps `just ci` green before handoff.
- `.pre-commit-config.yaml` `pytest-fast` now runs `tests/unit tests/architecture` only (974 tests, about 31 s, was 1508 tests, about 205 s). Full suite and the 90% gate are unchanged in `just ci` and CI.
- Docs: ADR-0097, ADR-0066 "Amended by" note, CLAUDE.md handoff item 2, `orchestrator-mode` skill.

### ✅ T-D81 [S] Drill-only break-glass public SSH for boot debugging → ADR-0094
- Root variable `break_glass_ssh_cidrs` (default `[]`, CIDR-validated, rejected unless `env = "drill"`) feeds the compute module: one SG inbound TCP 22 rule per CIDR (`dynamic` block) and one `ufw allow from <cidr> to any port 22 proto tcp` in cloud-init. Empty list leaves the SG and user-data unchanged.
- cloud-init: ufw block moved first in `runcmd` (before the Tailscale install) so break-glass survives a failed or hanging Tailscale join; `tailscale up` wrapped in `timeout 120`. sshd was not bound to `tailscale0`, so no sshd change.
- Docs: ADR-0094 amendment (2026-11-07), runbook `tailscale-ssh.md` section, CHANGELOG.
- Tests: `tests/unit/deploy/test_break_glass.py`; `terraform/tests/render.tftest.hcl` (rendered rule, prod rejection).

### ✅ T-D82 [S] 1 GiB swapfile via cloud-init before package install → ADR-0032
- cloud-init `swap:` key (`cc_mounts`, init stage) creates `/swapfile` (1 GiB) before `package_update_upgrade_install` and `runcmd`, protecting the 1 GB STARDUST1-S from first-boot OOM peaks. `vm.swappiness = 10` via `/etc/sysctl.d/99-swappiness.conf` and an early idempotent `bootcmd` `sysctl -w`.
- Docs: ADR-0032 amendment (2026-11-07, sizing note), `deploy.md` "Memory check", CHANGELOG.
- Tests: `tests/unit/deploy/test_swap.py`; `terraform/tests/render.tftest.hcl`.

### ✅ T-D83 [S] Keep rendered user-data secrets out of plan output → ADR-0098
- Compute module: `cloud_init = sensitive(local.user_data)` so state records the sensitive attribute; new `cloud_init_is_sensitive` output as a test hook. Prior state values written before this fix may print once on the first apply (mask it).
- `terraform/scripts/mask_plan.py` (stdlib filter) wired into `terraform.yml` plan/show/apply steps plus `::add-mask::` step; `plan.bin` no longer uploaded as an artifact; `just tf-plan-safe <env>` for local plans.
- Finding documented: a `cloud_init` change plans as in-place but cloud-init does not re-run; user-data changes need `-replace=module.compute.scaleway_instance_server.app`. Runbooks `deploy.md` (incl. T-D74 key rotation) and `disaster-recovery.md` updated.
- Future hardening (secrets out of user-data) described in ADR-0098, not built.
- Tests: `terraform/tests/render.tftest.hcl` (`issensitive`), `tests/unit/deploy/test_mask_plan.py`.

### ✅ T-D84 [S] Drill-only serial-console password for `operator`; create `docker` group before users → ADR-0094
- Root variable `break_glass_console_password` (bool, default `false`, rejected unless `env = "drill"`); `random_password.console` (24 chars, no specials); sensitive output `console_password`. Only the `bcrypt_hash` goes into user-data (compute variable `console_password_hash`, sensitive): `operator` gets `lock_passwd: false` + `hashed_passwd`. `ssh_pwauth: false` set explicitly.
- Bug fix: top-level cloud-init `groups: [docker]` so `useradd -G sudo,docker` cannot fail before `docker.io` installs.
- Docs: ADR-0094 amendment (2026-11-07), runbook `tailscale-ssh.md` section, CHANGELOG.
- Tests: `tests/unit/deploy/test_console_password.py`; `terraform/tests/render.tftest.hcl`.

### ✅ T-D86 [S] Drill-only boot-log upload from `bootcmd` to the drill bucket → ADR-0094
- Root variable `boot_log_upload` (bool, default `false`, rejected unless `env = "drill"`), passed to compute. Template: `bootcmd` writes uploader + 0600 creds to `/run`, starts it detached; uploads logs every 30 s for 60 min then every 5 min for 2 h to `boot-logs/<instance-id>/<boot-id>/` with secret redaction. Reuses the existing bucket credential.
- Storage: `expire_boot_logs` (drill only) lifecycle rule, 7 days on `boot-logs/`.
- Docs: ADR-0094 amendment, runbook `tailscale-ssh.md` "Boot logs (drill)", CHANGELOG.
- Tests: `tests/unit/deploy/test_boot_log_upload.py`; `terraform/tests/render.tftest.hcl`.

### ✅ T-D85 [S] Redact whole cloud-init/user_data heredocs in masked plan output → ADR-0098
- Finding (2026-11-07): after T-D83 the first plan printed the prior `user_data["cloud-init"]` value unmasked; random passwords/cookie secrets/UUID keys have no matchable shape.
- `terraform/scripts/mask_plan.py`: heredoc bodies under `cloud-init`/`cloud_init`/`user_data`/`user-data` keys replaced by `(redacted by mask_plan.py: N lines)` (delimiters kept; unterminated -> redact to EOF); values of `*PASSWORD*`/`*SECRET*`/`*TOKEN*`/`*AUTHKEY*`/`*IDENTITY*`/`*_KEY` keys masked. Streaming, stdlib only.
- Docs: ADR-0098 amendment (2026-11-07), CHANGELOG.
- Tests: `tests/unit/deploy/test_mask_plan.py`.

### ✅ T-D87 [S] Fix cloud-init init-stage failures: root:docker write_files and `operator` group collision → ADR-0094
- Root cause (drill VM `/var/log/cloud-init.log`, cloud-init 26.2): (1) `config-write_files` raised `getgrnam(): name not found: 'docker'` for the `owner: root:docker` compose entry (write_files runs before users_groups and before docker.io installs); the exception aborted the module, so Caddyfile, litestream config, deploy script etc. were never written. (2) `useradd operator` exit 9: Ubuntu's system group `operator` (gid 37) exists, so `operator` was never created.
- Fix: compose entry `defer: true` (written in the final stage, before `scripts_user`/runcmd); `operator` gets `no_user_group: true`.
- Tests: `tests/unit/deploy/test_cloud_init_ordering.py` (non-root-owned write_files must defer; no user named after a stock system group without `no_user_group`/`primary_group`).

### ✅ T-D88 [S] Release and environment policy; align local docs → ADR-0099
- ADR-0099 records: prod only via GitHub Actions from `main`; main pipeline; drill triggers (`*-deploy`, dispatch with TTL, PR pre-merge gate); exceptions; credential-based enforcement. Docs aligned (requirements 6.4, CLAUDE.md, implementation plan, terraform README, deploy/rollback/operator runbooks).

### ✅ T-D89 [M] Main-only release pipeline ci→build→tf apply→deploy; fix tflint pin → ADR-0099
- New `.github/workflows/release.yml` (push main, `concurrency: release-prod`): `ci` → `build` → `tf-apply-prod` (env `prod`, `-var app_image_tag=<build tag>`) → `deploy-prod` (env `prod`, `/ready` smoke inside deploy). ci/build/terraform/deploy are reusable (`workflow_call`); build/terraform-apply/deploy lose their own push/tag/release/workflow_run triggers. Prod apply/deploy/rollback refuse any ref other than `main`.
- terraform.yml: `setup-tflint` pinned to real v4.1.1 SHA (old SHA did not exist); apply job takes `env`, `image_tag`, `replace`, `destroy` for T-D90 (drill). restore-drill shares concurrency group `drill`.
- Tests: `tests/unit/deploy/test_build_workflow.py` (trigger shape + needs chain). `.github/workflows/README.md` documents the graph.

### ✅ T-D90 [M] Drill deploy pipeline and sweeper → ADR-0099
- `drill.yml`: ci (push/dispatch only) -> build -> terraform apply drill (`-replace` server + tailnet key, `app_image_tag` = build tag, `drill_expires_at`) -> smoke (`DRILL_URL/ready`, up to 10 min). Triggers: push `*-deploy`, `workflow_dispatch` (`ttl_minutes` 15..480 default 60, `keep`, `boot_logs`), `pull_request` to `main` (ephemeral: `teardown` job `always()` after any attempted apply, `destroy=true`). Smoke-only instead of deploy.yml: a fresh boot's cloud-init already runs the built tag (ADR-0099 amendment).
- TTL: root var `drill_expires_at` (drill-only, RFC3339 UTC) -> compute tag `expires-at=<ts>` (absent for prod; terraform tests). `drill-sweeper.yml` (cron `*/15`) lists drill-project servers via the Scaleway API and destroys expired / tagless >8 h orphans through terraform.yml; `drill-destroy.yml` manual. All share concurrency group `drill` with restore-drill.
- terraform.yml: optional inputs `drill_expires_at`, `boot_log_upload` (drill only). Tests `tests/unit/deploy/test_drill_workflows.py`; runbook `runbooks/drill.md`.

### ✅ T-D91 [S] Green `security.yml` (pip-audit + Trivy fs) → T-D13, ADR-0067
- pip-audit failed with "budget-planner: Dependency not found on PyPI" (audited the live env incl. the editable project); now audits the hash-pinned `uv export --no-emit-project` of `uv.lock`. Allowlist/materialize steps run via `uv run` / `uv run --with pyyaml` so PyYAML is guaranteed.
- cryptography 48.0.1 carried PYSEC-2026-3552/3553/3554 (CVE-2026-69247/69249 in Trivy): the global `cryptography<49` cap is now macOS-x86_64-only; Linux/CI/prod resolve 50.0.2. Lock's darwin-x86_64 fork (48.0.1) is allowlisted in `trivy_fs` until 2027-02-01.

### ✅ T-D92 [M] Least-privilege per-env CI credentials, drill state bucket, key-expiry monitor, runbooks → ADR-0100
- Bootstrap: drill state bucket in the drill project (`terraform/bootstrap/drill_bucket.tf`); new local-state root `terraform/bootstrap/ci/` (uncommitted state) with CI applications `ci-prod`, `ci-drill`, `ci-plan`, expiring API keys, state-bucket policies. `envs/drill/backend.hcl` -> new bucket.
- `.github/workflows/key-expiry.yml` weekly expiry monitor; runbooks `break-glass.md`, `key-rotation.md`, `github-settings.md`.
- Operator applies both bootstrap roots after plan review (ADR-0096 exception); see `runbooks/key-rotation.md`.

### ✅ T-D93 [S] One-time copy of the local prod DB onto the prod VM → ADR-0099 exception (d)
- `scripts/prod_db_seed.sh` (+ `just prod-db-seed`): `.backup` snapshot of `data/budget.sqlite` (read-only), integrity + row counts + sha256, refuse if the remote DB already has accounts/transactions (`--force-overwrite`), scp over tailnet as `operator`, remote swap with moved-aside `/data/pre-seed-<ts>/`, auto-rollback, `/ready` wait, litestream generations. Needs `--yes-i-own-prod-data` (exit 2 otherwise); `--dry-run` is local-only.
- Runbook: `docs/plans/v3/runbooks/prod-db-seed.md`. Tests: `tests/unit/deploy/test_prod_db_seed.py` (temp DBs only; fake ssh/scp).

### ✅ T-D94 [S] Fix `/ready` probe in `prod_db_seed.sh` → ADR-0099 exception (d)
- Real run rolled back: probe hit `https://localhost/ready` but Caddy has a cert only for the FQDN (TLS alert, `-k` no help). Now `curl --resolve "$FQDN:443:127.0.0.1" https://$FQDN/ready` (new `--fqdn`, default `budget.rising-dough.eu`, passed as `$2` to the remote script); second accepted signal: `budget-planner-app` healthy AND in-container `/ready` ok. 180 s timeout, rollback, aside dir, sha check unchanged. Tests and runbook updated.

### ✅ T-D95 [S] Runbooks and plans aligned with ADR-0099 release flow → ADR-0099, ADR-0037
- Docs only. Stale `workflow_run`, local `terraform apply` and `deploy.yml` dispatch instructions replaced in `runbooks/{deploy,rollback,tailscale-ssh,user-admin,disaster-recovery,restore}.md`, `operator-checklist.md`, `README.md`, `implementation_plan.md`, `terraform/README.md`. Superseded notes on T-D25, T-D31, T-D40. `runbooks/README.md` indexes drill, break-glass, key-rotation, github-settings, prod-db-seed. ADR-0037 amended in part.

### ✅ T-D96 [S] Human-gate the drill apply in GitHub Actions → ADR-0099, ADR-0101
- Drill apply (every trigger) runs in environment `drill` = required reviewers. Ungated environments with the same drill secrets/vars: `drill-teardown` (sweeper scan + destroy, `drill-destroy.yml`, `drill.yml` teardown and smoke) and `drill-plan` (drill leg of the PR plan). `terraform.yml` picks the environment per job (plan / apply / destroy). Runbook `runbooks/github-settings.md` lists the environments, secrets/vars and fixes the Tailscale OAuth section (one client, tag `tag:automation`, owner of `tag:prod`/`tag:drill`/`tag:ci`). Private-repo caveat: required reviewers need GitHub Pro/Team.
- Tests: `tests/unit/deploy/test_drill_workflows.py`.

### ✅ T-D97 [M] Drill is tailnet-only: no public DNS, no public 80/443 → ADR-0101
- Terraform: `module.dns` prod-only (`moved` to `[0]`); security group opens 80/443 only when `public_web`; variable `tailnet_dns_name` (required on drill) -> drill FQDN `budget-planner-drill.<tailnet>.ts.net`; Caddy on drill gets its `*.ts.net` certificate from tailscaled (socket dir mounted, no ACME, 443 only, ufw 443 on `tailscale0`). Prod rendering unchanged.
- `terraform/bootstrap/ci`: `ci-drill` loses `DomainsDNSFullAccess` on the prod project.
- `drill.yml` smoke joins the tailnet (`tag:ci`) and probes `https://budget-planner-drill.${TAILNET_DNS_NAME}/ready`; `vars.DRILL_URL` dropped there. `restore-drill.yml` probe/TF var adjusted. Operator: MagicDNS + HTTPS certificates on, ACL `tag:ci -> tag:drill:443`.
- Tests: `tests/unit/deploy/test_tailnet_only_drill.py`, `terraform/tests/render.tftest.hcl`, `test_tailscale_ssh.py`, `test_drill_workflows.py`.

### ✅ T-D98 [S] Drill pipeline is manual-only; PR merge gate via `drill-gate` commit status → ADR-0099
- `drill.yml`: only `workflow_dispatch`; input `mode` = `gate` (default: TTL backstop 90 min, `keep` ignored, always torn down) | `explore` (`ttl_minutes`, `keep`, `boot_logs`). Gate mode posts `pending` then `success`/`failure` (apply + smoke only) as commit status `drill-gate` on `github.sha`; run summary records ref and sha. Branch protection on `main` requires `drill-gate`; a new push needs a re-dispatch. Required reviewer on `drill` is now optional (T-D96).
- Docs: ADR-0099 amendment, ADR-0101 note, `runbooks/drill.md`, `runbooks/github-settings.md`, CLAUDE.md drill bullet, workflows README. Tests: `tests/unit/deploy/test_drill_workflows.py`.

### ✅ T-D99 [S] Fix failing `Terraform` workflow: bump stale trivy-action pin → (no ADR; CI fix)
- `terraform.yml` "Trivy config scan" pinned `aquasecurity/trivy-action@18f2510…` (v0.29.0), which pulls `aquasecurity/setup-trivy@v0.2.2`, a tag that no longer exists; job failed at "Set up job". Bumped to `ed142fd0673e97e23eac54620cfb913e5ce36c25` (v0.36.0), the same pin `security.yml` uses. Inputs used (`scan-type`, `scan-ref`, `exit-code`, `severity`, `ignore-unfixed`) are still valid in v0.36.0's `action.yaml`.

### ✅ T-D100 [S] Record open v3 items and operator go-live checklist → ADR-0099, ADR-0100
- Docs only. New `runbooks/operator-checklist.md` (ordered, human-only steps) and task entries T-D101..T-D109 below. T-D99 (trivy-action pin bump in `terraform.yml`) is tracked separately.

### ✅ T-D101 [S] Security workflow `trivy fs (repo)` step exits 1 on the v3→main PR
- Local trivy 0.69.3 scan of the committed tree is clean; CI uses trivy v0.70.0 via trivy-action v0.36.0. Next: read the job log (needs `gh auth login`), then fix or allowlist (`.security-allowlist.yml`).
- 2026-11-13: job log has no findings because the step writes SARIF only (`format: sarif`) and the SARIF upload is skipped without `CODEQL_TOKEN`. Local 0.69.3 scan of `git archive fa8f233` with a fresh DB is still clean. Step 1: add an `if: failure()` re-run of the scan with `format: table` so findings print to the job log. Step 2: fix or allowlist what it shows.
- Root cause (2026-11-13 run): the table re-run is clean. trivy-action logs "Building SARIF report with all severities": with `format: sarif` it drops the `severity` filter unless `limit-severities-for-sarif: true`, so `exit-code: 1` fired on LOW/MEDIUM findings. Fix: set `limit-severities-for-sarif: true` on both the fs and image scans. The table step stays as a diagnostic.
- Depends on: operator checklist step 1. Blocks: merge of PR v3→main.

### T-D102 [M] (won't do for now) Consolidate PR checks into one `pr.yml` graph
- Merge ci, security, terraform plan and lock-check into a single `pr.yml` graph with one summary required check. `release.yml`, `drill.yml` and the cron/manual workflows stay separate.
- Awaiting user decision. Would need an ADR if adopted (amends the ADR-0099 required-check set). Depends on: T-D99, T-D101.
- Decision 2026-11-16 (user): not now. Churn right before the first release; the `protect-main` ruleset already lists the 9 checks by name. Revisit if check names start changing often (each rename means a ruleset edit).

### ✅ T-D103 [L] Move all IAM resources into the local bootstrap → ADR-0104
- Decided 2026-11-13 (user): do it before operator checklist step 4 (bootstrap 3b).
- Code: `modules/iam` → `bootstrap/ci/modules/app_iam` (`module.app_prod`, `module.app_drill`); `modules/restore_reader` → `bootstrap/ci/modules/restore_reader`. Env stack: `removed { destroy = false }` for both modules; new root inputs `app_application_id`, `app_scw_access_key`, `app_scw_secret_key`, `restore_reader_application_id`; outputs move to `bootstrap/ci`. Workflows pass `APP_*` / `RESTORE_READER_APPLICATION_ID` secrets.
- CI policies: `ci-prod` and `ci-drill` lose `IAMManager`; `ci-prod` holds `IAMReadOnly` only while `ci_prod_iam_transition = true` (one release); `ci-plan` keeps `IAMReadOnly` for `key-expiry.yml`.
- Operator: import the existing prod IAM into `bootstrap/ci` (no new prod keys), read the current secrets from prod state once, set GitHub secrets; after the first release set `ci_prod_iam_transition = false` and re-apply. Runbook: `runbooks/key-rotation.md` part 2.
- 2026-11-16 operator import: the imported restore-reader key planned a replace (`expires_at` 1-year provider default -> null, forces replacement). Added `ignore_changes = [expires_at]`, as the app key already has (T-D74).

### T-D104 [S] (deferred) `release.yml` `replace` dispatch input for prod `-replace`
- `workflow_dispatch` input `replace`, main-only and approval-gated, for prod `-replace` operations (cloud-init changes need a server replace). Depends on: ADR-0099 (amendment).
- 2026-11-16 (ADR-0111): image, compose, Caddy and Litestream config now change through metadata without a new VM; only the fixed bootstrap in `cloud-init` still needs `-replace`, so this is needed rarely.
- Decision 2026-11-16 (user): keep for the next cloud-init change. Without it, a prod cloud-init change (e.g. T-D115's docker group) needs a manual host fix or break-glass `-replace`. A replace means a new VM, a Litestream restore and downtime.

### T-D105 [S] (won't do for now) `drill.yml` explore-mode inputs for drill break-glass variables
- Explore-mode dispatch inputs for the drill-only break-glass variables `break_glass_console_password` and `break_glass_ssh_cidrs`. Depends on: T-D98.
- Decision 2026-11-16 (user): not needed. `boot_logs=true` covers boot debugging and tailnet SSH works whenever the VM is up.

### ✅ T-D106 [S] Clean up leftover public-drill references after ADR-0101
- `terraform/scripts/preflight.py` and the `docs/plans/v3` docs still mention `drill.budget.rising-dough.eu`. `deploy.yml` and `rollback.yml` still read `vars.DRILL_URL`; switch them to the ts.net host derived from `vars.TAILNET_DNS_NAME`. Depends on: ADR-0101, T-D97.
- Decision 2026-11-16 (user): do next, after the first release (step 11). `deploy.yml`/`rollback.yml` work today only because `vars.DRILL_URL` already holds the ts.net URL.
- Done 2026-11-16: T-D129 removed `deploy.yml` and every `DRILL_URL` read; `preflight.py` no longer names the public host. Only historical notes in this file and the operator checklist mention it.

### ✅ T-D107 [S] Verify tailnet certificate on the first `mode=gate` drill run
- Verified 2026-11-16, gate run 43907146399 on `ec01640`: smoke `curl -fsS` (no `-k`) passed from CI as `tag:ci`, and the operator laptop got HTTP 200 with a valid certificate (`ssl_verify_result=0`). Caddy obtains the `*.ts.net` certificate from tailscaled; the first ~1 min after boot shows connect errors and 5 s timeouts while it does.
- Verify Caddy obtains the `*.ts.net` certificate from tailscaled (not verified against the Caddy or Tailscale docs). Also handle a stale `budget-planner-drill` tailnet node, which makes the new node register as `-1` and breaks the certificate name. Fix if it fails.
- Depends on: T-D98, operator checklist steps 2 and 9.

### T-D108 [S] (won't do for now) Per-env Tailscale OAuth clients
- Separate OAuth clients per environment instead of the single `tag:automation` client. Depends on: operator checklist step 2.
- Decision 2026-11-16 (user): low value for a single maintainer whose OAuth secret lives only in GitHub environments. Revisit if more people or environments get the secret.

### ✅ T-D109 [S] Resolve the prod deploy-key mismatch
- The deploy public key in prod's config has fingerprint `SHA256:PXLm…`; no local private key matches it. `~/.ssh/rising_dough_deploy` is `SHA256:p4pE…`. Decide which key the GitHub `prod` environment's deploy-key secret holds, then rotate the prod deploy pubkey through the pipeline if needed (`runbooks/key-rotation.md`). Depends on: operator checklist step 5.
- Superseded 2026-11-16 by ADR-0111 (T-D129): there is no deploy key; the migration removes the `deploy` user and its key.

### ✅ T-D110 [S] Fix shellcheck SC1122 in `scripts/prod_db_seed.sh` → (no ADR; CI fix)
- `just ci` fails on `test_shellcheck_clean`: the `print_plan` heredoc delimiter `PLAN` matches the first word of its first content line (`PLAN (one-time prod DB seed, …)`), so shellcheck reads that line as a malformed end token (SC1122). Rename the delimiter to `EOF_PLAN`. Output unchanged. The same run also reports SC2029 (info, still exit 1) on two `ssh` calls whose client-side expansion is intended; suppress each with a commented `# shellcheck disable=SC2029`.

### ✅ T-D111 [S] Drop unused `log_bucket_suffix` variable from `modules/storage` → (no ADR; CI fix)
- `Terraform` workflow `fmt + validate + lint` fails on tflint `terraform_unused_declarations`: `log_bucket_suffix` is declared but never read (its description already says "informational only"). Remove the variable and its pass-through in `terraform/main.tf`. Variables do not live in state, so plans stay no-op.

### ✅ T-D112 [S] Bump soupsieve 3.0.4 → 4.1 for CVE-2026-126190 → (no ADR; dependency fix)
- `pip-audit` fails on CVE-2026-126190 (fixed in soupsieve 4.0.0), published after the 2026-11-07 run. Dev-only (`beautifulsoup4`, dev group). `uv lock --upgrade-package soupsieve` → 4.1; no other lock changes.

### ✅ T-D113 [S] `terraform.yml` mask step fails on empty secrets → (no ADR; CI fix)
- "Mask secret inputs (T-D83)" ends its loop with `[ -n "$line" ] && echo …`. With an unset secret, the last status is 1 and `bash -e` fails the step before "Check required Terraform inputs" can name the missing inputs. Use `if …; then …; fi`. `plan (prod|drill)` still fails until the GitHub environments exist (operator checklist step 5), but now with the `check_tf_vars.py` message.

### ✅ T-D114 [S] `trivy image` fails on the v3→main PR
- Exposed once T-D101 let `trivy fs` pass: the image scan (now correctly HIGH/CRITICAL-filtered) exits 1, with findings hidden in SARIF. Step 1: `if: failure()` table re-run, same as fs. Step 2: fix (base image / dependency bump) or allowlist (`.security-allowlist.yml` `trivy_image`).
- 2026-11-13 findings: 109 HIGH/CRITICAL, all Debian 12.15 OS packages, none with a fixed version; Python packages clean. Decision (user): move the base to `python:3.12-slim-trixie` (ADR-0102). If trivy still fails on trixie, the rest needs a separate decision (see ADR-0102 Consequences).
- trixie result: 109 HIGH, 0 CRITICAL; only zlib1g CVE-2026-76844 has a fix. Decision (user): runtime `apt-get upgrade -y` + `ignore-unfixed: true` on the image scan only (ADR-0103).

### ✅ T-D115 [S] Forecast current-period Expenses includes overdue commitments → ADR-0105
- Bug: Plan · Forecast current row `Expenses` (from `budget.month_summary` committed) used window `[today, next_income)`, dropping unpromoted planned rows dated before today and recurring occurrences with `next_due < today`. Unbudgeted overdue vanished from EOM entirely.
- Fix: committed window has no lower bound (`committed_in_window(start=None)`); recurring expands from `next_due`. Also lowers Budget/Today "left" by budgeted overdue.
- Tests: `tests/unit/services/test_budget.py` + `tests/unit/services/test_forecast_monthly.py` overdue cases (planned + recurring, budgeted + unbudgeted, older than the current period, due today).

### ✅ T-D115 [S] `deploy` user cannot run `docker compose` (superseded by ADR-0111) → ADR-0037
- Found 2026-11-16 while verifying the T-D109 key: `deploy-budget-planner status` on prod printed `open /etc/budget-planner/docker-compose.yml: permission denied`. The script calls `docker compose` as `deploy`, but cloud-init gave `deploy` no `docker` group (the compose file is `root:docker 0640`). Every pipeline deploy and rollback would fail.
- Fix: `groups: [docker]` on the `deploy` user in `cloud-init/bootstrap.yaml.tpl`. The SSH forced command still restricts `deploy` to `deploy-budget-planner` (ADR-0037 section 3). Note: `docker` group membership is root-equivalent on the host, so the forced command is the security boundary.
- Running prod VM: cloud-init does not re-run (ADR-0098). Operator adds the group by hand once (`sudo usermod -aG docker deploy`), logged in `docs/CHANGELOG.md`. New VMs (drill, any prod replace) get it from cloud-init.

### ✅ T-D116 [S] Rename secret `GITHUB_DEPLOY_PUBKEY` → `DEPLOY_SSH_PUBKEY` → ADR-0093
- GitHub rejects secret names starting with `GITHUB_` (HTTP 422), so the secret `terraform.yml` and `restore-drill.yml` read could never be created; `TF_VAR_github_deploy_pubkey` was always empty in CI. Found 2026-11-16 during operator checklist step 5. Renamed in workflows and docs; the Terraform variable name is unchanged.

### ✅ T-D117 [S] CI identities locked out of the durability buckets → ADR-0105
- First PR plan with CI keys (2026-11-16): `ci-plan` 403 on `GetBucketCors` (ADR-0091 allow-list lists no CI identity). Same failure waits for `ci-prod` (release) and `ci-drill` (teardown).
- Code: `bucket_plan_principals` → `AllowTerraformPlanRead` statement (bucket config reads only); workflows pass `BUCKET_PLAN_PRINCIPALS`.
- Operator: add `application_id:<ci-prod>` to prod/prod-plan `BUCKET_ADMIN_PRINCIPALS`, `application_id:<ci-drill>` to the drill ones, `BUCKET_PLAN_PRINCIPALS = ["application_id:<ci-plan>"]` on prod/prod-plan; one targeted break-glass apply of the prod bucket policy.

### ✅ T-D118 [S] CI identities need Block Storage permissions → ADR-0100 (amendment)
- PR plan 2026-11-16: `ci-plan` `insufficient permissions: read volume` refreshing `scaleway_instance_server.app` (root volume is an SBS volume). `ci-prod`/`ci-drill` would fail the same way on apply/destroy.
- Code: bootstrap/ci policies add `BlockStorageFullAccess` (ci-prod, ci-drill) and `BlockStorageReadOnly` (ci-plan).
- Operator: apply `terraform/bootstrap/ci` locally (allowed exception, ADR-0099); keys unchanged.

### ✅ T-D119 [S] opentelemetry-api ReDoS (CVE-2026-126360) → T-D91
- pip-audit 2026-11-16: `opentelemetry-api` 1.45.1 (transitive via `fastapi`) has CVE-2026-126360 / GHSA-mf5v-w3w3-f6cg, quadratic regex backtracking in `TraceContextTextMapPropagator.extract()` on a crafted `traceparent`. Reachable: FastAPI's built-in telemetry (`tracing` on by default) calls `propagate.extract` on every request's headers, on the event loop.
- Fix: `uv lock --upgrade-package opentelemetry-api` → 1.45.2. Lockfile only; no allowlist entry.

### ✅ T-D120 [S] Drop dead CI secrets: DEPLOY_SSH_KNOWN_HOSTS_DRILL, CODEQL_TOKEN switch → ADR-0094
- `DEPLOY_SSH_KNOWN_HOSTS_DRILL` was never set and could not match a fresh drill VM; the host key comes from `ssh-keyscan` over the tailnet (ADR-0094). The pin step now only creates `~/.ssh/known_hosts`.
- `CODEQL_TOKEN` was only an on/off switch for the Trivy SARIF uploads (auth is `GITHUB_TOKEN`). Repo is public, Code Scanning is free: uploads are now unconditional, findings land in the Security tab.

### ✅ T-D121 [S] Register drill workflows on `main` before the first gate → ADR-0099
- 2026-11-16: `gh workflow run drill.yml --ref v3 -f mode=gate` → `HTTP 404: workflow drill.yml not found on the default branch`. GitHub dispatches only workflows that exist on the default branch; `main` had only `ci.yml`.
- Fix: PR #3 copies `drill.yml` and `drill-destroy.yml` byte-for-byte from v3 onto `main` (workflow_dispatch only, never run from `main`; identical files, so PR #2 has no conflict).
- Second failure: the dispatched run ended in `startup_failure` (no job log). `drill.yml` grants only `contents: read`, but its reusable callees request more: `build.yml` `packages: write` + `id-token: write`, `terraform.yml` `pull-requests: write`. GitHub refuses runs where a callee requests more than the calling job grants; actionlint does not check it. Same bug in `drill-destroy.yml` and `drill-sweeper.yml` (the TTL backstop could never have destroyed anything).
- Fix: job-level `permissions` on every reusable call in those three files; `tests/unit/deploy/test_reusable_permissions.py` asserts, for every workflow, that each caller grants what its local reusable workflow requests.
- `main`'s registration copies stay stale (never run; dispatch uses `--ref v3`); v3 merged `origin/main` first so PR #2 is a plain modification, no add/add conflict.
- Done when PR #3 is merged, the gate dispatch starts, and `drill-gate` is `success`.

### ✅ T-D122 [S] `build.yml` guard skipped every branch drill gate → ADR-0099
- First gate that started (run 43900541187, 2026-11-16): `build` skipped, so apply/smoke skipped and `drill-gate` = failure. The guard `github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'` meant "direct dispatch only from main", but in a called workflow `github.event_name`/`github.ref` are the caller's: a drill dispatched on a branch always skipped the build.
- Fix: `workflow_call` input `called` (default true); guard `inputs.called || github.ref == 'refs/heads/main'`. Direct dispatch has no such input, so it stays main-only. Test in `tests/unit/deploy/test_build_workflow.py`.

### ✅ T-D123 [S] Drill runs on DEV1-S: STARDUST1-S quota is 1 per organisation → ADR-0032 (amendment)
- Gate run 43903186571 (2026-11-16): `quota exceeded(s): cp_servers_type_STARDUST1_S has reached its quota (1/1)`; prod holds the only Stardust. Teardown removed the partial drill.
- Fix: root var `drill_instance_type` (default `DEV1-S`); prod pinned to `STARDUST1-S` in `main.tf`; compute output `server_type`; tftest runs for both envs. No prod diff.
- The STARDUST1-S quota cannot be raised (operator, 2026-11-16): `DEV1-S` for the drill is permanent.

### ✅ T-D124 [S] Drill teardown removes the drill's tailnet node → ADR-0101
- Found 2026-11-16 after the first green gate (run 43907146399): teardown destroyed the VM, but the ephemeral node `budget-planner-drill` stayed in the tailnet as offline. Ephemeral nodes are only removed after an offline period (minutes to hours). A drill started meanwhile registers as `budget-planner-drill-1`, so the `*.ts.net` certificate name and `DRILL_URL` do not match and smoke fails.
- Operator (one-time): Tailscale admin console > Settings > OAuth clients: new client `budget-planner-drill-cleanup`, scope `devices:core` write, tag `tag:drill` only. Store as `TS_CLEANUP_CLIENT_ID` / `TS_CLEANUP_SECRET` in `drill-teardown` (teardown, sweeper) and `drill` (early destroy).
- Code: a step after each drill destroy (drill.yml teardown, drill-destroy.yml, drill-sweeper.yml) gets an OAuth token, lists devices, and deletes every device whose hostname is `budget-planner-drill` or `budget-planner-drill-<n>` and that carries `tag:drill`. Never touches `tag:prod` or `tag:ci`. Idempotent: no device found is success. A failed delete is a warning, not a failed teardown (the VM is already gone).
- Test: static workflow test that each destroy path has the step and filters on `tag:drill`.
- Done 2026-11-16: shared `scripts/tailnet_drill_cleanup.py` + `tailnet-cleanup` job (`needs` the destroy job, `if: always()` unless destroy was skipped, environment `drill-teardown`) in all three destroy workflows; test `tests/unit/deploy/test_tailnet_drill_cleanup.py`. Until the operator creates the OAuth client and secrets the job only warns: remove the node by hand (admin console > Machines > `budget-planner-drill` > Remove) before the next drill.
- Proven 2026-11-17: cleanup OAuth client and `TS_CLEANUP_*` secrets set by the operator; explore drill 44039509630, then `drill-destroy.yml` 44041451732 logged `Removed tailnet node budget-planner-drill`, and the node was gone from the console.
- Not chosen: `tailscale logout` from a shutdown hook on the VM (Scaleway destroy does not reliably shut down cleanly first).

### ◐ T-D126 [S] GHCR image retention for `budget-planner` → ADR-0099
- No retention today: every release and every drill gate pushes a `sha-…` image (plus cosign signature artifacts) to `ghcr.io/mtkublin/budget-planner`, and GHCR keeps all versions forever. A private package counts against the GitHub Packages storage quota.
- Plan: weekly `image-retention.yml` (cron + `workflow_dispatch` with `dry_run`, default true for the first runs) using `actions/delete-package-versions` (pinned by SHA):
  - keep: newest 20 `sha-…` versions, everything tagged `main` or `v*` (T-D125), and the images prod has as `current` and `previous` (read via the deploy `status` command, or covered by N);
  - delete: untagged versions and orphaned signature artifacts older than 7 days, `sha-…` beyond the newest 20.
- Needs a token with `delete:packages` (the workflow's `GITHUB_TOKEN` with `packages: write` works when the package is linked to the repo).
- Test: static workflow test for the keep rules, `dry_run` default and a pinned action.
- Done 2026-11-16: `.github/workflows/image-retention.yml` + `scripts/ghcr_retention.py` (the action cannot express the signature/child-manifest rules; selection is unit-tested in `tests/unit/deploy/test_image_retention.py`). Scheduled runs dry-run until the repo variable `IMAGE_RETENTION_ENABLED` is `true`; dispatch deletes only with `dry_run=false`. Also kept: every version younger than 7 days and child manifests of kept indexes (provenance/SBOM make `build-push-action` push untagged children). Prod current/previous are assumed to be within the newest 20. Runbook: `runbooks/image-retention.md`.
- Check first: `gh auth refresh -s read:packages`, then `gh api /users/mtkublin/packages/container/budget-planner` for visibility and version count.
- Timing (user, 2026-11-16): after the first release.
- 2026-11-18: first dry run (run 44297239247) FAILED: `ghcr_retention.py` `fetch_children` raised `HTTP Error 404` on a registry manifest GET, so no plan was produced. Open bug; retention stays disabled. Status changed from done to partial (◐) until a dry run succeeds.
- 2026-11-18 fix (branch `wi/docs/v3-remaining/RET`): root cause was the `Accept` header. `fetch_children` asked only for index media types, and GHCR answers `404 MANIFEST_UNKNOWN` ("Accept header does not support OCI manifests") for a cosign `.sig` artifact, which is a plain OCI image manifest. The Accept header now lists all four manifest types; a remaining 404 means "children undetermined" and then no untagged version is deleted (other errors abort). Dry run 44299557709 on the branch is green: 59 kept, 0 to delete (everything is younger than 7 days or protected). Stays ◐: enabling `IMAGE_RETENTION_ENABLED` and the first real run are the user's decision.
- 2026-11-18: `IMAGE_RETENTION_ENABLED=true` set by the operator. First real scheduled run Monday 2026-11-23 03:17 UTC. Done when that run (or a `dry_run=false` run) shows `mode: APPLY` and the next release still deploys.

### ✅ T-D125 [M] Release prod from GitHub releases on `main` → ADR-0109 (Accepted 2026-11-16)
- Decouple merge from release: `release.yml` triggers on `release: published` (tag `vX.Y.Z`); the tag's commit must be an ancestor of `origin/main`. Image also tagged `v…`; rollback by version; tag ruleset on `v*` (operator only, immutable).
- Touches `release.yml`, `build.yml`, `terraform.yml`, `deploy.yml` (main-ref guards become "main or a `v*` tag on main", one shared tested script), `rollback.yml`, runbooks `deploy.md` / `rollback.md`, `github-settings.md` (tag ruleset).
- Timing (user, 2026-11-16): after the first merge-triggered release (operator checklist step 11). Accepting ADR-0109 flips it to Accepted.

### ✅ T-D127 [S] Deploy forced command did not split `SSH_ORIGINAL_COMMAND` → ADR-0037
- First pipeline release (run 43913941966, 2026-11-16): `deploy-prod` got the usage text, exit 1. Host syslog: `subcmd=deploy sha-89ac3c2`, i.e. one word. The script's strict-mode `IFS=$'\n\t'` does not split on spaces, so `args=( $SSH_ORIGINAL_COMMAND )` stayed one element; single-word `status` worked, `deploy <tag>` and `rollback <tag>` never could. Prod was untouched (still `sha-075f986`).
- Fix: `IFS=' ' read -r -a args <<< "$SSH_ORIGINAL_COMMAND"` (also no glob expansion). New `tests/unit/deploy/test_deploy_script.py` drives the rendered script through `SSH_ORIGINAL_COMMAND`.
- Prod host: cloud-init does not re-run, so the running VM gets the same one-line patch by hand (logged in CHANGELOG); new VMs (drill, future prod replace) get it from cloud-init.

### ✅ T-D128 [S] One prod approval per release → ADR-0110 (Accepted 2026-11-16)
- `deploy.yml` runs prod in the reviewer-less environment `prod-deploy` (deploy secrets only; branches `main` + tags `v*`). The terraform apply in `prod` is the single approval; `deploy-prod` still needs the apply. `rollback.yml` stays on `prod`.
- Touches `deploy.yml`, `release.yml` comment, `tests/unit/deploy/test_release_approval.py`, runbooks `github-settings.md`, `deploy.md`, `operator-checklist.md`.

### ✅ T-D129 [L] Terraform-declared host state, pulled by a host agent → ADR-0111
- Why: the first pipeline release (2026-11-16) showed the SSH deploy path never worked (ADR-0111 Context). Prod got `sha-89ac3c2` by logged break-glass.
- ✅ a. Docs: ADR-0111, ADR-0037/0110 superseded notes, this task, CHANGELOG.
- ✅ b. Agent `terraform/host/agent/bp_agent.py` (stdlib only): fetch config, generation check, pinned cosign install + verify, atomic file writes, compose pull/up, service restarts, local `/ready` probe, `status.json`, back-off. Unit tests for the pure parts (`tests/unit/deploy/test_bp_agent.py`).
- ✅ c. Terraform: compute module renders `bp-config` (all managed files, image ref + previous ref, cosign policy, generation) and `bp-agent` into `user_data` (sensitive); vars `app_image_ref`, `app_image_previous_ref`; outputs `app_image_ref`, `app_image_previous_ref`, `host_config_generation`, `host_image_ref`; cloud-init reduced to fixed bootstrap + loader + systemd timer + `DOCKER-USER` metadata block; Caddy serves `/.well-known/bp-deploy-status.json`. tftest.
- ✅ d. CI (`scripts/ci/host_release.py`): `terraform.yml` passes the refs (previous from state), monitors the status after apply, re-applies swapped refs on failure in the same job; `release.yml` without `deploy-prod`; `rollback.yml` as an apply; `deploy.yml` and `deploy-budget-planner` removed; drill gate checks the status; `restore-drill.yml` resolves the newest release to a digest. Workflow tests.
- e. 2026-11-16 drills: explore run 43953729753 (`c10aba8`): first boot converged through the agent, status `ok`, `/ready` 200, cosign verified on the host. Break drill 43955571040 (T-D33 image, `/ready` 503): app `unhealthy`, agent held in `applying` waiting for `/ready` (the `failed` transition was not observed: operator tailnet dropped). `rollback.yml env=drill` 43959552086: in-place update (0 add, 1 change, 0 destroy) with refs swapped back to `c10aba8`; host convergence not checked (same reason). Drill destroyed (43960430008). Still open: the final `drill-gate` on the PR #14 head, which first needs the stale tailnet nodes `budget-planner-drill` and `budget-planner-drill-1` gone (T-D124 cleanup client, or remove by hand).
- e. Drill (user go 2026-11-16): gate run proves first-boot convergence, cosign verify and the metadata size limit; an explore drill (`keep=true`) plus `rollback.yml env=drill` proves a live metadata update converging without reboot. Caddyfile is first validated by that boot (no local `caddy validate`).
- f. 2026-11-18: migration script run by the operator (`bp-agent bootstrap installed; deploy path removed`; timer + guard active, `guard-ok`; loader 404 until the first apply, as expected). Release `v3.0.0` (run 44288680132) did not reach prod: first the `prod` environment allowed no tags (operator added the `v*` tag rule), then the prod-only ref guard failed (T-D134). Prod still on `sha-89ac3c2`; next release `v3.0.1`.
- f. 2026-11-18: release `v3.0.1` (run 44294472551) is the first release through the host agent. In-place update (0 add, 1 change, 0 destroy); prod runs `v3.0.1@sha256:2246e6f…`; the status file reports `state: ok`; `/ready` is 200; the CSP header is sent (T-D132). The prod state now records a previous ref. The final `drill-gate` was green on PR #14 and PR #16. Never run on prod yet: the step "Roll back to the previous ref (prod)" (only runs when convergence fails). Watch the next release.
- f. Prod migration (needs user go): runbook `runbooks/host-state-migration.md` + `terraform/host/migrate/adr-0111-install-agent.sh` (✅ written; one logged break-glass: install loader + timer + firewall rule, remove `deploy` user and key), then the first release through the new path. GitHub: delete `prod-deploy` environment and deploy secrets.

### ✅ T-D130 [S] Turn off Dependabot version-update PRs → (no ADR; tooling)
- Decision 2026-11-16 (user): the weekly Dependabot PRs and branches (GitHub Actions, Docker base image) are noise for a single maintainer. Removed `.github/dependabot.yml` (its mention in `HANDOFF.md` is historical); open Dependabot PRs closed and their branches deleted. Dependabot security updates were already off.
- What still catches vulnerable dependencies: `security.yml` (pip-audit, trivy fs + image) on every PR, and GitHub vulnerability alerts (no PRs). Action and base-image bumps are manual from now on.

### ✅ T-D131 [S] `Trivy config scan` panics on the ADR-0111 Terraform → (no ADR; CI fix)
- Explore drill run 43951985795 (2026-11-16): `fmt + validate + lint` failed in "Trivy config scan" with `panic: value is marked, so must be unmarked first` (go-cty, trivy `iac/terraform/context.mergeObjects`). Trigger: `modules/compute` merges objects that hold `sensitive()` values (T-D129). Reproduced with trivy 0.69.3 and 0.70.0 (the trivy-action v0.36.0 default); 0.76.2 does not panic and reports 0 misconfigurations.
- Fix: `version: v0.76.2` on that step in `terraform.yml`. `security.yml` scans (fs, image) are unchanged.

### ✅ T-D132 [S] CSP header never sent on HTML responses → ADR-0036
- Evidence (2026-11-16): `curl -I https://budget.rising-dough.eu/auth/login` returns `200 text/html` with no `Content-Security-Policy`; Observatory B/75 solely for that (`runbooks/security-audit-log.md` F1).
- Cause: `Caddyfile.tpl` attached the CSP with `header @html ...` where `@html { header Content-Type text/html* }`. A site-level named matcher is a request matcher, so it tests the request `Content-Type` and never matches a browser GET. The first fix idea, a `match { header ... }` block inside `header`, does not exist in Caddy 2.8: it parses and silently emits a bogus `Match:` response header and sets the CSP on every response (proven against `caddy:2.8`).
- Fix: keep the CSP at Caddy (ADR-0036 §3) and set it in `reverse_proxy { @html header Content-Type text/html*  handle_response @html { header Content-Security-Policy "..."  copy_response } }`. In `reverse_proxy` the named matcher is a response matcher; non-HTML responses are untouched. The nonce is the same `{vars.nonce}` that is sent upstream in `X-CSP-Nonce`. The policy string is unchanged.
- Test: `tests/unit/deploy/test_caddy_csp.py` (CSP only under a `handle_response` response matcher, no site-level request-matcher CSP, no bogus `match` block, policy keeps the nonce); render tftest asserts the rendered Caddyfile has the response matcher. Real Caddy 2.8 proof in the commit notes (HTML gets the CSP with the nonce the upstream received; JSON does not).
- Prod gets it with the next release (ADR-0111: Caddyfile via `bp-config`, host agent reloads Caddy). Then re-run Observatory (expect >= A+).

### ✅ T-D134 [S] Prod-only release steps never ran before the first tagged release → ADR-0109, ADR-0111
- Release `v3.0.0` (2026-11-18, run 44288680132) stopped twice before touching prod:
  1. Environment `prod` allowed only branch `main`: `Tag "v3.0.0" is not allowed to deploy to prod`. `github-settings.md` asked for the tag rule `v*`; it was never set. Operator added it.
  2. `terraform.yml` apply job, step "Guard env / ref": `python3 scripts/ci/ref_guard.py` runs with working directory `terraform/`, so the script was not found (exit 2). The drill branch of that `case` skipped the guard, so no drill ever ran the line, and the unit tests import `ref_guard.py` directly.
- Latent third bug: the apply job checked out with depth 1, so `ref_guard.py`'s "tag commit is on main" test would refuse any tag that is not the tip of `main`.
- Fix: `../scripts/ci/ref_guard.py`; `fetch-depth: 0` for prod in the apply job; the drill now runs the same guard, with a refusal (exit 1) only a notice and any other failure fatal. New `tests/unit/deploy/test_workflow_script_paths.py`: every `python3 <script>.py` in every workflow exists relative to its step's working directory (fails on the old file). `github-settings.md`: check command for the `prod` tag rule.
- Still prod-only, untestable on the drill: "Wait for host convergence (prod)" and "Roll back to the previous ref (prod)" (the apply runner is not on the tailnet, ADR-0111). They call `host_release.py` (unit-tested; the drill smoke job runs the same `wait`).
- Docs: the ADR-0111 runbooks said `ssh app@budget-planner-prod`; `app` is the container user (nologin, no key). Fixed to `operator@` everywhere.

### ✅ T-D133 [M] DRY the GitHub workflows → ADR-0099
- Found 2026-11-18 reviewing T-D134. In value order:
  1. `restore-drill.yml` has its own Terraform init/apply/destroy and 27 `TF_VAR_*` lines instead of calling `terraform.yml`; move apply and destroy onto `terraform.yml` (as `drill-destroy.yml` does) and keep only restore, verify and evidence steps.
  2. `terraform.yml` repeats ~25 `TF_VAR_*` mappings in the `plan` and `apply` jobs; one source (composite action or a script that exports them from one list). Workflow-level `env:` cannot read environment secrets.
  3. The tailnet cleanup job is defined in `drill.yml`, `drill-destroy.yml` and `drill-sweeper.yml`; one reusable workflow.
  4. Tag → digest resolution is inline in `rollback.yml` and `restore-drill.yml`; a `host_release.py resolve-ref` subcommand with tests.
  5. Action pins drift (`setup-uv`: floating `@v3` in `ci.yml`, v3.2.4 in `lock-check.yml`, v4.1.0 in `security.yml`; `setup-buildx-action` v3.10.0 vs v3.7.1) and Dependabot is off (T-D130); align them and add a test that each action has one pin and it is a SHA.
- Done when: one gate drill and one restore drill are green on the change. Not part of the `v3.0.1` fix.
- Code done 2026-11-18 (ADR-0117), restore-drill proof done 2026-11-18 (run 44351020259, green, first `restore-log.md` entry); gate-drill proof pending (◐): (1) `restore-drill.yml` is now `drill-lock` -> `image` -> `apply` (terraform.yml, env `drill`) -> `restore-drill` (env `drill`, the only one with `DEPLOY_SSH_PRIVATE_KEY`; tailnet, SSH, restore, verify, evidence) -> `destroy` (terraform.yml, `always()` once apply was attempted) -> `verify-destroy` / `tailnet-cleanup` / `report` (issue + labels); unused Scaleway CLI install dropped. (2) `scripts/ci/tf_env.py` + `.github/actions/terraform-env` replace both `TF_VAR_*` blocks (drill-only rules unit-tested in `test_tf_env.py`). (3) `tailnet-cleanup.yml` reusable, called by all four drill workflows. (4) `host_release.py resolve-ref` (tests in `test_host_release.py`). (5) one SHA per action, `test_action_pins.py`; setup-uv v4.1.0, setup-buildx v3.10.0, setup-node v4.4.0, setup-just v2.0.0 everywhere. Tests updated for moved locations only (`test_ci_terraform_inputs`, `test_ci_ssh_key_drill_only`, `test_tailnet_only_drill`, `test_tailnet_drill_cleanup`, `test_tailscale_ssh`, `test_backup_age_ceiling`, `test_drill_workflows`).
- 2026-11-18 (closeout): gate-drill proof green. `drill-gate` run 44366621363 on 4a20548 (PR #25, merged as e993538). That was the last open proof, so T-D133 is ✅. The gate exercised the `terraform-env` action and `tailnet-cleanup.yml`; the restore-drill proof is run 44351020259.
- Added from the readiness review: the restore job waits (bounded, 10 min) for the host agent status (`host_release.py wait` on `/.well-known/bp-deploy-status.json`, this generation applied, state ok, expected image running) before "Trigger restore", so a failed first convergence in back-off cannot run `compose up -d` mid-restore. Test: `test_restore_waits_for_host_agent_status_before_restore`.
- Drill proof must exercise: `drill.yml` gate (apply + smoke + teardown through the new `terraform-env` action and `tailnet-cleanup.yml`, `ci_ssh_pubkey` / `drill_run_id` reach Terraform); `restore-drill.yml` dispatch end to end (restore job on env `drill` reads `DEPLOY_SSH_PRIVATE_KEY`, `OPERATOR_SSH_PUBKEY`, `TS_OAUTH_*`; verify-destroy backend access in `drill-teardown`, issue on a forced failure); `rollback.yml` target resolution on drill.

### ✅ T-D135 [S] WebAuthn RP settings never reach the host → ADR-0067, ADR-0111
- Found 2026-11-18 while re-scoping T-D43. `config.py` defaults to `webauthn_rp_id=localhost` and `webauthn_origin=http://localhost:8000`, and the comment there says production must set both. `terraform/cloud-init/compose/docker-compose.yml.tpl` sets neither `BUDGET_WEBAUTHN_RP_ID` nor `BUDGET_WEBAUTHN_ORIGIN`, and nothing in production config rejects the defaults. So prod and drill most likely serve `rp_id=localhost`, and passkey registration or sign-in from the real hostname fails in the browser. Password sign-in is unaffected. Confirm on the next explore drill (passkey registration from `/settings/security`) before the fix.
- Fix: render both variables from the host's public hostname in the compose template (prod `budget.rising-dough.eu`, drill the tailnet name). In production, refuse to start when `webauthn_rp_id` is `localhost` or the origin is not `https://<rp_id>` (fail fast, like `cookie_secret`). Unit test for the validator; tftest that the rendered compose sets both. Reaches prod with the next release through the host agent (no VM replacement).
- Done 2026-11-18: the compose template renders `BUDGET_WEBAUTHN_RP_ID=<hostname>` and `BUDGET_WEBAUTHN_ORIGIN=https://<hostname>` from the compute module's `hostname` (prod `budget.rising-dough.eu`, drill `budget-planner-drill.<tailnet>.ts.net`). `Settings._finalise` refuses production with `webauthn_rp_id=localhost` or an origin other than `https://<rp_id>`. Tests: `tests/unit/test_config.py` (validator), `terraform/tests/render.tftest.hcl` (rendered bp-config compose for prod and drill); production test fixtures now pass valid values. Reaches prod with the next release through the host agent (bp-config update, no VM replacement); an app image with the validator needs those env vars, which the same apply delivers.
- Verified on prod 2026-11-18 (operator): the app env has `BUDGET_WEBAUTHN_RP_ID=budget.rising-dough.eu` and `BUDGET_WEBAUTHN_ORIGIN=https://budget.rising-dough.eu`. Drill proof 2026-11-18 (DRILL-2, run 44356288331): `scripts/drill/passkey_check.py` passed (password sign-in, forced rotation, passkey registered, signed out, passkey sign-in).

### ✅ T-D136 [S] Prod Litestream cannot restart once replicas are age-encrypted → ADR-0114, ADR-0078, ADR-0111
- Found 2026-11-18 by the T-D56 cut-over work. Since release `v3.0.1` the replicate config has `age.recipients` only, so new snapshots and WAL segments in the prod bucket are age ciphertext (Litestream 0.3.14 keeps the running generation; file names stay `*.lz4`).
- Root cause (verified against Litestream v0.3.14 source): `Replica.Sync` clears its position on any error and on process start, and when `r.Pos().Generation` differs from the DB generation it calls `Replica.calcPos`. `calcPos` reads the newest WAL segment of the generation and runs `age.Decrypt(rd, r.AgeIdentities...)` **only if `len(r.AgeIdentities) > 0`**, then `io.Copy(io.Discard, lz4.NewReader(rd))`. With no identity and a ciphertext last segment, the LZ4 reader fails on the age header; `Sync` returns `cannot determine replica position: ...`; the monitor loop only logs and retries, so replication stalls while the container stays "up". The converse also holds: once identities are set, a plaintext last segment makes `age.Decrypt` fail the same way.
- Restart triggers: host reboot, a change to `litestream.yml` or `litestream.env` (the host agent runs `docker compose restart litestream`), any release that recreates the container (release `v3.0.2` carries T-D135's compose change).
- Fix (ADR-0114): (1) the replicate config gets `age.identities: [${LITESTREAM_AGE_IDENTITY}]` beside the recipient (prod, drill, prod-sim); (2) the litestream service runs `litestream-entrypoint.sh` (a static file the host agent writes beside the other config, mounted read-only), which exports the identity from `litestream-age.key` and, once per host (marker `/data/.litestream-age-generation`), deletes Litestream's local meta dir `/data/.budget.db-litestream` so the next start opens a new generation, whose snapshot and segments are all ciphertext. `/data/budget.db` is never touched. Restore-only config unchanged.
- Rollout: `bp-config` carries the new yml, entrypoint and compose; the agent writes files, `compose up -d` recreates litestream (first start: reset + marker), then `restart litestream` (second start: marker present, no reset). Exactly one new generation.
- Tests: `tests/unit/deploy/test_litestream_age.py` (replicate configs carry identity + recipient, compose wiring, agent file entry), `tests/unit/deploy/test_litestream_entrypoint.py` (script behaviour with a stub `litestream`: one-time reset, marker, never touches the DB, missing identity refuses), render tftest (rendered config and bp-config entries on prod and drill).
- Local proof 2026-11-18 (Litestream 0.3.14 image, file replica, same `calcPos` path as S3): recipient-only restart logged `cannot determine replica position: lz4: bad magic number` and stalled; identity added over a plaintext last segment logged `...parsing age header: unexpected intro`; with the new config and entrypoint both states recover with one new generation, a second restart keeps it, and `litestream restore` with the identity returns every row and `integrity_check` ok. The full prod-sim stack was not run.
- Released in `v3.0.2` (main at `da05e10`) and verified on prod 2026-11-18. The one-time generation reset was logged at 2026-11-18T14:37Z ("forcing a new generation (one-time, ADR-0114)"). Litestream opened generation `2901fbd3873a6696`, wrote a snapshot, and writes WAL segments every 10 to 60 s with no errors; a second start did not force again. Replication had stalled from 2026-11-07T17:52Z (incident record in `runbooks/restore.md`; RPO at most ~24 h). Drill proof 2026-11-18 (DRILL-2, drill generation `6ce9a8950d6d4780`): `docker restart budget-planner-litestream` logged no forcing line and no errors; after a DB write, WAL segments 00000004 and 00000005 were written to s3 in that generation. The T-D56 cut-over is unblocked by this task, after the restore drill (T-D40).

### ✅ T-D137 [S] Let `restore-drill.yml` SSH into the drill host with the CI key (drill only) → ADR-0094, ADR-0111
- Found 2026-11-18 (restore drill runs 44297154259 / 44302972922): `restore-drill.yml` loads the `drill` secret `DEPLOY_SSH_PRIVATE_KEY` (public fingerprint `SHA256:p4pENTdc...`) and SSHes as `operator`, but since ADR-0111 removed the `deploy` user, drill hosts authorise only `OPERATOR_SSH_PUBKEY` (the operator's personal key): `Permission denied (publickey)`.
- Decision (user-approved in session 2026-11-18, "if it affects drill env only"): CI does NOT get the operator's private key. Drill hosts additionally authorise the CI key's PUBLIC key for `operator`. Prod never does. No new ADR: this is not a deploy path (ADR-0111 still has no SSH deploy; only the drill restore trigger/verify uses it) and ADR-0094 (tailnet-only SSH, operator user) is unchanged.
- Change: root variable `ci_ssh_pubkey` (default `""`, validated as a single-line ssh-ed25519 public key). `main.tf` local `ci_ssh_pubkey_effective = var.env == "drill" ? var.ci_ssh_pubkey : ""` is the only value passed to the compute module (`ci_ssh_pub`), so prod cannot render it whatever the variable holds. `bootstrap.yaml.tpl` adds it as a second `ssh_authorized_keys` entry when non-empty. Output `ci_ssh_authorized` (boolean) is a test hook.
- Workflows: `TF_VAR_ci_ssh_pubkey` from the environment VARIABLE `CI_SSH_PUBKEY` (public key, not a secret) in `restore-drill.yml` (job fixed to `drill`) and in `terraform.yml` plan/apply behind `<env> == 'drill' && vars.CI_SSH_PUBKEY || ''`. No prod job references it.
- Tests: `terraform/tests/render.tftest.hcl` (no key by default, key renders as second entry, prod drops it even when set, drill authorises it, a non-public-key value is rejected); `tests/unit/deploy/test_ci_ssh_key_drill_only.py` (static: no prod job, every shared-job use guarded).
- Operator step (user, public key, not run by an agent; fingerprint checked against `SHA256:p4pENTdc`):
  - `gh variable set CI_SSH_PUBKEY -e drill -R mtkublin/rising-dough < ~/.ssh/rising_dough_deploy.pub`
  - `gh variable set CI_SSH_PUBKEY -e drill-plan -R mtkublin/rising-dough < ~/.ssh/rising_dough_deploy.pub` (so the PR plan matches the apply)
  - Do NOT set it on `prod` or `prod-plan`.
- Done 2026-11-18 for the code. Drill proof 2026-11-18: restore-drill run 44351020259, step `Verify operator SSH login (T-D41)`, succeeded. Takes effect on the next drill apply (cloud-init runs on first boot; existing drill hosts are disposable).

### ✅ T-D138 [M] Explicit drill lock as the first step of every drill workflow → ADR-0115, ADR-0099, ADR-0101
- Asked 2026-11-18: "very explicit behaviour, checking if no other drill instance exists or is being brought up. could be a first step in the drill actions".
- Problem: (1) all drill workflows share concurrency group `drill`, which serialises RUNS only. A kept explore drill (`drill.yml mode=explore keep=true`) finishes its run after apply and smoke while the VM stays up until its `expires-at` tag, so the group is free; a gate or a `restore-drill.yml` dispatched in that window `-replace`s the explore VM (same drill Terraform state) and then destroys it, silently. (2) A concurrency group keeps at most one PENDING run: a third dispatch cancels the older pending run without notice (two orchestrators dispatch drills in parallel here).
- Design (ADR-0115): job `drill-lock` is the first job of `drill.yml`, `restore-drill.yml`, `drill-destroy.yml` and `drill-sweeper.yml`; every other job `needs` it directly or transitively. It runs `scripts/ci/drill_lock.py` in environment `drill-teardown` (ungated; holds `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`, `TS_CLEANUP_*`) with `actions: read`. Checks: (a) other drill-group workflow run active (GitHub API); (b) a Scaleway drill-project server named `budget-planner-drill*` exists (ground truth); (c) an online `tag:drill` node `budget-planner-drill[-n]` in the tailnet (cross-check, read-only). Race safety: the job runs inside the `drill` group, which the run already holds, so no other group member can create or replace a VM while it evaluates.
- Behaviour:

| Situation | Result |
|-----------|--------|
| no drill VM, no tailnet node, no other drill run | pass: "drill lock acquired: no drill VM, no other drill run" |
| drill VM up, `expires-at` in the past (sweeper not yet run) | fail: "expired drill still up ... run drill-destroy.yml first" (never destroys by itself) |
| drill VM up, not expired (or no usable tag) | fail: "drill VM <name> is up until <expires-at> (kept explore drill?); run drill-destroy.yml or wait". Observed 2026-11-18 (run 44383745599, kept explore drill 44381760469) |
| online `tag:drill` node | fail (same remedy) |
| other drill-group run active | fail: workflow name, run id, URL |
| `force=true` (`drill.yml`, `restore-drill.yml`; operator only) | skips (b)/(c) with a loud `::warning::`; (a) always applies |
| `drill-destroy.yml`, `drill-sweeper.yml` | (a) only (they are how (b)/(c) are cleared) |
| any API error or missing credential | fail closed with `::error::` (exit 2) |

- Notes: runs that are `queued`/`pending` and were created after this run are waiting behind it in the group and are not holders (otherwise the first of two parallel dispatches would fail on the second); `in_progress` and `waiting` always count. `rollback.yml` now has `run-name: rollback (<env>)`; a `rollback (drill)` run counts, a prod rollback does not. A third dispatch still cancels an older pending run (GitHub behaviour); the lock cannot see a cancelled run, so dispatch drills one at a time. `rollback.yml env=drill` (needs a VM) is unchanged.
- Tests: `tests/unit/deploy/test_drill_lock.py` (each table row, fail closed, workflow wiring: lock job first, every job needs it).
- Done 2026-11-18 for the code. Drill proof pending (orchestrator): dispatch a kept explore drill, then a gate; the gate must fail at `drill-lock` naming the VM and expiry; `drill-destroy.yml`, then a gate passes.
- DRILL-2 2026-11-18: `drill-lock` succeeded in runs 44356288331 and 44351020259 (no conflicting drill in either). Still open, and not run by DRILL-2: the negative case, a gate that fails at `drill-lock` while kept explore drill 44356288331 is up, and passes after `drill-destroy.yml` (run 44365679103 dispatched).
- 2026-11-18 (closeout): still ◐. The gate drill (run 44366621363) passed on the PR #25 head, which covers the positive path. Remaining: the negative case with the next explore drill. Keep the explore drill up, dispatch a gate, and check that it fails at `drill-lock` naming the VM and expiry. Then run `drill-destroy.yml` and check that the gate passes.
- 2026-11-18 (positive leg after destroy, ✅): restore-drill run 44387134093 (dispatched from `main` at b018739) passed `drill lock` after the kept explore drill 44381760469 had been destroyed. Both legs of ADR-0115 are now observed: the negative case (run 44383745599) and the positive case (run 44387134093).

### ✅ T-D139 [S] Drill gate fails at smoke: Let's Encrypt rate limit on the fixed drill name → ADR-0116, ADR-0101
- Found 2026-11-18 (gate run 44304732854, explore drill 44308968526, GATE-FIX). Symptom: smoke `curl: (28)` on `/ready` for 10 min after the node joined the tailnet. Evidence over SSH on the explore drill: containers all up, Caddy listening on 443, Caddy log `external certificate manager ... local-tailscaled.sock/localapi/v0/cert/... context deadline exceeded`, tailscaled log `getCertPEM: 429 urn:ietf:params:acme:error:rateLimited: too many certificates (5) already issued for this exact set of identifiers in the last 168h0m0s, retry after 2026-11-19 12:00 UTC`. Not a T-D135 / T-D136 regression (hypotheses 1 to 4 ruled out: cloud-init, host agent, WebAuthn validator and the name were fine; the app was healthy).
- Fix (ADR-0116): `drill_run_id` Terraform variable; the drill registers as `budget-planner-drill-<run id>`, so each drill orders a certificate for a new name. Workflows pass `github.run_id`.
- Tests: `terraform/tests/render.tftest.hcl` (unique name, fixed name without id, non-digits rejected, rejected on prod), `tests/unit/deploy/test_tailnet_only_drill.py::test_drill_tailnet_name_is_unique_per_run`.
- Gate proof 2026-11-18: run 44312318219 (head db163ad) green, smoke passed, teardown and tailnet node removal succeeded.
- Follow-up 2026-11-18 (T-D139-FIX): `rollback.yml env=drill` set `drill_run_id` to its own run id and renamed the live drill host (44356288331 to 44360554182; Caddy lost its certificate). Fixed: re-applies on an existing drill reuse the id from state (`terraform output drill_run_id`), with an optional `drill_run_id` rollback input as repair override; fails if none. Tests: `tests/unit/deploy/test_drill_run_id.py`. Proof 2026-11-18 (DRILL-2): repair run 44362948854, rollback run 44364434084 (no target, no id: log `state: 44356288331`) and roll-forward run 44365282708 all kept `budget-planner-drill-44356288331`.

### T-D143 [S] Boot the VM from local SSD, not Block Storage → ADR-0118, ADR-0032
- Found 2026-11-18 (prod billing): a "Block Storage Volume" line (~€0.78/mo) next to the Flex IPv4. `scaleway_instance_server.app` has no `root_volume`, so the provider default (SBS) applies; ADR-0032 assumed the included 10 GB local SSD. Catalog check: `STARDUST1-S` and `DEV1-S` in `pl-waw-2` accept `l_ssd` (max 10 GB for Stardust).
- Change: `root_volume { volume_type = "l_ssd", size_in_gb = 10 }` in `terraform/modules/compute/main.tf`; expose the root volume type/size as module outputs.
- Tests: `terraform/tests/render.tftest.hcl` asserts `l_ssd` and 10 GB for prod and drill.
- Blocked for prod on T-D156 (ADR-0127); the drill gate can run first.
- Proof: drill gate green (boot from `l_ssd`, smoke passes); then prod release with operator approval (VM replaced, IPs kept, DB restored by the compose Litestream restore step); after the next billing day no Block Storage line on prod.

### ✅ T-D144 [M] Alert on stalled Litestream replication → ADR-0119, ADR-0114, T-D44
- Found 2026-11-18: the 2026-11-07 to 2026-11-18 stall (T-D136) went unnoticed for 11 days because `/health` and `/ready` do not look at the replica.
- Design (ADR-0119): a `litestream-probe` compose service lists the replica every 5 min (`litestream generations`) and writes `status.json` (newest object time, generation, checked_at; no secrets). The app serves `GET /health/replication`: 200 when the newest object is younger than 26 h (`BUDGET_REPLICATION_MAX_AGE_HOURS`) and the probe is fresh, 503 otherwise. Public, no auth. Delivered through `bp-config` and the compose file: no VM replacement.
- Code: `services/replication_health.py` (pure), `web/routers/health.py`, `config.py` (2 settings), auth / must-change-password exempt sets, `docker-compose.yml.tpl`, `litestream-replication-probe.sh`, `user_data.tf` managed file.
- Tests: `tests/unit/services/test_replication_health.py`, `tests/integration/web/test_health_replication.py`, `tests/unit/deploy/test_replication_probe.py`.
- Runbook: `restore.md` "Replication stall: detect and recover"; `disaster-recovery.md` uptime section points at the new monitor.
- DRILL-2 2026-11-18 (explore drill 44356288331): `/health/replication` returned 200 `status: ok` on the real S3 replica (generation `6ce9a8950d6d4780`, age 126 s) and still 200 after every rollback. Prod verify and the second monitor are done (dated line below).
- 2026-11-18 (closeout): released to prod in v3.0.3 (release run 44369978294, apply 1 change / 0 destroy; running `ghcr.io/mtkublin/budget-planner:v3.0.3@sha256:bef6512523df4c67727a5d443b01baf3384ad1d1793bad81e5ca5a9e563f4864`; `/ready` 200). Prod `GET https://budget.rising-dough.eu/health/replication` returns 200 `{"status":"ok"}`, generation `2901fbd3873a6696`; 40/40 GET samples returned 200. The user added the second UptimeRobot monitor as a **Keyword** monitor (keyword `"status":"ok"`, alert when it does not exist, 5 min) instead of the plain status-code monitor. The plain HTTP(S) monitor failed because the free plan probes with HEAD and the route returned 405. T-D146 fixes that, and it ships in v3.0.4.
- Done when: code merged and released (v3.0.3); `curl -fsS https://budget.rising-dough.eu/health/replication` returns 200 `status: ok` on prod (first look at the probe parsing); a stale file in a drill or scratch run returns 503; **user: add a second UptimeRobot monitor on `https://budget.rising-dough.eu/health/replication`, HTTP(s), 5 min, plain status-code monitor (no keyword), up = 2xx, same alert contact as `/health`**, and confirm it is green.

### ✅ T-D145 [S] Audit attribution: domain rows written by non-admin users lack user_id → T-D54, T-D43, ADR-0122
- Found 2026-11-18 on drill 44356288331, audit ids 48-50: account, category and transaction create rows written by a non-admin user carry `user_id=NULL` and `actor_user_id=NULL`. The audit tail treats them as other-user, so it is safe, but attribution is missing.
- Root cause: domain routers and services never pass a `RequestCtx`, so `repositories._shared.mutate` used `RequestCtx.empty()` for every domain write (since T-D14, commit 92d4675, default added "so existing call sites keep working"). It affects every user, including admins, and every `mutate` entity type: account, category, transaction, planned_transaction, recurring_rule, recurring_override, snapshot, budget_default, budget_recurring_override, budget_one_off_override. `fx_rate` is global (no owner) and stays NULL. `users`, auth and session rows were already attributed. Row 46 (users update, `user_id=4`, actor NULL) is the user's own forced password change: the contract leaves `actor_user_id` NULL for self-service `users` rows and `audit_tail` falls back to `user_id`, so it needs no fix.
- Change (ADR-0122): `mutate` and `services.audit.write_audit` take a mandatory `user_id` (row owner, `None` only for ownerless entities); the row gets `user_id = actor_user_id = owner`. Migration `0016_audit_backfill_owner.sql` fills NULL `user_id` from the entity's owner row; `actor_user_id` is not recoverable and stays NULL. `ip`/`session_id`/`user_agent` on domain rows remain NULL (follow-up).
- Tests: `tests/integration/test_audit_attribution.py` (every entity type, audit_tail, backfill), `tests/integration/web/test_audit_attribution_web.py` (non-admin HTTP writes).
- Prod: all domain audit rows since multi-user (v3, migration 0012 / T-D14) have `user_id` NULL; after the release the 0016 migration attributes them (except hard-deleted `recurring_override` rows and `fx_rate`). Applied by the normal release only, never by hand.
- Done when: merged and released; a non-admin write on prod shows `user_id`/`actor_user_id` set in `/debug/audit-tail`.

### ◐ T-D146 [S] `/health`, `/health/replication` and `/ready` answer HEAD like GET → T-D144, ADR-0033, ADR-0119
- Found 2026-11-18 on prod v3.0.3: `HEAD` on all monitored paths returned 405 while `GET` returned 200. The free UptimeRobot plan monitors with HEAD and cannot change the method, so the monitors would report down.
- Change: the three routes use `api_route(..., methods=["GET", "HEAD"])` (precedent: `today.py`). HEAD returns the same status as GET, including 503 on stale replication and on not-ready, with an empty body. Auth, CSRF, must-change-password and cache-control middleware do not filter by GET only, and the app rate limit covers auth routes only (ADR-0072), so no middleware change.
- Tests: `tests/integration/web/test_health.py`, `tests/integration/web/test_health_replication.py` (HEAD status equals GET status, empty body, ok and failing cases).
- 2026-11-18: fix in PR #26 (`fix/T-D146-head-health`, commit 1be10cf). Not on prod yet: the prod release is deferred to v3.0.4, bundled with other agents' fixes (user decision). prod: ships in v3.0.4.
- Done when: merged and released; `curl -sI https://budget.rising-dough.eu/health/replication` returns 200 on prod and UptimeRobot monitors are green.

### T-D147 [S] Auto-satisfy `drill-gate` for PRs that cannot affect the deploy → ADR-0121, ADR-0099, T-D98
- Decision 2026-11-18: a full drill on docs-only PRs is overkill.
- Change: `.github/workflows/drill-gate-skip.yml` (pull_request_target to `main`; `statuses: write`, `contents: read`) and `scripts/ci/drill_gate_skip.py` (allowlist classifier, fail closed). On `skip` it posts `drill-gate` success (`skipped: no deploy-relevant changes (ADR-0121)`); on `gate` it posts nothing.
- Tests: `tests/unit/deploy/test_drill_gate_skip.py` (classifier table, workflow context, permissions, no failure/pending, SHA pins).
- Done when: merged, and a docs-only PR shows `drill-gate` success without a drill run while a `src/` PR still needs the real gate.
- 2026-11-18: first real skip worked on PR #30 (run 44397753231); PR #29 exposed the stale-base-SHA bug; fixed in T-D147-FIX2

### ✅ T-D140 [M] Prod CSP blocks HTMX and inline JS → ADR-0113, ADR-0036
- Problem (prod v3.0.1, 2026-11-18): Caddy sends the ADR-0036 nonce CSP on HTML responses (T-D132), so the browser blocks the htmx CDN script (`unpkg.com`), every inline `<script>` in `base.html` and about ten partials, about 25 inline `onclick=` / `hx-on::` handlers, and the Google Fonts stylesheet. Result: Add (Today, Ledger), Promote (Today) and Override (Plan/Budget) are dead buttons in prod. Dev has no Caddy, so no CSP, so dev works.
- Why it got through: the drill smoke has no browser under the CSP, and e2e runs without Caddy.
- Decision: strict nonce `script-src` stays; vendored htmx, self-hosted fonts, no inline script or handlers, delegated static JS, `style-src 'unsafe-inline'` as a stopgap (ADR-0113). ADR-0036 gets a dated `style-src` addendum.
- Done when: Add, Promote and Override work in prod after a release; the e2e CSP guard (T-D140c) fails on any CSP violation.
- [x] T-D140a: vendor htmx at a pinned 2.x in `static/vendor/`; self-host fonts (`fonts.css`, `font-display: swap`) and drop Google Fonts links; move the `base.html` inline script to static JS; `<meta name="htmx-config">` with `includeIndicatorStyles: false` and `allowEval: false`; Caddy `style-src 'self' 'unsafe-inline'` (no nonce) with a unit test.
- [x] T-D140b: move the inline `<script>` blocks and the `onclick` / `hx-on` handlers in partials to delegated static JS (`data-*` attributes, works for HTMX-swapped content).
- [x] T-D140c: e2e CSP guard. The fixture parses the prod CSP from `terraform/cloud-init/compose/Caddyfile.tpl` (no drift) and fails tests on any browser CSP violation.
- [ ] T-D140d (follow-up, not in this fix): replace `style="..."` attributes (27 templates) with classes, then drop `'unsafe-inline'` from `style-src`. Deferred 2026-11-18 (user decision) to the redesign migration (ADR-0107); tracked in `docs/plans/ui-redesign/`.

### ✅ T-D141 [S] Add transaction from Today never submits → ADR-0113
- Problem: submitting the Add transaction slide-over from `/today` (and `/plan`, `/accounts`, any page except `/ledger`) does nothing. Found by the T-D140c e2e test; pre-existing, not a CSP issue.
- Cause: `partials/transactions/_form.html` posts with `hx-target="#txn-table tbody"` and `afterbegin`. `#txn-table` only exists on `/ledger`; elsewhere htmx raises `htmx:targetError` and sends no POST. The same target also swallowed the 422 re-render (the error form was inserted into the table body, not the slide-over).
- Fix: create form targets itself (`#txn-form`, `outerHTML`), so a 422 re-renders the form in the slide-over on every page. `POST /transactions` success answers `HX-Reswap: none` plus the `ledger-stale` trigger (the ledger table refetches itself, so the row insert was redundant), and `HX-Refresh: true` when the request did not come from `/ledger` (`HX-Current-URL`), so Today's hero, net card and Upcoming reflect the new entry. The overlay closes through the existing `data-reset-on-submit` handler. Chosen over a per-page flag or `HX-Retarget` because it needs no router context and no per-region refresh wiring.
- Done when: e2e submits Add from `/today` under the prod CSP, the overlay closes, the entry shows on Today and on `/ledger`; 422 still re-renders in the slide-over; Add on `/ledger` still shows the new row.
- Not in scope: the planned and recurring forms (`partials/planned/_form.html`, `partials/recurring/_form.html`) have the same table-bound `hx-target` when opened from Today; follow-up T-D142.

### ✅ T-D142 [S] Add planned / recurring from Today never submits → ADR-0113
- Problem: the "+ Planned" and "+ Recurring" buttons on `/today` (also the command palette, shortcuts and the add-entry overlay on any non-ledger page) open a form that submits nothing. Found while fixing T-D141.
- Cause: `partials/planned/_form.html` posts with `hx-target="#planned-table tbody"` and `partials/recurring/_form.html` with `hx-target="table.ledger tbody"` (`afterbegin` / `beforeend`). Those tables exist only on `/ledger` (planned and recurring views) and the legacy list pages; elsewhere htmx raises `htmx:targetError` and sends no POST. A 422 re-render was swallowed by the same target.
- Fix (same pattern as T-D141): the create forms target themselves (`#planned-form` / `#recurring-form`, `outerHTML`), so a 422 re-renders in the slide-over on every page. `POST /planned` and `POST /recurring` success answer `HX-Reswap: none` plus the existing `forecast-stale` / `ledger-stale` triggers (the ledger table refetches itself on `ledger-stale`) via `refresh_unless_on(..., "/ledger")`, which adds `HX-Refresh: true` off `/ledger` so Today's Upcoming reflects the new item. The overlay closes through `data-reset-on-submit`. Edit forms are unchanged.
- Done when: e2e submits "+ Planned" and "+ Recurring" from `/today` under the prod CSP, the overlay closes, the planned item shows on Today (Upcoming) and in the ledger planned view, the rule shows in the ledger recurring view; a 422 re-renders in the slide-over.

### ✅ T-D152 [S] Ledger drops filters on refetch, row actions, pagination and search → ADR-0113
- Problem: with a ledger filter set (category, dates, account, direction, search), any `ledger-stale` refetch (add, edit, delete, promote), Older/Newer pagination and the search box reload the table without the other filters while the filter inputs still show them. Found by a browser audit; pre-existing.
- Cause: `ledger/_table.html` had `hx-include="form.filter-chips"` but the filter form has class `rd-chips rd-ledger-chips`, so nothing matched (htmx logged `hx-include returned no matches` on every request from inside `#ledger-table`). The search input's own GET sent only `q` because an input inside a form does not include the form.
- Fix: the filter form gets a stable `id="ledger-filters"`. The table root includes `#ledger-filters` for its own `ledger-stale` refetch and sets `hx-disinherit="hx-include"` so row actions (POST/DELETE, modal GETs) do not receive filter params; the pagination buttons and the search input carry `hx-include="#ledger-filters"` explicitly.
- Done when: e2e (`tests/e2e/test_ledger_filters.py`, prod CSP) shows filters kept after a refetch, with search, and across pagination, and no `hx-include returned no matches` console warning.

### ✅ T-D150 [S] Create account / category never submits; e2e guard for htmx target errors → ADR-0113
- Problem: on a drill the user opened "+ New account" and "+ New category", clicked Create, and nothing happened. Pre-existing on main, not a CSP issue.
- Cause: `partials/accounts/_form.html` posts with `hx-target="#accounts-grid"` (`beforeend`); no template defines `#accounts-grid` (the list is a table), so htmx raises `htmx:targetError` on every page and sends no POST. `partials/categories/_form.html` posts with `hx-target="table.ledger tbody"`; the only page that hosts the form is `/settings?tab=categories` (`/categories` redirects there; `categories/index.html` is dead), which has no `table.ledger` on that tab, so the same error. The category form also lacked `data-reset-on-submit`, so the slide-over would not have closed. A 422 re-render was swallowed by the same targets.
- Fix (same pattern as T-D141 / T-D142): create forms target themselves (`#account-form` / `#category-form`, `outerHTML`), so a 422 re-renders in the slide-over. `POST /accounts` and `POST /categories` success answer `HX-Reswap: none` plus their existing triggers and `HX-Refresh: true` (neither list page refetches on a trigger, so a reload is the only way the new item appears). The category form gains `data-reset-on-submit`. Edit forms are unchanged.
- Guard: the e2e `page` fixture (T-D140c) also records `htmx:targetError` events (target selector, triggering element) and fails the test at teardown. `htmx:sendError` / `htmx:responseError` are left out if they are noisy for the deliberate 422/429 swaps.
- Done when: e2e creates an account from `/accounts` and a category from `/settings`, both appear after create; a 422 re-renders in the slide-over; the whole e2e suite passes under the new guard.

### ✅ T-D154 [S] Command palette "New transaction" / "Keyboard shortcuts" dead; promote toast never offers Undo → ADR-0113
- Problem: found by a browser audit under the prod CSP, pre-existing on main. (A) Cmd/Ctrl+K then "New transaction" or "Shortcuts cheatsheet" closes the palette and nothing opens. (B) After "Promote all due" on `/today` the toast has no Undo button and is always styled as info.
- Cause: (A) `palette.js` dispatches a `palette:action` event that nothing listens to. (B) the toast handler in `static/js/app-init.js` reads `kind` and `undo_href`, but the server (`routers/planned.py`, `routers/recurring.py`, `routers/categories.py`) sends `variant`, `undo_url` and `undo_payload`; the payload was never posted either (the undo endpoints read CSV form fields `promoted_txn_ids` / `promoted_planned_ids` / `advanced_rule_ids`).
- Fix: (A) `palette.js` handles `new` by loading `/add?when=happened` into `#modal-root` via `htmx.ajax` (works on every page, no dependency on the top-bar button) and `shortcuts` by opening `#shortcuts-dialog`. (B) the toast handler reads `variant` / `undo_url` / `undo_payload`, renders the message as text, and POSTs the payload (arrays joined as CSV) to `undo_url` with `htmx.ajax` (CSRF header comes from `htmx-csrf.js`). (C) drop the dead `[data-fab]` branch in `shortcuts.js`.
- Done when: e2e under the prod CSP: palette opens the Add slide-over on `/today` and `/ledger` and the shortcuts dialog; "Promote all due" shows a success-styled toast with Undo and Undo puts the item back in Upcoming and removes it from the ledger; integration test proves the planned undo restores `promoted_to_txn_id`.
- Not in scope: `rising-dough.js` and `shortcuts.js` both bind `n` / `?` / `g` chords (duplicate handlers); reported separately.

### ✅ T-D151 [M] Edit / override / promote forms depend on ledger row ids; panels stay open; override errors invisible → ADR-0113
- Problem (browser audit under the prod CSP, pre-existing): Today → Upcoming → Override opens a form whose Save does nothing (`htmx:targetError target=#recurring-17`). After a successful edit or promote the slide-over stays open. A recurring override 422 replaces the whole ledger row with bare text.
- Cause: the edit / override / promote forms target ledger row ids (`#txn-{id}`, `#planned-p-{id}`, `#recurring-{id}`), which exist only on `/ledger`; Today rows are `upcoming-planned-{id}` / `upcoming-recurring-{id}`. Edit forms lack a close hook, promote modals have none. `POST /recurring/{id}/overrides` answers `Response(422, text)` and `app-init.js` force-swaps 422s into the form target.
- Fix (same pattern as T-D141 / T-D142): forms target themselves (`#txn-form`, `#planned-form`, `#recurring-form` with `outerHTML`; promote and override modals target `closest .slide-over-root`), so a 422 re-renders in place on every page. Update / promote / override success answers `HX-Reswap: none` plus the existing triggers via `refresh_unless_on(..., "/ledger")` (the ledger table refetches on `ledger-stale`; off-ledger the page reloads). The overlay closes through `data-close-overlay-on-success`. The planned promote modal moves to the slide-over shell. Override validation errors re-render the override form with `errors`, keeping the entered year / month / amount.
- Done when: e2e under the prod CSP (`tests/e2e/test_edit_paths.py`): Today Override (recurring and planned) saves and closes; ledger txn edit closes and the row shows the new value; ledger planned promote closes; an invalid override month shows the error inside the panel and the ledger row stays.

### ✅ T-D153 [S] Planned entry with the same source and destination account returns 500 → ADR-0113
- Problem: submitting the planned form with Account and Dest account set to the same account answers HTTP 500; the client only gets `htmx:responseError` and the user sees nothing. Found by a browser audit; pre-existing on main. The same hole exists for transactions (transit with `dest == account`, and editing a row onto its own stored destination).
- Cause: `planned_transactions` and `transactions` carry `CHECK (account_id <> dest_account_id OR dest_account_id IS NULL)`, but `POST /planned`, `POST /planned/{id}` and the transaction create / update routes only check that the destination exists, so SQLite raises `IntegrityError`. (`recurring_rules` has no such CHECK; no change there.)
- Fix: a pure rule `services.account_pair.validate_distinct_accounts(account_id, dest_account_id)` returns an error message (or `None`); the routers call it with the other field validation and re-render the form with `errors["dest_account_id"]` and 422, nothing written. Update paths check against the submitted destination, falling back to the stored one when the field is empty (editing the source onto the stored destination).
- Done when: unit tests cover the rule; integration tests show 422, the error text in the re-rendered form and no DB write for create and update (planned and transactions); e2e (`tests/e2e/test_planned_validation.py`, prod CSP) shows the error inside the open slide-over on `/today`.

### ✅ T-D155 [S] Budget override tier toggle stuck on "This month only" on /plan/year → ADR-0113
- Problem: in the Override form opened from a /plan Year cell, clicking "Every <Mon>" or "New default" checks the hidden radio but the segmented control keeps "This month only" highlighted and the hint text never changes. Found on an explore drill.
- Cause: T-D140 moved the inline tier-sync script into `static/js/budget-override.js`, but that file was loaded only by a `<script>` at the bottom of `plan/_budget_tab.html`. The Year cell popover (`new_override_form`, inline and modal variants) never loaded it.
- Fix: `budget-override.js` is loaded from `base.html` (`defer`, `?v=t155`) and removed from the budget tab. Its slot / opener handlers are scoped to `[data-override-*]`. The inline-save refetch of `#plan-budget` now runs only when that region exists; on the Year tab the page reloads so the saved cell shows. Audit of other partial-only scripts: `passkeys.js` (auth layout + security settings) and `users-admin.js` (users list) are loaded by the only pages that use them; no others.
- Done when: e2e (`tests/e2e/test_override_tier_toggle.py`, prod CSP) shows the active chip and hint change on the Year popover and the Budget tab inline form, and a recurring override saved from the Year popover appears in the cell.

### T-D156 [M] Make a prod VM replacement safe unattended → ADR-0127, ADR-0071, ADR-0094, ADR-0111
- Found 2026-11-18 (T-D143 review): a replacing prod apply would boot with a used, expired single-use Tailscale key (no SSH); a wrong or empty replica gives a silent empty DB (`-if-replica-exists`); nothing proves the data came back; the last writes before destroy are unproven; the 600 s release wait is untimed for a fresh Stardust boot. Cross-checked against `docs/v3-remaining` (2026-11-18): the generation risk is gone (v3.0.2, generation `2901fbd3873a6696`), and the restore itself is proven by run 44330551119 (through `restore-from-prod`, not the compose path). The rest is open on every branch.
- Work items:
  - (a) `local.vm_spec` hash in the `tailscale_tailnet_key.vm` description (forces a new key with every replacement); prod mode for `tailnet-cleanup.yml` (remove offline `budget-planner-prod*` nodes except the new one) after a replacement converges.
  - (b) `allow_empty_db` variable (default false, true on drill); `litestream-restore` fails when the DB is missing, there is no generation and the flag is false; writes `/data/restore-report.json`.
  - (c) Host agent publishes `restore` in `bp-deploy-status.json`; `terraform.yml` detects a server replacement from the plan JSON, requires `restore.result == "restored"`, waits 1800 s, and skips the image rollback.
  - (d) `litestream` stop grace 30 s (already set); drill proof of the shutdown flush (write a row, destroy through Terraform, restore, row present). If it fails: `drain` flag in `bp-config` (ADR-0127 §4 fallback).
  - (e) `restore.md` / `deploy.md`: record row counts before and compare after a replacing release.
  - (f) `replace-rehearsal.yml` (ADR-0127 §7): one drill runs the fail-closed check, a seed on a Block Storage root, the `l_ssd` replacement with a writer running, and the verify (restore report, generation, no lost committed rows, integrity, tailnet cleanup + rename). Adds drill-only `drill_root_volume_type` / `drill_allow_empty_db`. Also fixes `mask_plan.py` swallowing the rest of a plan after a heredoc that forces replacement (`EOT # forces replacement`).
- Tests: render tftest (`vm_spec_id` changes with the spec and ends the key description; `allow_empty_db` false on prod, true on drill); unit tests for the restore guard script (`test_litestream_restore_guard.py`), the agent status field and the plan-replacement detection in `host_release.py`.
- Proof: drill gate green; after the merge, a green `replace-rehearsal.yml` run from `main` on the release commit, before the release is cut (covers the flush proof (d) and the empty-bucket refusal); the restore-drill run still green.
- Depends on: `docs/v3-remaining` merged (T-D40-FIX, ADR-0117 workflow layout). Merged into the branch 2026-11-18.
- Progress 2026-11-18: done on `docs/t-d143-l-ssd-root`: (a) Terraform part (key description), (b) guard script + `allow_empty_db` + report, (d) grace already 30 s, (e) runbooks.
- Progress 2026-11-18 (after the merge): (a) prod mode of `tailnet-cleanup.yml` / `scripts/tailnet_drill_cleanup.py --env prod` (offline `tag:prod` `budget-planner-prod[-n]` only, then rename the online node), called by `release.yml` job `tailnet-cleanup-prod` when `server_replaced`; (c) agent `restore` status field, `host_release.py replaced` + `wait --require-restore`, `terraform.yml` replacement path (1800 s wait, no image rollback, job timeout 50 min). Operator steps done 2026-11-18: `prod-tailnet` environment (no reviewers, `main` + `v*`) and the `budget-planner-prod-cleanup` OAuth client, both secrets set (`github-settings.md` §1, §4). Open: drill proofs (d) and the empty-bucket drill.
- Local proof 2026-11-18 against the real Litestream v0.3.14 (built from source; file replica, age-encrypted): empty replica fails by default and starts `empty` with the flag; a replicated DB is restored after removal (4/4 rows, report `restored` + generation); a rerun keeps the report; a wrong identity (`no identity matched`) and an unreadable replica (`cannot fetch generations`) fail even with the flag. Finding on the way: `litestream generations` stats the DB first and fails when it is missing, so the guard keys on `restore`'s own `no matching backups found` instead.
- Rehearsal 2026-11-19 (run 44504615949, from main 843d267): guard refusal, in-place vs replacement detection, seed and replacement under writes passed (writer committed rows 21..87, then SSH exit 255 as the old host went away). The writer step then failed on a workflow bug: GitHub runs `run:` with `bash -eo pipefail`, and `set -uo pipefail` does not clear `-e`, so the failing pipeline ended the step before the exit-255 check. `verify` was skipped. Fix: the writer step runs with `set +e` (T-D156-FIX, `fix/T-D156-rehearsal-writer`); then re-run the rehearsal.
- Rehearsal 2026-11-19 (run 44513330068, main b99a04b, after the PR #32 writer fix): restore guard, detection, tailnet rename, restore of the seeded generation and convergence passed. The flush check failed: writer committed row 65, new host had 1–64 (1 row lost; the old host vanished without stopping the app). Drain follow-up: T-D157 (ADR-0127 amendment 2026-11-19). T-D143's release stays blocked.

### T-D157 [M] Drain the old host before a replacing apply → ADR-0127 (amendment 2026-11-19), ADR-0111, ADR-0110
- Found 2026-11-19 by `replace-rehearsal.yml` (run 44513330068): a replacement lost the last committed row. Destroying the VM does not stop the app and Litestream cleanly.
- Design (ADR-0127 amendment): when the plan replaces the server, `terraform.yml` sets the `bp-drain` metadata key on the current server (Scaleway API, request id = run id + attempt) and waits for the agent to report `drained`, then applies. On a failed drain, or a failed apply with the old server still there, it deletes the key and fails. The agent stops `app`, waits 30 s with `litestream` running, writes the `drained` marker and publishes `state: "drained"`. With the key gone it re-applies (`compose up`) and clears the marker.
- Work items:
  - (a) `host_release.py replaced` also prints `server_id=<zone>/<uuid>` from the plan's prior state (an output would be missing from state on the first release).
  - (b) `bp_agent.py`: `bp-drain` read (404 = none), drain step, marker, `drained` status, undrain re-apply.
  - (c) `scripts/ci/scw_user_data.py` (set/delete one key, stdlib, no secrets printed) and `host_release.py wait-drained`.
  - (d) `terraform.yml` steps: drain request, wait-drained, undrain on failure (`if: failure()`), for both envs when `replaced == true`.
  - (e) Runbook `deploy.md` (replacing releases, recovering a stuck drain).
- Tests: agent unit tests (drain, repeated run, litestream down → failed, undrain re-apply, 404 = no drain); `scw_user_data.py` (request shape, 404 on delete tolerated, no token in output); `wait-drained`; workflow wiring (drain before apply, only when replaced, undrain on failure, credentials from env).
- Proof: drill gate green on the PR; after the merge, `replace-rehearsal.yml` green from `main` (0 lost rows, writer ends with "app gone").
