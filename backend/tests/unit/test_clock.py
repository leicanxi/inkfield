from datetime import UTC, datetime

import pytest

from app.core.clock import FrozenClock, require_utc, shanghai_business_date, shanghai_week_start


@pytest.mark.parametrize(
    ("instant", "expected_date", "expected_week_start"),
    [
        (datetime(2026, 7, 12, 15, 59, tzinfo=UTC), "2026-07-12", "2026-07-06"),
        (datetime(2026, 7, 12, 16, 0, tzinfo=UTC), "2026-07-13", "2026-07-13"),
        (datetime(2025, 12, 31, 16, 0, tzinfo=UTC), "2026-01-01", "2025-12-29"),
    ],
)
def test_shanghai_business_boundaries(
    instant: datetime, expected_date: str, expected_week_start: str
) -> None:
    clock = FrozenClock(instant)
    assert shanghai_business_date(clock).isoformat() == expected_date
    assert shanghai_week_start(clock).isoformat() == expected_week_start


def test_frozen_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="aware"):
        FrozenClock(datetime(2026, 1, 1))


def test_require_utc_normalizes_aware_timestamp() -> None:
    value = datetime.fromisoformat("2026-07-16T08:00:00+08:00")
    assert require_utc(value) == datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
