"""Application configuration — single source of truth.

All settings are loaded from environment variables / `.env` on first access.
Values are frozen; mutations raise `pydantic.ValidationError`.
Access via `get_settings()`; the result is cached process-wide.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE

# Default dev DB lives under `data/` (gitignored). CI/tests override via env.
DEFAULT_BASE_CURRENCY: Final = "PLN"
SHA256_HEX_LENGTH: Final = 64
_DEFAULT_SQLITE_PATH: Final = Path("data") / "budget.sqlite"
_DEFAULT_DATABASE_URL: Final = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"
# ADR-0034 §2: production DB lives on the host-mounted volume shared with
# the Litestream sidecar. Four slashes because the path is absolute.
_PROD_DATABASE_URL: Final = "sqlite:////data/budget.db"
# Known dev secret so local work and tests do not need to invent one.
# Treated as a fallback only when ``env`` is ``dev`` or ``test``.
_DEV_COOKIE_SECRET: Final = "dev-only-cookie-secret-change-in-prod"  # noqa: S105 — dev default


Env = Literal["dev", "test", "production"]


@dataclass(frozen=True, slots=True, repr=False)
class ResolvedSettings:
    """Values derived from :class:`Settings` (ADR-0021 amendment, ADR-0130 section 5).

    Built by :meth:`Settings.resolve`; never mutated. ``cookie_secret`` is
    secret, so it is left out of ``repr``.
    """

    database_url: str
    cookie_secret: str

    def __repr__(self) -> str:
        return f"ResolvedSettings(database_url={self.database_url!r}, cookie_secret='***')"


PRODUCTION_MIN_BCRYPT_ROUNDS = 12


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
    base_currency: str = Field(default=DEFAULT_BASE_CURRENCY, min_length=3, max_length=3)
    display_timezone: str = Field(default=DEFAULT_DISPLAY_TIMEZONE)
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
    # T-Q291: bcrypt cost for the injected ``PasswordHasher`` (production 12; tests lower it).
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)
    session_lifetime_days: int = Field(default=14, ge=1, le=90)
    # ADR-0076 §1: hard cap measured from ``sessions.created_at``; sliding
    # expiry never extends past it.
    session_absolute_lifetime_days: int = Field(default=30, ge=1, le=365)
    # ADR-0076 §2: how long a login / re-auth counts as "recent" (T-D53b).
    session_reauth_window_minutes: int = Field(default=10, ge=1, le=60)
    # ADR-0078 §7: age after which audit ip / user_agent are nulled and ended
    # sessions deleted (T-D60).
    retention_personal_days: int = Field(default=90, ge=7, le=3650)
    # ADR-0145: NBP table A host; the adapter appends ``/api/exchangerates/tables/A/``.
    fx_api_url: str = Field(default="https://api.nbp.pl")
    # ADR-0145: in-app daily FX refresh. ``None`` = on in production, off in dev/test.
    fx_refresh_enabled: bool | None = Field(default=None)
    # ADR-0145 amendment: a table dated more than this many days before today is rejected whole.
    fx_max_table_age_days: int = Field(default=7, ge=1, le=60)
    # ADR-0146: ``/health/fx`` is 503 when a used currency's newest rate is older than this.
    fx_max_rate_age_days: int = Field(default=4, ge=1, le=60)
    # ADR-0078 §4 / T-D57: ceiling (days) on the age of any copy of user data
    # outside the live DB. Pre-migration backups are pruned once older than
    # ``backup_max_age_days - 7``. The Terraform twin
    # is ``var.backup_max_age_days`` (bucket noncurrent expiry).
    backup_max_age_days: int = Field(default=37, ge=7, le=365)
    # ADR-0119 / T-D144: status file written by the litestream-probe sidecar.
    # Empty = replication freshness check disabled (dev, prod-sim).
    replication_status_file: str = Field(default="")
    # ADR-0119: newest replica object must be younger than this (24 h snapshot + margin).
    replication_max_age_hours: int = Field(default=26, ge=2, le=720)
    # ADR-0067 §1: WebAuthn relying-party identity. Production must set
    # these to the deployed hostname and its ``https://`` origin; the
    # defaults only work for ``just dev`` on localhost.
    webauthn_rp_id: str = Field(default="localhost", min_length=1)
    webauthn_rp_name: str = Field(default="Rising Dough", min_length=1)
    webauthn_origin: str = Field(default="http://localhost:8000", min_length=1)
    # ADR-0072: fixed-window auth rate limits (counters in ``auth_rate_limit``).
    # ``rate_limit_enabled=False`` is an incident kill switch; tests tighten
    # the per-route limits by constructing ``Settings(...)`` directly.
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_login_per_minute: int = Field(default=5, ge=1)
    rate_limit_login_per_hour: int = Field(default=20, ge=1)
    rate_limit_login_ip_per_hour: int = Field(default=100, ge=1)
    rate_limit_passkey_login_per_minute: int = Field(default=10, ge=1)
    rate_limit_passkey_login_per_hour: int = Field(default=60, ge=1)
    rate_limit_register_per_minute: int = Field(default=5, ge=1)
    rate_limit_register_per_hour: int = Field(default=20, ge=1)
    # T-D18a: per signed-in user, ``POST /settings/password``.
    rate_limit_password_change_per_minute: int = Field(default=5, ge=1)
    rate_limit_password_change_per_hour: int = Field(default=20, ge=1)
    # T-D53b / ADR-0076 §2: per signed-in user, step-up re-auth attempts.
    rate_limit_reauth_per_minute: int = Field(default=5, ge=1)
    rate_limit_reauth_per_hour: int = Field(default=20, ge=1)
    # ADR-0061 §3 / ADR-0069: admin bootstrap credentials, injected by
    # cloud-init. The env names carry a ``BUDGET_PLANNER_`` prefix (not the
    # model-wide ``BUDGET_``), so they are bound via explicit aliases; the
    # field name stays usable as an init kwarg for tests. Validation of
    # presence happens inside ``services.users.bootstrap_admin`` only.
    # ``pydantic-alias`` ignore: AliasChoices is a dynamic alias by design
    # (env name + field name); both fields have defaults, so the plugin's
    # "required dynamic alias" concern does not apply.
    admin_email: str | None = Field(  # type: ignore[pydantic-alias]  # AliasChoices is a dynamic alias by design; field has a default
        default=None,
        validation_alias=AliasChoices("BUDGET_PLANNER_ADMIN_EMAIL", "admin_email"),
    )
    admin_initial_password: SecretStr | None = Field(  # type: ignore[pydantic-alias]  # AliasChoices is a dynamic alias by design; field has a default
        default=None,
        validation_alias=AliasChoices(
            "BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD", "admin_initial_password"
        ),
    )

    # T-UR32 / ADR-0134 section 9: lowercase hex sha256 of the one-time setup
    # token, generated by the drill workflow. Unset (or blank) = setup closed.
    # The plain token is never configured, stored or logged.
    setup_token_hash: str | None = Field(  # type: ignore[pydantic-alias]  # AliasChoices is a dynamic alias by design; field has a default
        default=None,
        validation_alias=AliasChoices("BUDGET_PLANNER_SETUP_TOKEN_HASH", "setup_token_hash"),
    )

    @field_validator("setup_token_hash")
    @classmethod
    def _normalise_setup_token_hash(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalised = v.strip().lower()
        if not normalised:
            return None
        if len(normalised) != SHA256_HEX_LENGTH or any(
            c not in "0123456789abcdef" for c in normalised
        ):
            raise ValueError("BUDGET_PLANNER_SETUP_TOKEN_HASH must be a sha256 hex digest")
        return normalised

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

    @field_validator("fx_api_url")
    @classmethod
    def _validate_provider_url(cls, v: str) -> str:
        parts = urlsplit(v)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
            raise ValueError("fx_api_url must be an http(s) URL without credentials (ADR-0145)")
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

    def _require_production_bcrypt_floor(self) -> None:
        if self.bcrypt_rounds < PRODUCTION_MIN_BCRYPT_ROUNDS:
            raise ValueError(
                f"bcrypt_rounds must be >= {PRODUCTION_MIN_BCRYPT_ROUNDS} in production "
                "(T-Q291, ADR-0033 §2)."
            )

    @model_validator(mode="after")
    def _finalise(self) -> Settings:
        if self.session_absolute_lifetime_days < self.session_lifetime_days:
            raise ValueError(
                "session_absolute_lifetime_days must be >= session_lifetime_days (ADR-0076 §1)."
            )
        # T-D03: cookie_secret policy. Production without a secret is a
        # hard failure; dev falls back to the known-dev value (see
        # :meth:`resolve`) and emits a one-shot warning so the fallback is
        # observable; test env also falls back but stays silent.
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

        if self.env == "production" and not self.fx_api_url.startswith("https://"):
            raise ValueError("fx_api_url must be https in production (ADR-0145).")

        # T-D135: WebAuthn relying-party policy. The localhost defaults make
        # passkeys fail in the browser on the real hostname, so production
        # refuses to start with them (ADR-0067 §1).
        if self.env == "production":
            self._require_production_bcrypt_floor()
            if self.webauthn_rp_id == "localhost":
                raise ValueError(
                    "webauthn_rp_id must not be 'localhost' in production — set "
                    "BUDGET_WEBAUTHN_RP_ID to the public hostname (ADR-0067 §1)."
                )
            expected_origin = f"https://{self.webauthn_rp_id}"
            if self.webauthn_origin != expected_origin:
                raise ValueError(
                    f"webauthn_origin must be {expected_origin!r} in production — set "
                    "BUDGET_WEBAUTHN_ORIGIN to https://<BUDGET_WEBAUTHN_RP_ID> (ADR-0067 §1)."
                )
        return self

    def daily_refresh_active(self) -> bool:
        """Whether the daily FX refresh task runs (explicit setting, else production only)."""
        if self.fx_refresh_enabled is None:
            return self.env == "production"
        return self.fx_refresh_enabled

    def resolve(self) -> ResolvedSettings:
        """Return the derived values: prod DB default and dev cookie-secret fallback.

        T-D04: production defaults the DB path to ``/data/budget.db`` when the
        operator has not overridden it; dev / test keep the repo-local default.
        T-D03: an empty ``cookie_secret`` falls back to the known dev value
        (production already refused it in validation).
        """
        database_url = (
            _PROD_DATABASE_URL
            if self.env == "production" and self.database_url == _DEFAULT_DATABASE_URL
            else self.database_url
        )
        return ResolvedSettings(
            database_url=database_url, cookie_secret=self.cookie_secret or _DEV_COOKIE_SECRET
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached; tests clear it via ``cache_clear``)."""
    return Settings()
