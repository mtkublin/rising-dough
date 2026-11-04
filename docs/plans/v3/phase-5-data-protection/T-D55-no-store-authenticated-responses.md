# T-D55 — `no-store` on authenticated responses; logout clears site data

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: yes (coordinate middleware order with T-D53)
- **Depends on**: T-D02b, T-D07
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §2, [ADR-0070](../../../adr/0070-auth-web-layer-cookies-middleware-order.md) §6

## Context

Only two routes send `Cache-Control: no-store`. After logout, the back button or a shared machine's disk cache can still show financial pages to someone who is not logged in.

## Deliverables

1. `web/middleware/cache_control.py` — pure-ASGI middleware: if `request.state.user` is set (authenticated) and the path is not under `/static/`, set `Cache-Control: no-store` (overwrite weaker values). Registered inside `AuthRequiredMiddleware` so `request.state.user` is populated; document position in ADR-0070 §6 order list via an addendum line in ADR-0078.
2. `POST /auth/logout` and self-revoke add `Clear-Site-Data: "cache", "storage"`.
3. Remove now-redundant per-route `no-store` lines only if covered by the middleware (keep `/settings/users` explicit — harmless).

## Acceptance criteria

- Integration: every authenticated GET of `/today`, `/ledger`, `/budget`, `/accounts`, `/settings/security`, one HTMX partial, and one JSON route returns `no-store`; `/static/css/*`, `/health`, `/ready`, `/auth/login` (unauthenticated) are unchanged.
- Logout response carries `Clear-Site-Data`.
- E2E (Playwright): log in → open `/ledger` → log out → `page.go_back()` → login page or fresh redirect, never the cached ledger.

## Validation hook

```sh
just test tests/integration/web/test_cache_control.py tests/e2e/test_logout_back_button.py
```
