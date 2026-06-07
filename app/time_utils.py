from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return UTC time as naive datetime for current SQLAlchemy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
