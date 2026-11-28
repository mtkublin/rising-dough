"""Auth + CSRF contract for every ledger-surface route (ADR-0106 section 1, T-UT04c).

One parametrised matrix over all 43 routes: unauthenticated requests are bounced
to login (or 401 for HTMX), and every mutating route rejects a request without a
valid CSRF token.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi.testclient import TestClient

from tests.contract.conftest import covers

Ids = dict[str, int]

KEYS: Final[tuple[str, ...]] = (
    "GET /ledger",
    "GET /ledger/table",
    "GET /ledger/recently-deleted",
    "GET /ledger/recently-deleted/panel",
    "GET /transactions",
    "GET /transactions/_limit_preview",
    "GET /transactions/table",
    "POST /transactions",
    "GET /transactions/{txn_id}/edit",
    "POST /transactions/{txn_id}",
    "POST /transactions/{txn_id}/delete",
    "POST /transactions/{txn_id}/restore",
    "GET /transactions/export",
    "POST /planned/batch/promote-due",
    "POST /planned/batch/undo",
    "GET /planned/table",
    "POST /planned",
    "GET /planned/{planned_id}/edit",
    "POST /planned/{planned_id}",
    "POST /planned/{planned_id}/delete",
    "POST /planned/{planned_id}/restore",
    "GET /planned/{planned_id}/promote",
    "POST /planned/{planned_id}/promote",
    "GET /planned/export",
    "POST /recurring",
    "POST /recurring/formula/preview",
    "GET /recurring/{rule_id}/edit",
    "POST /recurring/{rule_id}",
    "POST /recurring/{rule_id}/deactivate",
    "GET /recurring/{rule_id}/overrides/new",
    "POST /recurring/{rule_id}/overrides",
    "POST /recurring/{rule_id}/overrides/{occurrence_date}/delete",
    "GET /recurring/{rule_id}/promote",
    "POST /recurring/{rule_id}/promote",
    "POST /recurring/{rule_id}/skip-next",
)
_PARAMS: Final = {
    "txn_id": "txn",
    "planned_id": "pl",
    "rule_id": "rule",
}


def concrete_path(key: str, ids: Ids) -> str:
    """Turn a route key into a request path using the seeded ids."""
    path = key.split(" ", 1)[1].replace("{occurrence_date}", "2026-01-01")
    for param, seed in _PARAMS.items():
        path = path.replace("{" + param + "}", str(ids[seed]))
    return path


ROUTES: Final = [(k, k.split(" ", 1)[0]) for k in KEYS]
MUTATING: Final = [r for r in ROUTES if r[1] == "POST"]


def test_matrix_lists_every_ledger_route() -> None:
    assert len(ROUTES) == 35
    assert len(set(KEYS)) == 35


@covers(*KEYS)
@pytest.mark.parametrize(("key", "method"), ROUTES, ids=[r[0] for r in ROUTES])
def test_anonymous_request_redirects_to_login(
    anon_client: TestClient, seeded: Ids, key: str, method: str
) -> None:
    r = anon_client.request(method, concrete_path(key, seeded), follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login?next=")


@covers(*KEYS)
@pytest.mark.parametrize(("key", "method"), ROUTES, ids=[r[0] for r in ROUTES])
def test_anonymous_htmx_request_gets_401(
    anon_client: TestClient, seeded: Ids, key: str, method: str
) -> None:
    r = anon_client.request(
        method, concrete_path(key, seeded), headers={"HX-Request": "true"}, follow_redirects=False
    )
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


@covers(*(k for k, _ in MUTATING))
@pytest.mark.parametrize(("key", "method"), MUTATING, ids=[r[0] for r in MUTATING])
def test_mutation_without_csrf_token_is_rejected(
    raw_client: TestClient, seeded: Ids, key: str, method: str
) -> None:
    raw_client.cookies.delete("__Host-csrf")
    r = raw_client.post(concrete_path(key, seeded), data={})
    assert r.status_code == 403
    assert r.json() == {"detail": "missing_cookie"}


@covers(*(k for k, _ in MUTATING))
@pytest.mark.parametrize(("key", "method"), MUTATING, ids=[r[0] for r in MUTATING])
def test_mutation_with_wrong_csrf_header_is_rejected(
    raw_client: TestClient, seeded: Ids, key: str, method: str
) -> None:
    raw_client.get("/health")  # mint the cookie
    r = raw_client.post(concrete_path(key, seeded), data={}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert r.json() == {"detail": "invalid_csrf"}
