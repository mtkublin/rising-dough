"""Unit test for the shared redirect-only route split (runs in the required e2e job, no browser)."""

from __future__ import annotations

import pytest

from tests.e2e.redirect_routes import split_redirect_routes

pytestmark = [pytest.mark.e2e]


def test_split_redirect_routes_names_the_redirecting_routes() -> None:
    measured, redirected = split_redirect_routes({"/a": 200, "/b": 303, "/c": 200, "/d": 302})
    assert measured == ["/a", "/c"]
    assert redirected == ["/b", "/d"]
