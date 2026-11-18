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

Start the application manually before installing the service:

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

- **`No module named rgbmatrix`:** activate/check the application's virtual
  environment and install the bindings from
  `/home/darren/rpi-rgb-led-matrix/bindings/python` using the command above.
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
