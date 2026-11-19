from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import time
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo


READINGS_URL = (
    "https://environment.data.gov.uk/flood-monitoring/id/measures/"
    "0007-level-tidal_level-i-15_min-mAOD/readings"
)
LOGGER = logging.getLogger(__name__)
POLL_SECONDS = 15 * 60
MAX_AGE = timedelta(hours=2)


@dataclass(frozen=True)
class LampTideData:
    level: float
    rising: bool | None = None
    observed_at: datetime | None = None
    height: float | None = None
    low: float | None = None
    high: float | None = None
    demo: bool = False


@dataclass(frozen=True)
class Reading:
    at: datetime
    height: float


def fetch_readings(since: datetime) -> list[Reading]:
    if since.tzinfo is None:
        raise ValueError("Tide history requires a timezone-aware time")
    query = urlencode({
        "since": since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "_sorted": "", "_limit": 400,
    })
    with urlopen(f"{READINGS_URL}?{query}", timeout=10) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("Tower Pier response exceeds 2 MB")
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Tower Pier response must contain a readings list")
    readings = {}
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid Tower Pier reading")
        stamp, height = item.get("dateTime"), item.get("value")
        if not isinstance(stamp, str) or type(height) not in (int, float) or not math.isfinite(height):
            raise ValueError("Invalid Tower Pier timestamp or height")
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("Tower Pier timestamp has no timezone")
        readings[at.astimezone(timezone.utc)] = float(height)
    return [Reading(at, height) for at, height in sorted(readings.items())]


class TowerPierTides:
    """Observed Tower Pier levels, eased toward each measurement without prediction."""

    def __init__(self, fetch: Callable[[datetime], list[Reading]] = fetch_readings,
                 monotonic: Callable[[], float] = time.monotonic):
        self.fetch = fetch
        self.monotonic = monotonic
        self.next_poll = float("-inf")
        self.data: LampTideData | None = None
        self.target: float | None = None
        self.level: float | None = None
        self.updated_at: float | None = None

    def get(self, now: datetime) -> LampTideData | None:
        if now.tzinfo is None:
            raise ValueError("Tide observations require a timezone-aware time")
        now = now.astimezone(timezone.utc)
        elapsed = self.monotonic()
        # Advance the previous target first: a new observation must not jump the lamp.
        if self.level is not None and self.target is not None and self.updated_at is not None:
            weight = -math.expm1(-max(0, elapsed - self.updated_at) / 600)
            self.level += (self.target - self.level) * weight
        self.updated_at = elapsed
        if elapsed >= self.next_poll:
            self.next_poll = elapsed + POLL_SECONDS
            try:
                since = now - timedelta(hours=72)
                readings = sorted(
                    (reading for reading in self.fetch(since) if since <= reading.at <= now),
                    key=lambda reading: reading.at,
                )
                if (len(readings) < 48
                        or readings[-1].at - readings[0].at < timedelta(hours=24)):
                    raise ValueError("Tower Pier needs at least 24 hours and 48 recent observations")
                latest, previous = readings[-1], readings[-2]
                if now - latest.at > MAX_AGE:
                    raise ValueError("Latest Tower Pier observation is over two hours old")
                low = min(reading.height for reading in readings)
                high = max(reading.height for reading in readings)
                if high - low < 0.1:
                    raise ValueError("Tower Pier history has no usable tidal range")
                target = min(1.0, max(0.0, (latest.height - low) / (high - low)))
                difference = latest.height - previous.height
                rising = None if abs(difference) < 0.01 else difference > 0
                self.target = target
                if self.level is None:
                    self.level = target
                self.data = LampTideData(target, rising, latest.at, latest.height, low, high)
                LOGGER.info(
                    "Tower Pier %s: %.2f mAOD, recent range %.2f-%.2f mAOD, %s",
                    latest.at.astimezone(ZoneInfo("Europe/London")).strftime("%Y-%m-%d %H:%M %Z"),
                    latest.height, low, high,
                    "steady" if rising is None else "rising" if rising else "falling",
                )
            except (OSError, URLError, ValueError) as exc:
                LOGGER.warning("Tower Pier tide data unavailable; holding last light: %s", exc)
        if self.data is None or self.level is None:
            return None
        return LampTideData(self.level, self.data.rising, self.data.observed_at,
                            self.data.height, self.data.low, self.data.high)


class SimulatedLampTides:
    def __init__(self, percent: float | None = None):
        if percent is not None and (type(percent) not in (int, float) or not 0 <= percent <= 100):
            raise ValueError("Simulated tide level must be from 0 to 100")
        self.percent = percent

    def get(self, now: datetime) -> LampTideData:
        if self.percent is not None:
            return LampTideData(self.percent / 100, demo=True)
        position = (now.timestamp() / 1800) % 2
        return LampTideData(1 - abs(position - 1), rising=position < 1, demo=True)
