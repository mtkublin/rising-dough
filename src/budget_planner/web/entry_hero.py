"""The new-entry dialog hero: the amount input or the formula result (T-UR07b, T-UR00b).

The amount shows back as the user typed it, grouped at the currency exponent (domain.money);
the handoff signs a computed formula amount like a typed one.
"""

from __future__ import annotations

from collections.abc import Mapping

from budget_planner.domain.money import format_major, parse_amount_minor


def typed_amount(raw: str, currency: str) -> str:
    """The amount the user typed, shown back grouped (``13,000.00``) when it is a plain figure.

    Text that is not a non-negative amount of the currency stays as typed, so a 422 echoes it.
    """
    minor = parse_amount_minor(raw, currency)
    return raw if minor is None or minor < 0 else format_major(minor, currency, grouped=True)


def new_entry_hero(
    tab: str,
    values: Mapping[str, str],
    *,
    currency: str,
    sign: object,
    errors: Mapping[str, str],
    formula: tuple[str, str] | None,
) -> dict[str, object]:
    """The dialog hero: the amount input (account currency, category sign) or the formula result."""
    if tab == "repeats" and values.get("amount_source") == "formula":
        figure, note = formula or ("\N{EM DASH}", "")
        prefix = "\N{RIGHTWARDS ARROW} next amount "
        next_amount = note.removeprefix(prefix) if note.startswith(prefix) else None
        return {
            "currency": currency,
            "sign": sign,  # the handoff signs the computed amount like the typed one
            "amount_id": "seg-amount-source",
            "output": True,
            "amount_value": figure,
            # The handoff shows "next amount" under "+ add component", not in the hero band.
            "note": "" if next_amount else note,
            "next_amount": next_amount,
        }
    name = "default_amount" if tab == "repeats" else "amount"
    return {
        "currency": currency,
        "sign": sign,
        "amount_id": f"field-{name}",
        "amount_name": name,
        "amount_value": typed_amount(values.get(name, ""), currency),
        "placeholder": format_major(0, currency),
        "error": errors.get(name),
    }
