# CLAUDE.md

Context for Claude Code sessions working on astryx-panel.

## What this project is

A custom WLED firmware build targeting the **Adafruit MatrixPortal ESP32-S3**
with a HUB75 matrix panel. This repo holds tooling and configuration only;
WLED sources live in the git-ignored checkout `WLED/` at the repo root
(clone of https://github.com/wled/WLED). The release to build is pinned by
`WLED_VERSION` in `config/wled.conf` (latest stable, `v16.0.1` as of
2026-08-30); `check-env.sh` warns and `build.sh` warns if the checkout is at
something else. Do not vendor WLED code into this repo.

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
- The script self-heals PATH for PlatformIO in non-interactive shells
  (`~/.platformio/penv/bin`). Node/npm must be on PATH already; how Node is
  installed is the user's choice and the tooling must not assume a manager.
- A first compile of a new env can fail with `compilation terminated` and no
  error message (OOM during parallel compile on this VM); retry once before
  investigating.
- `bin/flash.sh` does a from-scratch esptool flash (bootloader @0x0,
  partitions @0x8000, boot_app0 @0xe000, firmware @0x10000, `--erase-all`
  unless `-n`). Without `-f` it uses the boot files from the local PlatformIO
  build; with `-f <release.bin>` (or `-d`) it downloads WLED-WebInstaller's
  boot files into git-ignored `.cache/boot/`. `--dry-run` prints the command.
- `bin/provision.sh [host]` (default host 4.3.2.1 = WLED-AP) pushes `config/cfg.json` (partial config: HUB75
  bus + 2D matrix layout — the parts build flags cannot bake) to a running
  board via `POST /json/cfg` (merge + save), reboots, and verifies. `-u`
  replaces `cfg.json` via `/upload` (fresh boards only). The file describes a
  64×64 HUB75 panel plus the status NeoPixel (WS2812 on GPIO 4); keep
  `pin[0..1]`, `panels[0].w/h`, `len` and `total` consistent when changing it.
- GIFs: `config/gifs/*.gif` → `bin/gen-presets.sh` writes `config/presets.json`
  (one Image-effect preset per GIF, `fx` 53, segment name = filename, plus an
  "All GIFs" playlist set as boot preset `def.ps` in cfg.json). `provision.sh`
  uploads GIFs and presets.json via `/upload` before the panel config, and
  verifies by reading files back (`-g` presets only, `-v` verify only).
  WLED limits: GIF ≤ panel size (no downscaling), name ≤ 32 chars, one GIF
  playing at a time. `gen-presets.sh` overwrites presets.json.
- `gfx/` holds scripts that *generate* GIFs and other panel images, writing
  into `config/gifs/`; one script per animation/image family. Board tooling
  belongs in `bin/`, not here. After generating, re-run `bin/gen-presets.sh`.

## Toolchain

- Node ≥ 20, Python 3.12, PlatformIO 6.1.19 (versions pinned by
  `WLED/.nvmrc` and `WLED/requirements.txt`).
- Espressif32 and espressif8266 platforms are pre-cached in `~/.platformio`.
- Provisioning is managed by an external Ansible playbook (infra agent).

## Conventions

- Keep changes out of the WLED checkout except for git-ignored files
  (`platformio_override.ini`, `wled00/my_config.h`); upstream files stay
  pristine so the checkout can track upstream.
- Prefer `config/platformio_override.ini` build flags over editing `my_config.h`.
