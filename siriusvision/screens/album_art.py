import math

from PIL import Image, ImageDraw

from siriusvision.screens.base import RenderContext


class AlbumArt:
    name = "album-art"

    def render(self, context: RenderContext) -> Image.Image:
        image = Image.new("RGB", (context.width, context.height))
        draw = ImageDraw.Draw(image)
        for y in range(context.height):
            draw.line((0, y, context.width - 1, y), fill=(12 + y // 3, 10 + y // 2, 40 + y))
        draw.ellipse((18, 9, 46, 37), fill=(255, 164, 119))
        for y in range(36, 64):
            colour = (9, 29 + (y - 36), 49 + (y - 36))
            draw.line((0, y, 63, y), fill=colour)
        for row in range(5):
            y = 40 + row * 5
            width = 8 + row * 3
            offset = round(2 * math.sin(row * 2))
            draw.line((32 - width + offset, y, 32 + width + offset, y), fill=(191, 111, 130))
        return image
