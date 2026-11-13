import math

from PIL import Image, ImageDraw

from siriusvision.screens.base import RenderContext
from siriusvision.screens.pixel_font import draw_text, text_width
from siriusvision.services.moon import moon_phase


class TideMoon:
    name = "tide-moon"

    def render(self, context: RenderContext) -> Image.Image:
        theme = context.theme
        image = Image.new("RGB", (context.width, context.height), theme.background)
        draw = ImageDraw.Draw(image)
        if context.tide is None:
            draw_text(draw, "OFFLINE", 18, 30, theme.foreground)
            return image
        phase, _, label = moon_phase(context.now)
        cx, cy, radius = 48, 15, 9
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=theme.moon_shadow)
        # A sphere lit from the right while waxing, and from the left while waning.
        terminator = math.cos(2 * math.pi * phase)
        for dy in range(-radius, radius + 1):
            half = math.sqrt(radius * radius - dy * dy)
            for dx in range(math.ceil(-half), math.floor(half) + 1):
                lit = dx >= terminator * half if phase < 0.5 else dx <= -terminator * half
                if lit:
                    draw.point((cx + dx, cy + dy), fill=theme.moon_light)
        draw_text(draw, label, 48 - text_width(label) // 2, 27, theme.foreground)
        for x in range(64):
            y = round(47 - 8 * math.sin(context.tide.phase + (x - 32) * 0.09))
            draw.point((x, y), fill=theme.tide_curve)
        marker_y = round(47 - 8 * math.sin(context.tide.phase))
        draw.ellipse((30, marker_y - 2, 34, marker_y + 2), fill=theme.tide_marker)
        draw_text(draw, "DEMO DATA" if context.tide.demo else "TIDE", 2, 2, theme.foreground)
        return image
