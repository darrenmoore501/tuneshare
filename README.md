# SiriusVision

Pixel-art screens for Sirius, a boat with a planned 64×64 LED display. Phase 1
runs entirely offline on a Mac; no Pi, network, Spotify account or credentials
are needed.

![SiriusVision simulator showing the spoken clock at 14:07](docs/images/preview.png)

## macOS quick start

Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/macos/)
with Tk support. Check `python3 -m tkinter` opens a window. Some Homebrew
Python installations require the matching `python-tk` package. Then:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m siriusvision --display preview
```

After installation, the last command is the one-command startup. The
640×640 preview scales the 64×64 RGB frame with nearest-neighbour pixels.
The title, optional grid overlay and controls are simulator UI, not part of
the native frame.

- **N / right**: next screen; **P / left**: previous screen.
- **Space**: pause/resume rotation; **1–4**: select a screen in configured
  order; **Q**: quit. Screen changes cross-fade in the preview.
- The default rotation is 30 seconds; pausing does not stop clock updates or
  the tide animation.

```sh
python -m siriusvision --display preview --screen word-clock --time 14:07
python -m siriusvision --display preview --screen tide-moon --demo
python -m siriusvision --display png --screen letter-clock --time 12:22 --output /tmp/clock.png
python -m pytest
```

`--time HH:MM` overrides the current local time on today's date (24-hour
input). Without it, the clock uses the configured timezone, including DST.
PNG output is a single 64×64 RGB frame and works without Tk. The preview
requires a graphical desktop and Tkinter.

## Configuration and screens

Copy `config.example.json` to an appropriate local path and pass
`--config /path/to/config.json`; otherwise built-in defaults are used. Set
screen order, `cycle_seconds` (1–86400), `brightness` (0–100),
`pi_brightness` (1–100; defaults to 20), IANA `timezone`, `clock_format`
(12 or 24), `show_grid`, and at least four hexadecimal `palette` colours.
Brightness is applied at output, not inside screen rendering. Invalid
settings are reported on startup.

* **Word clock:** complete words at native resolution, dynamically scaled to
  fit. Minutes below ten include ZERO. In 12-hour mode AM/PM is shown for
  minutes 00–19; for 20–59 it is omitted to keep the face uncluttered.
  24-hour mode spells the hour from ZERO to TWENTY THREE.
* **Letter clock:** an original ten-row, fifteen-column face of 3×5 glyphs
  on a 4×6 pitch, starting at (2,2). Dim letters stay in place; highlighted
  spans spell the time rounded to the nearest five minutes. Separate FIVE
  and TEN spans distinguish minutes from hours; the hour advances for
  “TO” and at the rounding boundary near the hour.
* **Tide + moon:** the wave is **DEMO DATA**, not a Thames prediction or
  navigational information. `demo_tides` defaults to true and the screen
  labels it visibly; `--demo` enables it explicitly. Set `demo_tides` to
  false to show OFFLINE until a real provider exists. The moon is an offline
  approximation using a 29.530588853-day synodic period from the
  2000-01-06 18:14 UTC new-moon epoch; it is not an ephemeris.
* **Album art:** a generated, original sunset gradient, not Spotify artwork.

## Architecture and phase status

Each screen implements `render(context)` and returns a native Pillow RGB
image; it has no knowledge of the output backend. The context carries
timezone-aware time, palette, brightness and optional tide data. The screen
manager supplies offline data before drawing and offers selection and
cycling APIs. The preview and PNG displays validate frames and apply output
brightness. The tiny bitmap font is original to this project.

The Pi matrix backend is implemented; there is still no real tide provider,
Spotify OAuth, personal photos, web UI or GPIO button. Real providers must
run independently of rendering, handle failures and timeouts, and label their
sources. `.env`, tokens, caches and private `photos/` are ignored; never
commit credentials or personal images.

## Raspberry Pi deployment

The headless `pi` backend sends complete native 64×64 RGB frames to the
separately installed `rpi-rgb-led-matrix` driver and leaves refreshing to the
hardware. See [docs/raspberry-pi.md](docs/raspberry-pi.md) for Raspberry Pi OS
installation, manual startup, and systemd service instructions. The
matrix defaults to 20% hardware brightness; configure `pi_brightness` to
adjust it. The existing `brightness` setting continues to control preview
and PNG output. A config that specifies only `brightness` also uses that
value for Pi output when it is 1–100; zero remains valid for preview/PNG and
leaves the Pi-specific default unchanged.
