import base64
import json
import logging
import os
import stat
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request

from PIL import Image

from siriusvision.config import Config
from siriusvision.services.spotify_auth import (
    LoginRequired, SpotifyError, TokenClient, atomic_write, object_json, request_bytes,
)
from siriusvision.services.spotify_state import FRAME_SIZE, STATE_FILE


PLAYBACK_URL = "https://api.spotify.com/v1/me/player/currently-playing"
LOG = logging.getLogger(__name__)


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    # Metadata is also printed in terminals; drop control characters from API text.
    return "".join(char for char in value if char.isprintable()) if isinstance(value, str) else ""


def _items(value) -> list:
    return value if isinstance(value, list) else []


def _https_host(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme == "https" and parsed.port in (None, 443)
                and parsed.username is None and parsed.password is None):
            return parsed.hostname or ""
    except ValueError:
        pass
    return ""


def spotify_link(value: object) -> str:
    url = _text(value)
    return url if len(url) <= 1024 and _https_host(url) == "open.spotify.com" else ""


def _external_link(data: dict) -> str:
    return spotify_link(_object(data.get("external_urls")).get("spotify"))


def _artwork_url(url: str) -> bool:
    host = _https_host(url)
    return host.endswith((".scdn.co", ".spotifycdn.com"))


@dataclass(frozen=True)
class Playback:
    state: str = "inactive"
    is_playing: bool = False
    track_id: str = ""
    title: str = ""
    artists: tuple[str, ...] = ()
    album_id: str = ""
    album: str = ""
    images: tuple[str, ...] = ()
    link: str = ""


def parse_playback(data: dict) -> Playback:
    playing = data.get("is_playing") is True
    item = _object(data.get("item"))
    if not item:
        return Playback("unsupported", True) if playing else Playback()
    if (data.get("currently_playing_type", "track") != "track"
            or item.get("type", "track") != "track" or item.get("is_local") is True):
        return Playback("unsupported", playing)

    album = _object(item.get("album"))
    images = []
    for candidate in _items(album.get("images")):
        image = _object(candidate)
        url = _text(image.get("url"))
        if _artwork_url(url):
            width, height = image.get("width"), image.get("height")
            dimension = min(width, height) if type(width) is int and type(height) is int else 0
            # Prefer the smallest source that won't need to be enlarged.
            rank = (0, dimension) if dimension >= 64 else (1, -dimension)
            images.append((rank, url))
    return Playback(
        state="playing" if playing else "paused", is_playing=playing,
        track_id=_text(item.get("id")), title=_text(item.get("name")),
        artists=tuple(name for artist in _items(item.get("artists"))
                      if (name := _text(_object(artist).get("name")))),
        album_id=_text(album.get("id")), album=_text(album.get("name")),
        images=tuple(url for _, url in sorted(images)),
        link=_external_link(album) or _external_link(item),
    )


def currently_playing(tokens: TokenClient) -> Playback:
    def get(access: str) -> tuple[int, bytes]:
        return request_bytes(Request(PLAYBACK_URL, headers={
            "Authorization": f"Bearer {access}",
        }), 128 * 1024)

    access = tokens.access_token()
    try:
        status, data = get(access)
    except SpotifyError as exc:
        if exc.status != 401:
            raise
        status, data = get(tokens.access_token(rejected=access))
    return Playback() if status == 204 else parse_playback(object_json(data))


def fit_artwork(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as source:
        width, height = source.size
        if max(width, height) > 2048:
            raise ValueError("Artwork dimensions exceed the size limit")
        scale = 64 / max(width, height)
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resized = source.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        if size == FRAME_SIZE:
            return resized
        frame = Image.new("RGB", FRAME_SIZE)
        frame.paste(resized, ((64 - size[0]) // 2, (64 - size[1]) // 2))
        return frame


class PlaybackPoller:
    def __init__(self, config: Config, tokens: TokenClient):
        self.config = config
        self.tokens = tokens
        self.path = Path(config.spotify_runtime_dir) / STATE_FILE
        self._art_url = ""
        self._encoded = None
        self._bad_art_url = ""
        self._art_retry_until = 0.0
        self._cdn_retry_until = 0.0
        self._failures = 0
        self._last_error = None

    def _artwork(self, playback: Playback) -> str | None:
        if playback.state != "playing" or not playback.images or not playback.link:
            return None
        url = playback.images[0]
        if url == self._art_url:
            return self._encoded
        now = time.monotonic()
        if now < self._cdn_retry_until or (url == self._bad_art_url and now < self._art_retry_until):
            return None
        try:
            _, data = request_bytes(Request(url), 2 * 1024 * 1024)
            self._encoded = base64.b64encode(fit_artwork(data).tobytes()).decode("ascii")
            self._art_url = url
            return self._encoded
        except SpotifyError as exc:
            LOG.warning("No Spotify artwork: %s", exc)
            if exc.retry_after:
                self._cdn_retry_until = time.monotonic() + exc.retry_after
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            LOG.warning("Spotify artwork could not be decoded")
        self._bad_art_url = url
        self._art_retry_until = time.monotonic() + 300
        return None

    def poll(self) -> float:
        """Publish the new frame (or clear it) and return the delay until the next poll."""
        try:
            playback = currently_playing(self.tokens)
        except SpotifyError as exc:
            self.path.unlink(missing_ok=True)
            message = str(exc)
            if self._last_error != message:
                LOG.warning("%s", message)
                self._last_error = message
            if isinstance(exc, LoginRequired):
                self._art_url, self._encoded = "", None
            if exc.retry_after:
                return exc.retry_after
            if exc.status in (400, 401, 403, 404) or isinstance(exc, LoginRequired):
                return max(300, self.config.spotify_idle_poll_seconds)
            self._failures = min(self._failures + 1, 5)
            return max(self.config.spotify_idle_poll_seconds, 30 * 2 ** (self._failures - 1))

        self._failures = 0
        self._last_error = None
        delay = (self.config.spotify_poll_seconds if playback.state == "playing"
                 else self.config.spotify_idle_poll_seconds)
        encoded = self._artwork(playback)
        if encoded:
            # Allow for one slow request, but never leave a dead poller's cover up indefinitely.
            expires = time.monotonic() + delay + 30
            snapshot = {"expires": expires, "rgb": encoded, "spotify_url": playback.link}
            atomic_write(self.path, json.dumps(snapshot).encode(), 0o644)
        else:
            self.path.unlink(missing_ok=True)
        return delay

    def check_runtime(self) -> None:
        info = self.path.parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o755):
            raise SpotifyError("Spotify runtime directory must be owned by the poller with mode 0755")
