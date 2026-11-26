"""Formula terms: errors, percent parsing and term building (ADR-0047).

Split from ``recurring_formula`` (G25); that module re-exports every public name.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from budget_planner.domain.money import (
    bps_to_percent,
    format_bps_percent,
    parse_percent_str,
    percent_to_bps,
)
from budget_planner.domain.recurring import (
    FORMULA_SCHEMA_VERSION,
    AmountFormula,
    FormulaTerm,
    TermSign,
)

# Basis-point ceiling: 10 000% — formula sanity guard, not a product
# limit. Anything above this is almost certainly a data-entry mistake
# (coefficient_bps=120 ≠ 1200 confusion). Floor is 1 bps (0.01%).
_BPS_MIN = 1
_BPS_MAX = 1_000_000


class FormulaError(ValueError):
    """Raised when a formula fails validation at the save boundary."""


class FormulaCycleError(FormulaError):
    """Raised when a formula would create a dependency cycle (ADR-0047)."""


FORMULA_CYCLE_MARK = "formula cycle"


# ---------------------------------------------------------------------------
# Parsing + building (used by routers + tests)
# ---------------------------------------------------------------------------
def parse_percent_to_bps(percent_str: str) -> int:
    """Convert a decimal percent string ("12", "12.5", "0.075") to int bps.

    Rounds half-up to the nearest basis point. Raises :class:`FormulaError`
    on non-decimal input or out-of-range values. Accepts "," as a decimal
    separator (same policy as ``domain.money.parse_amount_str``).
    """
    normalised = (percent_str or "").strip().replace(",", ".")
    if not normalised:
        raise FormulaError("coefficient is required for formula rules")
    dec = parse_percent_str(normalised)
    if dec is None:
        raise FormulaError("coefficient must be a decimal number")
    bps = percent_to_bps(dec)
    if bps < _BPS_MIN or bps > _BPS_MAX:
        raise FormulaError(
            f"coefficient must be between {format_bps_percent(_BPS_MIN)}% "
            f"and {format_bps_percent(_BPS_MAX)}%"
        )
    return bps


def term_input_rows(formula: AmountFormula) -> list[dict[str, object]]:
    """Persisted formula terms as form-shaped rows (percent string, sign, category ids)."""
    return [
        {
            "sign": term.sign,
            "coefficient_percent": format(bps_to_percent(term.coefficient_bps).normalize(), "f"),
            "source_category_ids": tuple(term.source_category_ids),
        }
        for term in formula.terms
    ]


def _parse_sign(raw: str) -> TermSign:
    cleaned = (raw or "+").strip()
    if cleaned not in {"+", "-"}:
        raise FormulaError("term sign must be '+' or '-'")
    return "+" if cleaned == "+" else "-"


def build_term(
    *,
    sign: str,
    coefficient_percent: str,
    source_category_ids: Iterable[int],
) -> FormulaTerm:
    """Validate + build a single :class:`FormulaTerm` from form inputs."""
    parsed_sign = _parse_sign(sign)
    bps = parse_percent_to_bps(coefficient_percent)
    seen: set[int] = set()
    cleaned: list[int] = []
    for raw in source_category_ids:
        cid = int(raw)
        if cid in seen:
            continue
        seen.add(cid)
        cleaned.append(cid)
    if not cleaned:
        raise FormulaError("each term needs at least one source category")
    return FormulaTerm(
        sign=parsed_sign,
        coefficient_bps=bps,
        source_category_ids=tuple(cleaned),
    )


def build_formula(terms: Sequence[FormulaTerm]) -> AmountFormula:
    """Wrap a validated terms list into an :class:`AmountFormula`.

    Non-empty terms list required. Each term must already pass :func:`build_term`.
    """
    if not terms:
        raise FormulaError("formula needs at least one term")
    return AmountFormula(terms=tuple(terms), schema_version=FORMULA_SCHEMA_VERSION)
