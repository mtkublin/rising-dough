"""Wire names the web layer repeats: HTMX request/response headers and media types.

One definition each (G19). HTTP header names are case-insensitive, so the canonical
spelling here is the one HTMX documents; lookups behave exactly like the lowercase
literals they replaced. HX-Trigger event names live in ``web/htmx.py`` (``Event``).
"""

from __future__ import annotations

from typing import Final

HX_REQUEST: Final = "HX-Request"
HX_CURRENT_URL: Final = "HX-Current-URL"
HX_REDIRECT: Final = "HX-Redirect"
HX_RESWAP: Final = "HX-Reswap"
HX_RETARGET: Final = "HX-Retarget"
HX_REFRESH: Final = "HX-Refresh"
CONTENT_DISPOSITION: Final = "Content-Disposition"

JSON_MEDIA_TYPE: Final = "application/json"
HTML_MEDIA_TYPE: Final = "text/html"
