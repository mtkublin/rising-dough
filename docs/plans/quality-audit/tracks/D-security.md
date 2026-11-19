# Track D: Security (T-Q07)

> Read-only audit at `AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. All `path:line` cites are valid at that SHA. Reviewer stance: OWASP-minded security review. No code, tests, config or infra were changed; every experiment ran against scratch DBs under `/tmp` (never `data/budget.sqlite`) on `127.0.0.1` through an in-process `TestClient`. Repro scripts and their recorded output sit in `docs/plans/quality-audit/repro/D/`.

## Critical findings

**None.** No cross-user data exposure, no authentication bypass and no committed secret was found. The closest item is **D-01 (High)**: any signed-in user can clear user 1's income-anchor preference (a cross-user *write*, no read). It is rated High because it needs a second active user in prod and changes a setting, not data. **If prod has more than one active user, treat D-01 as Critical** under the rubric's "wrong money shown today" wording, because the anchor drives the fiscal-month window of user 1's budget (`services/budget.py:421`).

## Summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | none |
| High | 1 | D-01 |
| Medium | 2 | D-02, D-06 |
| Low | 10 | D-03, D-04, D-05, D-07, D-08, D-09, D-10, D-11, D-12, D-13 |

Route authorisation: 113 API routes plus the `/static` mount were enumerated from the live app. **No IDOR was found.** All 43 routes with a path id return 404 (or a harmless silent no-op on two idempotent deletes) for a foreign id, every foreign-key id in a form is validated against the caller, and the admin surface is 404 for non-admins. The one scoping defect is D-01 (a hard-coded user id, not a missing filter).

## 1. Coverage statement

**Read in full or in the relevant part:** `web/app.py`, all of `web/middleware/` (auth, csrf, security_headers, cache_control, admin, must_change_password, request_id by header only), `web/auth_cookies.py`, `web/deps.py`, `web/errors.py`, `web/templating.py`, `logging.py`, `config.py` (security fields), `web/routers/` (auth.py, settings_users.py, settings_password.py, budget.py, health.py, debug.py, plus the batch-undo handlers in planned.py and recurring.py, the create/update handlers in transactions.py, and the handler signatures and user-scoping call sites of every other router via an AST table), `services/auth.py` (password login), `services/rate_limit.py`, `repositories/sessions.py` (create), `repositories/transactions.py` (dynamic SQL), the `|safe` / `Markup` / `tojson` / `hx-*` / inline-script surface of all 110 templates, `deploy/Caddyfile`, `terraform/cloud-init/{bootstrap.yaml.tpl, compose/*.tpl}`, `terraform/modules/{compute,storage,bucket_policy}`, `Dockerfile`, `.github/workflows/security.yml`, `drill-gate-skip.yml` and every `uses:` line in `.github/`, `.security-allowlist.yml`, `.secrets.baseline`, the committed `terraform/bootstrap/terraform.tfstate` and `deploy/*.key`.

**Checklist items applied (plan §3 Track D):** authN/authZ and IDOR (runtime), admin guard, sessions and passkeys, CSRF, headers and caching, input validation, XSS, SQL injection, secrets and logging, supply chain, Terraform / cloud-init.

**Dynamic evidence:**
- `repro/D/idor_matrix.py`: 3 users (admin, victim V, attacker A), 61 requests per mode, four modes (control, attack with V's path ids, FK injection with V's ids in form fields, admin on V's ids), each on a fresh DB copy. 244 requests in total. Output: `repro/D/idor_matrix_output.txt`.
- `repro/D/probe_headers_validation.py`: headers on every response class, about 35 malformed-input probes, session lifecycle. Output: `repro/D/probe_output.txt`.
- `repro/D/income_anchor_cross_user.py` (D-01), `repro/D/csrf_nonascii.py` (D-02), `repro/D/sql_fstring_audit.py` (SQLi), `repro/D/enumerate_routes.py` and `repro/D/route_table.py` (route inventory).

**Not done or only partly done (stated, not hidden):**
- No request was sent to any remote host, prod or drill. Caddy, ufw, Tailscale ACLs, Scaleway security groups and the bucket policy were reviewed as config only. Anything that depends on real proxy behaviour is a Question for H4.
- The WebAuthn ceremony itself (`py_webauthn` verification, sign-count branch) was read at design level (ADR-0067) but not exercised: no authenticator is available in an in-process test. Challenge reuse is analysed from `auth_cookies.py` and listed as a Question for H3.
- Services other than `auth`, `rate_limit`, `audit_tail` and the repository SQL were not read line by line. Scoping there was verified behaviourally by the matrix, not by reading every query. The static `tests/architecture/test_user_id_filter*.py` guard was used as a starting point only (it parses repository SQL, so it cannot see D-01, which lives in a router).
- Terraform IAM, CI secrets and environment scoping belong to H1 and H4; only the plan's named items (ufw, Tailscale, Litestream encryption, bucket policy, pinned actions) were checked here.
- Semgrep parsed 35 HTML/JS files only partially (baseline README), so the manual template review in §3.5 carries the XSS conclusion.
- `data/demo.sqlite` (tracked in git) was not opened. Whether it contains real password hashes or real-looking data is a Question.

## 2. Route-by-route authorisation and IDOR table

Source: `repro/D/enumerate_routes.py` (118 entries incl. `/static` mount and FastAPI built-ins) and `repro/D/route_table.py` (handler, path params, dependencies, first line where the caller id reaches a repository or service). "Auth" = behind `AuthRequiredMiddleware` (`web/middleware/auth.py:49-58` defines the only exemptions: `/health`, `/ready`, `/healthz`, `/health/replication`, `/auth/login`, `/auth/login/begin`, `/auth/login/finish`, and `/static/*`). "Admin / extras" shows the admin guard, step-up re-auth (`require_recent_auth`, `web/deps.py:153`) and rate limits. "Scoping" is the first `path:line` in the handler where `user_id` is passed down. "Runtime" results come from `idor_matrix.py`. Every route taking a record id was replayed with another user's id.

**Allowlist check:** there is no route reachable without a session other than the seven exempt paths above, and none of the 113 routes has an unexpected `Depends` gap: every non-exempt, non-redirect route either uses `current_user_id` / `current_user` / `current_admin` or is a static redirect. `/healthz` appears in the exempt sets but has no route (404, harmless leftover).

| Method | Path | Handler | Auth | Admin / extras | Record-id params | Scoping | Verdict |
|---|---|---|---|---|---|---|---|
| GET | `/` | `today.py:35` | yes | no | - | - | OK: static redirect, no data |
| GET | `/accounts` | `accounts.py:122` | yes | no | - | `accounts.py:129` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| POST | `/accounts` | `accounts.py:185` | yes | no | - | `accounts.py:225` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| GET | `/accounts/last-checked` | `accounts.py:133` | yes | no | - | `accounts.py:144` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/accounts/new` | `accounts.py:152` | yes | no | - | - | OK: no record id; acts on session user |
| POST | `/accounts/{account_id}` | `accounts.py:278` | yes | no | account_id | `accounts.py:290` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/accounts/{account_id}/delete` | `accounts.py:348` | yes | no | account_id | `accounts.py:354` | OK: foreign id gives 200 silent no-op, owner data unchanged (runtime) |
| GET | `/accounts/{account_id}/edit` | `accounts.py:250` | yes | no | account_id | `accounts.py:257` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/accounts/{account_id}/reconcile` | `accounts.py:410` | yes | no | account_id | `accounts.py:417` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/accounts/{account_id}/reconcile` | `accounts.py:444` | yes | no | account_id | `accounts.py:455` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/accounts/{account_id}/snapshot` | `accounts.py:366` | yes | no | account_id | `accounts.py:373` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/add` | `today.py:196` | yes | no | - | `today.py:210` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/afford` | `today.py:175` | yes | no | - | `today.py:183` | OK: static redirect, no data |
| GET | `/analytics` | `analytics.py:22` | yes | no | - | - | OK: static redirect, no data |
| GET | `/auth/login` | `auth.py:332` | no | no | - | - | public by design |
| POST | `/auth/login` | `auth.py:343` | no | no + rate-limit | - | - | public by design |
| POST | `/auth/login/begin` | `auth.py:380` | no | no | - | - | public by design |
| POST | `/auth/login/finish` | `auth.py:391` | no | no + rate-limit | - | - | public by design |
| POST | `/auth/logout` | `auth.py:442` | yes | no | - | - | OK: no record id; acts on session user |
| POST | `/auth/passkeys/{credential_id}/revoke` | `auth.py:582` | yes | no + step-up | credential_id | `auth.py:590` | OK: scoped to caller; foreign id gives 404 (runtime) |
| GET | `/auth/reauth` | `auth.py:657` | yes | no | - | - | OK: no record id; acts on session user |
| POST | `/auth/reauth` | `auth.py:668` | yes | no + rate-limit | - | `auth.py:695` | OK: no record id; acts on session user |
| POST | `/auth/reauth/begin` | `auth.py:712` | yes | no | - | `auth.py:722` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| POST | `/auth/reauth/finish` | `auth.py:728` | yes | no + rate-limit | - | `auth.py:742` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| GET | `/auth/register` | `auth.py:465` | yes | no | - | - | OK: static redirect, no data |
| POST | `/auth/register/begin` | `auth.py:471` | yes | no + step-up | - | `auth.py:482` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| POST | `/auth/register/finish` | `auth.py:493` | yes | no + step-up + rate-limit | - | `auth.py:506` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| GET | `/auth/sessions` | `auth.py:549` | yes | no | - | - | OK: static redirect, no data |
| POST | `/auth/sessions/{handle}/revoke` | `auth.py:555` | yes | no | handle | `auth.py:572` | OK: scoped to caller; foreign id gives 404 (runtime) |
| GET | `/budget` | `budget.py:296` | yes | no | - | `budget.py:303` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/budget-legacy` | `plan.py:284` | yes | no | - | - | OK: static redirect, no data |
| POST | `/budget/defaults/{category_id}` | `budget.py:326` | yes | no | category_id | `budget.py:334` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/budget/manage` | `budget.py:306` | yes | no | - | - | OK: static redirect, no data |
| POST | `/budget/one-off/{category_id}/{year}/{month}` | `budget.py:402` | yes | no | category_id,year,month | `budget.py:412` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/budget/preferences/income-anchor` | `budget.py:375` | yes | no | - | `budget.py:387,394` (literal `1`) | **FAIL (D-01)**: writes user 1 regardless of caller |
| POST | `/budget/recurring/{category_id}/{month}` | `budget.py:347` | yes | no | category_id,month | `budget.py:356` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/budget/rules/{category_id}/overrides` | `budget.py:234` | yes | no | category_id | `budget.py:246` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/budget/rules/{category_id}/overrides/new` | `budget.py:169` | yes | no | category_id | `budget.py:182` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/budget/yearly` | `budget.py:143` | yes | no | - | `budget.py:158` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/categories` | `categories.py:22` | yes | no | - | - | OK: static redirect, no data |
| POST | `/categories` | `categories.py:78` | yes | no | - | `categories.py:109` | OK: static redirect, no data |
| GET | `/categories/new` | `categories.py:33` | yes | no | - | - | OK: no record id; acts on session user |
| POST | `/categories/{category_id}` | `categories.py:149` | yes | no | category_id | `categories.py:159` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/categories/{category_id}/archive` | `categories.py:240` | yes | no | category_id | `categories.py:247` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/categories/{category_id}/delete` | `categories.py:200` | yes | no | category_id | `categories.py:206` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/categories/{category_id}/edit` | `categories.py:121` | yes | no | category_id | `categories.py:128` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/categories/{category_id}/restore` | `categories.py:264` | yes | no | category_id | `categories.py:271` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/debug/audit-tail` | `debug.py:23` | yes | yes | - | `debug.py:30` | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| GET | `/dev/components` | `dev_components.py:20` | yes | no | - | - | OK: no record id; acts on session user |
| GET | `/forecast` | `forecast.py:64` | yes | no | - | `forecast.py:72` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/forecast/view` | `forecast.py:83` | yes | no | - | `forecast.py:91` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/health` | `health.py:34` | no | no | - | - | public by design |
| GET | `/health/replication` | `health.py:82` | no | no | - | - | public by design |
| GET | `/ledger` | `ledger.py:394` | yes | no | - | `ledger.py:403` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/ledger/recently-deleted` | `ledger.py:451` | yes | no | - | `ledger.py:461` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/ledger/table` | `ledger.py:440` | yes | no | - | `ledger.py:448` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/plan` | `plan.py:67` | yes | no | - | `plan.py:80` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/plan/analytics` | `plan.py:254` | yes | no | - | `plan.py:273` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/planned` | `planned.py:55` | yes | no | - | - | OK: static redirect, no data |
| POST | `/planned` | `planned.py:219` | yes | no | - | `planned.py:235` | OK: static redirect, no data |
| POST | `/planned/batch/promote-due` | `planned.py:75` | yes | no | - | `planned.py:82` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| POST | `/planned/batch/undo` | `planned.py:111` | yes | no | - | `planned.py:135` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| GET | `/planned/export` | `planned.py:547` | yes | no | - | `planned.py:555` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/planned/new` | `planned.py:189` | yes | no | - | `planned.py:203` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/planned/table` | `planned.py:174` | yes | no | - | `planned.py:186` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| POST | `/planned/{planned_id}` | `planned.py:337` | yes | no | planned_id | `planned.py:350` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/planned/{planned_id}/delete` | `planned.py:404` | yes | no | planned_id | `planned.py:410` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/planned/{planned_id}/edit` | `planned.py:304` | yes | no | planned_id | `planned.py:311` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/planned/{planned_id}/promote` | `planned.py:435` | yes | no | planned_id | `planned.py:442` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/planned/{planned_id}/promote` | `planned.py:483` | yes | no | planned_id | `planned.py:493` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/planned/{planned_id}/promote/inline` | `planned.py:461` | yes | no | planned_id | `planned.py:469` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/planned/{planned_id}/restore` | `planned.py:419` | yes | no | planned_id | `planned.py:427` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/ready` | `health.py:40` | no | no | - | - | public by design (see D-05) |
| GET | `/recurring` | `recurring.py:58` | yes | no | - | - | OK: static redirect, no data |
| POST | `/recurring` | `recurring.py:268` | yes | no | - | `recurring.py:306` | OK: static redirect, no data |
| POST | `/recurring/batch/promote-due` | `recurring.py:424` | yes | no | - | `recurring.py:437` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| POST | `/recurring/batch/undo` | `recurring.py:469` | yes | no | - | `recurring.py:497` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| POST | `/recurring/formula/preview` | `recurring.py:546` | yes | no | - | `recurring.py:581` | OK: user-scoped; FK ids validated against caller (runtime fk matrix) |
| GET | `/recurring/new` | `recurring.py:119` | yes | no | - | `recurring.py:133` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| POST | `/recurring/{rule_id}` | `recurring.py:632` | yes | no | rule_id | `recurring.py:639` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/recurring/{rule_id}/deactivate` | `recurring.py:752` | yes | no | rule_id | `recurring.py:758` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/recurring/{rule_id}/edit` | `recurring.py:592` | yes | no | rule_id | `recurring.py:599` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/recurring/{rule_id}/overrides` | `recurring.py:809` | yes | no | rule_id | `recurring.py:819` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/recurring/{rule_id}/overrides/new` | `recurring.py:770` | yes | no | rule_id | `recurring.py:782` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/recurring/{rule_id}/overrides/{occurrence_date}/delete` | `recurring.py:870` | yes | no | rule_id,occurrence_date | `recurring.py:878` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/recurring/{rule_id}/promote` | `recurring.py:966` | yes | no | rule_id | `recurring.py:973` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/recurring/{rule_id}/promote` | `recurring.py:1015` | yes | no | rule_id | `recurring.py:1025` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/recurring/{rule_id}/promote/inline` | `recurring.py:976` | yes | no | rule_id | `recurring.py:989` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/recurring/{rule_id}/skip-next` | `recurring.py:1087` | yes | no | rule_id | `recurring.py:1094` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/settings` | `settings.py:51` | yes | no | - | `settings.py:62` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/settings/close` | `settings.py:94` | yes | no | - | - | OK: static redirect, no data |
| GET | `/settings/password` | `settings_password.py:108` | yes | no | - | - | OK: no record id; acts on session user |
| POST | `/settings/password` | `settings_password.py:121` | yes | no + rate-limit | - | `settings_password.py:142` | OK: no record id; acts on session user |
| GET | `/settings/security` | `settings_security.py:63` | yes | no | - | - | OK: no record id; acts on session user |
| GET | `/settings/users` | `settings_users.py:138` | yes | yes | - | - | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| POST | `/settings/users` | `settings_users.py:148` | yes | yes + step-up | - | `settings_users.py:162` | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| POST | `/settings/users/{user_id}` | `settings_users.py:228` | yes | yes + step-up | user_id | `settings_users.py:242` | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| POST | `/settings/users/{user_id}/delete` | `settings_users.py:289` | yes | yes + step-up | user_id | `settings_users.py:299` | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| GET | `/settings/users/{user_id}/edit` | `settings_users.py:213` | yes | yes | user_id | `settings_users.py:222` | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| POST | `/settings/users/{user_id}/reset-password` | `settings_users.py:267` | yes | yes + step-up | user_id | `settings_users.py:281` | OK: admin-only (middleware `admin.py:44-47` + `current_admin`); non-admin gets 404 (runtime) |
| GET | `/today` | `today.py:41` | yes | no | - | `today.py:52` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/today/afford` | `today.py:144` | yes | no | - | `today.py:161` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/today/upcoming` | `today.py:96` | yes | no | - | `today.py:111` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/transactions` | `transactions.py:113` | yes | no | - | - | OK: static redirect, no data |
| POST | `/transactions` | `transactions.py:237` | yes | no | - | `transactions.py:254` | OK: static redirect, no data |
| GET | `/transactions/_limit_preview` | `transactions.py:166` | yes | no | - | `transactions.py:179` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/transactions/export` | `transactions.py:461` | yes | no | - | `transactions.py:469` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/transactions/new` | `transactions.py:200` | yes | no | - | `transactions.py:217` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| GET | `/transactions/table` | `transactions.py:183` | yes | no | - | `transactions.py:197` | OK: user-scoped read; foreign filter ids return nothing (runtime) |
| POST | `/transactions/{txn_id}` | `transactions.py:357` | yes | no | txn_id | `transactions.py:370` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/transactions/{txn_id}/delete` | `transactions.py:437` | yes | no | txn_id | `transactions.py:441` | OK: foreign id gives 200 silent no-op, owner data unchanged (runtime) |
| GET | `/transactions/{txn_id}/edit` | `transactions.py:320` | yes | no | txn_id | `transactions.py:327` | OK: foreign id gives 404, no state change (runtime) |
| POST | `/transactions/{txn_id}/restore` | `transactions.py:447` | yes | no | txn_id | `transactions.py:453` | OK: foreign id gives 404, no state change (runtime) |
| GET | `/docs`, `/docs/oauth2-redirect`, `/openapi.json` | FastAPI built-ins (`web/app.py:168`) | yes | no | - | - | OK for authorisation (anonymous gets 302); exposed to every signed-in user in prod (D-12) |
| GET | `/static/*` | `StaticFiles` mount (`web/app.py:201`) | no (by design) | no | - | - | OK: only `web/static/` (CSS, JS, fonts, vendor htmx); no user data |

**Runtime IDOR summary** (`idor_matrix_output.txt`, 61 requests per mode):
- `control` (V on V's own records): 51 x 200, 3 x 204, 2 x 303, 5 x 404. The five 404s are my own seed gaps (restoring a category that was not deleted) plus the four admin routes where V is not an admin. All other payloads were valid, so the attack results below are meaningful.
- `attackA` (A, V's ids in the path): every route with a record id answered 404, except `POST /transactions/{id}/delete` and `POST /accounts/{id}/delete` (200, silent no-op: the repository `soft_delete(conn, user_id, id)` matches nothing, `transactions.py:441`, `accounts.py:354`) and the two `batch/undo` POSTs (204, nothing changed). V's rows, V's sessions and V's passkeys were byte-identical before and after (SHA-1 per table). No V sentinel string appeared in any response body.
- `fk` (A, own path id, V's account / category / destination ids in the form): rejected with 422 on every create and update route (transactions, planned, recurring, reconcile, budget overrides, formula preview). The cross-reference probe found zero attacker-owned rows pointing at V-owned accounts or categories.
- `admin` (admin session, V's ids): V's data routes behave exactly like for any other non-owner (404 or no-op, no read). `/settings/users/{V}` edit, save, reset-password and delete work as designed (admin power, see "Accepted risks").
- Read-side filters (`?account_id=<V's>`) on `/ledger`, `/ledger/table`, `/transactions/export`, `/planned/export`, `/forecast/view`, `/today/afford`, `/transactions/_limit_preview`, `/accounts/last-checked`: 200 with empty or own data, no V value in the body (`income_anchor_output.txt`).

## 3. Checks done and results

### 3.1 Sessions, passkeys, rate limiting (ADR-0033, 0067, 0076)

| Check | Result | Evidence |
|---|---|---|
| Session id entropy and storage | 256-bit `secrets.token_urlsafe(32)`; DB stores `sha256(token)` (ADR-0076 §3), audit rows carry only a 16-hex handle | `repositories/sessions.py:124-135` |
| Fixation | Pass. The server never accepts a client-chosen session id; every login issues a new token and revokes the one the browser presented | `routers/auth.py:249-260` (`_start_session`) |
| Rotation on re-auth and password change | Pass (new token on `complete_reauth`; `change_password` sets a rotated cookie and revokes other sessions) | `routers/auth.py:632-650`, `settings_password.py:160-166` |
| Rotation on privilege change | Pass by construction: `is_admin` and `must_change_password` are re-read from the DB on every request (`AuthRequiredMiddleware._resolve`), so a demotion applies at once. Reset-password and delete revoke the target's sessions (matrix: `sessions_alive` changed) | `middleware/auth.py:97-110` |
| Logout invalidation | Pass. `POST /auth/logout` revokes server-side, expires the cookie and sends `Clear-Site-Data: "cache", "storage"`. Replaying the old token afterwards gives 302 to login | `probe_output.txt` ("GET /today with revoked token -> 302") |
| Cookie flags | Session: `HttpOnly`, `Secure`, `SameSite=Lax`, `__Host-` prefix (non-dev). Challenge cookie: `SameSite=Strict`, HttpOnly, 300 s. CSRF cookie: not HttpOnly by design | `auth_cookies.py:84-131`, `csrf.py:104-121` |
| Open redirect via `next` | Pass. `safe_next` rejects `//`, `/\`, control characters, schemes, netlocs and the login path; used by login, reauth, passkey finish, must-change-password | `auth_cookies.py:218-231` |
| Passkey challenge | Stateless HMAC-SHA256 envelope (purpose, user id, challenge, timestamp), 300 s TTL, purpose and user bound, cleared after every `finish`. Not single-use on the server (see Question H3-1) | `auth_cookies.py:150-205` |
| User enumeration | Pass. Unknown email and wrong password give the same generic 401 page, with a dummy bcrypt verify to equalise timing | `services/auth.py:219-237` |
| Rate limiting on `/auth/*` | Present on password login (5/min and 20/h per IP+email, 100/h per IP), passkey login finish (10/min, 60/h per IP), register finish, reauth and password change (per user). Not on `*/begin` (cheap, no secret check). Gaps: D-06 | `routers/auth.py:116-200`, `config.py:90-103` |
| Step-up | `require_recent_auth` guards user admin POSTs, passkey revoke, passkey register and revoking *other* sessions | `routers/settings_users.py:148,228,267,289`, `auth.py:557-575` |

### 3.2 CSRF

Double-submit token (`middleware/csrf.py`): cookie minted for any request without one, POST/PUT/PATCH/DELETE must carry the same value in `X-CSRF-Token` or `_csrf_token`; only `/health`, `/ready`, `/healthz` are exempt. HTMX gets the token from `<meta name="csrf-token">` through `static/htmx-csrf.js`. All 113 routes were enumerated: every state-changing route is POST (no state-changing GET found; `/accounts/last-checked`, `/settings/close` and the `promote` GET forms are read-only). Runtime: POST without token gives 403 `missing_cookie` / `invalid_csrf` for anonymous and signed-in callers; a JSON body with only the header is accepted (`probe_output.txt`). Observations: the token is not bound to the session (acceptable given the `__Host-` prefix, which blocks cookie tossing from sibling subdomains); a non-ASCII `_csrf_token` crashes `secrets.compare_digest` (`csrf.py:175`), giving an unauthenticated 500 (D-02). Middleware order puts CSRF innermost, so anonymous POSTs to protected routes get the login redirect and non-admin POSTs to `/settings/users*` get 404 before any 403, as ADR-0073 intends.

### 3.3 CSP, security headers, Cache-Control (ADR-0036, ADR-0078 §2)

Header matrix from `probe_output.txt` (in-process app, no Caddy):

| Response class | HSTS, XFO, nosniff, Referrer, Permissions | CSP | `Cache-Control: no-store` |
|---|---|---|---|
| 200 / 302 / 403 / 404 / 422, signed in | yes | **no** (Caddy only) | yes |
| 200 / 302 / 401 / 403, anonymous (login page, redirects, `/health`) | yes | no | no (by ADR-0078 §2) |
| `/static/*` | yes | no | no (by design) |
| **500 from an unhandled exception, signed in** | **no** | no | **no** |

CSP is emitted only by Caddy, only for `text/html` upstream responses (`Caddyfile.tpl:49-54`): `default-src 'self'; script-src 'self' 'nonce-...'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; ...; frame-ancestors 'none'; object-src 'none'; form-action 'self'`. The templates contain no inline script and no inline handler (`grep` for `<script` finds only `src=` tags; htmx runs with `allowEval: false`, `base.html:6-7`), so the policy is strong where it applies. Findings: D-03 (error responses), D-08 (CSP edge-only, vestigial nonce, `unsafe-inline` styles, trusted client nonce header).

### 3.4 Input validation (422 versus 500)

35 malformed inputs (`probe_output.txt`). Good: bad dates, NaN, Infinity, negative amounts, junk enums, junk colours, junk currencies, `-1` ids and non-numeric path ids all give 422 or 404. Failures (500): D-02. Accepted without limit: D-04.

### 3.5 XSS

Jinja `autoescape=select_autoescape(["html","jinja2"])` (`templating.py:201`) and all 110 templates are `.html`. The only `|safe` uses are `_button.html:8,13` (`attrs`), `_table_row.html:5` (`cell.html`), `_slideover_page.html:28` (an already-rendered fragment). `attrs` and `cell.html` have no caller outside `/dev/components` (grep over `templates/` and `routers/`). `tojson` appears once, in a single-quoted attribute (`partials/transactions/_form.html:20`), which is safe because Jinja's `tojson` escapes `'`, `<`, `>`, `&`. `Markup(...)` is built in three helpers (`templating.py:124,161` plus `routers/transactions.py:414` hit by bandit, which is an unrelated `assert`): user text goes through `escape()` (`templating.py:158`); the category colour goes unescaped into a `style` attribute but is constrained by a DB `CHECK (color GLOB '#[0-9a-f]{6}')` and service validation (probe: `color=javascript:x` gives 422). No `hx-vals`, `hx-on` or `onclick` exists anywhere in the templates. HTMX attributes interpolate only integer ids and the coerced `view` name. Plotly has been replaced by server-side SVG (`web/charts.py`, ADR-0054), so there are no client-side chart labels; SVG text is rendered through autoescape. `CLAUDE.md` still lists Plotly in the stack (doc drift for Track G). Result: no XSS found. Defence-in-depth note: `_direction_badge` (`templating.py:116-125`) puts a non-escaped `label` into `Markup`; safe today because `direction` comes from a CHECK-constrained column or the `Direction` enum.

### 3.6 SQL injection

`repro/D/sql_fstring_audit.py` lists every interpolation inside SQL-looking f-strings under `src/`: 51 sites, equal to bandit's 51 B608. The interpolated expressions are exclusively module constants (`_COLUMNS`, `_RULE_COLUMNS`, `_ONE_OFF_COLS`, ...), a `cols` string built from those constants, an `IN (?,?,...)` placeholder list, a `WHERE deleted_at IS NULL` fragment, a fixed `ASC`/`DESC` chosen from a bool (`repositories/transactions.py:130-131`), and the column list of `UPDATE ... SET {', '.join(sets)}` where `sets` is built from `changes.keys()` of a frozen patch dataclass (`repositories/accounts.py:121-126`, `categories.py:121-124`, `planned.py:202-205`, `recurring.py:323-326`, `transactions.py:215-218`). Values always go through `?` parameters, `LIKE` uses a parameter (`transactions.py:104-105`), and no `ORDER BY` takes request input. **0 exploitable.** Maintainability note: the `SET {fields}` pattern is safe only while patch dataclasses never accept caller-chosen keys; a guard test on `Patch*.as_dict()` keys would pin that. All non-repository SQL (`routers/planned.py:142`, `routers/recurring.py:503`, `services/accounts.py`) uses bound parameters.

### 3.7 Secrets and log redaction (ADR-0078 §5)

- No secret is committed: detect-secrets baseline hits are false positives (see §4); `deploy/litestream-age-DEV-ONLY.key` is a deliberately committed dev-only age identity for the local prod-sim stack (comment states it protects nothing; allowlisted); `terraform/bootstrap/terraform.tfstate` is committed on purpose (ADR-0096 §5) and holds bucket metadata only (I listed resource attribute names: no key, secret, password or token attribute is non-empty).
- Config: production refuses to start without `BUDGET_COOKIE_SECRET` (`config.py:191-207`); the dev fallback is a fixed string, used only outside production.
- Log redaction: structlog processor with a deny-list applied before rendering (`logging.py:25-55,77-90`) and a query-string stripper for uvicorn access logs (`logging.py:58-67`); Caddy strips query strings, Cookie, Authorization and Set-Cookie (`Caddyfile.tpl:60-72`). Gap: D-09 (exception text bypasses the redactor).
- Admin generated passwords are shown once in a `no-store` response (`settings_users.py:81-83,101-112`).
- Initial admin password and cookie secret live in the container environment and in the `bp-config` metadata (`docker-compose.yml.tpl:21,27`); the initial password stays set after first login. Question H4-3.

### 3.8 Supply chain and infrastructure

- **Python deps:** `uv.lock` pins every package with hashes; the image builds with `uv sync --frozen --no-dev` (`Dockerfile:34-38`); `pyproject.toml` uses lower bounds only, which is fine with the lock. CI runs `pip-audit --strict`, trivy fs and trivy image (`.github/workflows/security.yml`), weekly and on PRs. Ad hoc result in §4.
- **GitHub Actions:** all `uses:` references are pinned to a 40-hex SHA with a version comment (grep for non-SHA, non-local refs returned nothing). Only one workflow uses `pull_request_target` (`drill-gate-skip.yml`); it checks out the base branch, takes the file list from the API and passes PR values only through `env` (reviewed; no injection path found). `security.yml` reads `.security-allowlist.yml` from the checked-out PR tree (Question H1-1).
- **Images:** app image is pinned by digest and cosign-verified by the host agent (`terraform/host/agent/bp_agent.py:168-182`). Caddy and Litestream are pulled by mutable tag, the base image `python:3.12-slim-trixie` by tag (D-10).
- **Cloud-init / host:** ufw default-deny incoming; SSH only on `tailscale0`; the Scaleway security group has no inbound 22 and, for the tailnet-only drill, no public web rule (`modules/compute/main.tf:12-45`); unattended security upgrades; Docker `icc:false`, `no-new-privileges`; containers are blocked from the metadata API (`bootstrap.yaml.tpl:185-204`, ADR-0111 §6); the Tailscale auth key is a single-use file on tmpfs, deleted after `tailscale up`. Gaps: D-11, D-06 (fail2ban).
- **Litestream:** replica encrypted client-side with age (recipient in `litestream.yml.tpl:22-30`), identity delivered as a root file; bucket is `private` with an allow-list policy and a 7-day noncurrent-version lifecycle (`modules/storage/main.tf:54-75`). The replicate and probe containers also hold the identity (so a host compromise reads the replica, which ADR-0078 accepts).
- **Terraform scanners:** tflint clean; checkov found no applicable policies (coverage gap, not a clean bill; Trivy config scan in CI is the real check).

## 4. Scanner triage (baseline at `docs/plans/quality-audit/baseline/`)

| Scanner | Raw result | Triage |
|---|---|---|
| bandit `-r src -ll` | 0 High, 53 Medium, 33 Low | **B608 x51 false positives** (module constants, placeholder lists and patch-dataclass keys only; §3.6). **B704 x4**: `templating.py:124,161` safe as analysed (§3.5; hardening note only); the two other hits at `routers/transactions.py:414` and `recurring.py:708,1102` are `assert` (B101), not Markup. **B101 x3**: asserts as type narrowing after validation, not security checks (safe unless run with `-O`; they sit after an `errors` early return). No true positives. |
| pip-audit | 3 advisories, all `cryptography 48.0.1` (PYSEC-2026-3552/3553/3554) | **False positive for prod.** `uv.lock` forks cryptography: 48.0.1 is selected only for `darwin` + `x86_64` (`uv.lock:14,1309`), Linux and the image resolve 50.0.2, which contains the fixes (`pyproject.toml:59-64`). It is a true positive on the operator's own x86_64 Mac (dev only). Existing trivy-fs allowlist entry has a re-audit date of 2027-02-01. No finding. |
| detect-secrets | 8 hits, 4 files | **All false positives**: baseline self-hit, SRI hashes in a mockup JS file, prose in `docs/plans/v3/HANDOFF.md`, the `private` provider blob in `terraform/bootstrap/terraform.tfstate:82` (verified: no secret attribute in that state). The committed age file `deploy/litestream-age-DEV-ONLY.key` is intentional, dev-only, allowlisted (noted, not a finding). |
| semgrep p/python + p/owasp-top-ten | 0 findings | Weak negative (HTML/JS partly unparsed). Manual review in §3.5 replaces it for templates. |
| tflint | clean | No finding. |
| checkov | 0 checks run | Coverage gap (no policies for Scaleway). Not evidence of safety. Manual review in §3.8. |

I re-ran nothing ad hoc: the baseline had landed on `audit/quality` and was merged before triage.

## 5. Findings

Severity per plan §5.1, root cause per §5.2. Cites are valid at `AUDIT_SHA`.

### D-01 | High | Confirmed | scoping-gap | Income-anchor preference always targets user 1

- **Location(s):** `src/budget_planner/web/routers/budget.py:375-399` (handler `set_income_anchor`; literal `1` at lines 387 and 394). Callee: `services/preferences.py:44-58`.
- **Description:** `POST /budget/preferences/income-anchor` takes no `current_user_id` dependency and calls `set_income_anchor_category_id(conn, 1, ...)`. Every signed-in user therefore reads and writes **user 1's** preference, never their own. This violates ADR-0061 / requirements §6.9 ("every user-owned table filtered on `user_id = current_user.id`"). The static guard `tests/architecture/test_user_id_filter*.py` only parses repository SQL, so a literal in a router slips through. Everywhere else the settings drawer reads the preference with the caller's id (`routers/settings.py:76,86`), so a second user sees their own (unset) anchor in the UI while their edits land on user 1.
- **Evidence:** `repro/D/income_anchor_cross_user.py` (recorded in `income_anchor_output.txt`): user 2 posts an empty `category_id`; the preference row of user 1 is deleted (`before: [(1, 'income_anchor_category_id', '3')]`, after: `[]`). Posting user 2's own category returns 422 `category 4 not found or soft-deleted` because it is validated against user 1's categories, so the feature cannot work for any non-first user.
- **Impact:** a second user silently resets the first user's fiscal-month anchor (`services/budget.py:421`: falls back to the calendar month when unset), which changes which transactions the owner's monthly budget summary counts. No data is read, and the change is reversible, but the owner sees wrong monthly totals with no explanation. A non-first user cannot set their own anchor at all. Becomes Critical if prod has more than one active user.
- **Mitigation:** add `user_id: int = Depends(current_user_id)` to the handler and pass it to both service calls; add an integration test with two users (user 2 changes the anchor, user 1's row is untouched, user 2's row is written). Add an architecture test that fails on an integer literal passed as `user_id` anywhere under `web/` and `services/`.
- **Effort:** S. **Related:** ADR-0061, ADR-0025, requirements §6.9, H2.

### D-02 | Medium | Confirmed | security-control | Unvalidated input reaches the server-error handler (500) on many routes

- **Location(s):** every `{id}` path parameter typed plain `int` (43 routes, e.g. `routers/transactions.py:320,357,437,447`), amounts through `to_minor_units` (`domain/money.py:198-207`, "does not clamp the magnitude") at `routers/transactions.py:233`, `planned.py:209`, `accounts.py:182,224,477`, `recurring.py:851,1050`, `budget.py:254,340,364,420`; `routers/budget.py:78-85` (`int(q.get("month"))`), `routers/budget.py:402-424` (year not range-checked, DB `CHECK year BETWEEN 1900 AND 9999` raises `IntegrityError`); `routers/recurring.py:107-125,264-` (`int(v)` on `source_category_ids`); `routers/recurring.py:491-492` and `planned.py:121-122` (id lists beyond int64); `routers/ledger.py:53-68` (`page` beyond int64); `web/middleware/csrf.py:175` (non-ASCII token).
- **Description:** requests the user (or an unauthenticated caller, for the CSRF case) controls produce `OverflowError`, `decimal.InvalidOperation`, `ValueError`, `calendar.IllegalMonthError`, `sqlite3.IntegrityError` or `TypeError`. These are not mapped to 422, so the catch-all `handle_server_error` answers 500 and logs a stack trace per request. No data leaks (the body is the generic page) and no write happens, but input validation at the boundary is the stated rule (common/coding-style) and 500s hide real faults in monitoring.
- **Evidence:** `repro/D/probe_headers_validation.py` -> `probe_output.txt` (500 for `GET /transactions/99999999999999999999/edit`, `POST /transactions amount=1e400` and `amount=9999999999999999999999`, `category_id=99999999999999999999`, `GET /ledger?page=999999999999999999999`, `GET /budget?month=13`, `GET /budget?year=0&month=0`, `POST /budget/one-off/3/99999999/5`, `amount=1e400` on budget and accounts, `POST /budget/defaults/3` with a 20-digit amount, `POST /recurring` with `source_category_ids=abc`, `POST /recurring/batch/undo` with a huge id). `repro/D/csrf_nonascii.py`: anonymous `POST /auth/login` with `_csrf_token=café` gives 500.
- **Impact:** noisy 500s and error logs; a signed-in user can generate unbounded stack-trace log volume; one unauthenticated 500 path exists. Related: amounts have no upper bound, so a stored amount near 2^63 would make later `SUM()` aggregates raise (self-inflicted for that user's own pages).
- **Mitigation:** introduce shared bounded types in `web/` (for example `RecordId = Annotated[int, Path(ge=1, le=2**63 - 1)]`, `Month`, `Year`, `PageNo`) and use them on every route; make `parse_amount_str` (`domain/money.py:210`) reject magnitudes above a named maximum (for example 10^12 major units) and catch `InvalidOperation` from quantize; compare CSRF tokens with `compare_digest` on `.encode()` bytes (`csrf.py:175`). Add one test that loops over `app.routes` with oversized ids and asserts no 5xx.
- **Effort:** M. **Related:** D-03, D-04, Track C.

### D-03 | Low | Confirmed | security-control | 500 responses skip the security-header and no-store middleware

- **Location(s):** `web/errors.py:155-156` (`add_exception_handler(Exception, ...)`), `web/app.py:187-199` (middleware stack).
- **Description:** Starlette runs the catch-all `Exception` handler in `ServerErrorMiddleware`, which wraps the whole stack, so the 500 response never passes `SecurityHeadersMiddleware` or `CacheControlMiddleware`. A signed-in user's 500 page is returned without HSTS, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` and without `Cache-Control: no-store`, contrary to ADR-0078 §2 ("every response served to an authenticated session").
- **Evidence:** `probe_output.txt`: the 500 lines show `missing=[... 'strict-transport-security', 'x-frame-options', ...]` and `cache-control=None`, while 404 and 422 for the same session carry `no-store` and the headers.
- **Impact:** low. In prod Caddy re-adds HSTS, XFO, nosniff, Referrer-Policy and Permissions-Policy to every proxied response and CSP to HTML (`Caddyfile.tpl:20-27,49-54`), so only `no-store` is lost. The 500 body is generic and carries the request id only.
- **Mitigation:** convert the three header concerns into one pure-ASGI middleware registered outermost (outside `ServerErrorMiddleware`'s inner response, i.e. wrap `app` itself in `create_app`), or make `handle_server_error` set the headers explicitly. A route-class-wide regression test: force a 500 and assert all baseline headers.
- **Effort:** S. **Related:** D-02, D-08, ADR-0078 §2.

### D-04 | Low | Confirmed | security-control | No limit on field length, body size or page size

- **Location(s):** `routers/accounts.py:185` (name), `transactions.py:237` (`description`), `routers/ledger.py:68` (`page_size`), `terraform/cloud-init/compose/Caddyfile.tpl:41-58` (no `request_body max_size`), `deploy/Caddyfile`.
- **Description:** a 1 MB account name and a 100,000-character description were accepted (200); `?page_size=999999999` returns every row. Neither Caddy nor the app caps request bodies. All writes are replicated to the object store by Litestream and mirrored into `audit_log` payloads.
- **Evidence:** `probe_output.txt` ("POST /accounts name 1MB -> 200", "description=100k chars -> 200", "GET /ledger?page_size=999999999 -> 200").
- **Impact:** an authenticated user can bloat the single SQLite file, the audit log and the replica, or slow their own pages. There are at most about 10 trusted users, so abuse risk is low.
- **Mitigation:** cap lengths in the service-layer drafts (name <= 120, description <= 500) and clamp `page_size` to a named maximum in `parse_filters`; add `request_body { max_size 256KB }` to the Caddy site block.
- **Effort:** S. **Related:** D-02.

### D-05 | Low | Confirmed | infra-exposure | Unauthenticated `/ready` runs a full `PRAGMA integrity_check` per request and echoes exception text

- **Location(s):** `web/routers/health.py:40-79` (and exemption in `middleware/auth.py:49-58`).
- **Description:** `/ready` is reachable without a session through the public Caddy site and executes `PRAGMA integrity_check` (a full scan, O(database size)) on every call, with no rate limit anywhere on public routes. On failure the 503 body includes the raw exception string (`connect failed: {exc}` can contain the DB path).
- **Evidence:** code citation (a request test would only time a small scratch DB).
- **Impact:** cheap CPU / IO amplification for an unauthenticated caller as the DB grows; minor path disclosure on error. `/health/replication` and `/.well-known/bp-deploy-status.json` are also public by design (ADR-0111, ADR-0119) and disclose the running version and replication freshness.
- **Mitigation:** make `/ready` use a cheap probe (`SELECT 1` plus `PRAGMA quick_check(1)` cached for 30 s) and drop the exception text from the body (log it); keep the full check for the deploy pipeline only if needed behind the status file.
- **Effort:** S. **Related:** D-06, ADR-0111.

### D-06 | Medium | Probable | security-control | Authentication abuse controls are per-IP only; throttled attempts still write to the DB

- **Location(s):** `routers/auth.py:116-143` (`login_rate_limit`), `services/rate_limit.py:120-141` (`audit_throttled`), `services/rate_limit.py:155-166`, `Dockerfile:104-108` (`--proxy-headers --forwarded-allow-ips=*`), `terraform/cloud-init/bootstrap.yaml.tpl:77` (fail2ban installed, no jail), requirements §6.7 line 346.
- **Description:** (a) the password counter key is `ip|email`, so there is no per-account cap: an attacker with many source addresses gets 20 attempts per hour per address against one account (mitigated by the 12-character minimum and bcrypt cost, but the admin account is the prize). (b) After the limit is reached, **every further request still writes** an `audit_log` row (`audit_throttled`, payload includes the attacker-supplied email, unbounded length) and a rate-limit row, on the single SQLite writer. (c) The client address comes from `X-Forwarded-For` with `--forwarded-allow-ips=*`, so the limiter is only as trustworthy as "Caddy is the only peer that can reach port 8000" (compose uses an internal `edge` network and `expose`, so true today; the Litestream containers share that network). (d) Requirements §6.7 promises `fail2ban` jails on `sshd` and `caddy-auth` and ADR-0036 mentions an edge rate limit; the package is installed but no jail and no rate-limit module exist (config drift).
- **Evidence:** code citations only; no flood test was run (rules of engagement).
- **Impact:** credential stuffing against a single account is bounded only by the number of source IPs; an unauthenticated caller can grow `audit_log` and the replica with throttled-attempt rows at wire speed, and contend for the SQLite write lock.
- **Mitigation:** add a per-email global bucket (for example 30 per hour across all IPs, in addition to the existing buckets); write at most one `rate_limited` audit row per bucket per window (or count only); truncate the email in the payload to 254 characters; either add the missing fail2ban jail definition and a Caddy rate-limit layer, or correct requirements §6.7 and ADR-0036.
- **Effort:** M. **Related:** D-05, ADR-0072, ADR-0079, H3.

### D-07 | Low | Confirmed | config-drift | `BUDGET_TRUSTED_HOSTS` is configured but never enforced

- **Location(s):** `config.py:54-57,169-176` (field and comment "TrustedHostMiddleware once T-D07 lands"), `terraform/cloud-init/compose/docker-compose.yml.tpl:23` (set in prod), `web/app.py:187-199` (no `TrustedHostMiddleware`).
- **Description:** the app accepts any `Host` header (probe: `Host: evil.test` gives the normal login redirect). Caddy serves one hostname so an off-host request does not normally arrive, but the app is the only layer that could reject it and `request.url.netloc` is used when validating `HX-Current-URL` (`middleware/auth.py:117-122`).
- **Impact:** negligible today; a latent gap if Caddy is ever given a second site or the app is exposed directly.
- **Mitigation:** register Starlette's `TrustedHostMiddleware(allowed_hosts=settings.trusted_hosts)` when the tuple is non-empty (dev keeps it empty).
- **Effort:** S. **Related:** T-D07, requirements §6.7.

### D-08 | Low | Confirmed | security-control | CSP exists only at the proxy; app sends none and trusts a client-supplied nonce

- **Location(s):** `web/middleware/security_headers.py:41-51,70-71,76-78`, `terraform/cloud-init/compose/Caddyfile.tpl:49-54`, `deploy/Caddyfile:5-8` (comment says CSP "ships with T-D07").
- **Description:** the app's own middleware sets five headers but no CSP, so dev, tests, prod-sim and any direct-to-app path run without one; the policy exists only for HTML responses proxied by Caddy. The app also adopts the inbound `X-CSP-Nonce` header unchanged (an attacker reaching the app directly picks the nonce); no template uses the nonce any more (`grep nonce web/templates` is empty), so the propagation is vestigial. `style-src 'unsafe-inline'` is needed for the many inline `style=` attributes (49 in templates).
- **Impact:** low in prod (Caddy overwrites the header with a per-request UUID). The gap is that CSP regressions cannot be caught by tests, because the CSP is not in the app.
- **Mitigation:** emit the CSP from `SecurityHeadersMiddleware` (same policy string as Caddy, nonce generated by the app, inbound header ignored), keep Caddy as a second layer, and add a test asserting the header on HTML responses; plan a move of inline styles to classes to drop `unsafe-inline`.
- **Effort:** M. **Related:** D-03, ADR-0036, requirements §6.7.

### D-09 | Low | Confirmed | security-control | Exception text bypasses log redaction

- **Location(s):** `web/errors.py:117-125` (`logger.error(..., exc_info=exc)`), `logging.py:25-55,77-90` (redaction works on structured keys only).
- **Description:** the deny-list redactor sees event keys, not the text of exception messages or tracebacks. Python exceptions raised from user input embed the value, for example `ValueError("invalid literal for int() with base 10: 'abc'")` or date parsing errors that quote the input. These land in the journald JSON unredacted, which ADR-0078 §5 intends to prevent for amounts, names, descriptions and search terms.
- **Evidence:** the `POST /recurring` probe with `source_category_ids=abc` logged `invalid literal for int() with base 10: 'abc'` (visible in the run output, not stored in `probe_output.txt`; reproduce with `probe_headers_validation.py` and read stderr).
- **Impact:** low: values are limited to what raises an exception (a malformed field, mostly numbers and dates), and logs are local journald with 14-day Caddy retention. It does contradict the stated control.
- **Mitigation:** fix at the source (D-02 stops most such exceptions); additionally run the formatted traceback through a scrubber that masks quoted literals after known message patterns, or log only `type(exc).__name__` plus the frame location for `ValueError`/`InvalidOperation`.
- **Effort:** S. **Related:** D-02, ADR-0078 §5.

### D-10 | Low | Confirmed | dependency | Mutable image tags on the prod host, and a stale "pinned by digest" claim

- **Location(s):** `terraform/cloud-init/compose/docker-compose.yml.tpl:60,77,102,122` (`litestream/litestream:0.3.14`, `caddy:2.8`), comment at line 4 ("caddy image is a custom build pinned by digest", ADR-0036 §2), `Dockerfile:9,43` (`python:3.12-slim-trixie`), `Dockerfile:24` (`pip install uv` unpinned, builder stage only).
- **Description:** only the app image is pinned by digest and cosign-verified (`bp_agent.py:181-182`). Caddy (internet-facing, root, holds the TLS keys) and Litestream (holds the bucket credentials and the age identity) are pulled by tag on the host, so a retagged or compromised upstream image would be run with those privileges; the compose comment claims otherwise. `apt-get upgrade` in the runtime stage and the builder's `pip install uv` make image builds non-reproducible.
- **Impact:** supply-chain exposure on two privileged containers; no known exploit.
- **Mitigation:** pin `caddy` and `litestream` by `@sha256:` digest in the template (the host agent already enforces digests for the app image and can verify these), and pin the base image digest and `uv` version in the Dockerfile; fix or remove the comment.
- **Effort:** S. **Related:** ADR-0036, ADR-0103, ADR-0111, H1, H4.

### D-11 | Low | Probable | infra-exposure | Docker-published ports bypass ufw; the tailnet-only drill relies on the cloud security group alone

- **Location(s):** `terraform/cloud-init/compose/docker-compose.yml.tpl:125-130` (publishes 80/443 on all interfaces), `terraform/cloud-init/bootstrap.yaml.tpl:125-135` (`daemon.json` without `"iptables": false`), `bootstrap.yaml.tpl:238` (`ufw allow in on tailscale0 to any port 443` for the drill).
- **Description:** Docker inserts its own DNAT and `FORWARD` rules, which ufw's `INPUT` rules do not govern. The documented defence in depth ("host `ufw` for drill allows 443/tcp only on `tailscale0`", ADR-0101 §1) therefore does not restrict the published Caddy port; the only effective public-reachability control for the drill is the Scaleway security group (default drop, `modules/compute/main.tf:12-45`).
- **Evidence:** config citation; not verified on a VM (H4).
- **Impact:** if the security group is ever loosened or mis-applied, the drill VM (which runs arbitrary feature branches and restored prod data) is public although the docs say a second layer exists.
- **Mitigation:** bind the Caddy ports to the tailnet address for the drill (`ports: ["100.x.y.z:443:443"]` rendered from a Terraform variable) or add the filter to the `DOCKER-USER` chain next to the existing metadata guard (`bootstrap.yaml.tpl:200`); update ADR-0101 to state where the control really sits.
- **Effort:** S. **Related:** ADR-0094, ADR-0101, H4.

### D-12 | Low | Confirmed | infra-exposure | Dev and schema surfaces are live in production

- **Location(s):** `web/app.py:168` (`docs_url="/docs"`, default `/openapi.json`), `web/routers/dev_components.py:17-27` (`/dev/components`), `web/app.py` `_ROUTER_NAMES` (registers `dev_components` unconditionally).
- **Description:** any signed-in user can read the full route and parameter schema and the internal component gallery in prod. `/docs` loads Swagger UI from a CDN, which the CSP blocks (broken page, but a third-party script origin in the design). No data is exposed.
- **Impact:** information disclosure to authenticated users only; aids targeted probing.
- **Mitigation:** register `dev_components` only when `settings.env != "production"` and construct the app with `docs_url=None, openapi_url=None` in production.
- **Effort:** S. **Related:** ADR-0079.

### D-13 | Low | Confirmed | config-drift | Documented security controls without an implementation

- **Location(s):** requirements §6.7 (`docs/requirements.md:340-346`: "`fail2ban` jails on `sshd` + `caddy-auth`", "Mozilla Observatory", "CSP ... Caddy injects, app propagates to Jinja"), `terraform/cloud-init/bootstrap.yaml.tpl:77` (package only), `Caddyfile.tpl` header comment ("rate limit"), `deploy/Caddyfile:5-8` (stale "CSP ships with T-D07").
- **Description:** the NFR text and ADR-0036's Caddyfile summary list a fail2ban jail, an edge rate limit and an app-side nonce use that do not exist (no jail files, no `rate_limit` directive, no template uses the nonce). Reviewers relying on §6.7 would assume controls that are absent (see D-06, D-08).
- **Impact:** false assurance; no direct exploit.
- **Mitigation:** either implement (D-06 mitigation) or edit requirements §6.7 and ADR-0036 to the real state, in the docs-first order of CLAUDE.md.
- **Effort:** S. **Related:** D-06, D-08, Track G.

## 6. Accepted or documented risks (not findings)

- **Admin password reset equals account takeover in v3.** An admin can reset another user's password (`settings_users.py:267-286`), receive the one-shot password, log in and read that user's data (the user is then forced to rotate). This is the documented v3 position (requirements §6.8, ADR-0078 §8, ADR-0079 adversary A1, to be closed by v4 envelope encryption). The action is audited and revokes the target's sessions. Listed so Track H2 does not rediscover it as new.
- **`/debug/audit-tail` shows cross-user metadata** (entity ids, types, timestamps) to admins by ADR-0078 §1; payloads of other users are replaced by a placeholder. `n` is clamped to 100 (`services/audit_tail.py:16-17,57`).
- **Replica identity on the host.** The age identity sits next to the database, as ADR-0078 §3 accepts.
- **Silent 200 on foreign-id deletes** (transactions, accounts) is not an oracle (it behaves the same for non-existent ids) but is inconsistent with the 404s on every other route; Track C may want it unified.

## 7. Questions (leads for Track H)

**H2 (isolation and privilege)**
1. `POST /recurring` and `POST /recurring/{id}` with `terms[i][source_category_ids]` set to **another user's** category ids on the *create/update* path (not only the preview, which returned 422). The preview rejects them, but `validate_formula_sources` was not read; confirm the saved rule can never sum another user's category, and that `compute_formula_amount` joins on `user_id`.
2. `services/forecast.py`, `services/budget.py`, `services/analytics.py` and `today_data.py` aggregate across accounts and categories. The matrix covered query parameters on the HTTP surface, not every service entry point. Try crafted `account_id` lists in the `/forecast` and `/plan` query strings with other users' ids, and the CSV exports with `include_deleted`-style filters.
3. `batch/undo` (`planned.py:111-165`, `recurring.py:469-543`) trusts id lists posted by the client and reads `audit_log` **without a `user_id` filter** (`planned.py:142-147`, `recurring.py:503-507`). Writes are owner-scoped, so no cross-user write was seen, but try a rule id whose latest audit row belongs to a different actor, and a double-submit, to see whether it can restore another state than the batch's (correctness, own data).
4. Admin chain: reset another user's password, log in as them, then use that session to reach `/settings/users` flows for a second admin; check the last-admin rule under concurrent demotion and deletion.
5. Preference and drawer writes: which other endpoints take a user id from a constant or a form field? D-01 was found by reading `budget.py`; `settings.py` and `services/preferences.py` callers are worth one more pass.

**H3 (authentication and sessions)**
1. Passkey login challenge is a signed cookie, not a server-side single-use value. For authenticators with a zero sign counter (synced passkeys), the sign-count branch `(new > 0 or stored > 0) and new <= stored` never trips, so a captured `(challenge cookie, assertion)` pair could be replayed within 300 s. Needs a MITM or malware position; check whether `authenticate_passkey_finish` marks the challenge used anywhere.
2. Rate-limit key spoofing: `uvicorn --forwarded-allow-ips=*` plus `X-Forwarded-For` (`Dockerfile:104-108`). With the app reachable only through Caddy, does Caddy 2.8 overwrite a client-supplied `X-Forwarded-For`? If not, per-IP limits are bypassable by header rotation.
3. Parallel requests against `login_rate_limit`: the counter is a read-modify-write in one transaction; confirm there is no window where N concurrent requests all pass, and measure the audit-row growth described in D-06.
4. Re-auth window (`session_reauth_window_minutes`): can a stale session obtain a fresh `authenticated_at` through `/auth/reauth/finish` with a passkey of another user (challenge purpose is bound to `user_id`, the credential lookup should be too)?
5. Forced password rotation gate (`must_change_password`): the exempt list includes `/auth/logout` and `/health/replication`; confirm no other state-changing route is reachable with a flagged session, including `/auth/reauth*` and passkey registration.
6. The non-ASCII CSRF token crash (D-02) is reachable before login; check whether any other pre-auth parser (form field names, multipart) has a similar uncaught exception.

**H4 (infrastructure)**
1. Does Caddy 2.8's `reverse_proxy` overwrite inbound `X-Forwarded-For` and `X-Real-IP` as assumed? Does it strip a client-supplied `X-CSP-Nonce`? (`request_header X-CSP-Nonce {vars.nonce}` is set both site-wide and in `header_up`.)
2. Is app port 8000 reachable from the Litestream or probe containers (shared `edge` network), and from the host's loopback? Confirm Docker's ufw bypass (D-11) on a drill VM from a non-tailnet address.
3. The initial admin password and cookie secret sit in the app container environment, in `bp-config` metadata and in rendered Terraform state; check `docker inspect`, `/proc/1/environ` access for the `operator` user (passwordless sudo, in the `docker` group), and whether the initial password variable can be unset after first login.
4. `/.well-known/bp-deploy-status.json`, `/health` (version), `/health/replication`: what do they reveal to an unauthenticated caller that helps targeting, and is Caddy's 502 page (when the app is down) free of the CSP-less HTML gap?
5. Replica and drill-bucket access with a drill credential: can the drill key list or read prod objects (bucket policy `bucket_policy/main.tf`, ADR-0091)? Encrypted replica objects are only as safe as the age identity on the VM.

**H1 (CI and supply chain)**
1. `security.yml` builds the pip-audit ignore list from `.security-allowlist.yml` **in the PR checkout**. A PR can add its own `--ignore-vuln` entries. Is `security` a required check, and is CODEOWNERS or a ruleset protecting that file?
2. `drill-gate-skip.yml` posts a success `drill-gate` status for PRs whose changed paths all match the classifier allowlist in `scripts/ci/drill_gate_skip.py`. Which paths are on that list, and can any of them change deploy behaviour (docs that are read by workflows, `.security-allowlist.yml`, `terraform/tests/`)?
3. Mutable tags for Caddy and Litestream on the prod host (D-10): is there any workflow that rewrites the compose template from a branch other than `main`?

**Track C / G cross-references**
- `CLAUDE.md` still names Plotly; charts are server-side SVG (ADR-0054). Requirements §6.7 lists controls that do not exist (D-13).
- Several routers still hold business logic and SQL (layering); D-01 is a symptom: a service-level `user_id` literal that no repository-level guard can see.
- `tests/architecture/test_user_id_filter*.py` should be extended to flag integer literals passed as `user_id` (D-01 mitigation).
