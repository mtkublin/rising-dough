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
    press: str  # "" = the overlay shows the filled form, nothing is submitted
    answer: str  # "" = wait for the server's response only (it may carry no error element)
    checks: tuple[str, ...] = ()  # radio inputs to check (CSS selector)
    skip_validation: bool = False  # submit past the browser's ``required`` check
    refocus: str = ""  # input the handoff file has focused on load (value not selected)
    keep_focus: bool = False  # the handoff shows the typed field focused (thick hero underline)


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
    # T-UR00b W3, F4b. The recipes only type what the handoff file shows (a duplicate category
    # name still answers 500: the comparison shows it). The amount is the focused input of the
    # file, its value not selected (the app selects it on focus, the file's script loads later).
    "pages/overlays/new-account.html": DialogSubmit(
        fills=(), press="", answer="", refocus="#modal-root input[name=opening_balance]"
    ),
    "pages/overlays/new-account--filled.html": DialogSubmit(
        fills=(
            ("#modal-root input[name=opening_balance]", "1,250.00"),
            ("#modal-root input[name=name]", "Revolut EUR"),
            ("#modal-root input[name=currency]", "EUR"),
        ),
        press="",
        answer="",
        refocus="#modal-root input[name=opening_balance]",
    ),
    "pages/overlays/new-account--error.html": DialogSubmit(
        fills=(("#modal-root input[name=currency]", "XYZ"),),
        press=_SUBMIT,
        answer="",
        skip_validation=True,
        refocus="#modal-root input[name=opening_balance]",
    ),
    "pages/overlays/new-category--filled.html": DialogSubmit(
        fills=(("#modal-root input[name=name]", "Pets"),),
        press="",
        answer="",
        checks=("#modal-root .rd-swatch[data-color=sky] input",),
    ),
    "pages/overlays/new-category--error.html": DialogSubmit(
        fills=(("#modal-root input[name=name]", "Takeaway"),),
        press=_SUBMIT,
        answer="",
        skip_validation=True,
    ),
    # T-UR00b F7. The handoff shows the budget override dialogs with the amount typed (the
    # scope radio is the opener's `tier`); the app prefills the default and selects it.
    **{
        f"pages/overlays/override--budget-{tier}.html": DialogSubmit(
            fills=(("#modal-root input[name=amount]", amount),),
            press="",
            answer="",
            keep_focus=True,
        )
        for tier, amount in (("month", "650.00"), ("every", "700.00"), ("default", "650.00"))
    },
}


def submit_dialog(page: Any, handoff_page: str) -> None:
    """Fill (and submit) the open dialog of ``handoff_page``; wait for the server's answer."""
    recipe = DIALOG_SUBMITS[handoff_page]
    for selector, value in recipe.fills:
        page.fill(selector, value)
    for selector in recipe.checks:
        page.check(selector, force=True)
    if recipe.press:
        if recipe.skip_validation:
            page.evaluate("() => { document.querySelector('#modal-root form').noValidate = true; }")
        with page.expect_response(lambda r: r.request.method == "POST", timeout=15000):
            page.click(recipe.press)
        if recipe.answer:
            page.wait_for_selector(recipe.answer, timeout=15000)
        else:
            page.wait_for_load_state("networkidle", timeout=15000)
    if recipe.refocus:
        page.mouse.move(0, 0)  # no hover on the submit control that was pressed
        page.evaluate("sel => document.querySelector(sel).focus()", recipe.refocus)
        page.wait_for_timeout(150)  # the focus handler selects the value one frame later
        page.evaluate(
            "sel => { const el = document.querySelector(sel);"
            " el.setSelectionRange(el.value.length, el.value.length);"
            " getSelection()?.removeAllRanges(); }",
            recipe.refocus,
        )
        return
    # No focus ring or text selection: the handoff files show neither.
    if not recipe.keep_focus:
        page.evaluate("() => document.activeElement?.blur()")
    page.evaluate("() => getSelection()?.removeAllRanges()")
    if "new-category" in handoff_page and "error" not in handoff_page:
        page.focus("#modal-root input[name=name]")  # the category files keep the name field focused
    if handoff_page.endswith("--error.html") and "new-category" not in handoff_page:
        # dialog.js moves focus into the swapped dialog after it opens (a race with the blur above):
        # settle it, then match the file: the invalid field is focused (not new-category--error).
        page.wait_for_timeout(300)
        page.evaluate("() => document.activeElement?.blur()")
        page.evaluate("() => document.querySelector('#modal-root [aria-invalid=true]')?.focus()")
    if "one-time-password" in handoff_page:
        # The file shows the close button focused with its ring: a keyboard user's Tab from the
        # dialog start lands there (a script focus after a pointer press shows no ring).
        page.keyboard.press("Shift")
        page.focus("#modal-root .rd-dialog__close")
    page.mouse.move(0, 0)  # the pointer rests off the dialog, as in the handoff (no hover tint)
