# ADR-0144: Pure-ASGI Middleware; the `[[framework]]` Category Is What Starlette Forces

- **Status**: Accepted
- **Date**: 2026-11-22
- **Relates to**: [ADR-0021](0021-functional-style-no-oop.md), [ADR-0033](0033-v3-auth-single-user-passkey.md), [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md)
- **Finding**: B-13 (framework rows), compliance-inventory section 16 E04 and section 17 question 2; task T-Q274 (follows T-Q254, T-Q235)

## Context

ADR-0130 accepted `BaseHTTPMiddleware` subclasses, `APIRouter` singletons and `logging.Filter` as a permanent `[[framework]]` allowlist category. T-Q254 and T-Q235 showed the pure-ASGI function shape works for the outermost layers. Six user middlewares were still classes.

## Decision

1. Convert every remaining middleware class to a pure-ASGI function `x_middleware(app) -> ASGIApp` built with `web/middleware/asgi.py::http_only`: `request_id_middleware`, `auth_required_middleware`, `cache_control_middleware`, `must_change_password_middleware`, `admin_required_middleware`, `csrf_middleware`. Order, status codes, headers, cookies and log-id binding are unchanged (security headers stay outermost).
2. Scope and response mutation goes through helpers in `asgi.py` only: `set_state` (`scope["state"]`, i.e. `request.state`), `set_header`, `add_cookie` (reuses the `Response`-based cookie writers on a throwaway response), `sets_cookie`. The single `param-mutation:framework` entry for `asgi.py` is the only new `[[framework]]` row; the 13 class and mutation rows of the converted modules are deleted.
3. CSRF buffers a form body once and replays it, then defers to the real `receive` (so `http.disconnect` stays visible); the previous private `request._receive` swap is gone.
4. What stays a permanent `[[framework]]` entry (reason in the TOML): `APIRouter` module singletons in routers, `web/htmx.py` response-header mutation, the `logging.Filter` subclass, and `asgi.py::set_state`. These are imposed by FastAPI/Starlette/stdlib; converting them adds indirection with no purity gain.

## Consequences

- No `BaseHTTPMiddleware` left: no per-request task hop, and contextvars (request id) are bound in the request's own task.
- `response_sets_cookie` in `auth_cookies.py` is replaced by `asgi.sets_cookie`.
- Adding a middleware means a function plus `http_only`; a class fails G20.
