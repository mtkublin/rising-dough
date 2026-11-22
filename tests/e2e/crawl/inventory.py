"""Read / write / diff of the committed control inventory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

INVENTORY_PATH = Path(__file__).resolve().parents[1] / "crawl_inventory.json"
UPDATE_ENV = "CRAWL_UPDATE"


def updating() -> bool:
    return os.environ.get(UPDATE_ENV) == "1"


def sort_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry.get("via", "")),
        str(entry["kind"]),
        str(entry["name"]),
        str(entry["target"]),
    )


def canonical(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unique entries in deterministic order."""
    unique = {json.dumps(e, sort_keys=True): e for e in entries}
    return sorted(unique.values(), key=sort_key)


def load() -> dict[str, list[dict[str, Any]]]:
    if not INVENTORY_PATH.exists():
        return {}
    data: dict[str, list[dict[str, Any]]] = json.loads(INVENTORY_PATH.read_text())
    return data


def store(inventory: dict[str, list[dict[str, Any]]]) -> None:
    ordered = {route: inventory[route] for route in sorted(inventory)}
    INVENTORY_PATH.write_text(json.dumps(ordered, indent=2, sort_keys=True) + "\n")


def diff(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[str]:
    exp = {json.dumps(e, sort_keys=True) for e in expected}
    act = {json.dumps(e, sort_keys=True) for e in actual}
    return [f"- {line}" for line in sorted(exp - act)] + [f"+ {line}" for line in sorted(act - exp)]
