import math

from PIL import Image, ImageDraw

from siriusvision.screens.base import RenderContext
from siriusvision.screens.pixel_font import draw_text, text_width
from siriusvision.services.moon import moon_phase


class TideMoon:
    name = "tide-moon"

    def render(self, context: RenderContext) -> Image.Image:
        image = Image.new("RGB", (context.width, context.height))
        draw = ImageDraw.Draw(image)
        if context.tide is None:
            draw_text(draw, "OFFLINE", 18, 30, context.palette[1])
            return image
        phase, _, label = moon_phase(context.now)
        cx, cy, radius = 48, 15, 9
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=(20, 27, 38))
        # A sphere lit from the right while waxing, and from the left while waning.
        terminator = math.cos(2 * math.pi * phase)
        for dy in range(-radius, radius + 1):
            half = math.sqrt(radius * radius - dy * dy)
            for dx in range(math.ceil(-half), math.floor(half) + 1):
                lit = dx >= terminator * half if phase < 0.5 else dx <= -terminator * half
                if lit:
                    draw.point((cx + dx, cy + dy), fill=(244, 215, 154))
        draw_text(draw, label, 48 - text_width(label) // 2, 27, context.palette[0])
        for x in range(64):
            y = round(47 - 8 * math.sin(context.tide.phase + (x - 32) * 0.09))
            draw.point((x, y), fill=context.palette[2])
            if x % 4 == 0:
                draw.point((x, y + 1), fill=(26, 74, 91))
        marker_y = round(47 - 8 * math.sin(context.tide.phase))
        draw.ellipse((30, marker_y - 2, 34, marker_y + 2), fill=context.palette[0])
        draw_text(draw, "DEMO DATA" if context.tide.demo else "TIDE", 2, 2, context.palette[1])
        return image
