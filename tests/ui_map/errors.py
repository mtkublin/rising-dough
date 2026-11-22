"""Error pages (404, 409, 422, 500) and flash error fragments."""

from __future__ import annotations

from tests.ui_map.locator import by_id, role

main = by_id("main")
alert = role("alert")
status = role("status")
heading = role("heading", level=1)
back_link = role("link", "Back to dashboard")
