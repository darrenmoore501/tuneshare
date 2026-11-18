# Raspberry Pi deployment

These instructions target the Raspberry Pi 1 Model B running Raspberry Pi OS
13 (Trixie), with the panel already wired and verified using the native
`rpi-rgb-led-matrix` demonstration. The display backend uses the existing
`regular-pi1` mapping, 64 rows, 64 columns, one panel, and driver-timed refresh.
Do not change the working GPIO wiring or mapping.

## Install SiriusVision and the Python bindings

The application uses the distribution Pillow package through a virtual
environment with system packages enabled; it does not need Tkinter.

```sh
sudo apt update
sudo apt install -y python3 python3-venv python3-dev python3-pil \
  build-essential cmake cython3
cd /home/darren
git clone https://github.com/darrenmoore501/tuneshare.git
cd /home/darren/tuneshare
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e .
```

The project accepts Pillow 9.2 or newer (below 14), allowing the OS-provided
Pillow to satisfy the requirement without building Pillow for ARMv6.

The native driver is assumed to be checked out and its C++ library built at
`/home/darren/rpi-rgb-led-matrix`. If it still needs compiling, build it with
one job from its root:

```sh
cd /home/darren/rpi-rgb-led-matrix
make -j1
```

Build and install the Python bindings into SiriusVision's virtual environment
using the driver's current Python build configuration (scikit-build-core,
CMake, and Cython). Run pip from the bindings directory; limiting the CMake
parallel level keeps peak memory use suitable for a Pi 1:

```sh
cd /home/darren/rpi-rgb-led-matrix/bindings/python
CMAKE_BUILD_PARALLEL_LEVEL=1 /home/darren/tuneshare/.venv/bin/python -m pip install .
```

Verify that the virtual environment can import the native binding:

```sh
/home/darren/tuneshare/.venv/bin/python -c \
  'from rgbmatrix import RGBMatrix; print(RGBMatrix)'
```

## Configure and run manually

Optionally create a local config file. The example uses Europe/London and
defaults to 20% Pi brightness. `pi_brightness` is passed to the matrix driver
and is not also applied to the Pillow image. It must be 1–100 because the
driver does not support a zero brightness; zero remains valid for preview and
PNG output. The existing `brightness` setting still controls those outputs,
and a config that sets `brightness` to 1–100 but omits `pi_brightness` uses
that value for the Pi as well. A desktop `brightness` of zero leaves the
Pi-specific default unchanged.

```sh
cd /home/darren/tuneshare
cp config.example.json config.json
```

Start the application manually before installing the service. Use the full
path to the virtual environment's Python with `sudo`: `sudo python3` normally
selects system Python, even if you activated `.venv` in your shell.

```sh
sudo /home/darren/tuneshare/.venv/bin/python -m siriusvision \
  --display pi --config /home/darren/tuneshare/config.json
```

Add `--screen letter-clock` to start on a different configured screen.
Screens advance using `cycle_seconds`; the default is 30 seconds. The
application updates at most once per second and avoids resending unchanged
frames. Stop it with **Ctrl+C** or `sudo kill -TERM <pid>`; shutdown clears
the panel.

The driver needs elevated privileges for optimal GPIO timing. When initialized
as root, it normally drops to the `daemon` account. Ensure the application,
configuration, and any local resources remain readable/traversable after that
drop. For this deployment the configuration contains only display settings,
so grant read/traverse access to the application tree and traverse access to
the home directory:

```sh
sudo chmod o+x /home/darren
sudo chmod -R o+rX /home/darren/tuneshare
```

Do not store secrets in this tree or configuration. The service template runs
as root to initialize the driver; the driver performs its normal privilege
drop. Do not run package installation or development commands with `sudo pip`.

## Install the systemd service

The service template uses the absolute deployment paths above. Install it
after the manual launch has been verified:

```sh
sudo cp /home/darren/tuneshare/deploy/siriusvision.service \
  /etc/systemd/system/siriusvision.service
sudo systemctl daemon-reload
sudo systemctl enable siriusvision.service
sudo systemctl start siriusvision.service
```

Operate and inspect it with:

```sh
sudo systemctl stop siriusvision.service
sudo systemctl start siriusvision.service
sudo systemctl status siriusvision.service
sudo journalctl -u siriusvision.service -f
```

systemd sends SIGTERM on stop; the application clears the panel before exit.
Unexpected failures restart after five seconds.

## Optional Spotify now playing

Spotify is off by default. When enabled on the Pi, a track with a usable
cover takes over the display without cycling. When paused, stopped, offline,
or unable to get a cover, the display stays on the normal word clock.
`spotify_fallback_screen` can name a different fixed fallback. The polling
defaults are 30 seconds for music and 60 seconds otherwise; keep intervals
conservative to avoid Spotify API limits. Explicit `--screen` and the
preview/PNG backends retain their usual behaviour, including demo album art.

### Configure and authorize

1. In the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard),
   create an app with Web API access. Register the exact redirect URI
   `http://127.0.0.1:8888/callback` (not `localhost`). Copy the **Client ID**,
   not the client secret. Check Spotify's current
   [development-mode requirements](https://developer.spotify.com/documentation/web-api/concepts/quota-modes),
   including account eligibility and whether your Spotify account needs to
   be added to the app's user allowlist.
2. Set `"spotify_enabled": true` in `/home/darren/tuneshare/config.json`.
   Leave `spotify_mode` set to `"auto"`; if adding settings to an existing
   config, omitted settings use their defaults. As `darren` on the Pi:

   ```sh
   cd /home/darren/tuneshare
   export SPOTIFY_CLIENT_ID='paste-your-client-id-here'
   ```

3. On the Mac, open a separate terminal and leave the tunnel running:

   ```sh
   ssh -N -L 8888:127.0.0.1:8888 darren@siriusvision.local
   ```

4. On the Pi, **without sudo**, run login. Open the printed URL in the
   Mac browser and approve the `user-read-currently-playing` permission.
   The callback server binds only to Pi loopback and closes after receiving
   the callback or after five minutes. After the Pi prints success, close
   the tunnel and check playback:

   ```sh
   .venv/bin/python -m siriusvision.spotify login
   .venv/bin/python -m siriusvision.spotify status
   ```

Credentials are saved in `/home/darren/.config/siriusvision/spotify_tokens.json`
(0600, directory 0700) and refreshed automatically. Do not copy this file
into the checkout or change its permissions. `status` makes a one-off API
request and prints an **Open in Spotify** link; do not loop it. The
[PKCE flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)
needs no client secret and SiriusVision never asks for your Spotify password.

### Verify before installing the poller service

Stop the existing display service if it owns the panel. In the Pi shell
where `SPOTIFY_CLIENT_ID` was exported:

```sh
sudo systemctl stop siriusvision.service
sudo install -d -o darren -g "$(id -gn)" -m 0755 /run/siriusvision-spotify
.venv/bin/python -m siriusvision.spotify watch --config config.json
```

In another Pi shell:

```sh
cd /home/darren/tuneshare
sudo .venv/bin/python -m siriusvision --display pi --config config.json
```

Start Spotify music, switch tracks on the same album, switch to another
album, then pause. Allow one polling interval for each change. The cover
should stay static until it changes and the clock should return on pause.
Stop the poller with Ctrl+C and confirm the clock stays usable. Stop the
manual display before restarting its systemd service.

### Start automatically at boot

From `/home/darren/tuneshare`, install the poller and add a display service
drop-in. This does not replace your existing display service or its other
overrides. `Wants=` starts the worker with the display but does not make the
display depend on successful authentication or network access.

```sh
sudo install -d -m 0755 /etc/siriusvision /etc/systemd/system/siriusvision.service.d
printf 'SPOTIFY_CLIENT_ID=%s\n' "$SPOTIFY_CLIENT_ID" | sudo tee /etc/siriusvision/spotify.env >/dev/null
sudo chmod 0600 /etc/siriusvision/spotify.env
sudo install -m 0644 deploy/siriusvision-spotify.service /etc/systemd/system/
sudo install -m 0644 deploy/spotify.conf /etc/systemd/system/siriusvision.service.d/
sudo systemctl daemon-reload
sudo systemctl enable siriusvision.service
sudo systemctl restart siriusvision.service
sudo systemctl status siriusvision.service siriusvision-spotify.service
sudo journalctl -u siriusvision-spotify.service -b
```

Alternatively, a local (untracked) config can specify `spotify_client_id`
for both manual and systemd commands. `SPOTIFY_CLIENT_ID` takes precedence.
The poller runs as `darren`. systemd creates `/run/siriusvision-spotify`
(0755, readable by `daemon`); only `darren` can write the token-free, atomic
frame snapshots. They expire if the poller stops updating. If changing
`spotify_runtime_dir`, provision a matching directory in both deployments.
The driver still drops privileges normally. To disconnect:

```sh
sudo systemctl stop siriusvision-spotify.service
.venv/bin/python -m siriusvision.spotify logout
```

That deletes the local credentials; revoke the app separately at
[Spotify account apps](https://www.spotify.com/account/apps/). To disable
automatic mode, set `"spotify_enabled": false`, remove the installed
`spotify.conf` drop-in, run `sudo systemctl daemon-reload`, and restart
`siriusvision.service`. For an update, stop both services before installing
the new code; the display's drop-in restarts the poller with it.

The 64×64 panel is not interactive and has no room for on-panel Spotify
attribution without altering the cover. The terminal `status` command
identifies Spotify as the source and provides the clickable album or track
URL on terminals that support URL links (otherwise copy it into a browser).
Pass `--config config.json` to also see the last published cover's link
when the poller and live Spotify status are between updates.
The app does not crop, overlay, or permanently archive covers. Review
[Spotify's design guidelines](https://developer.spotify.com/documentation/design)
and [developer policy](https://developer.spotify.com/policy) before distributing
or using this display beyond your personal installation.

To run the mocked checks with no account, network or GPIO:

```sh
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

## Update

Stop the service before updating files, then restart it:

```sh
sudo systemctl stop siriusvision.service
cd /home/darren/tuneshare
git pull
/home/darren/tuneshare/.venv/bin/python -m pip install -e .
sudo chmod -R o+rX /home/darren/tuneshare
sudo systemctl start siriusvision.service
```

The separate matrix driver and its Python bindings do not need rebuilding for
an application-only update.

## Troubleshooting

- **`The rgbmatrix Python bindings are required for --display pi`:** first
  verify the import with the same interpreter used to launch the app:

  ```sh
  sudo /home/darren/tuneshare/.venv/bin/python -c \
    'from rgbmatrix import RGBMatrix, RGBMatrixOptions'
  ```

  If this succeeds, use the same absolute Python path to launch SiriusVision.
  If the module is missing, install the bindings from
  `/home/darren/rpi-rgb-led-matrix/bindings/python` using the install command
  above (without `sudo`). For other import errors, check the reported cause.
- **Permission denied / GPIO timing problems:** start manually with `sudo` or
  inspect the systemd service's root startup. The hardware driver may drop
  privileges to `daemon`; verify directory traversal and file read
  permissions for `/home/darren` and `/home/darren/tuneshare`.
- **Wrong mapping, rows, or panel:** confirm the known-working physical setup
  and do not alter its wiring. The application sets `regular-pi1`, 64×64, and
  chain length 1; confirm that the native C++ demonstration still works with
  those same settings.
- **Service exits or restarts:** use
  `sudo journalctl -u siriusvision.service -b` to see the startup error. Verify
  the config path, virtual environment, bindings import, and panel permissions.
