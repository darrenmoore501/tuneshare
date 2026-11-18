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
    pi_brightness: int = 20
    timezone: str = "Europe/London"
    clock_format: int = 12
    demo_tides: bool = True
    show_grid: bool = False
    palette: tuple[str, ...] = ("#FFCC66", "#FF758F", "#75DCD1", "#83A8FF", "#D1A4FF")
    spotify_enabled: bool = False
    spotify_mode: str = "auto"
    spotify_poll_seconds: float = 30
    spotify_idle_poll_seconds: float = 60
    spotify_fallback_screen: str = "word-clock"
    spotify_runtime_dir: str = "/run/siriusvision-spotify"
    spotify_client_id: str = ""


def load_config(path: str | None = None) -> Config:
    data = {}
    if path:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read config: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    if "brightness" in data and data["brightness"] != 0 and "pi_brightness" not in data:
        data["pi_brightness"] = data["brightness"]
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
        if type(config.pi_brightness) is not int or not 1 <= config.pi_brightness <= 100:
            raise ValueError("pi_brightness must be an integer from 1 to 100")
        if type(config.clock_format) is not int or config.clock_format not in (12, 24):
            raise ValueError("clock_format must be 12 or 24")
        if type(config.demo_tides) is not bool or type(config.show_grid) is not bool:
            raise ValueError("demo_tides and show_grid must be booleans")
        if type(config.spotify_enabled) is not bool:
            raise ValueError("spotify_enabled must be a boolean")
        if config.spotify_mode != "auto":
            raise ValueError("spotify_mode must be auto")
        for key in ("spotify_poll_seconds", "spotify_idle_poll_seconds"):
            interval = getattr(config, key)
            if type(interval) not in (int, float) or not 1 <= interval <= 86400:
                raise ValueError(f"{key} must be between 1 and 86400")
        if config.spotify_fallback_screen not in SCREEN_NAMES:
            raise ValueError("spotify_fallback_screen must be a known screen name")
        if (not isinstance(config.spotify_runtime_dir, str) or "\0" in config.spotify_runtime_dir
                or not Path(config.spotify_runtime_dir).is_absolute()):
            raise ValueError("spotify_runtime_dir must be an absolute path")
        if not isinstance(config.spotify_client_id, str):
            raise ValueError("spotify_client_id must be a string")
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
