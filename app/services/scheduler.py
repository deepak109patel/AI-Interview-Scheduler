from datetime import datetime
from typing import Optional


def parse_datetime(dt_string: str) -> Optional[datetime]:
    """
    Try multiple datetime formats to parse a confirmed interview time.
    Returns a datetime object or None if parsing fails.
    """
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%m/%d/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(dt_string.strip(), fmt)
        except ValueError:
            continue
    return None


def format_scheduled_time(dt: datetime) -> str:
    """Return a human-friendly version of the scheduled datetime."""
    return dt.strftime("%A, %B %d %Y at %I:%M %p")
