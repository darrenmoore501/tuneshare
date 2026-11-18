import importlib

from PIL import Image

from siriusvision.displays.base import prepare_frame


class PiMatrixDisplay:
    def __init__(self, brightness: int = 20):
        if type(brightness) is not int or not 1 <= brightness <= 100:
            raise ValueError("Pi matrix brightness must be an integer from 1 to 100")
        try:
            rgbmatrix = importlib.import_module("rgbmatrix")
        except ImportError as exc:
            raise ImportError(
                "The rgbmatrix Python bindings are required for --display pi. "
                "Install them into SiriusVision's virtual environment and use "
                "sudo with the full path to .venv/bin/python instead of sudo python3 "
                "(see docs/raspberry-pi.md).\n"
                f"rgbmatrix import error: {exc}"
            ) from exc

        options = rgbmatrix.RGBMatrixOptions()
        options.rows = 64
        options.cols = 64
        options.chain_length = 1
        options.hardware_mapping = "regular-pi1"
        options.brightness = brightness
        options.disable_hardware_pulsing = False
        self.matrix = rgbmatrix.RGBMatrix(options=options)

    def show(self, image: Image.Image) -> None:
        prepare_frame(image, 100)
        self.matrix.SetImage(image)

    def close(self) -> None:
        if self.matrix is not None:
            self.matrix.Clear()
            self.matrix = None
