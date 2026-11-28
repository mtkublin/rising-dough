"""Device label parsing (T-UR34h): exact labels for real user agent strings."""

from __future__ import annotations

import pytest

from budget_planner.domain.user_agent import UNKNOWN_DEVICE, device_label

_FIREFOX_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0"
)
_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
_CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_EDGE_WIN = _CHROME_WIN + " Edg/131.0.0.0"
_CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)
_SAFARI_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)
_CHROME_LINUX = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_CHROME_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1"
)


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (_FIREFOX_MAC, "Firefox · macOS"),
        (_SAFARI_IPHONE, "Safari · iPhone"),
        (_CHROME_WIN, "Chrome · Windows"),
        (_EDGE_WIN, "Edge · Windows"),
        (_CHROME_ANDROID, "Chrome · Android"),
        (_SAFARI_MAC, "Safari · macOS"),
        (_CHROME_LINUX, "Chrome · Linux"),
        (_CHROME_IOS, "Chrome · iPhone"),
        ("curl/8.4.0", UNKNOWN_DEVICE),
        ("", UNKNOWN_DEVICE),
        (None, UNKNOWN_DEVICE),
        ("Mozilla/5.0 (Windows NT 10.0) Gecko", "Unknown browser · Windows"),
        ("Firefox/132.0", "Firefox · unknown system"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15) Gecko", "Unknown browser · macOS"),
        ("Mozilla/5.0 Gecko", UNKNOWN_DEVICE),
    ],
)
def test_device_label(user_agent: str | None, expected: str) -> None:
    assert device_label(user_agent) == expected
