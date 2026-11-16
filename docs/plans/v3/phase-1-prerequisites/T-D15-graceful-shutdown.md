# T-D15 — Graceful shutdown via lifespan + SIGTERM observer

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: T-D06 (structured log emits on SIGTERM)
- **Blocks**: T-D11 (compose smoke needs a clean exit code), ADR-0034 §6 Litestream flush window
- **References**: ADR-0034 §6

## Context

Litestream needs ~30 s to flush WAL after the app stops writing (ADR-0034 §6). Docker Compose honours `stop_grace_period`, but the app must exit cleanly on SIGTERM — uvicorn drains in-flight requests when the ASGI lifespan `shutdown` event is handled correctly.

v1 wires routes but never installs a lifespan. On SIGTERM, uvicorn's default drain still works, but there is no observability line that the signal was received and no explicit cleanup of app-scoped connections (future-proofing for when `app.state` grows connection pools).

## Deliverables

1. `src/budget_planner/web/app.py`:
   - Replace the implicit lifespan with an `@asynccontextmanager` that:
     - startup: no-op (routers already own their startup paths).
     - shutdown: closes any app-scoped sqlite connections if present on `app.state`; emits a structured log line `event="lifespan_shutdown"`.
   - Install a `signal.signal(SIGTERM, ...)` handler that emits `event="sigterm_received"` via structlog. The handler does **not** call `sys.exit` — uvicorn still owns the drain.
2. `tests/integration/web/test_graceful_shutdown.py`:
   - `subprocess.Popen` boots `uvicorn budget_planner.web.app:app` on an ephemeral port.
   - Hits `/health` to confirm it is up.
   - Sends SIGTERM.
   - Asserts `proc.wait(timeout=10)` returns exit code 0.

## Acceptance criteria

- Integration test green locally and in CI.
- Running `kill -TERM <pid>` against a dev uvicorn emits a structured `sigterm_received` log line before uvicorn exits.

## Validation hook

```sh
just test tests/integration/web/test_graceful_shutdown.py
```
