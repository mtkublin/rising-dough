"""Device label from a stored user agent (T-UR34h, ADR-0147 section 3, ADR-0148).

Pure string matching, no dependency. The label format is the handoff board's
``"<browser> · <os>"`` (``Firefox · macOS``, ``Safari · iPhone``). Order of the
marker tuples matters: the first match wins (Edge and Opera also say ``Chrome``, Chrome
also says ``Safari``, iPhone also says ``Mac OS X``). The known part is always shown
(``Unknown browser · macOS``, ``Firefox · unknown system``); ``Unknown device`` only when
neither part is known (ADR-0151 section 2).
"""

from __future__ import annotations

from typing import Final

UNKNOWN_DEVICE: Final = "Unknown device"
UNKNOWN_BROWSER: Final = "Unknown browser"
UNKNOWN_SYSTEM: Final = "unknown system"
LABEL_SEPARATOR: Final = " · "

_BROWSERS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("Edge", ("Edg/", "EdgA/", "EdgiOS/", "Edge/")),
    ("Opera", ("OPR/", "Opera")),
    ("Firefox", ("Firefox/", "FxiOS/")),
    ("Chrome", ("Chrome/", "CriOS/")),
    ("Safari", ("Safari/",)),
)
_SYSTEMS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("iPhone", ("iPhone",)),
    ("iPad", ("iPad",)),
    ("Android", ("Android",)),
    ("Windows", ("Windows",)),
    ("macOS", ("Macintosh", "Mac OS X")),
    ("ChromeOS", ("CrOS",)),
    ("Linux", ("Linux", "X11")),
)


def _first_match(user_agent: str, table: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for name, markers in table:
        if any(marker in user_agent for marker in markers):
            return name
    return None


def device_label(user_agent: str | None) -> str:
    """``"Firefox · macOS"``-style label; unknown parts are named (ADR-0151)."""
    if not user_agent:
        return UNKNOWN_DEVICE
    browser = _first_match(user_agent, _BROWSERS)
    system = _first_match(user_agent, _SYSTEMS)
    if browser is None and system is None:
        return UNKNOWN_DEVICE
    return f"{browser or UNKNOWN_BROWSER}{LABEL_SEPARATOR}{system or UNKNOWN_SYSTEM}"
