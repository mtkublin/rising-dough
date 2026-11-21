"""Route-coverage allowlists (T-UT03, ADR-0106 section 1).

``FRAMEWORK`` is permanent. The ``PENDING_T_UT04x`` sections are all gone:
every app route has ``@covers`` tests. ``ALLOWLIST`` is ``FRAMEWORK``.
"""

from __future__ import annotations

from typing import Final

FRAMEWORK: Final[dict[str, str]] = {
    "GET /openapi.json": "framework",
    "GET /docs": "framework",
    "GET /docs/oauth2-redirect": "framework",
    "MOUNT /static": "framework",
}

ALLOWLIST: Final[dict[str, str]] = {
    **FRAMEWORK,
}
