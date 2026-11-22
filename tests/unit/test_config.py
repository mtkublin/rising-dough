from __future__ import annotations

import warnings

import pytest

from budget_planner import config as config_module
from budget_planner.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_settings.cache_clear()


def test_defaults_match_requirements() -> None:
    # The root conftest pins ``BUDGET_ENV=test`` so the suite stays quiet;
    # assert against that shape here. Dev-specific behaviour has its own
    # test that overrides via ``monkeypatch``.
    s = Settings(_env_file=None)
    assert s.env == "test"
    assert s.base_currency == "PLN"
    assert s.display_timezone == "Europe/Warsaw"
    assert s.bind_host == "127.0.0.1"
    assert s.bind_port == 8000
    assert s.trusted_hosts == ()
    assert s.session_lifetime_days == 14
    assert s.session_absolute_lifetime_days == 30
    assert s.session_reauth_window_minutes == 10
    assert s.fx_api_url.startswith("https://")


def test_env_prefix_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_BASE_CURRENCY", "eur")
    monkeypatch.setenv("BUDGET_DISPLAY_TIMEZONE", "UTC")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    s = Settings(_env_file=None)
    assert s.base_currency == "EUR"
    assert s.display_timezone == "UTC"


def test_rejects_public_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_BIND_HOST", "0.0.0.0")  # noqa: S104 — asserting rejection
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    with pytest.raises(ValueError, match="loopback"):
        Settings(_env_file=None)


def test_rejects_bad_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_BASE_CURRENCY", "US1")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    with pytest.raises(ValueError, match="ISO 4217"):
        Settings(_env_file=None)


def test_rejects_unknown_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_DISPLAY_TIMEZONE", "Mars/Olympus")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    with pytest.raises(ValueError, match="unknown timezone"):
        Settings(_env_file=None)


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_trusted_hosts_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_TRUSTED_HOSTS", "budget.example.com, api.example.com ,")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    s = Settings(_env_file=None)
    assert s.trusted_hosts == ("budget.example.com", "api.example.com")


def test_trusted_hosts_empty_default() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = Settings(_env_file=None)
    assert s.trusted_hosts == ()


def test_cookie_secret_required_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_ENV", "production")
    with pytest.raises(ValueError, match="cookie_secret is required in production"):
        Settings(_env_file=None)


def test_cookie_secret_dev_fallback_warns(
    monkeypatch: pytest.MonkeyPatch,
    recwarn: pytest.WarningsRecorder,
) -> None:
    monkeypatch.setenv("BUDGET_ENV", "dev")
    s = Settings(_env_file=None)
    assert s.resolve().cookie_secret  # populated by the dev fallback
    assert any("cookie_secret" in str(w.message) for w in recwarn.list)


def test_cookie_secret_test_env_also_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_ENV", "test")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = Settings(_env_file=None)
    assert s.env == "test"
    assert s.resolve().cookie_secret


def test_session_lifetime_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    monkeypatch.setenv("BUDGET_SESSION_LIFETIME_DAYS", "0")
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        Settings(_env_file=None)
    monkeypatch.setenv("BUDGET_SESSION_LIFETIME_DAYS", "91")
    with pytest.raises(ValueError, match="less than or equal to 90"):
        Settings(_env_file=None)


def test_production_default_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUDGET_DATABASE_URL")  # T-Q231 session fixture sets it
    monkeypatch.setenv("BUDGET_ENV", "production")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    s = Settings(_env_file=None)
    assert s.resolve().database_url == "sqlite:////data/budget.db"


def test_production_db_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_ENV", "production")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x")
    monkeypatch.setenv("BUDGET_WEBAUTHN_RP_ID", "budget.example.eu")
    monkeypatch.setenv("BUDGET_WEBAUTHN_ORIGIN", "https://budget.example.eu")
    monkeypatch.setenv("BUDGET_DATABASE_URL", "sqlite:////srv/custom.db")
    s = Settings(_env_file=None)
    assert s.resolve().database_url == "sqlite:////srv/custom.db"


def _prod_env(monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    monkeypatch.setenv("BUDGET_ENV", "production")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x" * 32)
    for key, value in extra.items():
        monkeypatch.setenv(f"BUDGET_{key.upper()}", value)


def test_webauthn_localhost_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _prod_env(monkeypatch)
    with pytest.raises(ValueError, match="webauthn_rp_id must not be 'localhost'"):
        Settings(_env_file=None)


def test_webauthn_origin_mismatch_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _prod_env(monkeypatch, webauthn_rp_id="budget.example.eu")
    with pytest.raises(ValueError, match=r"webauthn_origin must be 'https://budget\.example\.eu'"):
        Settings(_env_file=None)


def test_webauthn_http_origin_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _prod_env(
        monkeypatch,
        webauthn_rp_id="budget.example.eu",
        webauthn_origin="http://budget.example.eu",
    )
    with pytest.raises(ValueError, match="webauthn_origin must be"):
        Settings(_env_file=None)


def test_webauthn_valid_pair_accepted_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _prod_env(
        monkeypatch,
        webauthn_rp_id="budget.example.eu",
        webauthn_origin="https://budget.example.eu",
    )
    s = Settings(_env_file=None)
    assert s.webauthn_rp_id == "budget.example.eu"


def test_webauthn_localhost_defaults_fine_outside_production() -> None:
    s = Settings(_env_file=None)
    assert s.webauthn_rp_id == "localhost"


def test_bcrypt_rounds_floor_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "PRODUCTION_MIN_BCRYPT_ROUNDS", 12)
    monkeypatch.setenv("BUDGET_ENV", "production")
    monkeypatch.setenv("BUDGET_COOKIE_SECRET", "x" * 32)
    monkeypatch.setenv("BUDGET_BCRYPT_ROUNDS", "4")
    with pytest.raises(ValueError, match="bcrypt_rounds must be >= 12"):
        Settings(_env_file=None)
