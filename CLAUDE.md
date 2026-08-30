# CLAUDE.md

Context for Claude Code sessions working on astryx-panel.

## What this project is

A custom WLED firmware build targeting the **Adafruit MatrixPortal ESP32-S3**
with a HUB75 matrix panel. This repo holds tooling and configuration only;
WLED sources live in the git-ignored checkout `WLED/` at the repo root
(clone of https://github.com/wled/WLED, WLED V5 dev, `17.0.0-devV5`). Do not
vendor WLED code into this repo.

## Key facts

- PlatformIO env: `matrixportal_s3_custom`, defined in
  `config/platformio_override.ini` (tracked in this repo, the board config
  source of truth; the WLED checkout sees it via the symlink
  `WLED/platformio_override.ini -> ../config/platformio_override.ini`, which
  `bin/build.sh` creates/repairs automatically).
- It extends WLED's stock `adafruit_matrixportal_esp32s3` env
  (`platformio.ini` in the WLED repo), which already handles: HUB75 driver
  (ESP32-HUB75-MatrixPanel-DMA, pinned), board pin mapping via
  `ARDUINO_ADAFRUIT_MATRIXPORTAL_ESP32S3`, PSRAM, USB-CDC on boot, and a
  custom board JSON (`boards/adafruit_matrixportal_esp32s3_wled.json`) that
  avoids erasing the filesystem on upload.
- Baked-in hardware defaults: `BTNPIN=6,7` `BTNTYPE=2,2` (Up/Down front
  buttons, push, active low) and `I2CSDAPIN=16` `I2CSCLPIN=17` (STEMMA QT).
  These seed the default button array in `wled00/cfg.cpp`; they only apply on
  a fresh config (new install / factory reset) — an existing `cfg.json` wins.

## Building

- Script: `bin/build.sh` (runs from `WLED/`). Options:
  `-e <env>` (default `adafruit_matrixportal_esp32s3`), `-u` upload,
  `-p <port>`, `-c` clean.
- Build sequence it implements: `npm ci` (once) → `npm run build` (generates
  `wled00/html_*.h` / `js_*.h`, required before any `pio run`) → `pio run -e <env>`.
- The script self-heals PATH for non-interactive shells: Node via fnm at
  `~/.local/share/fnm/node-versions/*/installation/bin`, PlatformIO at
  `~/.platformio/penv/bin`.
- A first compile of a new env can fail with `compilation terminated` and no
  error message (OOM during parallel compile on this VM); retry once before
  investigating.

## Toolchain

- Node ≥ 20 (fnm), Python 3.12, PlatformIO 6.1.19 (versions pinned by
  `WLED/.nvmrc` and `WLED/requirements.txt`).
- Espressif32 and espressif8266 platforms are pre-cached in `~/.platformio`.
- Provisioning is managed by an external Ansible playbook (infra agent).

## Conventions

- Keep changes out of the WLED checkout except for git-ignored files
  (`platformio_override.ini`, `wled00/my_config.h`); upstream files stay
  pristine so the checkout can track upstream.
- Prefer `config/platformio_override.ini` build flags over editing `my_config.h`.
