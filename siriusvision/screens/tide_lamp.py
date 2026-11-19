import math

from PIL import Image

from siriusvision.screens.base import RenderContext


BACKGROUND = (3, 6, 9)
DEEP_WATER = (8, 37, 61)
WATER = (18, 106, 145)
HIGHLIGHT = (82, 189, 208)
SAND = (80, 53, 31)
AMBER = (212, 154, 81)
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def blend(first: tuple[int, int, int], second: tuple[int, int, int],
          amount: float) -> tuple[float, float, float]:
    return tuple(a + (b - a) * amount for a, b in zip(first, second))


class TideLamp:
    name = "tide-lamp"

    def __init__(self):
        self._frame: Image.Image | None = None
        self._pixels: bytes | None = None
        self._level: float | None = None
        self._rendered = False

    def render(self, context: RenderContext) -> Image.Image:
        if (context.width, context.height) != (64, 64):
            raise ValueError("The tide lamp renders natively at 64x64")
        level = context.tide.level if context.tide is not None else None
        if level is not None and (not math.isfinite(level) or not 0 <= level <= 1):
            raise ValueError("Tide level must be between 0 and 1")
        if self._rendered and level == self._level and self._frame is not None:
            return self._frame
        waterline = 60 - 56 * level if level is not None else 32
        pixels = bytearray()
        for y in range(64):
            depth = max(0, min(1, (y - waterline) / max(1, 64 - waterline)))
            water = blend(HIGHLIGHT, WATER, min(1, depth * 4))
            water = tuple(a + (b - a) * depth ** 0.7 for a, b in zip(water, DEEP_WATER))
            warmth = (1 - level) if level is not None else 0
            glow = math.exp(-((y - waterline + 7) / 20) ** 2)
            sand = blend(SAND, AMBER, 0.48 * warmth * glow)
            water_weight = 1 / (1 + math.exp(-(y - waterline) / 2.4))
            colour = tuple(a + (b - a) * water_weight for a, b in zip(sand, water))
            if level is None:
                # A dim, non-measuring standby field, never an invented tide level.
                colour = tuple(a + (b - a) * 0.12 for a, b in zip(BACKGROUND, colour))
            for x in range(64):
                threshold = (BAYER[y % 4][x % 4] + 0.5) / 16
                pixels.extend(
                    max(0, min(255, math.floor(channel + threshold))) for channel in colour
                )
        output = bytes(pixels)
        if output != self._pixels:
            self._frame = Image.frombytes("RGB", (64, 64), output)
            self._pixels = output
        self._level = level
        self._rendered = True
        if self._frame is None:
            raise RuntimeError("Tide lamp frame was not created")
        return self._frame
