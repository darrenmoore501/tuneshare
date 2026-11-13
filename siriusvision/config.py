import json
from dataclasses import dataclass, fields
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCREEN_NAMES = ("word-clock", "letter-clock", "tide-moon", "album-art")


@dataclass(frozen=True)
class Config:
    screens: tuple[str, ...] = SCREEN_NAMES
    cycle_seconds: float = 30
    brightness: int = 80
    timezone: str = "Europe/London"
    clock_format: int = 12
    demo_tides: bool = True
    show_grid: bool = False
    palette: tuple[str, ...] = ("#FFCC66", "#FF758F", "#75DCD1", "#83A8FF", "#D1A4FF")


def load_config(path: str | None = None) -> Config:
    data = {}
    if path:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read config: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    unknown = set(data) - {field.name for field in fields(Config)}
    if unknown:
        raise ValueError(f"Unknown config settings: {', '.join(sorted(unknown))}")
    try:
        config = Config(**data)
        if not isinstance(config.screens, (list, tuple)) or not config.screens or any(
            not isinstance(name, str) or name not in SCREEN_NAMES for name in config.screens
        ):
            raise ValueError("screens must contain known screen names")
        if isinstance(config.cycle_seconds, bool) or not isinstance(config.cycle_seconds, (int, float)) or not 1 <= config.cycle_seconds <= 86400:
            raise ValueError("cycle_seconds must be between 1 and 86400")
        if type(config.brightness) is not int or not 0 <= config.brightness <= 100:
            raise ValueError("brightness must be an integer from 0 to 100")
        if type(config.clock_format) is not int or config.clock_format not in (12, 24):
            raise ValueError("clock_format must be 12 or 24")
        if type(config.demo_tides) is not bool or type(config.show_grid) is not bool:
            raise ValueError("demo_tides and show_grid must be booleans")
        if not isinstance(config.timezone, str):
            raise ValueError("timezone must be an IANA timezone name")
        ZoneInfo(config.timezone)
        if not isinstance(config.palette, (list, tuple)) or len(config.palette) < 4:
            raise ValueError("palette must have at least four #RRGGBB colours")
        for colour in config.palette:
            if not isinstance(colour, str) or len(colour) != 7 or colour[0] != "#":
                raise ValueError("palette colours must be #RRGGBB")
            int(colour[1:], 16)
    except (TypeError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"Invalid config: {exc}") from exc
    return config
