"""Target-keyed UI-map selection (ADR-0106 sections 2 and 5).

``--target=app`` resolves ``tests.ui_map.<surface>``; ``--target=mockup``
resolves ``tests.ui_map.mockup.<surface>``, a module that exposes the same
names against the handoff markup. A journey written on ``today.<name>`` works
on both because it asks ``surface("today", target)`` for the module.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Literal

Target = Literal["app", "mockup"]
TARGETS: tuple[Target, ...] = ("app", "mockup")


def surface(name: str, target: Target = "app") -> ModuleType:
    """UI-map module for ``name`` under ``target``."""
    package = "tests.ui_map" if target == "app" else "tests.ui_map.mockup"
    return import_module(f"{package}.{name}")


def public_names(module: ModuleType) -> frozenset[str]:
    """Names a surface module defines for tests (locators and builders)."""
    return frozenset(
        n
        for n, v in vars(module).items()
        if not n.startswith("_")
        and getattr(v, "__module__", module.__name__) == module.__name__
        and (callable(v) or hasattr(v, "kind"))
    )
