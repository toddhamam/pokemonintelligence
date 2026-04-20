"""Time helpers. All timestamps are UTC. All `as_of_date` values are calendar dates.

Any code that creates a timestamp MUST call `utc_now()` — never `datetime.now()` without
a tz. The point-in-time discipline depends on consistent tz-aware timestamps.
"""

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def today_utc() -> date:
    return utc_now().date()
