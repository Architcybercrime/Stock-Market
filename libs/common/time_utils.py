"""Time utilities. All internal timestamps are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_utc(ts: Any) -> datetime:
    """Coerce a datetime-ish value to timezone-aware UTC.

    Accepts datetime, ISO 8601 string, or unix epoch (int/float seconds).
    Naive datetimes are assumed to be UTC already.
    """
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=UTC)
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    raise TypeError(f"Cannot coerce {type(ts).__name__} to datetime")


def to_exchange_tz(ts: datetime, tz_name: str = "America/New_York") -> datetime:
    """Convert a UTC datetime to an exchange timezone for display only."""
    try:
        from zoneinfo import ZoneInfo
        return ts.astimezone(ZoneInfo(tz_name))
    except Exception:
        # Fallback for systems without tzdata
        return ts.astimezone(timezone.utc)
