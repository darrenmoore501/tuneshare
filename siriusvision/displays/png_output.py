from PIL import Image

from siriusvision.displays.base import prepare_frame


class PngDisplay:
    def __init__(self, path: str, brightness: int = 100):
        self.path = path
        self.brightness = brightness

    def show(self, image: Image.Image) -> None:
        prepare_frame(image, self.brightness).save(self.path, format="PNG")

    def close(self) -> None:
        pass
