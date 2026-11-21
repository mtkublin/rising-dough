"""CSPRNG adapter for the :class:`~budget_planner.domain.ports.TokenSource` port."""

from __future__ import annotations

import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SecretsTokenSource:
    """Tokens from :mod:`secrets` (the only production ``TokenSource``)."""

    def new_token(self, nbytes: int) -> str:
        return secrets.token_urlsafe(nbytes)
