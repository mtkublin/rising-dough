"""Shared ASGI protocol and header constants for the pure-ASGI middlewares (T-Q254)."""

from __future__ import annotations

#: ``message["type"]`` of the ASGI event that carries status and headers.
RESPONSE_START = "http.response.start"
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"
