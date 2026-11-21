from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from budget_planner import clock
from budget_planner.config import Settings

WARSAW = "Europe/Warsaw"


def test_utc_now_is_timezone_aware_utc() -> None:
    now = clock.utc_now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_frozen_pins_utc_now_and_restores_afterwards() -> None:
    pinned = datetime(2026, 1, 31, 23, 30, tzinfo=UTC)

    with clock.frozen(pinned):
        assert clock.utc_now() == pinned

    assert clock.utc_now() != pinned


def test_frozen_normalises_non_utc_instants_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))

    with clock.frozen(datetime(2026, 6, 1, 1, 0, tzinfo=plus_two)):
        assert clock.utc_now() == datetime(2026, 5, 31, 23, 0, tzinfo=UTC)
        assert clock.utc_now().tzinfo == UTC


def test_frozen_nests_and_unwinds_in_order() -> None:
    outer = datetime(2026, 1, 1, tzinfo=UTC)
    inner = datetime(2026, 2, 2, tzinfo=UTC)

    with clock.frozen(outer):
        with clock.frozen(inner):
            assert clock.utc_now() == inner
        assert clock.utc_now() == outer


def test_frozen_restores_even_when_the_block_raises() -> None:
    pinned = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(RuntimeError), clock.frozen(pinned):
        raise RuntimeError("boom")

    assert clock.utc_now() != pinned


def test_today_uses_the_given_timezone_not_utc() -> None:
    # 23:30 UTC on 31 Jan is already 1 Feb in Warsaw (UTC+1 in winter).
    with clock.frozen(datetime(2026, 1, 31, 23, 30, tzinfo=UTC)):
        assert clock.today("UTC") == date(2026, 1, 31)
        assert clock.today(WARSAW) == date(2026, 2, 1)
        assert clock.today(ZoneInfo(WARSAW)) == date(2026, 2, 1)


def test_today_returns_a_plain_date() -> None:
    with clock.frozen(datetime(2026, 7, 1, 12, 0, tzinfo=UTC)):
        result = clock.today(WARSAW)

    assert type(result) is date


def test_now_in_converts_the_instant() -> None:
    with clock.frozen(datetime(2026, 7, 1, 12, 0, tzinfo=UTC)):
        local = clock.now_in(WARSAW)

    assert local.hour == 14  # CEST, UTC+2
    assert local.utcoffset() == timedelta(hours=2)


def test_today_local_reads_the_settings_display_timezone() -> None:
    settings = Settings(_env_file=None, display_timezone="Pacific/Auckland")

    with clock.frozen(datetime(2026, 1, 31, 12, 0, tzinfo=UTC)):
        # Auckland is UTC+13 in January: already 1 Feb.
        assert clock.today_local(settings) == date(2026, 2, 1)


def test_fixed_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.fixed_clock(datetime(2026, 1, 1))  # noqa: DTZ001 - the point of the test


def test_fixed_clock_returns_its_instant() -> None:
    instant = datetime(2026, 3, 3, tzinfo=UTC)

    source: clock.Clock = clock.fixed_clock(instant)

    assert source.now() == instant


def test_system_clock_is_utc_aware() -> None:
    assert clock.SYSTEM_CLOCK.now().utcoffset() == timedelta(0)


def test_utc_now_iso_is_millisecond_utc_text_matching_sqlite_strftime() -> None:
    with clock.frozen(datetime(2026, 11, 19, 23, 30, 5, 123_987, tzinfo=UTC)):
        assert clock.utc_now_iso() == "2026-11-19T23:30:05.123Z"


def test_iso_utc_converts_to_utc_and_truncates_to_milliseconds() -> None:
    plus_two = timezone(timedelta(hours=2))

    assert clock.iso_utc(datetime(2026, 6, 1, 1, 0, 0, 999_999, tzinfo=plus_two)) == (
        "2026-05-31T23:00:00.999Z"
    )


def test_iso_utc_text_sorts_like_time_across_precisions() -> None:
    earlier = clock.iso_utc(datetime(2026, 11, 19, 10, 0, 0, 123_000, tzinfo=UTC))
    later = clock.iso_utc(datetime(2026, 11, 19, 10, 0, 0, 124_000, tzinfo=UTC))

    assert earlier < later


def test_warsaw_zone_resolves_in_the_runtime_environment() -> None:
    """OQ-3: tzdata ships in the venv (PyPI wheel), so the display zone never silently degrades."""
    instant = datetime(2026, 6, 30, 22, 30, tzinfo=UTC)

    assert instant.astimezone(ZoneInfo(WARSAW)).date() == date(2026, 7, 1)


def test_today_local_follows_display_zone_not_host_zone_at_warsaw_midnight() -> None:
    settings = Settings(display_timezone=WARSAW)

    with clock.frozen(datetime(2026, 6, 30, 22, 30, tzinfo=UTC)):
        assert clock.today_local(settings) == date(2026, 7, 1)
        assert clock.utc_now().date() == date(2026, 6, 30)


def test_today_local_at_month_end_rolls_the_month_in_warsaw() -> None:
    settings = Settings(display_timezone=WARSAW)

    with clock.frozen(datetime(2026, 1, 31, 23, 30, tzinfo=UTC)):
        assert clock.today_local(settings) == date(2026, 2, 1)
