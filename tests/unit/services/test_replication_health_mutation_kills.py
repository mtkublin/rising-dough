"""Mutation-kill tests for ``services/replication_health`` (T-Q247, ADR-0131).

Every verdict is asserted whole (status, ages, echoed raw timestamps and generation),
``now`` is injected.
Complements ``test_replication_health.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from budget_planner.services import replication_health as rh

NOW = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC)
MAX_AGE = timedelta(hours=1)
CHECKED = "2026-11-22T11:58:00+00:00"
NEWEST = "2026-11-22T11:30:00+00:00"


def _raw(**overrides: object) -> str:
    doc: dict[str, object] = {
        "checked_at": CHECKED,
        "newest_object_at": NEWEST,
        "generation": "gen-7",
    }
    doc.update(overrides)
    return json.dumps({k: v for k, v in doc.items() if v is not ...})


def test_disabled_verdict_and_body() -> None:
    assert rh.disabled() == rh.ReplicationHealth(ok=True, status="disabled")
    assert rh.disabled().body() == {
        "status": "disabled",
        "newest_object_at": None,
        "age_seconds": None,
        "max_age_seconds": None,
        "generation": None,
        "checked_at": None,
    }


def test_missing_file_reports_max_age_in_whole_seconds() -> None:
    verdict = rh.evaluate(None, now=NOW, max_age=timedelta(seconds=90.7))
    assert verdict == rh.ReplicationHealth(ok=False, status="missing", max_age_seconds=90)


@pytest.mark.parametrize("raw", ["not json", "[]", "null", '"text"', "42", ""])
def test_unreadable_documents_report_max_age(raw: str) -> None:
    verdict = rh.evaluate(raw, now=NOW, max_age=MAX_AGE)
    assert verdict == rh.ReplicationHealth(ok=False, status="unreadable", max_age_seconds=3_600)


def test_healthy_verdict_echoes_every_field() -> None:
    verdict = rh.evaluate(_raw(), now=NOW, max_age=MAX_AGE)
    assert verdict == rh.ReplicationHealth(
        ok=True,
        status="ok",
        newest_object_at=NEWEST,
        age_seconds=1_800,
        max_age_seconds=3_600,
        generation="gen-7",
        checked_at=CHECKED,
    )
    assert verdict.body() == {
        "status": "ok",
        "newest_object_at": NEWEST,
        "age_seconds": 1_800,
        "max_age_seconds": 3_600,
        "generation": "gen-7",
        "checked_at": CHECKED,
    }


def test_stale_verdict_echoes_every_field() -> None:
    old = "2026-11-22T10:00:00+00:00"
    verdict = rh.evaluate(_raw(newest_object_at=old), now=NOW, max_age=MAX_AGE)
    assert verdict == rh.ReplicationHealth(
        ok=False,
        status="stale",
        newest_object_at=old,
        age_seconds=7_200,
        max_age_seconds=3_600,
        generation="gen-7",
        checked_at=CHECKED,
    )


def test_probe_stale_boundary_is_strictly_greater_than_fifteen_minutes() -> None:
    at_limit = (NOW - rh.PROBE_MAX_AGE).isoformat()
    just_over = (NOW - rh.PROBE_MAX_AGE - timedelta(seconds=1)).isoformat()
    assert rh.evaluate(_raw(checked_at=at_limit), now=NOW, max_age=MAX_AGE).status == "ok"
    over = rh.evaluate(_raw(checked_at=just_over), now=NOW, max_age=MAX_AGE)
    assert over == rh.ReplicationHealth(
        ok=False,
        status="probe_stale",
        newest_object_at=NEWEST,
        age_seconds=None,
        max_age_seconds=3_600,
        generation="gen-7",
        checked_at=just_over,
    )


def test_custom_probe_max_age_is_honoured() -> None:
    verdict = rh.evaluate(_raw(), now=NOW, max_age=MAX_AGE, probe_max_age=timedelta(minutes=1))
    assert verdict.status == "probe_stale"


def test_probe_error_wins_over_a_fresh_object() -> None:
    verdict = rh.evaluate(_raw(error="boom"), now=NOW, max_age=MAX_AGE)
    assert verdict == rh.ReplicationHealth(
        ok=False,
        status="probe_error",
        newest_object_at=NEWEST,
        age_seconds=None,
        max_age_seconds=3_600,
        generation="gen-7",
        checked_at=CHECKED,
    )


def test_no_objects_and_missing_heartbeat() -> None:
    no_objects = rh.evaluate(_raw(newest_object_at=...), now=NOW, max_age=MAX_AGE)
    assert no_objects == rh.ReplicationHealth(
        ok=False,
        status="no_objects",
        newest_object_at=None,
        age_seconds=None,
        max_age_seconds=3_600,
        generation="gen-7",
        checked_at=CHECKED,
    )
    no_heartbeat = rh.evaluate(_raw(checked_at=...), now=NOW, max_age=MAX_AGE)
    assert no_heartbeat == rh.ReplicationHealth(
        ok=False,
        status="unreadable",
        newest_object_at=NEWEST,
        age_seconds=None,
        max_age_seconds=3_600,
        generation="gen-7",
        checked_at=None,
    )


def test_non_string_fields_are_dropped_from_the_echo() -> None:
    verdict = rh.evaluate(_raw(generation=12, newest_object_at=5), now=NOW, max_age=MAX_AGE)
    assert (verdict.status, verdict.generation, verdict.newest_object_at) == (
        "no_objects",
        None,
        None,
    )


def test_age_exactly_at_the_limit_is_fresh_and_one_second_more_is_stale() -> None:
    at_limit = (NOW - MAX_AGE).isoformat()
    over = (NOW - MAX_AGE - timedelta(seconds=1)).isoformat()
    assert rh.evaluate(_raw(newest_object_at=at_limit), now=NOW, max_age=MAX_AGE).ok is True
    stale = rh.evaluate(_raw(newest_object_at=over), now=NOW, max_age=MAX_AGE)
    assert (stale.ok, stale.status, stale.age_seconds) == (False, "stale", 3_601)


def test_read_status_text_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_bytes('{"generation": "zażółć"}'.encode())
    assert rh.read_status_text(str(path)) == '{"generation": "zażółć"}'
    assert rh.read_status_text(str(tmp_path / "absent.json")) is None
