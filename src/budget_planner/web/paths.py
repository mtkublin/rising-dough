"""Route fragments and HTTP method sets the routers repeat (G19): one definition each."""

from __future__ import annotations

from typing import Final

LEDGER_PATH: Final = "/ledger"
SETTINGS_PATH: Final = "/settings"
NEW_PATH: Final = "/new"
TABLE_PATH: Final = "/table"
TRANSACTIONS_PATH: Final = "/transactions"
PLANNED_PATH: Final = "/planned"

GET_HEAD_METHODS: Final = ("GET", "HEAD")
