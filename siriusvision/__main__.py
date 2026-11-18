import argparse
import signal
from dataclasses import replace
from datetime import datetime, time
from time import sleep
from typing import Callable

from siriusvision.app import ScreenManager
from siriusvision.config import SCREEN_NAMES, load_config
from siriusvision.displays.base import Display
from siriusvision.services.clock import local_now


def parse_time(value: str) -> time:
    try:
        if len(value) != 5 or value[2] != ":" or not (value[:2] + value[3:]).isdigit():
            raise ValueError
        return time(int(value[:2]), int(value[3:]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be HH:MM in 24-hour local time") from exc


def run_headless(manager: ScreenManager, display: Display, now: Callable[[], datetime],
                 should_stop: Callable[[], bool],
                 wait: Callable[[float], None] = sleep) -> None:
    last_frame = None
    try:
        while not should_stop():
            manager.tick()
            image = manager.render(now())
            frame = image.tobytes()
            if frame != last_frame:
                display.show(image)
                last_frame = frame
            wait(1.0)
    finally:
        display.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SiriusVision pixel-art display")
    parser.add_argument("--display", choices=("preview", "png", "pi"), default="preview",
                        help="output backend")
    parser.add_argument("--screen", choices=SCREEN_NAMES)
    parser.add_argument("--time", type=parse_time, help="override local time (HH:MM)")
    parser.add_argument("--config", help="path to JSON configuration")
    parser.add_argument("--demo", action="store_true", help="enable simulated tide data")
    parser.add_argument("--output", help="output PNG path (required for --display png)")
    args = parser.parse_args(argv)
    if args.display == "png" and not args.output:
        parser.error("--display png requires --output")
    try:
        config = load_config(args.config)
        if args.demo:
            config = replace(config, demo_tides=True)
        manager = ScreenManager(config, args.screen)
        now = lambda: local_now(config.timezone, args.time)
        if args.display == "png":
            from siriusvision.displays.png_output import PngDisplay
            display = PngDisplay(args.output, config.brightness)
            display.show(manager.render(now()))
            display.close()
        elif args.display == "pi":
            stop_requested = [False]
            previous_sigterm = signal.signal(
                signal.SIGTERM, lambda *_: stop_requested.__setitem__(0, True)
            )
            display = None
            try:
                from siriusvision.displays.pi_matrix import PiMatrixDisplay
                display = PiMatrixDisplay(config.pi_brightness)
                run_headless(manager, display, now, lambda: stop_requested[0])
            except KeyboardInterrupt:
                if display is not None:
                    display.close()
            finally:
                signal.signal(signal.SIGTERM, previous_sigterm)
        else:
            from siriusvision.displays.mac_preview import MacPreview
            MacPreview(manager, now).run()
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"siriusvision: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
