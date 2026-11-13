"""Flat colour palettes and semantic roles for native screens and the simulator."""

from dataclasses import dataclass, replace
from types import MappingProxyType


@dataclass(frozen=True)
class Palette:
    paper: str = "#F3EBDD"
    ink: str = "#17151A"
    red: str = "#D63A3A"
    pink_red: str = "#D94A66"
    mustard: str = "#D7A51D"
    blue: str = "#5A8FB8"
    teal: str = "#2E6F8E"
    green: str = "#4B7F5F"
    lavender_grey: str = "#7A7E98"
    plum: str = "#34253A"
    cloud_blue: str = "#5A6F86"
    muted_cloud_blue: str = "#303A46"


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    foreground: str
    inactive: str
    accents: tuple[str, ...]
    tide_curve: str
    tide_marker: str
    moon_shadow: str
    moon_light: str
    placeholder_sky: str
    placeholder_land: str
    placeholder_sun: str
    placeholder_wave: str


def _dark_theme(name: str, palette: Palette) -> Theme:
    return Theme(
        name=name, background=palette.ink, foreground=palette.paper,
        inactive=palette.muted_cloud_blue,
        accents=(palette.red, palette.mustard, palette.blue, palette.pink_red),
        tide_curve=palette.cloud_blue, tide_marker=palette.mustard,
        moon_shadow=palette.plum, moon_light=palette.paper,
        placeholder_sky=palette.plum, placeholder_land=palette.teal,
        placeholder_sun=palette.mustard, placeholder_wave=palette.pink_red,
    )


SHRIGLEY = Palette()
SHRIGLEY_DARK = _dark_theme("shrigley_dark", SHRIGLEY)
SHRIGLEY_PAPER = replace(
    SHRIGLEY_DARK, name="shrigley_paper", background=SHRIGLEY.paper,
    foreground=SHRIGLEY.ink, inactive=SHRIGLEY.lavender_grey,
    accents=(SHRIGLEY.red, SHRIGLEY.teal, SHRIGLEY.green, SHRIGLEY.plum),
    moon_shadow=SHRIGLEY.lavender_grey, moon_light=SHRIGLEY.mustard,
    placeholder_sky=SHRIGLEY.paper, placeholder_wave=SHRIGLEY.paper,
)
NIGHT_BLUE = _dark_theme("night_blue", replace(
    SHRIGLEY, ink="#101C2B", plum="#22334A", muted_cloud_blue="#2F4359",
))
NIGHT_BLUE = replace(
    NIGHT_BLUE, accents=(SHRIGLEY.blue, SHRIGLEY.paper, SHRIGLEY.mustard, SHRIGLEY.green),
    placeholder_wave=SHRIGLEY.blue,
)

DEFAULT_THEME = "shrigley_dark"
THEMES = MappingProxyType({theme.name: theme for theme in (
    SHRIGLEY_DARK, SHRIGLEY_PAPER, NIGHT_BLUE,
)})


def get_theme(name: str, accents: tuple[str, ...] | None = None) -> Theme:
    if not isinstance(name, str) or name not in THEMES:
        raise ValueError(f"Unknown theme: {name!r}; choose from {', '.join(THEMES)}")
    theme = THEMES[name]
    return replace(theme, accents=tuple(accents)) if accents is not None else theme
