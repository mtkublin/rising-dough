"""Formula preview on the recurring forms (T-D-UT12-3, ADR-0056 §4, ADR-0047, T-UR10).

Editing formula terms posts the draft to ``/recurring/formula/preview`` and swaps the
result next to the terms: the computed amount, or the inline error. The preview is a
pure read: it never closes the form and writes no row. The first journey drives the
old "+ Add" overlay of the ledger (until T-UR09), the second the edit-recurring dialog.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, days_from_today
from tests.e2e.ui_actions import choose_account, choose_category, open_new_entry
from tests.ui_map import edit_dialogs, entries, ledger
from tests.ui_map.locator import Locator, label

pytestmark = pytest.mark.e2e

LEDGER_ALL_TIME = "/ledger?view=actual&date_from=2000-01-01&date_to=2099-12-31"
LEDGER_RECURRING = "/ledger?view=recurring&date_from=2000-01-01&date_to=2099-12-31"


def _pick(world: World, field: Locator, option: str) -> None:
    box = world.find(ledger.overlay_field(field))
    box.click()
    box.fill(option)
    world.find(ledger.combo_option(option)).click()


def _open_formula_source(world: World, category: str) -> None:
    """Pick a source in the newest term: its picker is the only one still reading "pick sources"."""
    world.find(ledger.formula_pick_sources).click()
    world.find(ledger.formula_source(category)).last.check()  # closed pickers are not visible


def test_two_term_formula_shows_computed_preview(world: World) -> None:
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    bonus = world.category("Bonus", "income")
    world.category("Savings", "expense")
    world.rule(account, salary, "1000.00", "salary-rule")
    world.rule(account, bonus, "200.00", "bonus-rule")
    rules_before = world.scalar("SELECT COUNT(*) FROM recurring_rules")
    world.goto(LEDGER_ALL_TIME)
    open_new_entry(world.page)
    world.find(entries.tab_repeats).click()
    expect(world.find(entries.tab_repeats)).to_have_attribute("aria-current", "page")
    choose_category(world.page, "Savings")
    choose_account(world.page, "Checking")
    world.find(entries.amount_formula).check(force=True)

    world.find(entries.formula_pick).click()
    world.find(label("Salary", exact=True).inside(entries.formula_group)).check(force=True)
    world.find(entries.formula_percent).press_sequentially("50")  # keyup fires the preview
    expect(world.find(entries.formula_result)).to_contain_text("500.00")

    world.find(entries.formula_add_component).click()
    world.find(entries.formula_subtract).nth(1).check(force=True)
    world.find(entries.formula_pick).click()  # only the new component still reads "pick categories"
    world.find(label("Bonus", exact=True).inside(entries.formula_group)).nth(1).check(force=True)
    world.find(entries.formula_percent).nth(1).press_sequentially("10")
    expect(world.find(entries.formula_result)).to_contain_text("480.00")

    expect(world.find(entries.dialog)).to_be_visible()  # the preview did not close it
    assert world.scalar("SELECT COUNT(*) FROM recurring_rules") == rules_before


def test_add_component_keeps_the_first_component_sign(world: World) -> None:
    """The cloned component shared the radio group, so component 0 lost its "-" (T-UR58)."""
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    bonus = world.category("Bonus", "income")
    savings = world.category("Savings", "expense")
    world.rule(account, salary, "1000.00", "salary-rule")
    world.rule(account, bonus, "200.00", "bonus-rule")
    world.goto(LEDGER_ALL_TIME)
    open_new_entry(world.page)
    world.find(entries.tab_repeats).click()
    expect(world.find(entries.tab_repeats)).to_have_attribute("aria-current", "page")
    choose_category(world.page, "Savings")
    choose_account(world.page, "Checking")
    world.find(entries.amount_formula).check(force=True)

    world.find(entries.formula_subtract).check(force=True)
    world.find(entries.formula_pick).click()
    world.find(label("Bonus", exact=True).inside(entries.formula_group)).check(force=True)
    world.find(entries.formula_percent).press_sequentially("10")
    expect(world.find(entries.formula_result)).to_contain_text("non-positive")  # -20.00 alone

    world.find(entries.formula_add_component).click()
    world.find(entries.formula_pick).click()  # only the new component still reads "pick categories"
    world.find(label("Salary", exact=True).inside(entries.formula_group)).nth(1).check(force=True)
    world.find(entries.formula_percent).nth(1).press_sequentially("50")

    expect(world.find(entries.formula_subtract).first).to_be_checked()
    expect(world.find(entries.formula_result)).to_contain_text("480.00")  # 520.00 without the sign

    world.find(entries.field_note.inside(entries.dialog)).fill("sign-check")
    world.find(entries.save).click()
    expect(world.find(entries.dialog)).to_be_hidden()
    raw = world.scalar(
        "SELECT amount_formula FROM recurring_rules WHERE category_id = ?", (savings,)
    )
    terms = json.loads(raw)["terms"]
    assert [(t["sign"], t["coefficient_bps"], t["source_category_ids"]) for t in terms] == [
        ("-", 1000, [bonus]),
        ("+", 5000, [salary]),
    ]


def test_changing_the_start_date_to_the_source_month_updates_the_preview(world: World) -> None:
    """R7: a source starting next month has no amount today; the start date picks the month."""
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    world.category("Savings", "expense")
    source_start = days_from_today(40)  # always a later month than today
    world.rule(account, salary, "1000.00", "later-salary", start=source_start)
    world.goto(LEDGER_ALL_TIME)
    open_new_entry(world.page)
    world.find(entries.tab_repeats).click()
    expect(world.find(entries.tab_repeats)).to_have_attribute("aria-current", "page")
    choose_category(world.page, "Savings")
    choose_account(world.page, "Checking")
    world.find(entries.amount_formula).check(force=True)
    world.find(entries.formula_pick).click()
    world.find(label("Salary", exact=True).inside(entries.formula_group)).check(force=True)
    world.find(entries.formula_percent).press_sequentially("50")
    expect(world.find(entries.formula_result)).to_contain_text("no recurring amounts")

    world.find(entries.field_start.inside(entries.dialog)).fill(source_start)  # no other input
    expect(world.find(entries.formula_result)).to_contain_text("500.00")


def test_formula_cycle_shows_the_error_and_keeps_the_edit_dialog_open(world: World) -> None:
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    savings = world.category("Savings", "expense")
    rule_a = world.rule(account, salary, "1000.00", "salary-rule")
    world.post(
        "/recurring",
        {
            "cadence": "monthly",
            "start_date": days_from_today(3),
            "category_id": str(savings),
            "account_id": str(account),
            "amount_source": "formula",
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "10",
            "terms[0][source_category_ids]": str(salary),
            "default_description": "savings-rule",
        },
    )
    audit_before = world.scalar("SELECT COUNT(*) FROM audit_log")
    world.goto("/today")
    # No menu opens the edit dialog yet (the ledger rows move in T-UR10a): ask the route directly.
    world.page.evaluate(
        "(url) => window.htmx.ajax('GET', url, {target: '#modal-root', swap: 'innerHTML'})",
        f"/recurring/{rule_a}/edit",
    )
    dialog = edit_dialogs.recurring_dialog("salary-rule")
    expect(world.find(dialog)).to_be_visible()
    world.find(edit_dialogs.amount_formula(dialog)).dispatch_event("click")
    world.find(edit_dialogs.formula_pick(dialog)).click()
    world.find(edit_dialogs.formula_option(dialog, "Savings")).dispatch_event("click")
    world.find(edit_dialogs.formula_percent(dialog)).fill("10")
    world.find(edit_dialogs.formula_percent(dialog)).press(
        "Tab"
    )  # the change event posts the preview

    result = world.find(edit_dialogs.formula_result.inside(dialog))
    # the message names a rule of the cycle (the new check meets the savings rule first)
    expect(result).to_contain_text(re.compile(r"formula would create a cycle via rule \d+"))
    expect(result).to_have_attribute("data-code", "cycle")
    expect(world.find(dialog)).to_be_visible()  # the preview did not close it
    assert world.scalar("SELECT COUNT(*) FROM audit_log") == audit_before


PREVIEW_URL = "/recurring/formula/preview"


class _Watch:
    """Preview requests and console errors seen since the page opened (T-UR89)."""

    def __init__(self, world: World) -> None:
        self.posts: list[str] = []
        self.errors: list[str] = []
        world.page.on(
            "request",
            lambda r: self.posts.append(r.url) if r.url.endswith(PREVIEW_URL) else None,
        )
        world.page.on(
            "console", lambda m: self.errors.append(m.text) if m.type == "error" else None
        )


def test_new_entry_formula_without_terms_sends_no_preview(world: World) -> None:
    """No term yet: typing elsewhere posts nothing; one term -> one preview; cleared -> quiet."""
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    world.category("Savings", "expense")
    world.rule(account, salary, "1000.00", "salary-rule")
    world.goto(LEDGER_ALL_TIME)
    watch = _Watch(world)
    open_new_entry(world.page)
    world.find(entries.tab_repeats).click()
    expect(world.find(entries.tab_repeats)).to_have_attribute("aria-current", "page")
    choose_category(world.page, "Savings")
    choose_account(world.page, "Checking")
    world.find(entries.amount_formula).check(force=True)
    world.find(entries.field_start.inside(entries.dialog)).fill(days_from_today(2))
    world.find(entries.field_note.inside(entries.dialog)).press_sequentially("abc")
    world.page.wait_for_timeout(800)  # past the keyup delay
    assert watch.posts == []
    assert watch.errors == []

    world.find(entries.formula_pick).click()
    world.find(label("Salary", exact=True).inside(entries.formula_group)).check(force=True)
    world.find(entries.formula_percent).press_sequentially("50")
    expect(world.find(entries.formula_result)).to_contain_text("500.00")
    sent = len(watch.posts)
    assert sent >= 1

    world.find(entries.formula_percent).fill("")
    world.find(label("Salary", exact=True).inside(entries.formula_group)).uncheck(force=True)
    world.page.wait_for_timeout(800)
    expect(world.find(entries.formula_result)).to_have_count(0)  # hidden: quiet state
    after_clear = len(watch.posts)
    world.find(entries.field_note.inside(entries.dialog)).press_sequentially("d")
    world.page.wait_for_timeout(800)
    assert len(watch.posts) == after_clear  # a partial term may answer 422; none never posts


def test_edit_dialog_formula_without_terms_sends_no_preview(world: World) -> None:
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    rule_id = world.rule(account, salary, "1000.00", "salary-rule")
    world.goto("/today")
    watch = _Watch(world)
    world.page.evaluate(
        "(url) => window.htmx.ajax('GET', url, {target: '#modal-root', swap: 'innerHTML'})",
        f"/recurring/{rule_id}/edit",
    )
    dialog = edit_dialogs.recurring_dialog("salary-rule")
    expect(world.find(dialog)).to_be_visible()
    world.find(edit_dialogs.amount_formula(dialog)).dispatch_event("click")
    world.find(edit_dialogs.amount_formula(dialog)).dispatch_event("change")
    world.page.wait_for_timeout(800)
    assert watch.posts == []
    assert watch.errors == []

    world.find(edit_dialogs.formula_percent(dialog)).fill("10")
    world.find(edit_dialogs.formula_percent(dialog)).press("Tab")
    world.page.wait_for_timeout(800)
    assert len(watch.posts) >= 1
    posted = len(watch.posts)

    world.find(edit_dialogs.formula_percent(dialog)).fill("")
    world.find(edit_dialogs.formula_percent(dialog)).press("Tab")
    world.page.wait_for_timeout(800)
    assert len(watch.posts) == posted  # a partial term may answer 422; no terms never posts
