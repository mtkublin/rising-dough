"""Plan · year tab and the budget override dialogs on the Rising Dough markup (T-UR11, ADR-0107).

The handoff (``pages/plan/year.html`` and ``pages/overlays/override--*.html``) and the app render
the same markup, so one module serves both targets. The plan tabs and the period nav live in
``plan_budget`` and ``rd_fragments``; dialog helpers in ``rd_dialogs``.
"""

from __future__ import annotations

import re

from tests.ui_map import rd_dialogs, rd_fragments
from tests.ui_map.locator import Locator, role

hero = role("region", "Yearly budget")
heading = role("heading", "Yearly budget", level=1)
panel = role("region", "Yearly budget grid")

# The grid: one row per category, one link per month
table_region = role("region", re.compile(r"^Budget per category and month"))
table = role("table", re.compile(r"^Budget per category and month"))
rows = role("row").inside(table)
column_headers = role("columnheader").inside(table)
month_headers = role(
    "columnheader", re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$")
).inside(table)
current_month_header = role("columnheader", "OCT").inside(table)
cells = role("link", re.compile(r"^[^:]+, [A-Z][a-z]+: ")).inside(table)

# Year picker (period nav in year mode)
period_label = role("button", re.compile(r"^\d{4}")).inside(rd_fragments.period_nav)
period_prev = role("link", "Previous year", exact=True).inside(rd_fragments.period_nav)
period_next = role("link", "Next year", exact=True).inside(rd_fragments.period_nav)
picker_years = role("link", re.compile(r"^\d{4}$")).inside(role("dialog", "Pick period"))

# Categories without a budget
disclosure = role("button", re.compile(r"without a budget$"))


def row(category_name: str) -> Locator:
    return role("row", category_name).inside(table)


def row_cells(category_name: str) -> Locator:
    """The twelve month links of one category row."""
    return role("link").inside(row(category_name))


def cell(category_name: str, month_name: str) -> Locator:
    """One month link, named ``<Category>, <Month>: <amount> PLN, <state>`` (full month name)."""
    return role("link", re.compile(rf"^{re.escape(category_name)}, {month_name}: ")).inside(table)


def cell_editor(category_name: str, month_name: str) -> Locator:
    """The inline editor of a cell (``<Category>, <Month> budget``), open after a plain click."""
    return role("textbox", f"{category_name}, {month_name} budget", exact=True).inside(table)


# Inline cell editor scope chips (F4.8a): one editor is open at a time
cell_scope_group = role("radiogroup", "budget scope")
cell_scope_chips = role("radio").inside(cell_scope_group)


def cell_scope(label_text: str) -> Locator:
    """A scope chip of the inline editor: ``this month only`` / ``every <month>`` / default."""
    # the checked chip prints a leading check mark (chip.css), which is part of its name
    return role("radio", re.compile(rf"^(✓ )?{re.escape(label_text)}$")).inside(cell_scope_group)


def unbudgeted(category_name: str) -> Locator:
    """A category in the "without a budget" disclosure (a link in the app)."""
    return role("link", category_name, exact=True)


# --- Override dialogs (budget row menu and year cell) -------------------------
def dialog(category_name: str, period_label: str) -> Locator:
    """The app's dialog of a budgeted category (R4: "edit budget")."""
    return rd_dialogs.dialog(f"edit budget · {category_name} · {period_label}")


def set_dialog(category_name: str) -> Locator:
    """The app's dialog of a category without a budget (R4: "set budget")."""
    return rd_dialogs.dialog(f"set budget · {category_name}")


def handoff_dialog(category_name: str, period_label: str) -> Locator:
    """The handoff's dialog title (pre-R4: "override budget"); the app no longer prints it."""
    return rd_dialogs.dialog(f"override budget · {category_name} · {period_label}")


def tier(scope: Locator, label_text: str) -> Locator:
    """A scope radio: ``this month only`` / ``every <month>`` / ``every month (default)``.

    The handoff still prints ``new default`` for the last one.
    """
    return role("radio", label_text, exact=True).inside(scope)


def amount(scope: Locator) -> Locator:
    return rd_dialogs.hero_amount(scope)


def save(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "[ save ]")


def cancel(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "cancel")


def remove_override(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "remove override")


def remove_dialog() -> Locator:
    return rd_dialogs.alert_dialog("Remove override?")


def confirm_remove(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "remove")


def keep(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "keep")
