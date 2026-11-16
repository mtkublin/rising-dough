# T-D08 — CSRF protection

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: T-D07 (shared middleware chain), eventually T-D02 (auth)
- **Blocks**: real deployment of any state-changing route behind auth
- **References**: ADR-0033 §4, ADR-0033 §5

## Context

ADR-0033 §4 commits the app to a double-submit CSRF defence. Every state-changing request (POST/PUT/PATCH/DELETE) must carry an `X-CSRF-Token` header (HTMX-driven) or a `_csrf_token` form field (classic HTML form posts) matching the per-browser `__Host-csrf` cookie. HTMX reads the cookie via a small extension and injects the header on every request.

The middleware sits between `SecurityHeadersMiddleware` and the (future) `AuthRequiredMiddleware` so that:

- the token exists before the login form renders;
- 403 responses still carry request-id and the baseline security headers (ADR-0033 §5).

## Deliverables

1. `src/budget_planner/web/middleware/csrf.py` — Starlette `BaseHTTPMiddleware`:
   - Reads `__Host-csrf`; mints `secrets.token_urlsafe(32)` when absent.
   - Attaches the cookie with `Path=/`, `SameSite=Lax`, and `Secure` on every env except `dev` (where plain HTTP localhost would otherwise reject it). `HttpOnly` is **off** so the HTMX extension can read the cookie — the token is a nonce, not a credential.
   - Enforces matching token on unsafe methods; mismatch → `403 {"detail": "invalid_csrf"}`.
   - Exempt paths: `/health`, `/ready`, `/healthz`. Extend by appending to `_EXEMPT_PATHS`.
   - Form-field fallback (`_csrf_token`) buffers and replays the request body so FastAPI handlers still see the full payload.
2. `src/budget_planner/web/static/htmx-csrf.js` — HTMX extension registered via `htmx.defineExtension("csrf", …)`. Reads `__Host-csrf` from `document.cookie`, attaches `X-CSRF-Token` on POST/PUT/PATCH/DELETE.
3. `base.html` — loads `/static/htmx-csrf.js` after HTMX and sets `hx-ext="csrf"` on `<body>`.
4. `app.add_middleware(CSRFMiddleware)` wired after `RequestIdMiddleware` + `SecurityHeadersMiddleware`.
5. `rendering.py` — surfaces `request.state.csrf_token` as `csrf_token` in the shared Jinja context.
6. Integration test `tests/integration/web/test_csrf.py` covers:
   - priming GET sets the cookie,
   - unsafe method without cookie → 403 `missing_cookie`,
   - unsafe method with matching header → 200,
   - unsafe method with mismatched header → 403 `invalid_csrf`,
   - form-field fallback,
   - exempt-path bypass,
   - cookie stability across requests,
   - dev drops `Secure`, production keeps it,
   - Jinja context contains `csrf_token`.
7. `tests/integration/web/conftest.py` wraps the shared `client` fixture in a `_CSRFAwareTestClient` that auto-primes the cookie and auto-attaches the header on mutating requests so the 170+ existing POST assertions keep working without churn. The fixture pins `base_url="https://testserver"` so httpx's Secure-cookie policy is satisfied.
8. `tests/e2e/conftest.py` boots the uvicorn subprocess with `BUDGET_ENV=dev` + a well-known cookie secret (plain-HTTP e2e cannot carry a `Secure` cookie) and the `page` fixture primes `__Host-csrf` through Playwright's `APIRequestContext` + sets `extra_http_headers` on the browser context.

## Acceptance criteria

- `uv run pytest tests/integration/web/test_csrf.py` → all cases green.
- `uv run pytest` full suite green at ≥90 % coverage (1122 passed in local run).
- `uv run ruff check src tests` clean.
- `uv run mypy src tests` clean against the new module.

## Non-goals

- Signed/HMAC-wrapped tokens — the double-submit cookie is the full guarantee for v3. If the project moves to a stricter per-session signed token later, this file is the touch-point.
- Rate limiting the auth routes (T-D09) and the full auth layer (T-D02).

## Risks / notes

- `__Host-` requires `Secure`; Chrome/Firefox treat `http://localhost` and `http://127.0.0.1` as potentially-trustworthy so Secure cookies still work for the dev / e2e stacks. The explicit dev-mode drop is kept as a belt-and-braces fallback for any non-localhost HTTP dev scenario.
- The middleware consumes the request body when a form payload is advertised. The implementation buffers the raw body and replaces `request._receive` with a replay generator so downstream FastAPI form parsing sees the full body — mirrors Starlette's own form-parsing recipe.
