# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Registry of user-isolation cases for ``test_user_isolation.py`` (ADR-0130 S3, Q-015).

A case is ``(conn, world) -> None`` and asserts exact values for the owner (user 1), that the other user's (user 2)
and tombstoned rows never appear in the owner's results, and the reverse. ``world`` is the ``world_with_tombstones``
fixture (see ``conftest.py``). Register with ``@covers("module.function")``; the id must match the guard's
``<module>.<function>`` spelling. Case modules (``_isolation_*_cases.py``) are imported by ``test_user_isolation.py``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from tests.unit.services.conftest import World

Case = Callable[[sqlite3.Connection, World], None]

COVERED: dict[str, Case] = {}


def covers(function_id: str) -> Callable[[Case], Case]:
    def register(case: Case) -> Case:
        COVERED[function_id] = case
        return case

    return register
