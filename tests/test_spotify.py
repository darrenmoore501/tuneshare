import base64
import hashlib
import json
import socket
from datetime import datetime
from io import BytesIO
from stat import S_IMODE
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from siriusvision import spotify as cli
from siriusvision.__main__ import main, run_headless
from siriusvision.app import ScreenManager
from siriusvision.config import Config
from siriusvision.services import spotify, spotify_auth, spotify_state
from siriusvision.services.spotify_auth import Authorization, SpotifyError, TokenClient, TokenStore


def test_pkce_parameters_and_callback_validation():
    flow = Authorization("client")
    query = parse_qs(urlsplit(flow.url()).query)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest())
    assert query == {
        "client_id": ["client"], "response_type": ["code"],
        "redirect_uri": ["http://127.0.0.1:8888/callback"],
        "scope": ["user-read-currently-playing"], "state": [flow.state],
        "code_challenge_method": ["S256"], "code_challenge": [challenge.decode().rstrip("=")],
    }
    assert 43 <= len(flow.verifier) <= 128
    assert flow.state != Authorization("client").state
    assert flow.callback_code(f"/callback?state={flow.state}&code=test") == "test"
    for path in ("/other", "/callback?state=bad&code=x",
                 f"/callback?state={flow.state}&state=&code=x",
                 f"/callback?state={flow.state}&code=x&code=y"):
        with pytest.raises(ValueError):
            flow.callback_code(path)
    with pytest.raises(spotify_auth.LoginRequired):
        flow.callback_code(f"/callback?state={flow.state}&error=access_denied")


@pytest.mark.parametrize("authorized", [True, False])
def test_login_callback_server_shuts_down(monkeypatch, authorized):
    flow = Authorization("client")
    events = []

    class Server:
        def __init__(self, address, handler):
            assert address == ("127.0.0.1", 8888)
            self.handler = handler

        def __enter__(self):
            return self

        def __exit__(self, *_):
            events.append("closed")

        def serve_forever(self):
            if authorized:
                request = object.__new__(self.handler)
                request.path = f"/callback?state={flow.state}&code=mock-code"
                request.reply = lambda status, _body: events.append(status)
                request.do_GET()

        def shutdown(self):
            pass

    monkeypatch.setattr(cli, "ThreadingHTTPServer", Server)
    if authorized:
        assert cli.wait_for_code(flow, timeout=1) == "mock-code"
        assert events == [200, "closed"]
    else:
        with pytest.raises(SpotifyError, match="timed out"):
            cli.wait_for_code(flow, timeout=0)
        assert events == ["closed"]


def test_token_exchange_expiry_refresh_permissions_and_logout(tmp_path, monkeypatch):
    store = TokenStore(tmp_path / "private" / "spotify_tokens.json")
    flow = Authorization("client")
    client = TokenClient("client", store)
    calls = []
    now = [1000]
    monkeypatch.setattr(spotify_auth.time, "time", lambda: now[0])

    def request(req, _limit):
        form = parse_qs(req.data.decode())
        calls.append(form)
        if form["grant_type"] == ["authorization_code"]:
            assert form == {
                "grant_type": ["authorization_code"], "code": ["mock-code"],
                "client_id": ["client"], "redirect_uri": [spotify_auth.REDIRECT_URI],
                "code_verifier": [flow.verifier],
            }
            return 200, b'{"access_token":"first","refresh_token":"keep","expires_in":3600}'
        assert form == {"grant_type": ["refresh_token"], "refresh_token": ["keep"],
                        "client_id": ["client"]}
        return 200, b'{"access_token":"renewed","expires_in":3600}'

    monkeypatch.setattr(spotify_auth, "request_bytes", request)
    client.authorize(flow, "mock-code")
    assert client.access_token() == "first"
    assert len(calls) == 1
    now[0] += 3601
    assert client.access_token() == "renewed"
    assert store.load()["refresh_token"] == "keep"
    assert S_IMODE(store.path.stat().st_mode) == 0o600
    assert S_IMODE(store.path.parent.stat().st_mode) == 0o700
    store.logout()
    with pytest.raises(spotify_auth.LoginRequired):
        client.access_token()


def song(track="first", album="a", playing=True):
    return {
        "is_playing": playing, "currently_playing_type": "track",
        "item": {
            "id": track, "name": f"Song {track}", "type": "track",
            "artists": [{"name": "First Artist"}, {"name": "Second Artist"}],
            "album": {
                "id": album, "name": f"Album {album}",
                "external_urls": {"spotify": f"https://open.spotify.com/album/{album}"},
                "images": [
                    {"url": f"https://i.scdn.co/image/{album}-large", "width": 640, "height": 640},
                    {"url": f"https://i.scdn.co/image/{album}", "width": 64, "height": 64},
                ],
            },
        },
    }


def test_playback_metadata_and_unsupported_content():
    data = song()
    playback = spotify.parse_playback(data)
    assert playback.is_playing
    assert (playback.track_id, playback.title, playback.artists) == (
        "first", "Song first", ("First Artist", "Second Artist"))
    assert (playback.album_id, playback.album, playback.link) == (
        "a", "Album a", "https://open.spotify.com/album/a")
    assert playback.images == ("https://i.scdn.co/image/a", "https://i.scdn.co/image/a-large")
    data["item"]["is_local"] = True
    assert spotify.parse_playback(data).state == "unsupported"
    data["currently_playing_type"] = "episode"
    assert not spotify.parse_playback(data).images
    assert spotify.parse_playback({"item": None, "is_playing": False}).state == "inactive"


def test_401_refreshes_and_retries_once(monkeypatch, tmp_path):
    store = TokenStore(tmp_path / "private" / "spotify_tokens.json")
    with store.locked():
        store.save({"access_token": "old", "refresh_token": "stored",
                    "expires_at": spotify_auth.time.time() + 1800, "client_id": "id"})
    requests = []

    def read(req, _limit):
        requests.append(req.get_header("Authorization"))
        if len(requests) == 1:
            raise SpotifyError("expired", status=401)
        return 204, b""

    def refresh(req, _limit):
        assert parse_qs(req.data.decode())["refresh_token"] == ["stored"]
        return 200, b'{"access_token":"new","expires_in":3600}'

    monkeypatch.setattr(spotify, "request_bytes", read)
    monkeypatch.setattr(spotify_auth, "request_bytes", refresh)
    assert spotify.currently_playing(TokenClient("id", store)).state == "inactive"
    assert requests == ["Bearer old", "Bearer new"]


def artwork_bytes(colour, size=(128, 128)):
    buf = BytesIO()
    Image.new("RGB", size, colour).save(buf, "PNG")
    return buf.getvalue()


class MockTokens:
    def access_token(self):
        return "mock-token"


def test_watch_frames_switch_album_skip_identical_redraw_and_fall_back(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(spotify_state.time, "monotonic", lambda: now[0])
    responses = iter([
        (200, song()), (200, song("second")), (200, song("third", "b")),
        (200, song("third", "b", playing=False)), (204, None), (200, song("fourth", "b")),
    ])
    downloads = []

    def request(req, _limit):
        if req.full_url == spotify.PLAYBACK_URL:
            status, body = next(responses)
            return status, json.dumps(body).encode() if body else b""
        assert req.get_header("Authorization") is None
        downloads.append(req.full_url)
        return 200, artwork_bytes("red" if req.full_url.endswith("/a") else "blue")

    monkeypatch.setattr(spotify, "request_bytes", request)
    config = Config(spotify_enabled=True, spotify_runtime_dir=str(tmp_path))
    poller = spotify.PlaybackPoller(config, MockTokens())
    playback = spotify_state.RuntimeArtwork(str(tmp_path))
    manager = ScreenManager(config, playback=playback)
    date = datetime(2026, 11, 18, 12, 0)
    clock = ScreenManager(Config()).render(date).tobytes()
    assert manager.render(date).tobytes() == clock
    assert poller.poll() == 30
    first = manager.render(date)
    assert first.getpixel((0, 0)) == (255, 0, 0)

    class Matrix:
        def __init__(self):
            self.pixels = []

        def show(self, frame):
            self.pixels.append(frame.getpixel((0, 0)))

        def close(self):
            pass

    display = Matrix()
    steps = iter((False, False, False, True))

    def wait(_):
        now[0] += 30
        if now[0] in (130, 160):
            assert poller.poll() == 30
        if now[0] == 130:
            assert manager.render(date) is first

    run_headless(manager, display, lambda: date, lambda: next(steps), wait)
    assert display.pixels == [(255, 0, 0), (0, 0, 255)]
    assert manager.name == "album-art"
    assert downloads == ["https://i.scdn.co/image/a", "https://i.scdn.co/image/b"]
    assert S_IMODE(poller.path.stat().st_mode) == 0o644
    assert poller.poll() == 60  # Paused
    assert manager.render(date).tobytes() == clock
    assert poller.poll() == 60  # 204
    assert manager.render(date).tobytes() == clock
    assert poller.poll() == 30
    assert len(downloads) == 2  # Resuming the same album does not re-download it.
    now[0] += 61
    assert manager.render(date).tobytes() == clock
    assert manager.name == "letter-clock"


@pytest.mark.parametrize(("http_error", "retry", "message"), [
    (HTTPError(spotify.PLAYBACK_URL, 403, "", {}, BytesIO(b"secret")), 300, "allowlist"),
    (HTTPError(spotify.PLAYBACK_URL, 429, "", {"Retry-After": "240"}, BytesIO()), 240, "rate limited"),
    (HTTPError(spotify.PLAYBACK_URL, 429, "", {"Retry-After": "15"},
               BytesIO(b'{"reason":"QUOTA_EXCEEDED"}')), 3600, "quota exceeded"),
    (HTTPError(spotify.PLAYBACK_URL, 503, "", {}, BytesIO()), 60, "503"),
    (URLError(socket.gaierror()), 60, "network"),
    (TimeoutError(), 60, "timed out"),
])
def test_http_errors_clear_state_and_back_off(tmp_path, monkeypatch, caplog, http_error, retry, message):
    class Opener:
        def open(self, request, timeout):
            assert timeout == 8
            if isinstance(http_error, HTTPError):
                raise HTTPError(http_error.url, http_error.code, "", http_error.headers,
                                BytesIO(body))
            raise http_error

    body = http_error.read() if isinstance(http_error, HTTPError) else b""
    monkeypatch.setattr(spotify_auth, "build_opener", lambda *_: Opener())
    poller = spotify.PlaybackPoller(Config(spotify_runtime_dir=str(tmp_path)), MockTokens())
    poller.path.write_text("stale cover")
    assert poller.poll() == retry
    assert not poller.path.exists()
    assert message in caplog.text
    assert "secret" not in caplog.text
    if retry == 60:
        assert [poller.poll() for _ in range(6)] == [60, 120, 240, 480, 480, 480]


def test_cover_fit_missing_invalid_and_new_album(tmp_path, monkeypatch):
    cover = spotify.fit_artwork(artwork_bytes("red", (120, 60)))
    assert cover.mode == "RGB" and cover.size == (64, 64)
    assert cover.getbbox() == (0, 16, 64, 48)
    poller = spotify.PlaybackPoller(Config(spotify_runtime_dir=str(tmp_path)), MockTokens())
    data = song()
    data["item"]["album"]["images"] = []
    monkeypatch.setattr(spotify, "currently_playing", lambda _: spotify.parse_playback(data))
    downloads = []

    def fetch(req, _limit):
        downloads.append(req.full_url)
        return 200, b"not an image" if req.full_url.endswith("/a") else artwork_bytes("blue")

    monkeypatch.setattr(spotify, "request_bytes", fetch)
    poller.poll()
    assert not downloads and not poller.path.exists()
    data = song()
    poller.poll()
    poller.poll()
    assert len(downloads) == 1 and not poller.path.exists()
    data = song(album="b")
    poller.poll()
    assert spotify_state.RuntimeArtwork(str(tmp_path)).artwork().getpixel((0, 0)) == (0, 0, 255)


def test_status_outputs_track_attribution_without_tokens(monkeypatch, capsys):
    monkeypatch.setattr(cli.os, "getuid", lambda: 1000)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "mock-client")
    monkeypatch.setattr(cli, "currently_playing", lambda _: spotify.parse_playback(song(playing=False)))
    assert cli.main(["status"]) == 0
    text = capsys.readouterr().out
    for value in ("paused", "Song first", "First Artist", "Album a", "https://open.spotify.com/album/a"):
        assert value in text
    assert "mock-client" not in text and "token" not in text


def test_spotify_config_preserves_desktop_outputs_and_explicit_screen(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    config = tmp_path / "config.json"
    config.write_text('{"spotify_enabled":true,"spotify_runtime_dir":"/do-not-read"}')
    monkeypatch.setattr(spotify_state, "RuntimeArtwork", lambda *_: pytest.fail("Must not use Spotify"))
    output = tmp_path / "album.png"
    assert main(["--config", str(config), "--display", "png", "--screen", "album-art",
                 "--output", str(output)]) == 0
    with Image.open(output) as image:
        assert image.mode == "RGB" and image.size == (64, 64) and image.getbbox()

    def preview(manager, now):
        assert manager.playback is None
        assert manager.name == "letter-clock"
        return SimpleNamespace(run=lambda: manager.render(now()))

    monkeypatch.setitem(sys.modules, "siriusvision.displays.mac_preview", SimpleNamespace(MacPreview=preview))
    assert main(["--config", str(config), "--display", "preview"]) == 0
    assert ScreenManager(Config(spotify_enabled=True), "letter-clock",
                         playback=object()).name == "letter-clock"
