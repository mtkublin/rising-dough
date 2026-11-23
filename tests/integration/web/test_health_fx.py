"""T-Q292 / ADR-0146: GET /health/fx (public, read-only, fail closed)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import accounts, fx as fx_repo
from budget_planner.web.app import create_app


@pytest.fixture
def cfg(tmp_path: Path) -> Settings:
    db_url = f"sqlite:///{(tmp_path / 'fx.sqlite').as_posix()}"
    cfg = Settings(_env_file=None, database_url=db_url, fx_refresh_enabled=True)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
        conn.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    finally:
        conn.close()
    return cfg


def _seed(cfg: Settings, *, user_id: int, ccy: str, rate_age_days: int | None) -> None:
    conn = get_connection(cfg)
    try:
        accounts.create(conn, user_id, NewAccount(name=f"{ccy} acc", currency=ccy))
        if rate_age_days is not None:
            day = clock.today_local(cfg) - timedelta(days=rate_age_days)
            fx_repo.upsert_rate(
                conn, NewFxRate(date=day, from_ccy=ccy, to_ccy="PLN", rate=Decimal("4.2"))
            )
    finally:
        conn.close()


def _get(cfg: Settings) -> tuple[int, dict[str, object]]:
    r = TestClient(create_app(settings=cfg)).get("/health/fx", follow_redirects=False)
    return r.status_code, r.json()


def test_ok_exact_body_counts_second_users_account(cfg: Settings) -> None:
    _seed(cfg, user_id=2, ccy="EUR", rate_age_days=4)
    code, body = _get(cfg)
    newest = (clock.today_local(cfg) - timedelta(days=4)).isoformat()
    assert code == 200
    assert body["status"] == "ok"
    assert body["currencies"] == [{"code": "EUR", "newest_date": newest, "age_days": 4}]
    assert body["max_age_days"] == 4
    assert isinstance(body["checked_at"], str)
    assert set(body) == {"status", "currencies", "max_age_days", "checked_at"}


def test_stale_is_503_with_ages(cfg: Settings) -> None:
    _seed(cfg, user_id=2, ccy="EUR", rate_age_days=5)
    _seed(cfg, user_id=1, ccy="USD", rate_age_days=0)
    code, body = _get(cfg)
    assert code == 503
    assert body["status"] == "stale"
    currencies = body["currencies"]
    assert isinstance(currencies, list)
    assert [(c["code"], c["age_days"]) for c in currencies] == [("EUR", 5), ("USD", 0)]


def test_never_is_503(cfg: Settings) -> None:
    _seed(cfg, user_id=2, ccy="CHF", rate_age_days=None)
    code, body = _get(cfg)
    assert (code, body["status"]) == (503, "never")
    assert body["currencies"] == [{"code": "CHF", "newest_date": None, "age_days": None}]


def test_enabled_without_foreign_account_is_ok_and_inactive_is_disabled(cfg: Settings) -> None:
    code, body = _get(cfg)
    assert (code, body["status"], body["currencies"]) == (200, "ok", [])
    _seed(cfg, user_id=1, ccy="EUR", rate_age_days=None)
    inactive = cfg.model_copy(update={"fx_refresh_enabled": False})
    assert _get(inactive)[0] == 200
    assert _get(inactive)[1]["status"] == "disabled"


def test_database_failure_fails_closed() -> None:
    broken = Settings(_env_file=None, database_url="sqlite:////dev/null", fx_refresh_enabled=True)
    code, body = _get(broken)
    assert (code, body["status"], body["currencies"]) == (503, "error", [])


def test_head_has_no_body_and_same_status(cfg: Settings) -> None:
    _seed(cfg, user_id=1, ccy="EUR", rate_age_days=9)
    r = TestClient(create_app(settings=cfg)).head("/health/fx")
    assert (r.status_code, r.content) == (503, b"")


def _prod(cfg: Settings, **update: object) -> Settings:
    return cfg.model_copy(
        update={
            "env": "production",
            "cookie_secret": "x" * 32,
            "trusted_hosts": ("testserver",),
            "webauthn_rp_id": "budget.example.test",
            "webauthn_origin": "https://budget.example.test",
            **update,
        }
    )


def test_production_with_refresh_disabled_is_503_disabled(cfg: Settings) -> None:
    code, body = _get(_prod(cfg, fx_refresh_enabled=False))
    assert (code, body["status"], body["currencies"]) == (503, "disabled", [])


def test_non_production_with_refresh_disabled_is_200_disabled(cfg: Settings) -> None:
    code, body = _get(cfg.model_copy(update={"fx_refresh_enabled": False}))
    assert (code, body["status"], body["currencies"]) == (200, "disabled", [])


def test_production_enabled_fresh_is_200_and_stale_is_503(cfg: Settings) -> None:
    _seed(cfg, user_id=1, ccy="EUR", rate_age_days=1)
    code, body = _get(_prod(cfg))
    assert (code, body["status"]) == (200, "ok")
    _seed(cfg, user_id=1, ccy="USD", rate_age_days=9)
    code, body = _get(_prod(cfg))
    assert (code, body["status"]) == (503, "stale")
