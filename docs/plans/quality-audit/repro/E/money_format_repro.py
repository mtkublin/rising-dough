"""T-Q08: templates format money as ``"{:,.2f}".format(minor / 100.0)`` instead of the filters.

Compares that inline expression with the ``money_num`` filter for a 0-decimal currency.
Run: ``uv run python docs/plans/quality-audit/repro/E/money_format_repro.py``.
"""

from __future__ import annotations

from budget_planner.web.templating import _money_num_filter

MINOR = 123456
for ccy in ("PLN", "JPY"):
    inline = "{:,.2f}".format(MINOR / 100.0)  # noqa: UP032 - mirrors the template expression
    print(f"{ccy}: inline template expr -> {inline:>12}   money_num filter -> {_money_num_filter(MINOR, ccy):>12}")
