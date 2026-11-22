"""Every route needs a ``@covers`` contract test or an allowlist entry (ADR-0106 section 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_planner.web.app import create_app
from tests.contract.route_allowlist import ALLOWLIST
from tests.contract.route_inventory import check_coverage, collect_covered, collect_routes
from tests.contract.routes_md import ROUTES_MD, render

HERE = Path(__file__).parent
_SELF = frozenset({"test_route_coverage.py", "conftest.py"})


@pytest.fixture(scope="module")
def routes() -> tuple:  # type: ignore[type-arg]
    return collect_routes(create_app())


def test_inventory_matches_allowlist_and_covers(routes: tuple) -> None:  # type: ignore[type-arg]
    keys = frozenset(r.key for r in routes)
    covered = collect_covered(HERE, skip=_SELF)
    assert check_coverage(keys, covered, ALLOWLIST) == ()


def test_inventory_is_not_empty(routes: tuple) -> None:  # type: ignore[type-arg]
    assert len(routes) > 100
    assert {"GET /today", "POST /auth/login"} <= {r.key for r in routes}


def test_routes_md_is_current(routes: tuple) -> None:  # type: ignore[type-arg]
    assert ROUTES_MD.read_text(encoding="utf-8") == render(routes), "run `just routes`"


# --- pure function ---------------------------------------------------------

ROUTES = frozenset({"GET /a", "POST /a", "GET /b"})


def test_check_passes_when_every_route_covered_or_allowlisted() -> None:
    assert check_coverage(ROUTES, frozenset({"GET /a"}), {"POST /a": "x", "GET /b": "x"}) == ()


def test_check_fails_when_allowlist_entry_removed_without_test() -> None:
    problems = check_coverage(ROUTES, frozenset({"GET /a"}), {"POST /a": "x"})
    assert problems == ("uncovered route (add @covers or allowlist): GET /b",)


def test_check_fails_on_stale_allowlist_entry() -> None:
    problems = check_coverage(ROUTES, ROUTES, {"GET /gone": "x"})
    assert problems == ("stale allowlist entry (route gone): GET /gone",)


def test_check_fails_when_route_is_both_covered_and_allowlisted() -> None:
    problems = check_coverage(ROUTES, ROUTES, {"GET /a": "x"})
    assert problems == ("allowlisted but covered (remove the allowlist entry): GET /a",)


def test_check_fails_on_covers_naming_unknown_route() -> None:
    problems = check_coverage(ROUTES, ROUTES | {"GET /nope"}, {})
    assert problems == ("@covers names unknown route: GET /nope",)


def test_collect_covered_reads_markers_statically(tmp_path: Path) -> None:
    (tmp_path / "test_x.py").write_text(
        "from tests.contract.conftest import covers\n"
        "@covers('GET /a', 'POST /a')\n"
        "def test_a(): ...\n"
        "@pytest.mark.covers('GET /b')\n"
        "def test_b(): ...\n"
    )
    assert collect_covered(tmp_path) == {"GET /a", "POST /a", "GET /b"}
