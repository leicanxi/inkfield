from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FrozenClock:
    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("FrozenClock requires an aware datetime")

    def now(self) -> datetime:
        return self.instant.astimezone(UTC)


def shanghai_business_date(clock: Clock) -> date:
    return clock.now().astimezone(SHANGHAI).date()


def shanghai_week_start(clock: Clock) -> date:
    business_date = shanghai_business_date(clock)
    return business_date - timedelta(days=business_date.weekday())


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
