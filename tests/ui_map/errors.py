"""Error pages (404, 409, 422, 500) and flash error fragments (handoff pages/errors)."""

from __future__ import annotations

from tests.ui_map.locator import by_id, role

main = by_id("main")
alert = role("alert")
status = role("status")
heading = role("heading", level=1)
back_link = role("link", "back to today")
reload_link = role("link", "reload")
retry_link = role("link", "try again")
form_link = role("link", "back to the form")
summary = by_id("error-summary")
