# Tower Pier tide lamp

The lamp uses Environment Agency station **0007**, Tower Pier by Tower Bridge.
It reads the official `0007-level-tidal_level-i-15_min-mAOD` measure every
15 minutes, requesting the last 72 hours (up to 400 observations). Heights
are metres above Ordnance Datum, not water depth below a boat.

At least 48 observations spanning 24 hours are required. The recent minimum
and maximum establish the displayed range; this is a rolling observed range,
not predicted astronomical high/low water. Rising/falling is derived from
successive observations, with changes below 1 cm treated as steady.
Timestamps are parsed in UTC; log diagnostics use Europe/London including DST.

The native 64x64 field blends midnight/ocean blue and soft cyan below a
horizontal, feathered waterline with dark sand and amber above. Static
ordered dithering avoids temporal shimmer. Some blue and warm colour remain
visible at both extremes. Measurements ease toward their new level with a
ten-minute time constant; the lamp does not invent a wave or forecast tide
turns. Unchanged output frames are not retransmitted.

On startup without usable data, a dim neutral field is shown, without text.
Network errors, insufficient history, a flat range, and observations older
than two hours are logged. After a successful reading, failures retain the
last measurement rather than simulating a tide. Do not use this ambient
display for navigation, mooring clearance, or safety decisions.

## Run and simulate

```sh
.venv/bin/python -m siriusvision --screen tide-lamp
.venv/bin/python -m siriusvision --screen tide-lamp --demo
.venv/bin/python -m siriusvision --display png --screen tide-lamp \
  --tide-level 50 --output /tmp/tide-50.png
```

`--tide-level` accepts 0 through 100 inclusive and makes no tide API requests.
`--demo` slowly sweeps between the extremes for visual testing only. A JSON
config can set `tide_simulation_level` to a percentage, or `null` for live data.
`demo_tides` defaults to `false`. Neither setting affects Spotify playback.

Brightness is independent of colour composition: `brightness` controls PNG
and preview outputs, while `pi_brightness` controls the matrix hardware.

## Existing configurations

Use the updated `config.example.json`. Valid screen names are only
`letter-clock`, `tide-lamp`, and `album-art`; remove `clock_format`, replace old
screen lists, and set `spotify_fallback_screen` to `letter-clock` or
`tide-lamp`. Old names are rejected explicitly rather than silently remapped.
The letter clock face and colours are unchanged.
