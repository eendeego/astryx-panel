# astryx-panel

Custom [WLED](https://github.com/wled/WLED) firmware build for the
**Adafruit MatrixPortal ESP32-S3** driving a HUB75 LED matrix panel.

This repository holds the build tooling and board-specific configuration; the
WLED source itself is a separate checkout under `WLED/` and is not vendored here.

## Layout

```
astryx-panel/                  # this repo
├── bin/build.sh               # build/flash script
├── bin/check-env.sh           # prerequisite checker
├── config/platformio_override.ini  # board config (source of truth)
├── WLED/                      # upstream WLED checkout (git-ignored, separate repo)
│   └── platformio_override.ini -> ../config/platformio_override.ini
├── README.md
└── CLAUDE.md                  # context for Claude Code sessions
```

Get the WLED sources with `git clone https://github.com/wled/WLED WLED` from the
repo root. WLED picks up the board config through the symlink shown above;
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
bin/build.sh -u [-p /dev/ttyACM0]     # build + flash over USB
bin/build.sh -c                       # clean build
```

Firmware output: `WLED/.pio/build/<env>/firmware.bin` and a versioned copy
under `WLED/build_output/release/`.

## Known quirks

- The first compile of a new env can occasionally die with
  `compilation terminated ... Error 1` and no diagnostic (memory pressure
  during parallel compilation). Re-running the build succeeds.
