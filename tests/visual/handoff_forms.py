"""Browser recipes of the handoff overlay states that follow a POST (T-UR00b, ADR-0147).

``add-user--error``, ``invite-user--error`` and ``one-time-password`` show what the server
answers to a submitted dialog: a 422 with the typed values, or the generated one-time password.
The harness opens the dialog (``handoff_openers``), fills the fields the handoff shows and
presses the submit control in the real page, so the CSRF token travels with the form and the
dialog is the app's own answer (HTMX swaps it into ``#modal-root``).

The one-time password is random per request (``SecretsTokenSource``, no injected seed in the
served process), so its glyphs cannot equal the handoff's fixed sample; only its shape is fixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

_SUBMIT = "#modal-root dialog[open] button[type=submit]"


@dataclass(frozen=True)
class DialogSubmit:
    """Fields to fill (selector, value), the control to press, the element showing the answer."""

    fills: tuple[tuple[str, str], ...]
    press: str
    answer: str


# overlay page -> recipe; the values are what the handoff shows typed in the form.
DIALOG_SUBMITS: Final[dict[str, DialogSubmit]] = {
    "pages/overlays/add-user--error.html": DialogSubmit(
        fills=(
            ("#modal-root input[name=email]", "partner@example.test"),
            ("#modal-root input[name=name]", "Ola"),
        ),
        press=_SUBMIT,
        answer="#modal-root .rd-field__error",
    ),
    "pages/overlays/invite-user--error.html": DialogSubmit(
        fills=(("#modal-root input[name=email]", "partner@example.test"),),
        press=_SUBMIT,
        answer="#modal-root .rd-field__error",
    ),
    "pages/overlays/one-time-password.html": DialogSubmit(
        fills=(),
        press="#modal-root dialog[open] button[name=reset]",
        answer="#modal-root .rd-secret__value",
    ),
}


def submit_dialog(page: Any, handoff_page: str) -> None:
    """Fill and submit the open dialog of ``handoff_page``; wait for the server's answer."""
    recipe = DIALOG_SUBMITS[handoff_page]
    for selector, value in recipe.fills:
        page.fill(selector, value)
    page.click(recipe.press)
    page.wait_for_selector(recipe.answer, timeout=15000)
