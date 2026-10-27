from datetime import datetime, timedelta
from typing import Annotated
from pydantic import AfterValidator


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("Timestamp must be timezone-aware UTC")
    return value


UTC = Annotated[datetime, AfterValidator(require_utc)]


def observation_age(acquired_at: datetime, at: datetime) -> float:
    return (require_utc(at) - require_utc(acquired_at)).total_seconds()


def is_fresh(acquired_at: datetime, at: datetime, max_age_s: float) -> bool:
    if max_age_s < 0:
        raise ValueError("max_age_s must be nonnegative")
    return 0 <= observation_age(acquired_at, at) <= max_age_s


def simulated_time(start: datetime, step: int, time_step_s: float) -> datetime:
    if step < 0 or time_step_s <= 0:
        raise ValueError("Invalid simulation step")
    return require_utc(start) + timedelta(seconds=step * time_step_s)
