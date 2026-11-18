import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import stat
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import fcntl


REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "user-read-currently-playing"
TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifyError(Exception):
    def __init__(self, message: str, *, status: int = 0, retry_after: float = 0):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class LoginRequired(SpotifyError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_bytes(request: Request, limit: int) -> tuple[int, bytes]:
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise SpotifyError("Spotify response exceeded the size limit")
            return response.status, data
    except HTTPError as exc:
        with exc:
            code = exc.code
            if code == 429:
                try:
                    retry = float(exc.headers.get("Retry-After", "0"))
                    retry = retry if math.isfinite(retry) else 0
                except ValueError:
                    retry = 0
                try:
                    quota = b"QUOTA_EXCEEDED" in exc.read(4096).upper()
                except (OSError, HTTPException):
                    quota = False
                raise SpotifyError(
                    "Spotify development quota exceeded; check the developer dashboard"
                    if quota else "Spotify rate limited the request",
                    status=code, retry_after=max(retry, 3600 if quota else 60),
                ) from None
            if code == 400 and request.full_url == TOKEN_URL:
                try:
                    error = object_json(exc.read(4096)).get("error")
                except (SpotifyError, OSError, HTTPException):
                    error = None
                if error == "invalid_grant":
                    raise LoginRequired("Spotify authorization expired or was revoked; run login") from None
            message = (
                "Spotify denied access (HTTP 403); check the requested scope, account "
                "eligibility/Premium requirements and app allowlist in the developer dashboard"
                if code == 403 else f"Spotify request failed (HTTP {code})"
            )
            raise SpotifyError(message, status=code) from None
    except (URLError, OSError, HTTPException):
        # Do not log request URLs, headers, or response bodies.
        raise SpotifyError("Spotify network request failed or timed out") from None


def object_json(data: bytes) -> dict:
    try:
        result = json.loads(data)
        if isinstance(result, dict):
            return result
    except (ValueError, RecursionError):
        pass
    raise SpotifyError("Spotify data was not a valid JSON object")


def atomic_write(path: Path, data: bytes, mode: int, *, durable: bool = False) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            if durable:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
        if durable:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


@dataclass(frozen=True)
class Authorization:
    client_id: str
    verifier: str = field(default_factory=lambda: secrets.token_urlsafe(64), repr=False)
    state: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    def url(self) -> str:
        digest = hashlib.sha256(self.verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        query = urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "scope": SCOPE, "state": self.state, "code_challenge_method": "S256",
            "code_challenge": challenge,
        })
        return f"https://accounts.spotify.com/authorize?{query}"

    def callback_code(self, target: str) -> str:
        path = urlsplit(target)
        if path.path != "/callback" or path.netloc or path.scheme:
            raise ValueError("Invalid callback path")
        query = parse_qs(path.query, keep_blank_values=True, max_num_fields=16)
        states = query.get("state", [])
        if len(states) != 1 or not hmac.compare_digest(states[0].encode(), self.state.encode()):
            raise ValueError("Invalid callback state")
        if "error" in query:
            raise LoginRequired("Spotify authorization was denied; run login to try again")
        codes = query.get("code", [])
        if len(codes) != 1 or not codes[0]:
            raise ValueError("Missing or repeated authorization code")
        return codes[0]


class TokenStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else (
            Path.home() / ".config" / "siriusvision" / "spotify_tokens.json"
        )

    @contextmanager
    def locked(self):
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise SpotifyError("Spotify credential directory must be owned by this user with mode 0700")
        fd = os.open(directory / ".spotify.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def load(self) -> dict:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            raise LoginRequired("No Spotify credentials; run login as the poller user") from None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16384):
                raise SpotifyError("Spotify token file must be a private, owner-only (0600) file")
            return object_json(stream.read(16384))

    def save(self, tokens: dict) -> None:
        atomic_write(self.path, json.dumps(tokens).encode(), 0o600, durable=True)

    def logout(self) -> None:
        with self.locked():
            self.path.unlink(missing_ok=True)


class TokenClient:
    def __init__(self, client_id: str, store: TokenStore):
        self.client_id = client_id
        self.store = store

    def _exchange(self, params: dict, previous_refresh: str = "") -> str:
        request = Request(TOKEN_URL, urlencode({"client_id": self.client_id, **params}).encode(),
                          {"Content-Type": "application/x-www-form-urlencoded"})
        _, body = request_bytes(request, 16384)
        response = object_json(body)
        access = response.get("access_token")
        refresh = response.get("refresh_token") or previous_refresh
        lifetime = response.get("expires_in")
        if (not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh
                or type(lifetime) not in (int, float) or not 0 < lifetime <= 86400):
            raise SpotifyError("Spotify returned incomplete token credentials")
        self.store.save({
            "client_id": self.client_id, "access_token": access, "refresh_token": refresh,
            "expires_at": time.time() + lifetime,
        })
        return access

    def authorize(self, flow: Authorization, code: str) -> None:
        with self.store.locked():
            self._exchange({
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": REDIRECT_URI, "code_verifier": flow.verifier,
            })

    def access_token(self, rejected: str | None = None) -> str:
        with self.store.locked():
            tokens = self.store.load()
            refresh = tokens.get("refresh_token")
            if tokens.get("client_id") != self.client_id or not isinstance(refresh, str) or not refresh:
                raise LoginRequired("Spotify credentials do not match this app; run login")
            access, expires = tokens.get("access_token"), tokens.get("expires_at")
            if (isinstance(access, str) and access and access != rejected
                    and type(expires) in (int, float) and expires > time.time() + 30):
                return access
            return self._exchange({"grant_type": "refresh_token", "refresh_token": refresh}, refresh)
