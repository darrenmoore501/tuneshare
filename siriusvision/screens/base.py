from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from PIL import Image

from siriusvision.services.tides import TideData


@dataclass(frozen=True)
class RenderContext:
    now: datetime
    palette: tuple[str, ...]
    clock_format: int = 12
    tide: TideData | None = None
    width: int = 64
    height: int = 64
    brightness: int = 100


class Screen(Protocol):
    name: str

    def render(self, context: RenderContext) -> Image.Image: ...
