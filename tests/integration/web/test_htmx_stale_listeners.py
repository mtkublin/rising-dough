"""T-Q236 (Q-038, OQ-27 default): every `*-stale` event has a panel that re-fetches itself."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

# (page, region id, event it refetches on)
_REGIONS = [
    ("/today", "today-hero", "today-stale"),
    ("/today", "upcoming-list", "today-stale"),
    ("/accounts", "accounts-hero", "balance-stale"),
    ("/settings?tab=categories", "settings-categories", "settings-categories-stale"),
]


@pytest.mark.parametrize(("path", "region_id", "event"), _REGIONS)
def test_page_region_refetches_itself_on_stale_event(
    client: TestClient, path: str, region_id: str, event: str
) -> None:
    r = client.get(path)

    assert r.status_code == 200
    region = BeautifulSoup(r.text, "html.parser").find(id=region_id)
    assert region is not None
    triggers = [t.strip() for t in str(region.get("hx-trigger")).split(",")]
    assert f"{event} from:body" in triggers
    assert region.get("hx-select") == f"#{region_id}"
    assert region.get("hx-swap") == "outerHTML"
    assert str(region.get("hx-get")).startswith(path.split("?", maxsplit=1)[0])


@pytest.mark.parametrize(
    ("path", "event", "refetch_url"),
    [
        (
            "/plan?tab=budget&year=2026&month=10",
            "budget-stale",
            "/plan?tab=budget&year=2026&month=10",
        ),
        ("/plan?tab=year&year=2026", "budget-stale", "/plan?tab=year&year=2026"),
        ("/plan?tab=forecast&horizon=6", "forecast-stale", "/plan?tab=forecast&horizon=6"),
    ],
)
def test_plan_tabs_reload_main_on_their_stale_event(
    client: TestClient, path: str, event: str, refetch_url: str
) -> None:
    """T-UR15a: the retired /budget and /forecast pages' listeners live on the Plan tabs."""
    r = client.get(path)

    assert r.status_code == 200
    listeners = [
        el
        for el in BeautifulSoup(r.text, "html.parser").select("[hx-trigger]")
        if f"{event} from:body" in str(el["hx-trigger"])
    ]
    assert len(listeners) == 1
    listener = listeners[0]
    assert listener.get("hx-get") == refetch_url
    assert (listener.get("hx-target"), listener.get("hx-select")) == ("#main", "#main")
    assert listener.get("hx-swap") == "outerHTML"
