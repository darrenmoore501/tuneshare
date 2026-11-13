import argparse
from datetime import time
from dataclasses import replace

from siriusvision.app import ScreenManager
from siriusvision.config import SCREEN_NAMES, load_config
from siriusvision.services.clock import local_now
from siriusvision.themes import THEMES


def parse_time(value: str) -> time:
    try:
        if len(value) != 5 or value[2] != ":" or not (value[:2] + value[3:]).isdigit():
            raise ValueError
        return time(int(value[:2]), int(value[3:]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be HH:MM in 24-hour local time") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SiriusVision pixel-art display")
    parser.add_argument("--display", choices=("preview", "png"), default="preview",
                        help="matrix hardware support is planned for a later phase")
    parser.add_argument("--screen", choices=SCREEN_NAMES)
    parser.add_argument("--theme", choices=tuple(THEMES), help="override the configured theme")
    parser.add_argument("--time", type=parse_time, help="override local time (HH:MM)")
    parser.add_argument("--config", help="path to JSON configuration")
    parser.add_argument("--demo", action="store_true", help="enable simulated tide data")
    parser.add_argument("--output", help="output PNG path (required for --display png)")
    args = parser.parse_args(argv)
    if args.display == "png" and not args.output:
        parser.error("--display png requires --output")
    try:
        config = load_config(args.config)
        if args.theme:
            config = replace(config, theme=args.theme)
        if args.demo:
            config = replace(config, demo_tides=True)
        manager = ScreenManager(config, args.screen)
        now = lambda: local_now(config.timezone, args.time)
        if args.display == "png":
            from siriusvision.displays.png_output import PngDisplay
            display = PngDisplay(args.output, config.brightness)
            display.show(manager.render(now()))
            display.close()
        else:
            from siriusvision.displays.mac_preview import MacPreview
            MacPreview(manager, now).run()
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"siriusvision: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
