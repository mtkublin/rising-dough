# E2E journeys

Real uvicorn + temp SQLite + Playwright. Local only: GitHub runners have no
Playwright browser (ADR-0097). Setup once: `uv run playwright install chromium firefox webkit`.

- `just test-e2e [ARGS]` runs `tests/e2e` on Chromium with `--no-cov`. Extra
  args pass through (`just test-e2e tests/e2e/test_x.py -k name`).
- `just test-e2e-browsers [ARGS]` runs the same journeys on Firefox, then
  WebKit, one engine at a time. Opt-in; not part of `just ci` (ADR-0106 §4).
- The engine is chosen with `--e2e-browser={chromium,firefox,webkit}`
  (default chromium; see `tests/e2e/conftest.py`).

Known per-browser failures on the old UI live in `BROWSER_XFAILS` in
`tests/e2e/conftest.py` as `xfail(strict=True)` with a reason. They never
apply to Chromium; a fix turns them XPASS and fails, so remove the entry then.
Currently: the three passkey journeys use a CDP virtual authenticator, which
exists only in Chromium.

Other targets: `just test-e2e --target=mockup ...` runs the UI-map journeys
against the frozen handoff (`--target` is registered in `tests/conftest.py`).

The app server must answer within `E2E_SERVER_READY_TIMEOUT_S` seconds
(default 60). Raise it on a loaded machine, e.g.
`E2E_SERVER_READY_TIMEOUT_S=120 just test-e2e`. A server that exits early
fails immediately regardless.

Verified 2026-11-20 (macOS 14.5, Playwright WebKit build 2251): Chromium 50
passed / 2 skipped; Firefox 47 passed / 2 skipped / 3 xfailed (the passkey
journeys). WebKit did not run on that host: `browser.new_page()` hangs after
launch (page init never completes), so every test stalls at its first page.
That is a host/engine problem, not a journey failure; re-verify on another
machine and record the counts here (any real WebKit failures become
`BROWSER_XFAILS` entries).
