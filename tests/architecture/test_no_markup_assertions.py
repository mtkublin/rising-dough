"""ADR-0106 section 2: tests must not assert on markup directly.

Scans ``tests/integration/web/`` and ``tests/e2e/`` (never ``tests/ui_map/``)
for markup-coupled assertions and requires every offender to be in
``ALLOWLIST`` (file -> exact count). The allowlist may only shrink: a file
above its count, a new offending file, or an entry above the actual count
all fail. Lower the number (or delete the entry) when you migrate a test to
the UI map.

Offenders counted, one per source line:
- ``... in <x>.text`` / ``.text`` substring checks (``"..." in r.text``,
  ``"..." not in resp.text``, ``r.text.count(...)``, ``.text.find(...)``);
- ``.select(`` / ``.select_one(`` (BeautifulSoup CSS selectors);
- Playwright ``.locator("<css>")`` calls (any ``.locator(`` call).
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("tests/integration/web", "tests/e2e")

_TEXT_IN = re.compile(r"\b(?:not\s+)?in\s+[\w\.\[\]\"']*\.text\b")
_TEXT_CALL = re.compile(r"\.text\.(?:count|find|index|startswith|endswith|__contains__)\(")
_SELECT = re.compile(r"\.select(?:_one)?\(")
_LOCATOR = re.compile(r"\.locator\(")


def count_offenders(source: str) -> int:
    """Number of source lines containing a markup-coupled assertion.

    Strings and comments are blanked out first so patterns inside literals
    do not count (``"x in r.text"`` as data is not an assertion).
    """
    code = _code_only(source)
    return sum(
        1
        for line in code.splitlines()
        if _TEXT_IN.search(line)
        or _TEXT_CALL.search(line)
        or _SELECT.search(line)
        or _LOCATOR.search(line)
    )


def _code_only(source: str) -> str:
    """Return ``source`` with string and comment tokens replaced by spaces.

    Locator arguments are strings, but the ``.locator(`` call itself is code,
    so blanking the argument keeps the call detectable.
    """
    lines = source.splitlines(keepends=True)
    grid = [list(line) for line in lines]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return source
    for tok in tokens:
        if tok.type not in (tokenize.STRING, tokenize.COMMENT, _FSTRING_MIDDLE):
            continue
        (r0, c0), (r1, c1) = tok.start, tok.end
        for r in range(r0 - 1, r1):
            start = c0 if r == r0 - 1 else 0
            end = c1 if r == r1 - 1 else len(grid[r])
            for c in range(start, min(end, len(grid[r]))):
                if grid[r][c] != "\n":
                    grid[r][c] = " "
    return "".join("".join(row) for row in grid)


_FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", -1)


def scan(root: Path = REPO_ROOT, dirs: tuple[str, ...] = SCANNED_DIRS) -> dict[str, int]:
    """Map relative file path -> offender count (only files with offenders)."""
    found: dict[str, int] = {}
    for d in dirs:
        for path in sorted((root / d).rglob("*.py")):
            n = count_offenders(path.read_text(encoding="utf-8"))
            if n:
                found[path.relative_to(root).as_posix()] = n
    return found


# file -> number of offending lines today. May only shrink (ADR-0106 section 2).
ALLOWLIST: dict[str, int] = {
    "tests/integration/web/test_accessibility.py": 4,
    "tests/integration/web/test_accounts.py": 18,
    "tests/integration/web/test_accounts_jpy.py": 1,
    "tests/integration/web/test_accounts_planned.py": 4,
    "tests/integration/web/test_accounts_reconcile_available.py": 4,
    "tests/integration/web/test_app.py": 1,
    "tests/integration/web/test_auth_login.py": 7,
    "tests/integration/web/test_auth_passkey.py": 2,
    "tests/integration/web/test_auth_rate_limit.py": 4,
    "tests/integration/web/test_auth_reauth.py": 5,
    "tests/integration/web/test_base_csp_compat.py": 2,
    "tests/integration/web/test_budget.py": 32,
    "tests/integration/web/test_budget_left_daily_spend.py": 10,
    "tests/integration/web/test_categories.py": 7,
    "tests/integration/web/test_csrf.py": 1,
    "tests/integration/web/test_debug_audit_tail.py": 2,
    "tests/integration/web/test_errors.py": 19,
    "tests/integration/web/test_fab.py": 3,
    "tests/integration/web/test_forecast.py": 17,
    "tests/integration/web/test_forms.py": 3,
    "tests/integration/web/test_formula_preview.py": 3,
    "tests/integration/web/test_ledger.py": 27,
    "tests/integration/web/test_palette.py": 3,
    "tests/integration/web/test_plan_analytics.py": 4,
    "tests/integration/web/test_planned.py": 16,
    "tests/integration/web/test_recurring.py": 33,
    "tests/integration/web/test_recurring_formula.py": 1,
    "tests/integration/web/test_redirects.py": 2,
    "tests/integration/web/test_root_redirect.py": 8,
    "tests/integration/web/test_same_account_validation.py": 6,
    "tests/integration/web/test_settings.py": 6,
    "tests/integration/web/test_settings_password.py": 10,
    "tests/integration/web/test_settings_password_rate_limit.py": 5,
    "tests/integration/web/test_settings_users.py": 13,
    "tests/integration/web/test_today.py": 10,
    "tests/integration/web/test_transactions.py": 26,
    "tests/e2e/conftest.py": 1,
    "tests/e2e/test_accessibility.py": 4,
    "tests/e2e/test_add_transaction_flow.py": 4,
    "tests/e2e/test_credit_card_journey.py": 18,
    "tests/e2e/test_csp_buttons.py": 52,
    "tests/e2e/test_edit_paths.py": 24,
    "tests/e2e/test_ledger_filters.py": 16,
    "tests/e2e/test_logout_back_button.py": 1,
    "tests/e2e/test_override_tier_toggle.py": 12,
    "tests/e2e/test_palette_toast.py": 11,
    "tests/e2e/test_passkey_journey.py": 9,
    "tests/e2e/test_planned_validation.py": 6,
    "tests/e2e/test_reconcile_flow.py": 3,
    "tests/e2e/test_recurring_promote_flow.py": 4,
    "tests/e2e/test_set_budget_flow.py": 3,
}


def compare(actual: dict[str, int], allowlist: dict[str, int]) -> list[str]:
    problems: list[str] = []
    for path, n in sorted(actual.items()):
        allowed = allowlist.get(path)
        if allowed is None:
            problems.append(f"{path}: {n} markup assertion(s), not in allowlist (use tests/ui_map)")
        elif n > allowed:
            problems.append(f"{path}: {n} markup assertion(s) exceeds allowlist {allowed}")
    for path, allowed in sorted(allowlist.items()):
        n = actual.get(path, 0)
        if allowed > n:
            problems.append(
                f"{path}: allowlist says {allowed} but only {n} remain; lower it to {n}"
            )
    return problems


def test_markup_assertions_match_allowlist() -> None:
    problems = compare(scan(), ALLOWLIST)
    assert not problems, "\n".join(problems)


def test_seeded_new_offender_file_fails(tmp_path: Path) -> None:
    web = tmp_path / "tests" / "integration" / "web"
    web.mkdir(parents=True)
    (web / "test_new.py").write_text('def test_x(r):\n    assert "Save" in r.text\n')
    problems = compare(scan(tmp_path), {})
    assert len(problems) == 1
    assert problems[0].startswith("tests/integration/web/test_new.py: 1 markup assertion(s)")


def test_exceeding_allowlisted_count_fails(tmp_path: Path) -> None:
    e2e = tmp_path / "tests" / "e2e"
    e2e.mkdir(parents=True)
    (e2e / "test_a.py").write_text('def t(page):\n    page.locator("#a")\n    page.locator("#b")\n')
    problems = compare(scan(tmp_path), {"tests/e2e/test_a.py": 1})
    assert len(problems) == 1 and "exceeds allowlist 1" in problems[0]


def test_stale_higher_allowlist_count_fails(tmp_path: Path) -> None:
    e2e = tmp_path / "tests" / "e2e"
    e2e.mkdir(parents=True)
    (e2e / "test_a.py").write_text("def t(page):\n    pass\n")
    problems = compare(scan(tmp_path), {"tests/e2e/test_a.py": 2})
    assert len(problems) == 1 and "lower it to 0" in problems[0]


def test_detector_patterns() -> None:
    samples = {
        'assert "x" in r.text': 1,
        'assert "x" not in resp.text': 1,
        "assert r.text.count('x') == 2": 1,
        'soup.select("tr.row")': 1,
        "soup.select_one('#a')": 1,
        'page.locator("input[name=q]")': 1,
        'page.get_by_role("button", name="Save")': 0,
        "assert r.status_code == 200": 0,
        '# "x" in r.text': 0,
        'DATA = "x in r.text"': 0,
        "assert r.json()['text'] == 'x'": 0,
    }
    for src, expected in samples.items():
        assert count_offenders(src + "\n") == expected, src


def test_ui_map_directory_is_not_scanned() -> None:
    assert all("ui_map" not in d for d in SCANNED_DIRS)
