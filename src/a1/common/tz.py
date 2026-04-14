"""Timezone utilities — Indian Standard Time (UTC+5:30)."""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Return current time in IST."""
    return datetime.now(IST)
