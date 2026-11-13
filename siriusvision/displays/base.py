from typing import Protocol

from PIL import Image, ImageEnhance


def prepare_frame(image: Image.Image, brightness: int) -> Image.Image:
    if image.size != (64, 64) or image.mode != "RGB":
        raise ValueError("Display requires a 64x64 RGB image")
    if not 0 <= brightness <= 100:
        raise ValueError("Brightness must be between 0 and 100")
    return ImageEnhance.Brightness(image).enhance(brightness / 100) if brightness != 100 else image


class Display(Protocol):
    def show(self, image: Image.Image) -> None: ...

    def close(self) -> None: ...
