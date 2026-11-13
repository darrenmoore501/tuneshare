from PIL import Image, ImageDraw

from siriusvision.screens.base import RenderContext
from siriusvision.screens.pixel_font import draw_text


GRID = (
    "ITXISXFIVEXXXXX",
    "AXQUARTERXTENXX",
    "TWENTYXFIVEXXXX",
    "HALFXPASTXTOXXX",
    "ONEXTWOXTHREEXX",
    "FOURXFIVEXSIXXX",
    "SEVENXEIGHTXXXX",
    "NINEXTENXXXXXXX",
    "ELEVENXTWELVEXX",
    "OCLOCKXXXXXXXXX",
)

# Keys distinguish words which occur more than once in the fixed face.
WORDS = {
    "IT": (0, 0, 2), "IS": (0, 3, 2), "MIN_FIVE": (0, 6, 4),
    "A": (1, 0, 1), "QUARTER": (1, 2, 7), "MIN_TEN": (1, 10, 3),
    "TWENTY": (2, 0, 6), "MIN_FIVE_25": (2, 7, 4),
    "HALF": (3, 0, 4), "PAST": (3, 5, 4), "TO": (3, 10, 2),
    "ONE": (4, 0, 3), "TWO": (4, 4, 3), "THREE": (4, 8, 5),
    "FOUR": (5, 0, 4), "FIVE": (5, 5, 4), "SIX": (5, 10, 3),
    "SEVEN": (6, 0, 5), "EIGHT": (6, 6, 5), "NINE": (7, 0, 4),
    "TEN": (7, 5, 3), "ELEVEN": (8, 0, 6), "TWELVE": (8, 7, 6),
    "OCLOCK": (9, 0, 6),
}
HOURS = ("TWELVE", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX",
         "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN")
MINUTES = ((), ("MIN_FIVE",), ("MIN_TEN",), ("A", "QUARTER"), ("TWENTY",),
           ("TWENTY", "MIN_FIVE_25"), ("HALF",), ("TWENTY", "MIN_FIVE_25"),
           ("TWENTY",), ("A", "QUARTER"), ("MIN_TEN",), ("MIN_FIVE",))


def highlighted_words(hour: int, minute: int) -> tuple[str, ...]:
    # Round to nearest five minutes, carrying into the next hour at :58.
    rounded = (minute + 2) // 5
    hour = (hour + (rounded >= 7)) % 12
    step = rounded % 12
    words = ["IT", "IS", *MINUTES[step]]
    if step:
        words.append("PAST" if step <= 6 else "TO")
    words.append(HOURS[hour])
    if not step:
        words.append("OCLOCK")
    return tuple(words)


class LetterClock:
    name = "letter-clock"

    def render(self, context: RenderContext) -> Image.Image:
        image = Image.new("RGB", (context.width, context.height))
        draw = ImageDraw.Draw(image)
        selected = {}
        for index, word in enumerate(highlighted_words(context.now.hour, context.now.minute)):
            row, start, length = WORDS[word]
            for column in range(start, start + length):
                selected[(row, column)] = context.palette[index % len(context.palette)]
        for row, line in enumerate(GRID):
            for column, char in enumerate(line):
                draw_text(draw, char, 2 + column * 4, 2 + row * 6,
                          selected.get((row, column), (19, 23, 27)))
        return image
