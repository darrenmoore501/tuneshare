import json
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageChops

from siriusvision.app import ScreenManager
from siriusvision.config import Config, load_config
from siriusvision.displays.base import prepare_frame
from siriusvision.displays.png_output import PngDisplay
from siriusvision.screens.base import RenderContext
from siriusvision.screens.letter_clock import GRID, WORDS, highlighted_words
from siriusvision.screens.pixel_font import text_width
from siriusvision.screens.word_clock import clock_words
from siriusvision.services.moon import moon_phase
from siriusvision.services.tides import DemoTides


@pytest.mark.parametrize(("hour", "minute", "expected"), [
    (0, 0, ["TWELVE", "ZERO", "ZERO", "AM"]),
    (12, 0, ["TWELVE", "ZERO", "ZERO", "PM"]),
    (12, 22, ["TWELVE", "TWENTY", "TWO"]),
    (14, 7, ["TWO", "ZERO", "SEVEN", "PM"]),
    (23, 59, ["ELEVEN", "FIFTY", "NINE"]),
])
def test_spoken_clock(hour, minute, expected):
    assert clock_words(hour, minute) == expected


def test_24_hour_clock():
    assert clock_words(0, 0, 24) == ["ZERO", "ZERO", "ZERO"]
    assert clock_words(14, 7, 24) == ["FOURTEEN", "ZERO", "SEVEN"]
    assert clock_words(23, 59, 24) == ["TWENTY", "THREE", "FIFTY", "NINE"]


@pytest.mark.parametrize("hour", range(24))
@pytest.mark.parametrize("clock_format", [12, 24])
def test_all_clock_words_fit(hour, clock_format):
    for minute in range(60):
        words = clock_words(hour, minute, clock_format)
        assert all(text_width(word) <= 60 for word in words)
        assert len(words) * 5 + (len(words) - 1) * 2 <= 64


def test_timezone_and_dst():
    london = ZoneInfo("Europe/London")
    assert datetime(2025, 3, 30, 0, 59, tzinfo=timezone.utc).astimezone(london).strftime("%H:%M %Z") == "00:59 GMT"
    assert datetime(2025, 3, 30, 1, 0, tzinfo=timezone.utc).astimezone(london).strftime("%H:%M %Z") == "02:00 BST"
    assert datetime(2025, 10, 26, 1, 0, tzinfo=timezone.utc).astimezone(london).strftime("%H:%M %Z") == "01:00 GMT"


def test_clock_source_converts_and_overrides(monkeypatch):
    from datetime import time
    from siriusvision.services import clock

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz):
            return datetime(2025, 3, 30, 1, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", FixedDateTime)
    assert clock.local_now("Europe/London").strftime("%H:%M %Z") == "02:00 BST"
    assert clock.local_now("Europe/London", time(14, 7)).strftime("%H:%M %Z") == "14:07 BST"


@pytest.mark.parametrize(("hour", "minute", "expected"), [
    (2, 0, ("IT", "IS", "TWO", "OCLOCK")),
    (2, 7, ("IT", "IS", "MIN_FIVE", "PAST", "TWO")),
    (12, 22, ("IT", "IS", "TWENTY", "PAST", "TWELVE")),
    (2, 25, ("IT", "IS", "TWENTY", "MIN_FIVE_25", "PAST", "TWO")),
    (2, 45, ("IT", "IS", "A", "QUARTER", "TO", "THREE")),
    (23, 59, ("IT", "IS", "TWELVE", "OCLOCK")),
])
def test_letter_words(hour, minute, expected):
    assert highlighted_words(hour, minute) == expected


def test_grid_word_coordinates():
    assert len(GRID) == 10 and all(len(row) == 15 for row in GRID)
    for word, (row, column, length) in WORDS.items():
        expected = {"MIN_FIVE": "FIVE", "MIN_FIVE_25": "FIVE", "MIN_TEN": "TEN"}.get(word, word)
        assert GRID[row][column:column + length] == expected
        assert 2 + (column + length - 1) * 4 + 3 <= 64
        assert 2 + row * 6 + 5 <= 64


def test_moon_new_full_and_timezones():
    new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    full = datetime(2000, 1, 21, 5, 40, tzinfo=timezone.utc)
    assert moon_phase(new)[1] < 0.01
    assert moon_phase(full)[1] > 0.99
    assert moon_phase(new) == moon_phase(new.astimezone(ZoneInfo("Europe/London")))
    with pytest.raises(ValueError):
        moon_phase(datetime(2025, 1, 1))


def test_screens_and_missing_data(tmp_path):
    now = datetime(2025, 6, 1, 14, 7, tzinfo=ZoneInfo("Europe/London"))
    manager = ScreenManager(Config())
    for name in manager.order:
        manager.select(manager.order.index(name))
        frame = manager.render(now)
        assert frame.size == (64, 64) and frame.mode == "RGB"
        assert frame.getbbox()
    manager = ScreenManager(Config(demo_tides=False), "tide-moon")
    offline = manager.render(now)
    demo = ScreenManager(Config(), "tide-moon").render(now)
    assert ImageChops.difference(offline, demo).getbbox()
    assert DemoTides().get(now).demo
    manager = ScreenManager(Config(), "tide-moon")
    new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    full = datetime(2000, 1, 21, 5, 40, tzinfo=timezone.utc)
    assert ImageChops.difference(manager.render(new).crop((38, 5, 59, 26)),
                                 manager.render(full).crop((38, 5, 59, 26))).getbbox()
    path = tmp_path / "frame.png"
    PngDisplay(str(path)).show(offline)
    with Image.open(path) as output:
        assert output.mode == "RGB" and output.size == (64, 64)


def test_display_validation_and_brightness():
    with pytest.raises(ValueError):
        prepare_frame(Image.new("L", (64, 64)), 100)
    with pytest.raises(ValueError):
        prepare_frame(Image.new("RGB", (63, 64)), 100)
    assert prepare_frame(Image.new("RGB", (64, 64), "white"), 0).getbbox() is None


def test_manager_controls():
    elapsed = [0]
    manager = ScreenManager(Config(cycle_seconds=5), monotonic=lambda: elapsed[0])
    elapsed[0] = 5
    manager.tick()
    assert manager.name == "letter-clock"
    manager.toggle_pause()
    elapsed[0] = 100
    manager.tick()
    assert manager.name == "letter-clock"
    manager.previous()
    assert manager.name == "word-clock"
    manager.toggle_pause()
    elapsed[0] += 5
    manager.tick()
    assert manager.name == "letter-clock"


@pytest.mark.parametrize("data", [
    {"brightness": -1}, {"brightness": True}, {"cycle_seconds": 0},
    {"timezone": "Not/AZone"}, {"screens": []}, {"demo_tides": "yes"},
    {"palette": ["#ffffff"]}, {"unexpected": True},
])
def test_invalid_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_config(str(path))


def test_cli_png(tmp_path):
    path = tmp_path / "letter.png"
    subprocess.run([sys.executable, "-m", "siriusvision", "--display", "png", "--screen",
                    "letter-clock", "--time", "12:22", "--output", str(path)], check=True)
    with Image.open(path) as image:
        assert image.size == (64, 64) and image.mode == "RGB"
    result = subprocess.run([sys.executable, "-m", "siriusvision", "--display", "png",
                             "--time", "24:00", "--output", str(path)], capture_output=True)
    assert result.returncode != 0 and b"HH:MM" in result.stderr
