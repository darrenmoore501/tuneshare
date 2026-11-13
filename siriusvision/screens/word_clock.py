from PIL import Image, ImageDraw

from siriusvision.screens.base import RenderContext
from siriusvision.screens.pixel_font import draw_text, text_width


ONES = ("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
        "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN",
        "SEVENTEEN", "EIGHTEEN", "NINETEEN")
TENS = ("", "", "TWENTY", "THIRTY", "FORTY", "FIFTY")


def number_words(value: int) -> list[str]:
    if value < 20:
        return [ONES[value]]
    return [TENS[value // 10]] + ([ONES[value % 10]] if value % 10 else [])


def clock_words(hour: int, minute: int, clock_format: int = 12) -> list[str]:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or clock_format not in (12, 24):
        raise ValueError("Invalid clock time or format")
    shown_hour = (hour % 12 or 12) if clock_format == 12 else hour
    words = number_words(shown_hour)
    if minute < 10:
        words += ["ZERO", ONES[minute]]
    else:
        words += number_words(minute)
    # Keep the three-word example TWELVE / TWENTY / TWO uncluttered.
    if clock_format == 12 and minute < 20:
        words.append("AM" if hour < 12 else "PM")
    return words


class WordClock:
    name = "word-clock"

    def render(self, context: RenderContext) -> Image.Image:
        words = clock_words(context.now.hour, context.now.minute, context.clock_format)
        image = Image.new("RGB", (context.width, context.height))
        draw = ImageDraw.Draw(image)
        scale = min(2, min((context.width - 4) // text_width(word) for word in words),
                    (context.height - 2 * (len(words) - 1)) // (5 * len(words)))
        if scale < 1:
            raise ValueError("Clock words do not fit canvas")
        height = len(words) * 5 * scale + (len(words) - 1) * 2
        y = (context.height - height) // 2
        for index, word in enumerate(words):
            x = (context.width - text_width(word, scale)) // 2
            draw_text(draw, word, x, y, context.palette[index % len(context.palette)], scale)
            y += 5 * scale + 2
        return image
