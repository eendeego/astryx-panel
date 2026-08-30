# astryx-panel

Custom [WLED](https://github.com/wled/WLED) firmware build for the
**Adafruit MatrixPortal ESP32-S3** driving a HUB75 LED matrix panel.

This repository holds the build tooling and board-specific configuration; the
WLED source itself is a separate checkout under `WLED/` and is not vendored here.

## Layout

```
astryx-panel/                  # this repo
├── bin/build.sh               # build (+ upload via PlatformIO)
├── bin/flash.sh               # full esptool flash: bootloader + partitions + firmware
├── bin/provision.sh           # push config/cfg.json (panel + 2D layout) to a running board
├── bin/check-env.sh           # prerequisite checker
├── config/platformio_override.ini  # board config (source of truth)
├── config/wled.conf           # WLED release to build (WLED_VERSION)
├── config/cfg.json            # partial WLED config: HUB75 bus + 2D matrix layout
├── WLED/                      # upstream WLED checkout (git-ignored, separate repo)
│   └── platformio_override.ini -> ../config/platformio_override.ini
├── README.md
└── CLAUDE.md                  # context for Claude Code sessions
```

The WLED release to build is pinned in `config/wled.conf` (`WLED_VERSION`,
currently the latest stable). Get the sources from the repo root with
`git clone --branch <WLED_VERSION> https://github.com/wled/WLED WLED` —
`bin/check-env.sh` prints the exact command and warns when the checkout is at
a different version. WLED picks up the board config through the symlink shown above;
`bin/build.sh` creates or repairs it automatically (manually:
`ln -sfn ../config/platformio_override.ini WLED/platformio_override.ini`).

## Hardware

- Adafruit MatrixPortal ESP32-S3 (8 MB flash, 2 MB PSRAM, dedicated HUB75 connector)
- Front buttons: **Up = GPIO 6**, **Down = GPIO 7** (active low)
- STEMMA QT / Qwiic I2C: **SDA = GPIO 16**, **SCL = GPIO 17**

## Build configuration

The build uses a custom PlatformIO environment `matrixportal_s3_custom`
(defined in `config/platformio_override.ini`) that extends
WLED's stock `adafruit_matrixportal_esp32s3` env and bakes in the button and
I2C pins above via `-D BTNPIN=6,7 -D BTNTYPE=2,2 -D I2CSDAPIN=16 -D I2CSCLPIN=17`.

Baked-in values are *defaults*: they take effect on a fresh install or after a
factory reset. A board with a saved `cfg.json` keeps its stored settings.

## Prerequisites

- Node.js ≥ 20 (`.nvmrc` in the WLED checkout pins 20.18)
- Python 3.12 with PlatformIO 6.1.19 (`pip install -r WLED/requirements.txt`)
- Membership in the `dialout` group for USB flashing

## Usage

```bash
bin/check-env.sh                      # verify build prerequisites; prints a fix for each problem
bin/build.sh                          # build (default env: adafruit_matrixportal_esp32s3)
bin/build.sh -e matrixportal_s3_custom  # build with baked-in pin config
bin/build.sh -u [-p /dev/ttyACM0]     # build + flash over USB (board already running WLED)
bin/build.sh -c                       # clean build
```

Firmware output: `WLED/.pio/build/<env>/firmware.bin` and a versioned copy
under `WLED/build_output/release/`.

## Flashing from scratch

`bin/build.sh -u` uploads the application only and expects a board that already
runs WLED. For a first install (a board still running TinyUF2/CircuitPython) or
to flash a release image, use `bin/flash.sh`, which writes the bootloader,
partition table, `boot_app0` and the firmware with esptool, after a full chip
erase by default:

```bash
bin/flash.sh -e matrixportal_s3_custom          # flash the local build (boot files from the same build)
bin/flash.sh -f WLED_16.0.1_ESP32-S3_Adafruit_Matrixportal.bin   # flash a release image
bin/flash.sh -n ...                              # keep existing settings (no chip erase)
bin/flash.sh --dry-run ...                       # show the esptool command only
```

If flashing (or `bin/build.sh -u`) fails to connect, put the board in ROM
bootloader mode — **1.** hold BOOT, **2.** tap RESET, **3.** release BOOT — and
re-run the command. The port is auto-detected when exactly one candidate exists; otherwise pass
`-p <port>`. With `-f` the boot files WLED's web installer uses are downloaded
once into `.cache/boot/` (git-ignored); `-d` forces that source for local
builds too. `esptool` comes from PATH or from PlatformIO's bundled copy.

## Provisioning the panel config

Build flags can seed most defaults (buttons, I2C, names, WiFi …), but not the
HUB75 output bus or the 2D matrix layout — WLED 16.0.1 has no compile-time
default for the matrix, and its first-boot code mangles HUB75 bus parameters.
Those live in `config/cfg.json`, a *partial* `cfg.json` — one 64×64 HUB75
panel plus the board's status NeoPixel (1× WS2812 on GPIO 4) and ESP-NOW
enabled; for another panel edit `pin[0..1]`, `panels[0].w/h` and `len`/`total`
together — that `bin/provision.sh` pushes to a running board:

```bash
bin/provision.sh                     # fresh board: connect to its WLED-AP, targets 4.3.2.1 by default
bin/provision.sh <board-ip>          # board already on WiFi: merge via /json/cfg, save, reboot, verify
bin/provision.sh -u [<board-ip>]     # replace cfg.json wholesale instead of merging (board reboots itself)
bin/provision.sh -P 1234 <board-ip>  # board with a settings PIN
bin/provision.sh -n <board-ip>       # merge only, reboot later yourself
```

The default merge mode is safe on an already-configured board: WLED merges
the file field by field. After the reboot the script reads `/json/cfg` back
and reports any difference from the file.

## Known quirks

- The first compile of a new env can occasionally die with
  `compilation terminated ... Error 1` and no diagnostic (memory pressure
  during parallel compilation). Re-running the build succeeds.
