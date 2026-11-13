import math

from PIL import Image, ImageDraw

from siriusvision.screens.base import RenderContext
from siriusvision.screens.pixel_font import draw_text


class AlbumArt:
    name = "album-art"

    def render(self, context: RenderContext) -> Image.Image:
        if context.album_art is not None:
            if context.album_art.mode != "RGB" or context.album_art.size != (context.width, context.height):
                raise ValueError("Album art must be a native-size RGB image")
            return context.album_art.copy()
        theme = context.theme
        image = Image.new("RGB", (context.width, context.height), theme.placeholder_sky)
        draw = ImageDraw.Draw(image)
        draw_text(draw, "NO ART", 2, 2, theme.foreground)
        draw.ellipse((18, 11, 46, 39), fill=theme.placeholder_sun)
        draw.rectangle((0, 36, context.width - 1, context.height - 1), fill=theme.placeholder_land)
        for row in range(5):
            y = 40 + row * 5
            width = 8 + row * 3
            offset = round(2 * math.sin(row * 2))
            draw.line((32 - width + offset, y, 32 + width + offset, y), fill=theme.placeholder_wave)
        return image
