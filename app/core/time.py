from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp. Everything is stored and compared in UTC."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Convert to UTC. A datetime without a timezone is assumed to already be UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
