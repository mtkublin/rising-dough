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
