from datetime import datetime, timezone
import math


SYNODIC_DAYS = 29.530588853
REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_phase(now: datetime) -> tuple[float, float, str]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Moon calculation requires a timezone-aware datetime")
    phase = ((now.astimezone(timezone.utc) - REFERENCE_NEW_MOON).total_seconds() / 86400 / SYNODIC_DAYS) % 1
    illumination = (1 - math.cos(2 * math.pi * phase)) / 2
    if phase < 0.035 or phase >= 0.965:
        label = "NEW"
    elif phase < 0.215:
        label = "WAXING"
    elif phase < 0.285:
        label = "FIRST"
    elif phase < 0.465:
        label = "WAXING"
    elif phase < 0.535:
        label = "FULL"
    elif phase < 0.715:
        label = "WANING"
    elif phase < 0.785:
        label = "LAST"
    else:
        label = "WANING"
    return phase, illumination, label
