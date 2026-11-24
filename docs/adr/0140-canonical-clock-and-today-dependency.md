# ADR-0140: One Clock, a `today` Dependency, and One Rounding Helper Module

- **Status**: Accepted
- **Date**: 2026-11-21
- **Amends**: [ADR-0007](0007-timezone-handling.md) (the display-zone "today" is now computed in one place), [ADR-0006](0006-multi-currency-model.md) (amendment 2026-11-21: rounding helpers and timestamp format)
- **Relates to**: [ADR-0021](0021-functional-style-no-oop.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0139](0139-canonical-fx-converter-cache-only-one-missing-rate-policy.md)
- **Finding**: Q-031 (A-13, C-08, F-21), Q-076 (C-18, C-19); task T-Q229; resolves OQ-3 and OQ-18 (defaults taken 2026-11-21, pending operator confirmation)

## Context

Twenty-odd call sites read the host clock directly. Half used the naive host `date.today()` (`/forecast`, `/budget`, the FX reference date, ledger status chips), half used the display zone (`/today`, `/plan`). On a UTC host between 00:00 and 01:00/02:00 Warsaw the two disagree, so one page says day N and the next says day N+1. Tests that call `datetime.now(UTC)` fail on the last day of a month and cannot freeze time. The soft-delete undo window compared a `T`-separated stored timestamp with SQLite `datetime('now', ...)` (space-separated), so a row 90 days and 12 hours old stayed listed.

## Decision

1. **`budget_planner/clock.py` is the only module that reads the host clock.** API: `utc_now()` (aware UTC instant), `today_local(settings)` (naive `date` in `settings.display_timezone`), `today(tz)`, `now_in(tz)`, `utc_now_iso()` / `iso_utc(instant)` (the stored timestamp text), and `frozen(instant)`. The override is a `ContextVar` (task and thread local); tests and the visual suite pin time through `clock.frozen`, never by patching `datetime`.
2. **Services never read the clock.** `today` / `now` are required arguments of pure services (no `None` fallback to the host). Routers get "today" from the FastAPI dependency `web.deps.get_today` (`clock.today_local(settings)`), repositories that stamp rows call `clock.utc_now()`. The existing `app.state.reauth_clock` / `rate_limit_clock` test hooks stay; their default is `clock.utc_now()`.
3. **One notion of "today": the display-zone date.** The host process timezone (`TZ`) is irrelevant to app logic; compose keeps `TZ` for log timestamps only.
4. **Enforcement.** Ruff `TID251` bans `datetime.date.today`, `datetime.datetime.now`, `datetime.datetime.utcnow` and `time.time` in `src/`; the per-file ignores for migrated files are deleted, and so are the `DTZ011` `noqa` comments. `clock.py` stays the one exempt file.
5. **Stored timestamp format.** Python writers and the retention/undo cutoffs use `clock.iso_utc` / `utc_now_iso`: `YYYY-MM-DDTHH:MM:SS.mmmZ` (millisecond precision, the same text SQLite's `strftime('%Y-%m-%dT%H:%M:%fZ','now')` produces). Cutoffs for the undo window and the personal-data retention purge are computed in Python in that format, so comparisons are always text-to-text of one format. Never compare against `datetime('now', ...)`.
6. **OQ-3 (tzdata in the image): yes.** The runtime venv carries the PyPI `tzdata` wheel (transitive dependency of `python-dateutil` and `pandas`, pinned in `uv.lock`), so `ZoneInfo("Europe/Warsaw")` resolves regardless of the OS image. A unit test resolves the zone. No Dockerfile change. Default taken 2026-11-21, pending operator confirmation. Confirmed by operator 2026-11-24.
7. **OQ-18 (display zone): Europe/Warsaw is the only supported display zone.** `Settings.display_timezone` stays a configurable IANA name (the code is zone-agnostic); only Warsaw is tested and supported. Default taken 2026-11-21, pending operator confirmation. Confirmed by operator 2026-11-24 (Europe/Warsaw is the default display zone, configurable via the validated `display_timezone` setting).

## Rounding (see the ADR-0006 amendment dated 2026-11-21, T-Q229)

`domain/money.py` owns `round_div(numerator, denominator, *, mode)` and `round_scaled(value, *, mode)`. The mode is an explicit argument; each call site keeps the mode it had, so no user-visible amount changes. Unifying to one mode is an operator question (OQ-ROUND).

## Consequences

- The `/today` vs `/forecast` midnight disagreement and the month-end test flake go away; INV-8 is a plain passing test.
- Callers of `balance_series`, `planned_base_amounts` and `list_planned` pass `today` explicitly.
- Allowlist entries removed: purity `eff-clock` (4), banned-patterns `banned-name` for `templating.py` and the `money-primitive` entries, money-scope `money-round` entries, the `DTZ011` ceiling, the INV-8 xfail.

## Amendment 2026-11-23 (T-Q311): a frozen test clock for the whole suite, a CI date matrix, no SQLite clock

Why: release CI of v3.1.1 failed on 2026-11-23 because a test passed a fixed `TODAY` to services while a repository (legitimately) read the real clock. Date-dependent tests passed on the day they were written and failed "after midnight". The control is to make the wall date irrelevant by default and to prove it on dangerous dates on every PR.

1. **Every test runs under `clock.frozen(...)`.** An autouse fixture in `tests/conftest.py` wraps each test. The instant is `BUDGET_TEST_NOW` (ISO datetime, `Z` or offset, naive means UTC) and defaults to `2026-11-21T12:00:00Z`. An unparseable value fails at `pytest_configure`. No freezegun or time-machine: the in-house clock stays the only source (single-clock rule, ruff TID251).
2. **Opt-out marker `real_clock`** (registered in `pyproject.toml`). Use it only when real time is the thing under test, with the reason in the test.
3. **Propagation.** `clock.frozen` is a `ContextVar`. `tests/integration/web/test_frozen_clock.py` proves it reaches sync and async routes run through Starlette's `TestClient` (anyio portal thread plus worker thread), so no process-level override is added to `clock.py`. `tests/e2e` and the visual suite drive a separate server process and stay on the real clock (or pin it through their own server settings); they are excluded from the matrix.
4. **CI date matrix.** `ci.yml` job `pytest (shifted clock)` runs `pytest -m "not e2e"` once per `BUDGET_TEST_NOW`: month end `2027-01-31T23:30:00Z`, leap day `2028-02-29T12:00:00Z`, year end `2026-12-31T23:30:00Z`, Warsaw DST switch `2027-03-28T01:30:00Z`. A test that fails on one of them is fixed at its cause (seed under the test's date, pass `today` explicitly), never by editing expected numbers, xfail or skip.
5. **No SQLite clock at runtime (guard G32, `tests/architecture/test_sql_now.py`).** `'now'` (`date`, `datetime`, `strftime`), `CURRENT_TIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIME` are banned in every string literal under `src/`. `migrations/` is excluded: migrations run once, in order, as immutable history (ADR-0007); column `DEFAULT (strftime(..., 'now'))` fallbacks and the one-off backfill in 0015 are not runtime queries. Stamps written by updates (`updated_at`, `deleted_at`, `fetched_at`) are now bound parameters from `clock.utc_now_iso()`: `repositories/_shared.py` (`update_sql`, `soft_delete_sql`, `undelete_sql`), `planned.py`, `preferences.py`, `fx.py`, `_unaudited.py` (6 runtime sites fixed, zero allowlist entries). Known remainder: inserts that rely on the `created_at` column default still read the host clock; a later task may pass it explicitly.
