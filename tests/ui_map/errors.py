"""Error pages (404, 409, 422, 500) and flash error fragments."""

from __future__ import annotations

from tests.ui_map.locator import by_id, role

main = by_id("main")
alert = role("alert")
status = role("status")
