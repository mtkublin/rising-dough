"""Delete dialog wording and links follow the account references (T-UR08b)."""

from __future__ import annotations

from datetime import UTC, datetime

from budget_planner.config import Settings
from budget_planner.domain.accounts import Account, AccountReferences
from budget_planner.web.accounts_view import delete_dialog
from budget_planner.web.templating import build_jinja_env

_NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _acc(name: str = "Checking") -> Account:
    return Account(
        id=4,
        user_id=1,
        name=name,
        type="bank",
        currency="PLN",
        opening_balance=0,
        is_liability=False,
        credit_limit_minor=None,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )


def test_unreferenced_zero_balance_account_gets_the_confirm() -> None:
    dlg = delete_dialog(_acc("Investments E"), AccountReferences(0, 0, 0), 0)
    assert (dlg.blocked, dlg.title, dlg.action) == (
        False,
        "Delete Investments E?",
        "/accounts/4/delete",
    )
    assert dlg.text == (
        "Nothing points at it: no transactions, planned or recurring items. "
        "This can\u2019t be undone."
    )


def test_transactions_and_planned_items_block_with_both_counts() -> None:
    dlg = delete_dialog(_acc(), AccountReferences(84, 2, 1), 0)
    assert dlg.blocked
    assert dlg.title == "Can\u2019t delete Checking"
    assert dlg.text == (
        "It still has 84 transactions and 3 planned or recurring items. "
        "Move or delete them first."
    )
    assert (dlg.link_label, dlg.link_href) == (
        "view 84 transactions",
        "/ledger?account_id=4&view=actual",
    )


def test_recurring_only_blocks_with_a_link_to_the_rules() -> None:
    dlg = delete_dialog(_acc("Investments D"), AccountReferences(0, 0, 2), 0)
    assert dlg.text == (
        "It has no transactions, but 2 recurring rules still use it. Move or delete them first."
    )
    assert (dlg.link_label, dlg.link_href) == (
        "view recurring rules",
        "/ledger?account_id=4&view=recurring",
    )


def test_planned_only_blocks_with_a_link_to_the_planned_items() -> None:
    dlg = delete_dialog(_acc(), AccountReferences(0, 1, 0), 0)
    assert dlg.text == (
        "It has no transactions, but 1 planned item still uses it. Move or delete them first."
    )
    assert dlg.link_href == "/ledger?account_id=4&view=planned"


def test_non_zero_balance_alone_blocks_without_a_link() -> None:
    dlg = delete_dialog(_acc(), AccountReferences(0, 0, 0), 12_345)
    assert dlg.blocked
    assert dlg.text == "Its balance is 123.45 PLN. Bring it to zero first."
    assert (dlg.link_label, dlg.link_href) == ("", "")


def test_dialog_macro_form_id_is_optional_and_backward_compatible() -> None:
    env = build_jinja_env(Settings(_env_file=None))
    src = (
        '{% from "fragments/dialogs/dialog.html" import dialog %}'
        '{% call dialog("d", "t", form_id=fid) %}x{% endcall %}'
    )
    with_id = env.from_string(src).render(fid="my-form")
    without = env.from_string(src).render(fid="")
    assert '<form class="rd-dialog__form" id="my-form"' in " ".join(with_id.split())
    assert "id=" not in without.split("<form", 1)[1].split(">", 1)[0]
