# UI map

One module per surface (`shell`, `today`, `ledger`, `plan`, `accounts`,
`settings`, `auth`, `errors`) naming the elements tests care about
(ADR-0106 section 2). Names are `Locator` values (frozen dataclasses from
`locator.py`) or functions returning one.

```python
from tests.ui_map import _html, ledger
from tests.ui_map.locator import to_playwright

_html.exists(response.text, ledger.row(tx_id))  # server-side (BeautifulSoup)
to_playwright(page, ledger.row_menu(tx_id)).click()  # Playwright
```

Builders (`locator.py`): `role(name, accessible_name, level=, exact=)`,
`label(text, exact=)`, `by_id(id, prefix=)`, `testid(value)` (last resort);
`loc.inside(scope)` scopes a locator. No CSS classes. Resolver
(`_html.py`): `resolve`, `resolve_one`, `exists`, `count`, `text_of`.

`tests/architecture/test_no_markup_assertions.py` blocks `in r.text`,
`.select(` and `.locator(` in `tests/integration/web` and `tests/e2e`; its
allowlist (file -> count) may only shrink. Migrate a test to the UI map,
then lower its count.

## Mockup variants and `--target=mockup` (T-UT09)

The first step of each redesign surface (ADR-0106 sections 2 and 5): add
`tests/ui_map/mockup/<surface>.py` exposing the **same names** as
`tests/ui_map/<surface>.py`, resolved against the handoff markup
(`docs/design/rising-dough-frontend/pages/...`). Handoff has fixed sample rows
and no row ids, so id-parameterised builders return the sample row. Add a
unit test like `test_mockup_today.py` (every name resolves, via `_html`, over
the static page), then map the surface's routes in `mockup_routes.py`
(seeded from `docs/plans/ui-test-harness/parity.md`).

Journeys use `journey.ui("today")` (or `tests.ui_map.target.surface(name,
target)`) so the same `today.<name>` resolves on either target, and
`journey.goto("/today")`, which maps the route to its handoff page under
`--target=mockup`. Run: `pytest --target=mockup tests/e2e/test_today_journey.py`
(plugin `tests/e2e/mockup_target.py`; serves the handoff on 127.0.0.1 with
`stand-in.js` active). Handoff-only flows (e.g. the promote overlay) are
skipped on `--target=app` with a reason. When the redesign lands, the app
module takes the mockup's definitions and the variant is deleted.
