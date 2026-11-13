from datetime import datetime, time
from zoneinfo import ZoneInfo


def local_now(zone: str, override: time | None = None) -> datetime:
    now = datetime.now(ZoneInfo(zone))
    return now.replace(hour=override.hour, minute=override.minute, second=0, microsecond=0) if override else now
