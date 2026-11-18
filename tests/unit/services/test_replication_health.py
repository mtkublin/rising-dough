"""T-D144 / ADR-0119: replication freshness verdicts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from budget_planner.services import replication_health as rh

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
MAX_AGE = timedelta(hours=26)


def _doc(**over: object) -> str:
    base: dict[str, object] = {
        "checked_at": "2026-11-18T11:58:00Z",
        "newest_object_at": "2026-11-18T10:00:00Z",
        "generation": "a1b2c3d4",
        "error": None,
    }
    return json.dumps({**base, **over})


def test_fresh_object_is_ok() -> None:
    v = rh.evaluate(_doc(), now=NOW, max_age=MAX_AGE)
    assert (v.ok, v.status, v.age_seconds) == (True, "ok", 7200)
    assert v.generation == "a1b2c3d4"


def test_object_just_inside_threshold_is_ok_and_just_outside_is_stale() -> None:
    inside = _doc(newest_object_at=(NOW - MAX_AGE).isoformat())
    outside = _doc(newest_object_at=(NOW - MAX_AGE - timedelta(seconds=1)).isoformat())
    assert rh.evaluate(inside, now=NOW, max_age=MAX_AGE).ok
    v = rh.evaluate(outside, now=NOW, max_age=MAX_AGE)
    assert (v.ok, v.status) == (False, "stale")


def test_missing_file_is_missing() -> None:
    v = rh.evaluate(None, now=NOW, max_age=MAX_AGE)
    assert (v.ok, v.status) == (False, "missing")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '"x"', "{}"])
def test_garbage_is_unreadable(raw: str) -> None:
    v = rh.evaluate(raw, now=NOW, max_age=MAX_AGE)
    assert (v.ok, v.status) == (False, "unreadable")


def test_old_heartbeat_is_probe_stale_even_with_fresh_object() -> None:
    v = rh.evaluate(_doc(checked_at="2026-11-18T11:00:00Z"), now=NOW, max_age=MAX_AGE)
    assert (v.ok, v.status) == (False, "probe_stale")


def test_probe_error_and_no_objects_fail() -> None:
    err = rh.evaluate(_doc(error="generations_failed"), now=NOW, max_age=MAX_AGE)
    none = rh.evaluate(_doc(newest_object_at=None), now=NOW, max_age=MAX_AGE)
    assert (err.ok, err.status) == (False, "probe_error")
    assert (none.ok, none.status) == (False, "no_objects")


def test_future_object_time_counts_as_age_zero() -> None:
    v = rh.evaluate(_doc(newest_object_at="2026-11-18T12:05:00Z"), now=NOW, max_age=MAX_AGE)
    assert (v.ok, v.age_seconds) == (True, 0)


def test_naive_timestamps_are_read_as_utc() -> None:
    v = rh.evaluate(
        _doc(newest_object_at="2026-11-18T10:00:00", checked_at="2026-11-18T11:59:00"),
        now=NOW,
        max_age=MAX_AGE,
    )
    assert v.ok


def test_body_has_no_secret_fields() -> None:
    body = rh.evaluate(_doc(), now=NOW, max_age=MAX_AGE).body()
    assert set(body) == {
        "status",
        "newest_object_at",
        "age_seconds",
        "max_age_seconds",
        "generation",
        "checked_at",
    }


def test_disabled_is_ok() -> None:
    assert rh.disabled().ok


def test_read_status_text(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    assert rh.read_status_text(str(f)) is None
    f.write_text("x", encoding="utf-8")
    assert rh.read_status_text(str(f)) == "x"
