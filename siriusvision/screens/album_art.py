from PIL import Image

from siriusvision.screens.base import RenderContext
from siriusvision.screens.letter_clock import LetterClock


class AlbumArt:
    name = "album-art"

    def render(self, context: RenderContext) -> Image.Image:
        if context.album_artwork is not None:
            return context.album_artwork
        return LetterClock().render(context)
