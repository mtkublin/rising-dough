# Track H3: Authentication and sessions red team (T-Q18 / H3)

Audited at `AUDIT_SHA` 9fb18cbca26ef305855efc8fc106d896edc82631. White-box, goal-driven, local only, read-only (no fixes). Repros live in `docs/plans/quality-audit/repro/H3/` with recorded outputs next to each script.

## Critical findings

None. No authentication bypass, no account takeover and no cross-user session confusion was reached. Every attempt to break the "verified fine" list of Track D (hashed session ids, fixation, rotation, logout and password-change invalidation, step-up guard, enumeration timing, `safe_next`) failed, see section 3.

## Summary

| ID | Severity | Confidence | Title |
|---|---|---|---|
| H3-01 | Medium | Confirmed | Rate-limit identity is the leftmost `X-Forwarded-For` entry, unvalidated: per-IP limits are bypassable, a victim's bucket can be poisoned, and arbitrary strings are persisted (conditional on the proxy not overwriting the header) |
| H3-02 | Low | Confirmed | Passkey login and re-auth challenges are not single-use: replay within 300 s opens a second session; with a counter-bearing authenticator the replay revokes the owner's passkey |
| H3-03 | Low | Confirmed | Pre-auth parser failures reach the catch-all 500: non-ASCII CSRF header or form token, multipart without boundary, more than 1000 form fields (extends D-02) |
| H3-04 | Low | Confirmed | A request in flight during re-auth rotation re-sets the old session token and signs the user out |
| H3-05 | Low | Confirmed | A holder of the session cookie can exhaust the owner's step-up bucket |
| H3-06 | Low | Confirmed | Revoking a passkey does not revoke the sessions that were created with it |
| H3-07 | Low | Confirmed | Throttled and failed logins persist an attacker-controlled email of any length in `audit_log` (quantifies D-06) |
| H3-08 | Low | Confirmed | CSRF token is neither format-checked, nor bound to the session, nor rotated at login or logout (defence in depth) |

## 1. Coverage statement

**Read in full:** `web/routers/auth.py`, `web/auth_cookies.py`, `web/middleware/{auth,csrf,must_change_password}.py`, `web/deps.py` (re-auth parts), `services/auth.py` (passkey and session parts), `services/reauth.py`, `services/rate_limit.py`, `services/password_change.py` (commit path), `repositories/{sessions,webauthn,rate_limit}.py`, `web/routers/settings_password.py`, the guard wiring of `settings_users.py`, `static/js/passkeys.js` (redirect, CSRF and `next` handling), `static/htmx-csrf.js`, ADR-0076 §2 to §5, ADR-0067 §1 to §3, the Dockerfile `CMD`, `deploy/Caddyfile` header lines.

**Dynamic evidence** (scratch DBs `/tmp/audit-H3-*.sqlite`, 3 seeded users: admin, victim V, attacker A; app in-process via `TestClient`, or under a real `uvicorn` on 127.0.0.1 started with `--proxy-headers --forwarded-allow-ips=*` for the rate-limit and race tests; the servers were stopped by the scripts):

| Script | Output | Covers |
|---|---|---|
| `h3_passkey_ceremonies.py` | `h3_passkey_ceremonies_output.txt` | software ES256 authenticator (own CBOR/COSE/authData builder, `none` attestation): login replay, counter regression, cross-user registration, cross-user re-auth, challenge purpose and user binding, user-handle confusion, sessions after passkey removal |
| `h3_sessions_reauth.py` | `h3_sessions_reauth_output.txt` | fixation, replay after logout / password change / re-auth rotation, re-auth window with an injected clock, HTMX and JSON stale shapes, forced-rotation gate on 16 routes plus 5 path-normalisation variants, demotion and delete, absolute cap |
| `h3_csrf_preauth.py` | `h3_csrf_preauth_output.txt` | login CSRF, header versus form precedence, content types, token lifecycle, pre-auth parser fuzz (12 inputs), 7 malformed passkey bodies with a valid challenge, stale-admin step-up, 17-entry open-redirect battery on login and re-auth, HX-Current-URL, reflected-value escaping |
| `h3_rate_limit.py` | `h3_rate_limit_output.txt` | 20-way parallel burst, email case and whitespace variants, XFF rotation, XFF multi-value, victim-bucket poisoning, audit growth, XFF-derived `ip` persistence and escaping, step-up bucket exhaustion |
| `h3_rotation_race.py` | `h3_rotation_race_output.txt` | in-flight request versus re-auth rotation |
| `h3_enumeration_timing.py` | `h3_enumeration_timing_output.txt` | enumeration timing and bodies at bcrypt cost 12 |

**Total request volume:** under 400 requests; the largest parallel burst was 20.

## 2. Goals attempted and results

| Goal | Result |
|---|---|
| Session fixation | Not possible. A planted cookie value is ignored and replaced; the planted value never authenticates (S1). |
| Theft and replay after logout, password change, re-auth | Old token dead in all three cases (S2). After passkey removal sessions survive: H3-06. |
| Rotation on privilege change | Demotion and soft-delete apply on the next request because `is_admin` is re-read per request (S5). Absolute cap holds; the one in-flight request that already resolved the session gets answered (S6, no issue). |
| Re-auth bypass: stale window, HTMX, JSON, other routes | Window enforced at 10 min with an injected clock; plain gets 303, HX gets 403 + `HX-Redirect`, JSON gets 403 + `redirect`; admin `reset-password` and `delete` guarded in both shapes (S3, C7). A stolen stale session without the password cannot pass `POST /auth/reauth` (401). |
| Re-auth token reuse across users or sessions | Re-auth is bound to the cookie's session; the challenge for `reauth` is bound to `user_id`; `verify_passkey_reauth` additionally checks `stored.user_id` (P4, P5). |
| Passkey: challenge reuse / replay | Works within the TTL: H3-02. |
| Passkey: challenge bound to session | Bound to purpose and user id only, not to a session or browser, by design (stateless HMAC cookie). A challenge from `login/begin` cannot be used for `reauth`, and an A-issued `register` challenge is rejected for V (P5). |
| Passkey: cross-user credential registration or assertion | Registering V's credential id (live or revoked) from A's session gives `duplicate_credential` because the UNIQUE constraint ignores `deleted_at`. V's key signing A's re-auth challenge gives 401 (P3, P4). |
| Passkey: user-handle confusion | Login resolves the user from the credential id only; a forged `userHandle=3` still yields V's session (P6). |
| Forced rotation gate (`must_change_password`) | 16 state-changing and read routes tested with a flagged session: everything except `/settings/password` (POST answered, 422 on empty body) and `/auth/logout` redirects to the rotation page, including `/auth/reauth*`, `/auth/register*`, passkey and session revoke. Path variants (`/settings/password/`, `//settings/password`, `..`) do not reach exempt routes (S4). |
| Rate-limit bypass: header rotation | Works: H3-01. |
| Rate-limit bypass: parallel requests | No TOCTOU. 20 parallel attempts on a 5/min bucket gave exactly 5 x 401 and 15 x 429; the counter is one atomic `INSERT ... ON CONFLICT ... RETURNING` (R1). |
| Rate-limit bypass: email case / whitespace variants | None. Seven variants share one counter (R2); lookup uses the same normalisation. |
| CSRF on HTMX posts | Header or form token must equal the cookie; PUT/PATCH/DELETE and `text/plain` without a token give 403; wrong header plus valid form token gives 403 (the header wins). Weaknesses: H3-08. |
| Login CSRF | Blocked unless the attacker can set the CSRF cookie (needs sibling-subdomain or MITM cookie injection, which `__Host-` blocks in browsers): H3-08. |
| Open redirect beyond `safe_next` | 17 variants on `next` of login and re-auth, `GET /auth/login?next=` when signed in, and `HX-Current-URL` on anonymous HTMX: no Location outside the origin. Percent-encoded (`/%2f/evil`) and `/%5c` values are kept literally and are relative in browsers. Reflected `next` and `email` values are autoescaped (C8, C9). |
| Enumeration timing | Existing, unknown, passkey-only and soft-deleted accounts cost the same (311 to 353 ms at cost 12, identical status and body length class); over-long passwords short-circuit for existing and unknown alike (7 to 8 ms). No oracle. |
| Password reset / invite flows | None exist: no email channel, no tokens. Admin create and reset return a one-shot generated password behind step-up and force rotation (`must_change_password`); the admin-reset account takeover is the accepted v3 risk (D section 6). |

**Not attempted (stated, not hidden):**

- No real browser or platform authenticator. The software authenticator proves server-side verification only; behaviour of synced-passkey sign counters is taken from the specification, not measured.
- No Caddy in front of the app. Everything that depends on Caddy overwriting `X-Forwarded-For` is a Question for H4 (Q1).
- No multi-process or multi-host concurrency, no load. The parallel burst was a single burst of 20 against one uvicorn worker.
- The in-flight rotation race was demonstrated with an extra slow route added by the script; whether the shipped UI ever has a request in flight during re-auth is open (Q2).
- Admin-only flows beyond the step-up guard (last-admin rule, concurrent demotion) belong to H2.

## 3. Verified fine under attack (do not re-check)

Session id entropy and hashing; fixation; logout, password-change and re-auth token invalidation; step-up window and all three response shapes; re-auth rate limit per user; challenge purpose and user binding; cross-user credential id handling; usernameless login ignoring `userHandle`; `safe_next` on every consumer; forced-rotation gate coverage; enumeration timing and bodies; email variant normalisation; atomic rate-limit counters; CSRF on all unsafe verbs; reflected-value escaping; malformed passkey bodies (7 shapes plus non-UTF-8 and non-object JSON: all 4xx, no 500).

## 4. Findings

### H3-01 | Medium | Confirmed | security-control | Rate-limit identity is the leftmost X-Forwarded-For entry; per-IP limits can be bypassed, a victim's bucket poisoned, and arbitrary strings persisted

- **Location(s):** `Dockerfile:104-108` (`--proxy-headers --forwarded-allow-ips=*`), `web/routers/auth.py:85-86,99-100` (`_client_ip`, `_ip_identity`), `web/routers/auth.py:116-143` (`login_rate_limit`, key `ip=<client>|email=<normalised>`), `web/routers/auth.py:146-162,183-203` (passkey and re-auth keys), `services/auth.py:151-172` and `repositories/sessions.py:124-135` (the same string stored as `ip` in `audit_log` and `sessions`).
- **Description:** with `forwarded-allow-ips=*` uvicorn takes the client address from `X-Forwarded-For` and, for a wildcard trust list, uses the first (leftmost) entry. The value is not validated as an IP address. The login limiter (ADR-0072) therefore keys on a string the caller chooses whenever the proxy in front forwards a client-supplied header unchanged or appends to it. Consequences measured under the Dockerfile's uvicorn flags: (a) rotating the header gave 30 wrong guesses against one account with no 429 and the 31st attempt with the right password succeeded (R3), so the 5/min and 20/h per account limits do not exist for a header-rotating attacker; (b) because the identity is attacker-controlled, an attacker can write to a victim's key by sending the victim's IP in the header: six wrong attempts labelled with the victim's address made the victim's real login with the right password return 429 (R5), a targeted lockout; (c) `X-Forwarded-For: 1.2.3.4|email=victim@x.test` produced the key `ip=1.2.3.4|email=victim@x.test|email=v@x.test`, and `not-an-ip` and an HTML payload were accepted and stored verbatim as `sessions.ip` and `audit_log.ip` (R4, R8; the Security page escapes it, so no XSS).
- **Evidence:** `repro/H3/h3_rate_limit.py` -> `h3_rate_limit_output.txt` (R3, R4, R5, R8). Parallel bursts and email variants were fine (R1, R2). With a proxy that overwrites the header (Caddy's documented default for untrusted clients) a single entry arrives and (a) to (c) do not apply; that is unverified here (Question H3-Q1). Without such a proxy hop (for example the app port reachable by another container on the `edge` network, D-06c) they apply directly.
- **Impact:** credential guessing against the admin account is bounded only by the bcrypt cost and the 12-character minimum; a targeted lockout of a known user from a known address; log and audit rows carry attacker-chosen text in the `ip` column.
- **Mitigation:** stop trusting the header by name. Set uvicorn's `--forwarded-allow-ips` to the proxy's fixed address (or the `edge` subnet) instead of `*`, make the proxy overwrite `X-Forwarded-For` and `X-Real-IP`, and add in `web/routers/auth.py` a `_client_ip` that validates the result with `ipaddress.ip_address` and falls back to `request.client.host`. In addition add the per-email global bucket proposed in D-06 (for example 30/h across all IPs) so one account has a cap independent of source address. Add a test that sends a rotating header through the ASGI stack and asserts a 429 after the account limit.
- **Alternatives:** keep `*` but derive the address from the right-most entry (the one the proxy appended): smaller change, still wrong if the topology gains a hop.
- **Effort:** S for the header handling and validation; M with the per-email bucket and tests.
- **Related:** D-06, D-11, ADR-0072, ADR-0079, Question H3-Q1 (H4).

### H3-02 | Low | Confirmed | security-control | Passkey login and re-auth challenges are not single-use; replay opens a second session, and with a counter-bearing key the replay revokes the owner's passkey

- **Location(s):** `web/auth_cookies.py:150-205` (stateless HMAC envelope, `verify_challenge` checks purpose, user, age only), `web/routers/auth.py:392-425` (`login_passkey_finish` clears the cookie only on the response), `services/auth.py:411-413,455-465` (`sign_count_regressed`, `revoke_credential` on regression), `services/reauth.py:135-143`.
- **Description:** the server keeps no record that a challenge was consumed. (a) A captured `(challenge cookie, assertion body)` pair replays for 300 s. For an authenticator whose counter stays 0 (synced passkeys, the common consumer case) `sign_count_regressed(0, 0)` is false, so the replay succeeds and creates another session (P1: live sessions 1 to 3, replayed session serves `/today`). (b) For an authenticator with a real counter the replay fails the regression check, and the code then **revokes the legitimate credential** (P2: row soft-deleted, the owner's next passkey login returns 401), so a captured assertion is also a way to remove a user's passkey without any credential.
- **Evidence:** `repro/H3/h3_passkey_ceremonies.py` -> `h3_passkey_ceremonies_output.txt` (P1, P2). Needs a position that reads the TLS-protected request body (compromised device, TLS-terminating logging proxy, browser extension), which already grants session theft; hence Low. The cookie is HttpOnly and `SameSite=Strict`, so a remote web attacker cannot supply it.
- **Impact:** a captured login assertion yields a fresh session for up to 5 minutes without further interaction; the same capture can disable a user's passkey.
- **Mitigation:** make the challenge single-use in `web/routers/auth.py` / `services/auth.py`: store the challenge nonce (hash) with its expiry in a small table (or the sessions DB) at `*/begin`, delete it with `DELETE ... RETURNING` at `*/finish` before verifying, and reject when absent. Separately treat a counter regression with `new == stored == 0` as not a regression and do not revoke on a mere regression of a credential that has a valid fresh challenge (log and refuse instead).
- **Effort:** M.
- **Related:** D section 7 H3-1, ADR-0067 §1 and §3 (design chose stateless challenges).

### H3-03 | Low | Confirmed | security-control | Pre-auth parser failures reach the catch-all 500 handler

- **Location(s):** `web/middleware/csrf.py:155-181` (`_read_form_token` and `secrets.compare_digest(submitted, existing)` run before routing and before auth for every unsafe request that carries a CSRF cookie; the exemption list is only the three probes).
- **Description:** answers D section 7 H3-6. Besides the non-ASCII token of D-02, three more unauthenticated inputs end in `unhandled ... on POST /auth/login` and a 500: a non-ASCII `X-CSRF-Token` header (latin-1 bytes; `TypeError` in `compare_digest`), `Content-Type: multipart/form-data` without a boundary (`HTTPException 400 'Missing boundary'` raised inside `BaseHTTPMiddleware`, which the app maps to 500), and a urlencoded body with more than 1000 fields (`HTTPException 400 'Too many fields'`). Other probes were handled correctly: invalid UTF-8 percent escapes, NUL bytes, duplicate `_csrf_token`, JSON body to a form route, non-ASCII session cookie bytes, seven malformed passkey bodies and non-UTF-8 JSON all gave 4xx.
- **Evidence:** `repro/H3/h3_csrf_preauth.py` -> `h3_csrf_preauth_output.txt` (C4: rows with `-> 500`; the logged exception names are in the script run).
- **Impact:** an unauthenticated caller can generate error-level stack-trace log lines at will; wrong status for malformed requests; no data exposure.
- **Mitigation:** in `web/middleware/csrf.py` wrap the token read in `try/except (HTTPException, MultiPartException)` and return the 400/403 JSON, and compare `submitted.encode()` with `existing.encode()` using `compare_digest` on bytes (the D-02 fix). Add one test per input listed above.
- **Effort:** S.
- **Related:** D-02, D-03.

### H3-04 | Low | Confirmed | htmx-contract | A request in flight during re-auth rotation re-sets the old token and signs the user out

- **Location(s):** `web/middleware/auth.py:168-176` (re-issues the resolved cookie value when the response does not set one), `services/reauth.py:146-169` and `repositories/sessions.py` `rotate_session_token` (token swapped in place), ADR-0076 §4 (assumes full-page submissions, "no concurrent HTMX requests race the swap").
- **Description:** a response that was started before the rotation but finishes after it carries `Set-Cookie: __Host-session=<old token>`. Browsers apply cookies in arrival order, so the cookie ends up as the revoked old token and the next navigation redirects to login. Reproduced with a slow route added by the script: reauth returned 303 with a new token, the late response set the old one, and the next request got 302 to `/auth/login`.
- **Evidence:** `repro/H3/h3_rotation_race.py` -> `h3_rotation_race_output.txt`. Whether the shipped pages issue concurrent or polling requests on `/auth/reauth` or `/settings/password` is open (Question H3-Q2); the same applies to password-change rotation.
- **Impact:** a spurious sign-out right after a successful step-up or password change when another tab or a polling fragment is in flight; no security exposure.
- **Mitigation:** in `AuthRequiredMiddleware.dispatch`, re-issue the cookie only if the session token is still the live one (re-check by hash after `call_next`), or accept the previous token for a short grace window after rotation (ADR-0076 §5 already names the grace window as the deferred design).
- **Effort:** S.
- **Related:** ADR-0076 §4 and §5.

### H3-05 | Low | Confirmed | security-control | A session-cookie holder can exhaust the owner's step-up bucket

- **Location(s):** `web/routers/auth.py:183-203` (`reauth_rate_limit`, key `user=<id>`), `web/routers/auth.py:669-700,729-760` (`reauth_password`, `reauth_passkey_finish`).
- **Description:** the re-auth bucket is per user, not per session or per user and IP. Five wrong passwords sent with a stolen session cookie make the owner's correct re-auth return 429 for the rest of the minute (and for the hour bucket after 20). The thief cannot pass re-auth, so this only denies the owner the step-up (passkey add and revoke, session revoke, admin user actions) and the "revoke the thief's session" action requires step-up. The same shape applies to `register_rate_limit` and `password_change_rate_limit`.
- **Evidence:** `repro/H3/h3_rate_limit.py` -> R7: `[401, 401, 401, 401, 401, 429]`, then the owner's correct password returned 429.
- **Impact:** while a session is stolen the owner can be kept from revoking other sessions by repeating the exhaustion every minute; a revoke of the current session (logout) is unguarded and still works, which ends the owner's session but not the thief's other sessions.
- **Mitigation:** key the re-auth bucket on `user=<id>|session=<handle>` plus a larger per-user ceiling, or exempt requests whose session is the one that just passed a login in the last window; and let "sign out everywhere" (revoke all) be reachable with the account password through the password-change flow (already revokes others).
- **Effort:** S.
- **Related:** ADR-0072, ADR-0076 §2.

### H3-06 | Low | Confirmed | security-control | Revoking a passkey does not revoke the sessions created with it

- **Location(s):** `web/routers/auth.py:583-592` (`revoke_passkey` redirects after the soft delete only), `services/auth.py:383-392`, `repositories/webauthn.py` `revoke_credential`; no link between `sessions` and `webauthn_credentials` (sessions record method only in the audit row).
- **Description:** a session opened through a passkey keeps working after that passkey is removed (P7: owner removes the passkey after step-up, the session created by it still serves `/today`). A user who removes a passkey because the device was lost or stolen expects its sessions to end; they must find and revoke them on the Security page (also behind step-up). The same holds for an admin-reset: the target's sessions are revoked, but a self-service passkey removal is not.
- **Evidence:** `repro/H3/h3_passkey_ceremonies.py` -> P7.
- **Impact:** after "my passkey device was stolen -> remove passkey" the thief's already-open session remains until it expires (sliding 14 days, capped at 30 days absolute).
- **Mitigation:** store the credential row id on `sessions` (nullable column) at passkey login and revoke those sessions in `services/auth.revoke_passkey` in the same transaction; or revoke all other sessions on passkey removal, as password change already does.
- **Alternatives:** document the behaviour in ADR-0076 and show on the removal confirmation that sessions stay (cheapest).
- **Effort:** S to M (migration for the column).
- **Related:** ADR-0067, ADR-0076, ADR-0074 (password change revokes others).

### H3-07 | Low | Confirmed | security-control | Pre-auth audit rows store the attacker's email with no length cap

- **Location(s):** `services/auth.py:151-172` (`_audit_login_failure`, `email.strip().lower()`), `services/rate_limit.py:120-141` (`audit_throttled`), `web/routers/auth.py:116-143`.
- **Description:** quantifies D-06b. A single unauthenticated `POST /auth/login` with a 200 000 character email stored an audit payload of 200 094 bytes (C6); there is no cap on form field size and the throttle path writes a row per request too (R6: 15 attempts left 15 `auth_event` rows, 10 of them throttled). The rows are replicated by Litestream.
- **Evidence:** `repro/H3/h3_csrf_preauth.py` C6, `h3_rate_limit.py` R6.
- **Impact:** an unauthenticated caller can grow the DB and replica by the body size per request, bounded only by the (bypassable, H3-01) rate limit and the server's body limits.
- **Mitigation:** as in D-06: truncate the stored email to 254 characters, write one `rate_limited` row per bucket per window, and add a request body size limit at the proxy and app.
- **Effort:** S.
- **Related:** D-04, D-06, H3-01.

### H3-08 | Low | Confirmed | security-control | CSRF token is not format-checked, not bound to the session and not rotated at login or logout

- **Location(s):** `web/middleware/csrf.py:155-181` (any cookie value is accepted and echoed back as the token), `web/routers/auth.py` `_start_session` (no token rotation).
- **Description:** the double-submit check compares two attacker-reachable values. An attacker who can set the CSRF cookie (sibling subdomain, active network attacker on plain HTTP before HSTS) can pick the token: a one-character cookie `a` plus form field `a` was accepted by `POST /auth/login` (C1) which enables login CSRF (victim signed into the attacker's account) and, after login, CSRF on any route. The token is identical before login, after login and after logout (C2). The `__Host-` prefix, `Secure` and HSTS (ADR-0078 §2) block cookie injection in browsers, so this is defence in depth.
- **Evidence:** `repro/H3/h3_csrf_preauth.py` C1, C2.
- **Impact:** none under the current browser guarantees; weakens the CSRF defence to the strength of the cookie-integrity assumption alone.
- **Mitigation:** mint the token as `HMAC(cookie_secret, session id or anonymous nonce)` and verify the signature in `CSRFMiddleware` (signed double-submit), and rotate it in `_start_session` and on logout.
- **Effort:** M.
- **Related:** ADR-0033 §4, ADR-0065, D section 3.2.

## 5. Questions

1. **H3-Q1 (H4, Caddy):** does Caddy 2.8 `reverse_proxy` overwrite or append to a client-supplied `X-Forwarded-For`? Caddy trusts no upstream by default and should drop and reset it, which would confine H3-01 to a non-proxied path (another container on the `edge` network); confirm on a drill VM with the real Caddyfile and with `X-Forwarded-For: 1.2.3.4` and `X-Forwarded-For: 1.2.3.4, 5.6.7.8` requests, then read `sessions.ip` or the rate-limit key.
2. **H3-Q2:** does any shipped page send HTMX requests (polling, `hx-trigger="load"`, lazy fragments, a second tab) while the user is on `/auth/reauth` or `/settings/password`? If so H3-04 is reachable in normal use and moves to Medium on usability.
3. **H3-Q3:** is 300 s of challenge replay acceptable to the owner given the threat model (A1 to A3 in ADR-0079 do not include a TLS-level capture)? If not, H3-02 is a small task with a table.
4. **H3-Q4:** should removing a passkey sign out the sessions that used it (H3-06), or is "sessions are independent of credentials" the intended invariant? ADR-0076 is silent.
5. **H3-Q5:** real authenticators: do the iCloud, Google and 1Password passkeys the user actually uses report counter 0 (making H3-02(a) the live case) or a counter (making H3-02(b) the live case)? A 2-minute check with the Security page after two logins answers it.
6. The step-up window is session-wide and never consumed: a successful guarded action leaves the window open for the rest of its 10 minutes (for example add a passkey, then revoke another session without another prompt). That matches ADR-0076 §2 but a per-action challenge for passkey add (the persistence primitive) would be stricter; for the owner to decide.
