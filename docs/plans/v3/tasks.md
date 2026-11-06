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

### ◻ T-D25 [S] First apply on `drill` → T-D21, T-D22, T-D24, T-D63, T-D69
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

### ✅ T-D66 [S] Restore drill always destroys drill env → T-D41
- `restore-drill.yml` runs `terraform destroy` `if: always()` (also after partial apply / cancel), preceded on failure by best-effort evidence capture uploaded as the `restore-drill-evidence` artifact, and followed by a verification step that fails the job loudly if destroy failed. Failure issue text updated. Operator decision 2026-11-06 (cost bound ~EUR 0.01/run). ADR-0034 §5 addendum.

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

### ◐ T-D56 [S] Litestream replica encryption (age) + version alignment → T-D21, T-D23, T-D41a
- **Status: code done; prod-sim + drill acceptance pending (needs Docker / drill env).** Verified: age is absent in Litestream 0.5.x (rejected since v0.5.1), so everything pins `litestream/litestream:0.3.14` (see ADR-0078 §3 addendum).
- One exact Litestream tag for prod + prod-sim (today `0.3` vs `0.5.x`), chosen for verified age support. Replicas encrypted to an operator-held age identity (0600 on host). Cut-over: new generation → restore drill → delete plaintext generations.
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

### ◻ T-D61 [S] Data inventory + "what the operator can see in v3" → T-D54..T-D60
- `runbooks/data-inventory.md`: every location of user data/secrets with protection + retention; honest operator-visibility statement.
- File: `phase-5-data-protection/T-D61-data-inventory-runbook.md`. Reference: ADR-0078 §8.

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
