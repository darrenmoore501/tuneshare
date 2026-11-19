import time
from datetime import datetime
from typing import Callable

from PIL import Image

from siriusvision.config import Config
from siriusvision.screens.album_art import AlbumArt
from siriusvision.screens.base import RenderContext
from siriusvision.screens.letter_clock import LetterClock
from siriusvision.screens.tide_lamp import TideLamp
from siriusvision.services.spotify_state import PlaybackArtwork
from siriusvision.services.tides import SimulatedLampTides, TowerPierTides


class ScreenManager:
    def __init__(self, config: Config, start: str | None = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 playback: PlaybackArtwork | None = None):
        self.config = config
        self.screens = {screen.name: screen for screen in (LetterClock(), TideLamp(), AlbumArt())}
        if start is not None and start not in self.screens:
            raise ValueError(f"Unknown screen: {start}")
        self.order = list(config.screens)
        if start is not None and start not in self.order:
            self.order.insert(0, start)
        self.index = self.order.index(start) if start else 0
        self.paused = False
        self.monotonic = monotonic
        self.changed_at = monotonic()
        self.tides = (SimulatedLampTides(config.tide_simulation_level)
                      if config.demo_tides or config.tide_simulation_level is not None
                      else TowerPierTides(monotonic=monotonic))
        self.playback = playback if config.spotify_enabled and start is None else None
        self._spotify_artwork = None

    @property
    def name(self) -> str:
        if self.playback is not None:
            return "album-art" if self._spotify_artwork is not None else self.config.spotify_fallback_screen
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
        if (self.playback is None and not self.paused
                and self.monotonic() - self.changed_at >= self.config.cycle_seconds):
            self.next()

    def render(self, now: datetime) -> Image.Image:
        if self.playback is not None:
            self._spotify_artwork = self.playback.artwork()
        tide = self.tides.get(now) if self.name == "tide-lamp" else None
        context = RenderContext(now=now, palette=tuple(self.config.palette),
                                tide=tide,
                                brightness=self.config.brightness, album_artwork=self._spotify_artwork)
        return self.screens[self.name].render(context)
