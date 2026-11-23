"""T-Q314: an unexpected crash of a lifespan background task is logged and reported."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine, Mapping, Sequence
from typing import Any

import pytest
from structlog.testing import capture_logs

from budget_planner.config import Settings
from budget_planner.web import background_tasks, fx_refresh_task, retention_task

SETTINGS = Settings(_env_file=None, env="test", fx_refresh_enabled=True)


def _run(factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
    errors: list[BaseException] = []

    def target() -> None:
        try:
            asyncio.run(factory())
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    worker = threading.Thread(target=target)
    worker.start()
    worker.join(timeout=30)
    assert not worker.is_alive()
    if errors:
        raise errors[0]


def _crash_events(logs: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [e for e in logs if e["event"] == "background_task_crashed"]


def _boom(_cfg: Settings) -> None:
    raise KeyError("unexpected")


def test_unexpected_error_ends_the_unwatched_task_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Current behaviour (pre-T-Q314): the loop dies, nothing is logged by the loop itself."""
    monkeypatch.setattr(retention_task, "run_once", _boom)

    async def scenario() -> None:
        task = asyncio.create_task(retention_task.run_forever(SETTINGS, 0))
        await asyncio.wait({task}, timeout=10)
        assert task.done()
        assert isinstance(task.exception(), KeyError)

    with capture_logs() as logs:
        _run(scenario)
    assert logs == []


def test_retention_crash_is_logged_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retention_task, "run_once", _boom)
    reported: list[str] = []

    async def scenario() -> None:
        task = asyncio.create_task(
            retention_task.run_forever(SETTINGS, 0), name=retention_task.TASK_NAME
        )
        background_tasks.watch(task, reported.append)
        await asyncio.wait({task}, timeout=10)
        await asyncio.sleep(0)  # let the done-callback run
        await retention_task.stop(task)

    with capture_logs() as logs:
        _run(scenario)
    events = _crash_events(logs)
    assert len(events) == 1
    assert events[0]["task"] == "retention-purge"
    assert events[0]["error_type"] == "KeyError"
    assert events[0]["log_level"] == "error"
    assert isinstance(events[0]["exc_info"], KeyError)
    assert reported == ["retention-purge"]


def test_retention_start_watches_the_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async def crashing(_cfg: Settings) -> None:
        raise ValueError("x")

    monkeypatch.setattr(retention_task, "run_forever", crashing)
    reported: list[str] = []

    async def scenario() -> None:
        task = retention_task.start(SETTINGS, reported.append)
        await asyncio.wait({task}, timeout=10)
        await asyncio.sleep(0)
        await retention_task.stop(task)

    with capture_logs() as logs:
        _run(scenario)
    assert [e["task"] for e in _crash_events(logs)] == ["retention-purge"]
    assert reported == ["retention-purge"]


def test_fx_crash_is_logged_and_reported() -> None:
    reported: list[str] = []

    def refresh(_cfg: Settings) -> bool:
        raise KeyError("unexpected")

    async def never(_s: float) -> None:
        raise AssertionError("must not sleep")

    async def scenario() -> None:
        coro = fx_refresh_task.run_forever(
            SETTINGS, refresh=refresh, missing=lambda _c: True, sleep=never
        )
        task = asyncio.create_task(coro, name=fx_refresh_task.TASK_NAME)
        background_tasks.watch(task, reported.append)
        await asyncio.wait({task}, timeout=10)
        await asyncio.sleep(0)

    with capture_logs() as logs:
        _run(scenario)
    events = _crash_events(logs)
    assert [(e["task"], e["error_type"]) for e in events] == [("fx-refresh", "KeyError")]
    assert reported == ["fx-refresh"]


def test_fx_start_watches_the_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async def crashing(_cfg: Settings) -> None:
        raise ValueError("x")

    monkeypatch.setattr(fx_refresh_task, "run_forever", crashing)
    reported: list[str] = []

    async def scenario() -> None:
        task = fx_refresh_task.start(SETTINGS, reported.append)
        assert task is not None
        await asyncio.wait({task}, timeout=10)
        await asyncio.sleep(0)
        await fx_refresh_task.stop(task)

    with capture_logs() as logs:
        _run(scenario)
    assert [e["task"] for e in _crash_events(logs)] == ["fx-refresh"]
    assert reported == ["fx-refresh"]


def test_job_errors_keep_the_loop_alive_and_are_not_crashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    second = threading.Event()

    def flaky(_cfg: Settings) -> None:
        calls.append(1)
        if len(calls) >= 2:
            second.set()
        raise RuntimeError("expected job error")

    monkeypatch.setattr(retention_task, "run_once", flaky)
    reported: list[str] = []

    async def scenario() -> None:
        task = asyncio.create_task(retention_task.run_forever(SETTINGS, 0))
        background_tasks.watch(task, reported.append)
        await asyncio.wait_for(asyncio.to_thread(second.wait), timeout=10)
        await retention_task.stop(task)

    with capture_logs() as logs:
        _run(scenario)
    assert any(e["event"] == "retention_purge_failed" for e in logs)
    assert _crash_events(logs) == []
    assert reported == []


def test_cancellation_on_stop_logs_nothing_and_reports_nothing() -> None:
    reported: list[str] = []

    async def scenario() -> None:
        task = retention_task.start(SETTINGS, reported.append)
        await asyncio.sleep(0)
        await retention_task.stop(task)
        assert task.cancelled()

    with capture_logs() as logs:
        _run(scenario)
    assert logs == []
    assert reported == []
