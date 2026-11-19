"""Hand-made mutants for T-Q11 V3.

Applies ONE mutation in place, runs only the targeted unit test file(s) with
--no-cov -n 0, and always reverts the file with `git checkout --` afterwards.
Usage: python mutate.py [mutant-id ...]   (from anywhere)
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[6]
S = "src/budget_planner/"
U = "tests/unit/"
RF = [U + "services/test_recurring_formula.py"]
FC = [U + "services/test_forecast.py", U + "services/test_forecast_monthly.py"]
RC = [U + "services/test_reconciliation.py", U + "services/test_reconciliation_available.py"]

M = [
    ("F-01a", S + "domain/money.py", 'sign = "-" if value < 0 else ""', 'sign = "-" if value <= 0 else ""', [U + "domain/test_money.py"]),
    ("F-01b", S + "domain/money.py", "{currency.upper()}", "{currency}", [U + "domain/test_money.py"]),
    ("F-02a", S + "services/recurring_formula.py", 'return int(dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))', 'return int(dec.quantize(Decimal("1"), rounding=None))', RF),
    ("F-02b", S + "services/recurring_formula.py", 'bps_dec = (dec * _PERCENT_TO_BPS).quantize(Decimal("1"), rounding=ROUND_HALF_UP)', 'bps_dec = (dec * _PERCENT_TO_BPS).quantize(Decimal("1"), rounding=None)', RF),
    ("F-03a", S + "services/forecast.py", "if (rule.id, occ.occurrence_date) in dedup_keys:", "if False:", FC),
    ("F-03b", S + "services/forecast.py", "if _rule_outside_window(rule, event_start, end_date):\n            continue", "if _rule_outside_window(rule, event_start, end_date):\n            break", FC),
    ("F-03c", S + "services/forecast.py", "    if rule.start_date > window_end:\n        return True", "    if rule.start_date >= window_end:\n        return True", FC),
    ("F-03d", S + "services/forecast.py", "    return rule.end_date is not None and rule.end_date < window_start", "    return rule.end_date is not None and rule.end_date <= window_start", FC),
    ("F-03e", S + "services/forecast.py", "    if cutoff < month_start:\n        return 0", "    if cutoff <= month_start:\n        return 0", FC),
    ("F-04a", S + "services/budget.py", "    return date(year, month, 1), date(year, month, last_day)", "    return date(year, month, 2), date(year, month, last_day)", [U + "services/test_budget.py"]),
    ("F-04b", S + "services/budget.py", "    if count <= 0:\n        return 0\n    quantised", "    if count < 0:\n        return 0\n    quantised", [U + "services/test_budget.py"]),
    ("F-05a", S + "services/recurring.py", "            new=updated_rule,\n            user_id=user_id,\n        )\n    return txn", "            new=updated_rule,\n            user_id=None,\n        )\n    return txn", [U + "services/test_recurring.py"]),
    ("F-05b", S + "services/recurring.py", "            if rule.next_due > today:\n                continue\n            override = _resolve_override_for_next_due(", "            if rule.next_due >= today:\n                continue\n            override = _resolve_override_for_next_due(", [U + "services/test_recurring.py"]),
    ("F-06a", S + "services/fx.py", "        timeout=_HTTP_TIMEOUT,\n    )\n    response.raise_for_status()", "        timeout=None,\n    )\n    response.raise_for_status()", [U + "services/test_fx.py"]),
    ("F-06b", S + "services/fx.py", "    rate = hit.rate if hit is not None else _fallback(conn, on_date, from_ccy, to_ccy)", "    rate = hit.rate if hit is not None else _fallback(conn, None, from_ccy, to_ccy)", [U + "services/test_fx.py"]),
    ("F-07a", S + "services/reconciliation.py", "    if credit_limit_minor <= 0:", "    if credit_limit_minor <= 1:", RC),
    ("F-07b", S + "services/reconciliation.py", "        chosen = categories_repo.find_by_id(conn, user_id, category_id)\n        if chosen is None:", "        chosen = None\n        if chosen is None:", RC),
    ("F-08a", S + "services/balance.py", "list_all(conn, user_id, include_deleted=True)\n    }", "list_all(conn, user_id, include_deleted=False)\n    }", [U + "services/test_balance.py"]),
    ("F-08b", S + "services/balance.py", "TransactionFilter(account_or_dest=account_id, up_to_date=as_of)", "TransactionFilter(account_or_dest=None, up_to_date=as_of)", [U + "services/test_balance.py"]),
    ("F-09a", S + "services/balance.py", "account = accounts_repo.find_by_id(conn, user_id, account_id, include_deleted=True)", "account = accounts_repo.find_by_id(conn, None, account_id, include_deleted=True)", [U + "services/test_balance.py"]),
    ("F-09b", S + "services/balance.py", "txns = _txns_affecting(conn, user_id, account_id, as_of=as_of_date)", "txns = _txns_affecting(conn, None, account_id, as_of=as_of_date)", [U + "services/test_balance.py"]),
    ("F-09c", S + "services/forecast.py", "        overrides = recurring_repo.list_overrides(conn, user_id, rule.id)\n        direction = directions_by_cat[rule.category_id]", "        overrides = recurring_repo.list_overrides(conn, None, rule.id)\n        direction = directions_by_cat[rule.category_id]", FC),
    ("F-09d", S + "services/recurring.py", "recurring_repo.mark_override_promoted(conn, user_id, match.id, txn_id=txn.id)", "recurring_repo.mark_override_promoted(conn, None, match.id, txn_id=txn.id)", [U + "services/test_recurring.py"]),
    ("F-10a", S + "services/budget.py", "for cat in categories_repo.list_all(conn, user_id, include_deleted=True)\n        if cat.direction is Direction.EXPENSE", "for cat in categories_repo.list_all(conn, user_id, include_deleted=False)\n        if cat.direction is Direction.EXPENSE", [U + "services/test_budget.py"]),
    ("F-10b", S + "services/recurring.py", "recurring_repo.list_rules(conn, user_id, active_only=True):\n            if rule.next_due > today:", "recurring_repo.list_rules(conn, user_id, active_only=False):\n            if rule.next_due > today:", [U + "services/test_recurring.py"]),
]

only = set(sys.argv[1:])
for mid, rel, old, new, tests in M:
    if only and mid not in only:
        continue
    path = ROOT / rel
    src = path.read_text()
    n = src.count(old)
    if n < 1:
        print(f"{mid}: PATTERN-COUNT {n} (not applied)", flush=True)
        continue
    try:
        path.write_text(src.replace(old, new))
        r = subprocess.run(
            ["uv", "run", "pytest", "--no-cov", "-p", "no:cacheprovider", "-n", "0", "-q", "-x", "-o", "addopts=", *tests],
            cwd=ROOT, capture_output=True, text=True,
        )
        tail = (r.stdout.strip().splitlines() or ["?"])[-1]
        verdict = "KILLED" if r.returncode == 1 else "SURVIVED" if r.returncode == 0 else f"ERR rc={r.returncode}"
        print(f"{mid}: {verdict}  [{tail}]", flush=True)
    finally:
        subprocess.run(["git", "checkout", "--", rel], cwd=ROOT, check=False)
