import base64
import json
import os
import stat
import time
from pathlib import Path
from typing import Protocol

from PIL import Image


FRAME_SIZE = (64, 64)
FRAME_BYTES = 64 * 64 * 3
MAX_STATE_BYTES = 24 * 1024
STATE_FILE = "playback.json"


class PlaybackArtwork(Protocol):
    def artwork(self) -> Image.Image | None: ...


class RuntimeArtwork:
    """Read public display frames without importing the OAuth or HTTP client."""

    def __init__(self, directory: str):
        self.path = Path(directory) / STATE_FILE
        self._file = None
        self._expires = 0.0
        self._encoded = None
        self._image = None
        self._url = ""

    def spotify_url(self) -> str:
        return self._url if self.artwork() is not None else ""

    def artwork(self) -> Image.Image | None:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATE_BYTES:
                    return None
                identity = (info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
                if identity != self._file:
                    self._file = identity
                    self._expires = 0
                    data = json.loads(stream.read(MAX_STATE_BYTES))
                    if not isinstance(data, dict):
                        return None
                    now = time.monotonic()
                    expires = data.get("expires")
                    if type(expires) not in (int, float) or not now < expires <= now + 86460:
                        return None
                    encoded = data.get("rgb")
                    if not isinstance(encoded, str):
                        return None
                    if encoded != self._encoded:
                        pixels = base64.b64decode(encoded, validate=True)
                        if len(pixels) != FRAME_BYTES:
                            return None
                        self._image = Image.frombytes("RGB", FRAME_SIZE, pixels)
                        self._encoded = encoded
                    url = data.get("spotify_url")
                    self._url = url if isinstance(url, str) else ""
                    self._expires = expires
                return self._image if time.monotonic() < self._expires else None
        except (OSError, ValueError, RecursionError):
            return None
