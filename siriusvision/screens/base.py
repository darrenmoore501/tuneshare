from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from PIL import Image

from siriusvision.services.tides import LampTideData


@dataclass(frozen=True)
class RenderContext:
    now: datetime
    palette: tuple[str, ...]
    tide: LampTideData | None = None
    width: int = 64
    height: int = 64
    brightness: int = 100
    album_artwork: Image.Image | None = None


class Screen(Protocol):
    name: str

    def render(self, context: RenderContext) -> Image.Image: ...
