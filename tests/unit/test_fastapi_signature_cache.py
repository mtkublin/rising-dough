"""T-CS08: the root conftest caches FastAPI's endpoint signature analysis.

Fails loudly if a FastAPI upgrade renames or stops using the function, so the
cache never silently becomes a no-op (or patches the wrong thing).
"""

from __future__ import annotations

import inspect

import fastapi.dependencies.utils as fastapi_dependency_utils


def _endpoint(item_id: int, q: str | None = None) -> dict[str, int]:
    return {"item_id": item_id}


def test_get_typed_signature_is_cached() -> None:
    assert hasattr(fastapi_dependency_utils.get_typed_signature, "cache_info")


def test_get_dependant_still_calls_get_typed_signature() -> None:
    source = inspect.getsource(fastapi_dependency_utils.get_dependant)
    assert "get_typed_signature(" in source


def test_cached_signature_matches_uncached() -> None:
    cached = fastapi_dependency_utils.get_typed_signature
    uncached = cached.__wrapped__  # type: ignore[attr-defined]

    assert cached(_endpoint) == uncached(_endpoint)
    assert cached(_endpoint) is cached(_endpoint)
