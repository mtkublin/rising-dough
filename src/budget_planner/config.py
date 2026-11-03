"""Application configuration — single source of truth.

All settings are loaded from environment variables / `.env` on first access.
Values are frozen; mutations raise `pydantic.ValidationError`.
Access via `get_settings()`; the result is cached process-wide.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Default dev DB lives under `data/` (gitignored). CI/tests override via env.
_DEFAULT_SQLITE_PATH: Final = Path("data") / "budget.sqlite"
_DEFAULT_DATABASE_URL: Final = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"
# ADR-0034 §2: production DB lives on the host-mounted volume shared with
# the Litestream sidecar. Four slashes because the path is absolute.
_PROD_DATABASE_URL: Final = "sqlite:////data/budget.db"
# Known dev secret so local work and tests do not need to invent one.
# Treated as a fallback only when ``env`` is ``dev`` or ``test``.
_DEV_COOKIE_SECRET: Final = "dev-only-cookie-secret-change-in-prod"  # noqa: S105 — dev default


Env = Literal["dev", "test", "production"]


class Settings(BaseSettings):
    """Immutable, env-driven settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BUDGET_",
        frozen=True,
        extra="forbid",
    )

    env: Env = Field(default="dev")
    database_url: str = Field(default=_DEFAULT_DATABASE_URL)
    base_currency: str = Field(default="PLN", min_length=3, max_length=3)
    display_timezone: str = Field(default="Europe/Warsaw")
    # Renamed from ``host`` / ``port`` in T-D03 — v3 config surface. The
    # loopback guard carries over from ADR-0005; v3 binds the container
    # loopback and Caddy terminates TLS in front of it (ADR-0036).
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int = Field(default=8000, ge=1, le=65535)
    # Comma-separated list. Consumed by Starlette's
    # ``TrustedHostMiddleware`` once T-D07 lands. ``NoDecode`` tells
    # pydantic-settings to hand the raw env string to our validator
    # instead of trying to JSON-parse it as a complex type.
    trusted_hosts: Annotated[tuple[str, ...], NoDecode] = Field(default=())
    # Required in production. Dev / test fall back to a known value and
    # emit a warning so the fallback is observable.
    cookie_secret: str = Field(default="")
    session_lifetime_days: int = Field(default=14, ge=1, le=90)
    fx_api_url: str = Field(default="https://api.frankfurter.app")
    # ADR-0067 §1: WebAuthn relying-party identity. Production must set
    # these to the deployed hostname and its ``https://`` origin; the
    # defaults only work for ``just dev`` on localhost.
    webauthn_rp_id: str = Field(default="localhost", min_length=1)
    webauthn_rp_name: str = Field(default="Rising Dough", min_length=1)
    webauthn_origin: str = Field(default="http://localhost:8000", min_length=1)
    # ADR-0061 §3 / ADR-0069: admin bootstrap credentials, injected by
    # cloud-init. The env names carry a ``BUDGET_PLANNER_`` prefix (not the
    # model-wide ``BUDGET_``), so they are bound via explicit aliases; the
    # field name stays usable as an init kwarg for tests. Validation of
    # presence happens inside ``services.users.bootstrap_admin`` only.
    # ``pydantic-alias`` ignore: AliasChoices is a dynamic alias by design
    # (env name + field name); both fields have defaults, so the plugin's
    # "required dynamic alias" concern does not apply.
    admin_email: str | None = Field(  # type: ignore[pydantic-alias]
        default=None,
        validation_alias=AliasChoices("BUDGET_PLANNER_ADMIN_EMAIL", "admin_email"),
    )
    admin_initial_password: SecretStr | None = Field(  # type: ignore[pydantic-alias]
        default=None,
        validation_alias=AliasChoices(
            "BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD", "admin_initial_password"
        ),
    )

    @field_validator("base_currency")
    @classmethod
    def _upper_ccy(cls, v: str) -> str:
        v_upper = v.upper()
        if not v_upper.isalpha():
            raise ValueError("base_currency must be a 3-letter ISO 4217 code")
        return v_upper

    @field_validator("admin_email")
    @classmethod
    def _normalise_admin_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalised = v.strip().lower()
        if not normalised:
            return None
        if "@" not in normalised or normalised.startswith("@") or normalised.endswith("@"):
            raise ValueError("BUDGET_PLANNER_ADMIN_EMAIL must be an email address")
        return normalised

    @field_validator("admin_initial_password")
    @classmethod
    def _blank_password_is_unset(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None or not v.get_secret_value():
            return None
        return v

    @field_validator("display_timezone")
    @classmethod
    def _validate_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {v!r}") from exc
        return v

    @field_validator("bind_host")
    @classmethod
    def _reject_public_bind(cls, v: str) -> str:
        # ADR-0005: v1 bound locally; v3 keeps the container-local invariant
        # because Caddy fronts TLS and we never want the uvicorn socket on a
        # public interface directly.
        if v in {"0.0.0.0", "::", "::0"}:  # noqa: S104 — reject, not emit  # nosec B104
            raise ValueError("bind_host must be a loopback address (see ADR-0005 / ADR-0036)")
        return v

    @field_validator("trusted_hosts", mode="before")
    @classmethod
    def _parse_trusted_hosts(cls, v: object) -> object:
        if isinstance(v, str):
            # Allow empty string to represent an empty tuple so env-only
            # deployments that do not need TrustedHostMiddleware do not have
            # to invent a sentinel.
            return tuple(host.strip() for host in v.split(",") if host.strip())
        return v

    @model_validator(mode="after")
    def _finalise(self) -> Settings:
        # T-D04: default the DB path to ``/data/budget.db`` in production
        # when the operator has not overridden it. Dev / test keep the
        # repo-local default so `just dev` works without env plumbing.
        if self.env == "production" and self.database_url == _DEFAULT_DATABASE_URL:
            object.__setattr__(self, "database_url", _PROD_DATABASE_URL)

        # T-D03: cookie_secret policy. Production without a secret is a
        # hard failure; dev falls back to the known-dev value and emits a
        # one-shot warning so the fallback is observable; test env also
        # falls back but stays silent (test runs would otherwise be swamped).
        if not self.cookie_secret:
            if self.env == "production":
                raise ValueError(
                    "cookie_secret is required in production — set BUDGET_COOKIE_SECRET "
                    "to a cryptographically random value (ADR-0033 §5)."
                )
            if self.env == "dev":
                warnings.warn(
                    "cookie_secret empty — falling back to the known dev value. "
                    "Set BUDGET_COOKIE_SECRET to silence this warning.",
                    stacklevel=2,
                )
            object.__setattr__(self, "cookie_secret", _DEV_COOKIE_SECRET)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
