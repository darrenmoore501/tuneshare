import argparse
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Full, Queue

from siriusvision.config import load_config
from siriusvision.services.spotify import PlaybackPoller, currently_playing, spotify_link
from siriusvision.services.spotify_auth import Authorization, SpotifyError, TokenClient, TokenStore
from siriusvision.services.spotify_state import RuntimeArtwork


def wait_for_code(flow: Authorization, timeout: float = 300) -> str:
    result: Queue[str | SpotifyError] = Queue(maxsize=1)

    class Callback(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *_):
            pass  # The query string contains the authorization code.

        def do_GET(self):
            try:
                code = flow.callback_code(self.path)
            except ValueError:
                self.reply(400, b"Invalid Spotify callback.")
            except SpotifyError as exc:
                self.finish_callback(exc, 400, b"Spotify authorization was denied.")
            else:
                self.finish_callback(code, 200, b"Callback received. Check the SiriusVision terminal.")

        def finish_callback(self, value: str | SpotifyError, status: int, body: bytes):
            try:
                result.put_nowait(value)
            except Full:
                pass
            self.reply(status, body)

        def reply(self, status: int, body: bytes):
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass  # The browser may have closed before reading the reply.

    with ThreadingHTTPServer(("127.0.0.1", 8888), Callback) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            print("Open this URL in your browser (with the SSH tunnel active):", flush=True)
            print(flow.url(), flush=True)
            try:
                value = result.get(timeout=timeout)
            except Empty:
                raise SpotifyError("Spotify login timed out; run login to try again") from None
        finally:
            server.shutdown()
            thread.join()
    if isinstance(value, SpotifyError):
        raise value
    return value


def watch(poller: PlaybackPoller) -> None:
    poller.check_runtime()
    stopped = threading.Event()
    previous = signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    try:
        poller.path.unlink(missing_ok=True)
        while not stopped.is_set():
            until = time.monotonic() + poller.poll()
            while not stopped.is_set() and (remaining := until - time.monotonic()) > 0:
                stopped.wait(min(remaining, 86400))
    finally:
        signal.signal(signal.SIGTERM, previous)
        poller.path.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SiriusVision Spotify now playing")
    parser.add_argument("command", choices=("login", "status", "watch", "logout"))
    parser.add_argument("--config", help="path to SiriusVision JSON configuration")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if os.getuid() == 0:
            raise SpotifyError("Run Spotify commands as the unprivileged poller user, not root")
        store = TokenStore()
        if args.command == "logout":
            store.logout()
            print("Local Spotify credentials removed. To revoke access, visit https://www.spotify.com/account/apps/")
            return 0
        config = load_config(args.config)
        client_id = os.environ.get("SPOTIFY_CLIENT_ID") or config.spotify_client_id
        if args.command == "watch" and not config.spotify_enabled:
            print("Spotify is disabled in this configuration.")
            return 0
        if not client_id:
            raise SpotifyError("Set SPOTIFY_CLIENT_ID or spotify_client_id before connecting")
        tokens = TokenClient(client_id, store)
        if args.command == "login":
            flow = Authorization(client_id)
            tokens.authorize(flow, wait_for_code(flow))
            print("Spotify authorized; private credentials saved.")
        elif args.command == "status":
            playback = currently_playing(tokens)
            print(f"Spotify playback: {playback.state}")
            print(f"Track: {playback.title or '-'}")
            print(f"Artist: {', '.join(playback.artists) or '-'}")
            print(f"Album: {playback.album or '-'}")
            print(f"Open in Spotify: {playback.link or '-'}")
            if config.spotify_enabled:
                panel_link = spotify_link(RuntimeArtwork(config.spotify_runtime_dir).spotify_url())
                if panel_link and panel_link != playback.link:
                    print(f"Album last published to the display: {panel_link}")
        else:
            watch(PlaybackPoller(config, tokens))
    except KeyboardInterrupt:
        return 130
    except (SpotifyError, ValueError, OSError) as exc:
        parser.exit(2, f"siriusvision.spotify: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
