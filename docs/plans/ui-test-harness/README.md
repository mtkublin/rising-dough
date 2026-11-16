# UI Behaviour Test Harness

> **What**: pin the app's UI behaviour with tests that do not depend on today's markup, so the Sourdough redesign ([`../ui-redesign/`](../ui-redesign/README.md)) can be done test-first.
> **Decision**: [ADR-0106](../../adr/0106-ui-behaviour-test-harness.md). Requirements: [`docs/requirements.md` §9](../../requirements.md#9-ui-behaviour-test-harness-added-2026-11-16).
> **When**: after v3 ships. May run in parallel with the quality-audit remediation (`../quality-audit/`, T-Q2xx), because it only touches `tests/` and the docs. Must be complete before the redesign starts (T-UR00).
> **Tasks**: [`tasks.md`](tasks.md) (T-UT01…T-UT12).

## Why

The redesign replaces every template, all CSS and the presentational JS. Today's tests cannot tell a real regression from a moved button:

| Suite | Today | Problem for the redesign |
|---|---|---|
| `tests/integration/web/` (47 files) | about 200 `in r.text` assertions, about 100 BeautifulSoup `.select(...)` parses | copy and class names change → mass red for the wrong reason |
| `tests/e2e/` (8 journeys) | 46 CSS `locator(...)`, 4 `get_by_*` | same; also too few journeys |
| `tests/visual/` | 5 routes × 3 viewports of the old design | baselines of screens being replaced |
| — | no route or feature inventory | parity with the handoff cannot be checked |

## Shape (ADR-0106)

```
tests/
├── contract/            HTTP + HTMX contract per route; route-coverage meta-test
├── ui_map/              semantic names → role / label / id locators, one module per surface
│   ├── _html.py           role/label/id resolver over BeautifulSoup (server-side checks)
│   ├── shell.py today.py ledger.py plan.py accounts.py settings.py auth.py errors.py
├── e2e/
│   ├── test_crawl.py      generated: activate every control on every page
│   ├── crawl_inventory.json
│   └── test_*_journey.py  journeys on UI-map names only
└── visual/              references from the handoff during the redesign (ADR-0106, amends ADR-0027 §4)
docs/plans/ui-test-harness/
└── parity.md            current feature ↔ handoff page/overlay, gaps as decisions
```

## Exit criteria

1. Every route in `app.routes` has a contract test, or an allowlisted reason (meta-test green).
2. No assertion in `tests/integration/web/` or `tests/e2e/` reads raw class names or copy; everything goes through `tests/ui_map/` (static check green).
3. The crawler is green on today's UI at 375 and 1440, and `crawl_inventory.json` is committed.
4. The journey list in T-UT08 is green on Chromium.
5. `parity.md` is complete and every gap has an operator decision.
6. The UI map resolves against the handoff for at least the Today surface (`--target=mockup`), proving the seam works before the redesign starts.
7. `just ci` green; no access to `data/budget.sqlite` at any point.

## Guardrails

- **No redesign work here.** Template changes are limited to adding `id` or `data-testid` hooks when role/label lookups are ambiguous, each listed in the task handoff.
- **Behaviour is frozen.** A test that exposes a real bug records it (new T-D/T-Q task) and is marked `xfail(strict=True)` with the task id. It is not fixed inside this effort.
- **Prod DB is hands off.** Crawler and journeys run on temp copies of a seeded scratch DB.
- **Orchestrator mode** (ADR-0066) for the parallel tasks: one worktree per item, item agents run scoped tests only, one `just ci` per merge batch (ADR-0097).
