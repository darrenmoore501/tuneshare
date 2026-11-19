import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageChops

from siriusvision.app import ScreenManager
from siriusvision.config import Config, load_config
from siriusvision.displays.base import prepare_frame
from siriusvision.displays.png_output import PngDisplay
from siriusvision.displays.pi_matrix import PiMatrixDisplay
from siriusvision.screens.base import RenderContext
from siriusvision.screens.letter_clock import GRID, WORDS, highlighted_words
from siriusvision.screens.tide_lamp import TideLamp
from siriusvision.services.tides import LampTideData, Reading, TowerPierTides


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


def test_screens_and_missing_data(tmp_path):
    now = datetime(2025, 6, 1, 14, 7, tzinfo=ZoneInfo("Europe/London"))
    manager = ScreenManager(Config(demo_tides=True))
    assert set(manager.screens) == {"letter-clock", "tide-lamp", "album-art"}
    for name in manager.order:
        manager.select(manager.order.index(name))
        frame = manager.render(now)
        assert frame.size == (64, 64) and frame.mode == "RGB"
        assert frame.getbbox()
    manager = ScreenManager(Config(), "tide-lamp")
    manager.tides = TowerPierTides(fetch=lambda _: [])
    offline = manager.render(now)
    demo = ScreenManager(Config(tide_simulation_level=75), "tide-lamp").render(now)
    assert ImageChops.difference(offline, demo).getbbox()
    path = tmp_path / "frame.png"
    PngDisplay(str(path)).show(offline)
    with Image.open(path) as output:
        assert output.mode == "RGB" and output.size == (64, 64)


def test_tide_lamp_extremes_smooth_waterline_and_static_dithering():
    lamp = TideLamp()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    blue_counts = []
    frames = []
    for level in (0, 0.25, 0.5, 0.75, 1):
        context = RenderContext(now, Config().palette, tide=LampTideData(level))
        frame = lamp.render(context)
        assert lamp.render(context) is frame
        pixels = [frame.getpixel((x, y)) for y in range(64) for x in range(64)]
        blue_counts.append(sum(b > r for r, g, b in pixels))
        assert all(max(pixel) > 0 for pixel in pixels)
        assert any(b > r for r, g, b in pixels)
        assert any(r > b for r, g, b in pixels)
        frames.append(frame)
    assert blue_counts == sorted(set(blue_counts))
    low = frames[0]
    high = frames[-1]
    assert sum(low.getpixel((x, y))[0] for y in range(64) for x in range(64)) > sum(
        high.getpixel((x, y))[0] for y in range(64) for x in range(64))
    context = RenderContext(now, Config().palette, tide=LampTideData(0.5001))
    nearby = lamp.render(context)
    assert max(ImageChops.difference(frames[2], nearby).getextrema()[i][1]
               for i in range(3)) <= 1
    with pytest.raises(ValueError, match="between 0 and 1"):
        lamp.render(RenderContext(now, Config().palette, tide=LampTideData(float("nan"))))


def test_tower_pier_polling_range_smoothing_and_outage(caplog):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    elapsed = [0.0]
    calls = []
    readings = [Reading(now - timedelta(minutes=15 * (192 - i)), (i % 48) / 8)
                for i in range(193)]
    failure = [False]

    def fetch(since):
        calls.append(since)
        if failure[0]:
            raise OSError("offline")
        return readings

    service = TowerPierTides(fetch, lambda: elapsed[0])
    with caplog.at_level("INFO"):
        first = service.get(now)
    assert first.level == 0 and first.low == 0 and first.high == 47 / 8
    assert first.rising is False
    assert "BST" in caplog.text
    service.get(now)
    assert len(calls) == 1 and calls[0] == now - timedelta(hours=72)
    readings[-1] = Reading(now, 5)
    elapsed[0] = 900
    assert service.get(now).level == 0  # No jump at observation arrival.
    elapsed[0] = 1200
    eased = service.get(now)
    assert 0 < eased.level < 5 / first.high
    assert eased.rising is False  # Still lower than the preceding observation.
    failure[0] = True
    elapsed[0] = 1800
    held = service.get(now)
    assert held.observed_at == first.observed_at and held.height == 5
    assert "offline" in caplog.text
    with pytest.raises(ValueError, match="timezone-aware"):
        service.get(now.replace(tzinfo=None))


@pytest.mark.parametrize("history", ["empty", "short", "flat", "stale"])
def test_tower_pier_rejects_unusable_history(history, caplog):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    readings = [Reading(now - timedelta(minutes=15 * i), i % 12) for i in range(193)]
    if history == "empty":
        readings = []
    elif history == "short":
        readings = readings[:20]
    elif history == "flat":
        readings = [Reading(reading.at, 1) for reading in readings]
    else:
        readings = [Reading(reading.at - timedelta(hours=3), reading.height)
                    for reading in readings]
    assert TowerPierTides(lambda _: readings).get(now) is None
    assert "Tower Pier tide data unavailable" in caplog.text


def test_tower_pier_response_parsing(monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    from siriusvision.services import tides

    payload = {"items": [
        {"dateTime": "2026-06-01T12:15:00+01:00", "value": 2.5},
        {"dateTime": "2026-06-01T11:00:00Z", "value": 2},
    ]}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, limit):
            assert limit == 2_000_001
            return json.dumps(payload).encode()

    def request(url, timeout):
        assert "0007-level-tidal_level-i-15_min-mAOD/readings" in url
        assert parse_qs(urlsplit(url).query)["since"] == ["2026-05-29T00:00:00Z"]
        assert timeout == 10
        return Response()

    monkeypatch.setattr(tides, "urlopen", request)
    since = datetime(2026, 5, 29, tzinfo=timezone.utc)
    readings = tides.fetch_readings(since)
    assert [reading.height for reading in readings] == [2, 2.5]
    assert readings[-1].at == datetime(2026, 6, 1, 11, 15, tzinfo=timezone.utc)
    payload["items"][0]["dateTime"] = "2026-06-01T12:15:00"
    with pytest.raises(ValueError, match="timezone"):
        tides.fetch_readings(since)
    payload["items"][0] = {"dateTime": "2026-06-01T12:15:00Z", "value": True}
    with pytest.raises(ValueError, match="timestamp or height"):
        tides.fetch_readings(since)


@pytest.mark.parametrize("level", [0, 50, 100])
def test_cli_tide_simulation_and_example_config(tmp_path, level):
    path = tmp_path / f"tide-{level}.png"
    subprocess.run([
        sys.executable, "-m", "siriusvision", "--config", "config.example.json",
        "--display", "png", "--screen", "tide-lamp", "--tide-level", str(level),
        "--output", str(path),
    ], check=True)
    with Image.open(path) as image:
        assert image.mode == "RGB" and image.size == (64, 64) and image.getbbox()
    result = subprocess.run([
        sys.executable, "-m", "siriusvision", "--display", "png",
        "--tide-level", "nan", "--output", str(path),
    ], capture_output=True)
    assert result.returncode == 2 and b"0 to 100" in result.stderr


def test_display_validation_and_brightness():
    with pytest.raises(ValueError):
        prepare_frame(Image.new("L", (64, 64)), 100)
    with pytest.raises(ValueError):
        prepare_frame(Image.new("RGB", (63, 64)), 100)
    assert prepare_frame(Image.new("RGB", (64, 64), "white"), 0).getbbox() is None


def test_pi_matrix_initialization_transmission_and_shutdown(monkeypatch):
    class Options:
        pass

    class Matrix:
        def __init__(self, options):
            self.options = options
            self.images = []
            self.cleared = False

        def SetImage(self, image):
            self.images.append(image)

        def Clear(self):
            self.cleared = True

    matrices = []

    def create_matrix(options):
        matrix = Matrix(options)
        matrices.append(matrix)
        return matrix

    monkeypatch.setattr(
        "importlib.import_module",
        lambda name: SimpleNamespace(RGBMatrixOptions=Options, RGBMatrix=create_matrix),
    )
    display = PiMatrixDisplay(brightness=27)
    matrix = matrices[0]
    assert (matrix.options.rows, matrix.options.cols, matrix.options.chain_length) == (64, 64, 1)
    assert matrix.options.hardware_mapping == "regular-pi1"
    assert matrix.options.brightness == 27
    assert matrix.options.disable_hardware_pulsing is False

    image = Image.new("RGB", (64, 64), "white")
    display.show(image)
    assert matrix.images == [image]
    with pytest.raises(ValueError):
        display.show(Image.new("RGB", (63, 64)))
    with pytest.raises(ValueError):
        display.show(Image.new("L", (64, 64)))
    display.close()
    display.close()
    assert matrix.cleared
    default_display = PiMatrixDisplay()
    assert matrices[-1].options.brightness == 20
    default_display.close()


def test_pi_matrix_brightness_validation():
    with pytest.raises(ValueError):
        PiMatrixDisplay(brightness=101)
    with pytest.raises(ValueError, match="1 to 100"):
        PiMatrixDisplay(brightness=0)
    with pytest.raises(ValueError):
        PiMatrixDisplay(brightness=True)


@pytest.mark.parametrize("error", [
    ModuleNotFoundError("No module named 'rgbmatrix'"),
    ImportError("cannot load native matrix library"),
])
def test_pi_matrix_binding_import_error(monkeypatch, error):
    def fail_import(name):
        raise error

    monkeypatch.setattr("importlib.import_module", fail_import)
    with pytest.raises(ImportError, match="rgbmatrix Python bindings") as exc:
        PiMatrixDisplay()
    assert ".venv/bin/python" in str(exc.value)
    assert str(error) in str(exc.value)


def test_headless_runner_cycles_skips_unchanged_frames_and_closes():
    from siriusvision.__main__ import run_headless

    elapsed = [0.0]
    manager = ScreenManager(Config(cycle_seconds=1, demo_tides=True), monotonic=lambda: elapsed[0])

    class StopAfter:
        def __init__(self, loops):
            self.loops = loops
            self.waits = 0

        def __call__(self):
            return self.waits >= self.loops

        def wait(self, seconds):
            assert seconds == 1.0
            elapsed[0] += seconds
            self.waits += 1

    class Display:
        def __init__(self):
            self.images = []
            self.closed = False

        def show(self, image):
            self.images.append(image)

        def close(self):
            self.closed = True

    display = Display()
    stop_after = StopAfter(3)
    run_headless(manager, display, lambda: datetime(2025, 6, 1, tzinfo=timezone.utc),
                 stop_after, stop_after.wait)
    assert manager.name == "album-art"
    assert len(display.images) == 3
    assert display.closed

    static_display = Display()
    stop_after = StopAfter(2)
    run_headless(ScreenManager(Config(cycle_seconds=30)),
                 static_display, lambda: datetime(2025, 6, 1, tzinfo=timezone.utc),
                 stop_after, stop_after.wait)
    assert len(static_display.images) == 1
    assert static_display.closed


def test_manager_controls():
    elapsed = [0]
    manager = ScreenManager(Config(cycle_seconds=5), monotonic=lambda: elapsed[0])
    elapsed[0] = 5
    manager.tick()
    assert manager.name == "tide-lamp"
    manager.toggle_pause()
    elapsed[0] = 100
    manager.tick()
    assert manager.name == "tide-lamp"
    manager.previous()
    assert manager.name == "letter-clock"
    manager.toggle_pause()
    elapsed[0] += 5
    manager.tick()
    assert manager.name == "tide-lamp"


@pytest.mark.parametrize("data", [
    {"brightness": -1}, {"brightness": True}, {"cycle_seconds": 0},
    {"timezone": "Not/AZone"}, {"screens": []}, {"demo_tides": "yes"},
    {"palette": ["#ffffff"]}, {"unexpected": True},
    {"tide_simulation_level": -1}, {"tide_simulation_level": 101},
    {"tide_simulation_level": True}, {"tide_simulation_level": float("nan")},
    {"screens": ["word-clock"]}, {"screens": ["tide-moon"]},
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


def test_cli_preview_remains_available(monkeypatch):
    from siriusvision import __main__ as cli

    calls = []

    class Preview:
        def __init__(self, manager, now):
            calls.append((manager.name, now))

        def run(self):
            calls.append("run")

    monkeypatch.setitem(
        sys.modules, "siriusvision.displays.mac_preview", SimpleNamespace(MacPreview=Preview)
    )
    assert cli.main(["--display", "preview", "--screen", "letter-clock"]) == 0
    assert calls[0][0] == "letter-clock"
    assert calls[1] == "run"


def test_config_brightness_defaults_and_overrides(tmp_path):
    defaults = load_config()
    assert defaults.brightness == 80
    assert defaults.pi_brightness == 20

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"pi_brightness": 0}))
    with pytest.raises(ValueError, match="pi_brightness must be an integer from 1 to 100"):
        load_config(str(path))

    path.write_text(json.dumps({"brightness": 0}))
    config = load_config(str(path))
    assert config.brightness == 0 and config.pi_brightness == 20

    path.write_text(json.dumps({"brightness": 42}))
    assert load_config(str(path)).pi_brightness == 42

    path.write_text(json.dumps({"brightness": 42, "pi_brightness": 13}))
    config = load_config(str(path))
    assert config.brightness == 42 and config.pi_brightness == 13


@pytest.mark.parametrize("interrupt", ["sigterm", "keyboard"])
def test_cli_pi_shutdown_restores_signal_and_closes_display(monkeypatch, interrupt):
    from siriusvision import __main__ as cli

    handlers = {}
    displays = []
    signal_state = {"restored": False}

    class Display:
        def __init__(self, brightness):
            self.brightness = brightness
            self.closed = False
            displays.append(self)
            if interrupt == "sigterm":
                handlers[cli.signal.SIGTERM](cli.signal.SIGTERM, None)

        def close(self):
            self.closed = True

    def signal_handler(signum, handler):
        previous = handlers.get(signum, cli.signal.SIG_DFL)
        if handler == cli.signal.SIG_DFL:
            signal_state["restored"] = True
        handlers[signum] = handler
        return previous

    monkeypatch.setattr(cli.signal, "signal", signal_handler)
    monkeypatch.setitem(
        sys.modules, "siriusvision.displays.pi_matrix", SimpleNamespace(PiMatrixDisplay=Display)
    )

    if interrupt == "keyboard":
        def interrupt_during_run(manager, display, now, should_stop):
            raise KeyboardInterrupt
        monkeypatch.setattr(cli, "run_headless", interrupt_during_run)

    assert cli.main(["--display", "pi"]) == 0
    assert displays and displays[0].closed
    assert signal_state["restored"]
