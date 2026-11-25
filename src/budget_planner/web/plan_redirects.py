"""Redirects from the retired ``/budget`` and ``/forecast`` pages to the Plan hub (T-UR15a, Q13).

One owner for the old-URL to ``/plan?tab=...`` mapping: the listed query parameters are kept
(``keep`` maps the old name to the new one), everything else is dropped. 307 keeps the method.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse

TEMPORARY_REDIRECT = 307


def to_plan(request: Request, tab: str, keep: Mapping[str, str]) -> RedirectResponse:
    pairs = [("tab", tab)]
    for old, new in keep.items():
        value = request.query_params.get(old)
        if value is not None:
            pairs.append((new, value))
    return RedirectResponse(f"/plan?{urlencode(pairs)}", status_code=TEMPORARY_REDIRECT)
