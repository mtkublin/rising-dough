# T-D06 — Structured JSON logging + request-id binding

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: nothing (consumes the existing `RequestIdMiddleware`)
- **Blocks**: Phase 2 cloud-init (journald needs stable JSON lines), Phase 4 observability
- **References**: ADR-0032 §8

## Context

v1 logs as `key=value` strings via `logging.Formatter`. Phase 2 ships to Scaleway where `journalctl` is the only log sink; a JSON renderer plus a request-id contextvar makes `jq` triage realistic without pulling in a log aggregator (deferred to v3.1 per `tasks.md` "Deferred").

## Deliverables

1. `pyproject.toml`: add `structlog>=24.4` to the runtime dependency group. `uv lock` refreshes `uv.lock`.
2. `src/budget_planner/logging.py`: structlog config — JSON renderer, ISO timestamp, `request_id` contextvar wired into every event.
3. `src/budget_planner/web/app.py`: `_configure_logging` delegates to `budget_planner.logging.configure(...)`. The function stays idempotent. Uvicorn's `uvicorn.access` / `uvicorn` loggers get the same JSON formatter so access logs are grep-friendly.
4. `src/budget_planner/web/middleware/request_id.py`: `bind_contextvars(request_id=...)` on request entry, `clear_contextvars()` on exit (via `try/finally` around `call_next`).

## Acceptance criteria

- `tests/unit/web/test_logging.py` uses `structlog.testing.LogCapture` to assert:
  - every log event carries an ISO `timestamp` and `event` key,
  - a log emitted inside a request includes the active `request_id`,
  - a log emitted outside a request has no `request_id` leaked from a previous request (contextvar cleared).
- Running the app (local) emits valid JSON on stdout. Spot-check in dev.

## Validation hook

```sh
uv lock
just test tests/unit/web/test_logging.py
just typecheck
```
