"""All stored times are UTC ISO 8601; bookings use the wall's local timezone."""
from datetime import datetime, timezone
import os
from zoneinfo import ZoneInfo


def wall_zone():
    return ZoneInfo(os.environ.get("ROCKWALL_TIMEZONE", "America/Chicago"))


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def booking_time(day: str, clock: str) -> str:
    local = datetime.fromisoformat(f"{day}T{clock}")
    if local.tzinfo is not None:
        raise ValueError("Use a local date and time without an offset")
    zoned = local.replace(tzinfo=wall_zone())
    if zoned.astimezone(timezone.utc).astimezone(wall_zone()).replace(tzinfo=None) != local:
        raise ValueError("That local time does not exist because of daylight saving time")
    return zoned.astimezone(timezone.utc).isoformat()


def normalize_time(value) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=wall_zone())
    return result.astimezone(timezone.utc).isoformat()
