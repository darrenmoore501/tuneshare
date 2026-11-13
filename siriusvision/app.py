import time
from datetime import datetime
from typing import Callable

from PIL import Image

from siriusvision.config import Config
from siriusvision.screens.album_art import AlbumArt
from siriusvision.screens.base import RenderContext
from siriusvision.screens.letter_clock import LetterClock
from siriusvision.screens.tide_moon import TideMoon
from siriusvision.screens.word_clock import WordClock
from siriusvision.services.tides import DemoTides


class ScreenManager:
    def __init__(self, config: Config, start: str | None = None,
                 monotonic: Callable[[], float] = time.monotonic):
        self.config = config
        self.screens = {screen.name: screen for screen in (WordClock(), LetterClock(), TideMoon(), AlbumArt())}
        self.order = list(config.screens)
        if start is not None and start not in self.order:
            self.order.insert(0, start)
        self.index = self.order.index(start) if start else 0
        self.paused = False
        self.monotonic = monotonic
        self.changed_at = monotonic()
        self.tides = DemoTides()

    @property
    def name(self) -> str:
        return self.order[self.index]

    def select(self, index: int) -> None:
        self.index = index % len(self.order)
        self.changed_at = self.monotonic()

    def next(self) -> None:
        self.select(self.index + 1)

    def previous(self) -> None:
        self.select(self.index - 1)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.changed_at = self.monotonic()

    def tick(self) -> None:
        if not self.paused and self.monotonic() - self.changed_at >= self.config.cycle_seconds:
            self.next()

    def render(self, now: datetime) -> Image.Image:
        tide = self.tides.get(now) if self.config.demo_tides and self.name == "tide-moon" else None
        context = RenderContext(now=now, palette=tuple(self.config.palette),
                                clock_format=self.config.clock_format, tide=tide,
                                brightness=self.config.brightness)
        return self.screens[self.name].render(context)
