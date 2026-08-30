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
├── bin/provision.sh           # push cfg.json, GIFs and presets to a running board
├── bin/gen-presets.sh         # build config/presets.json from config/gifs/*.gif
├── bin/check-env.sh           # prerequisite checker
├── config/platformio_override.ini  # board config (source of truth)
├── config/wled.conf           # WLED release to build (WLED_VERSION)
├── config/cfg.json            # partial WLED config: HUB75 bus + 2D matrix layout, boot preset
├── config/gifs/               # animated GIFs to play on the panel (drop files here)
├── config/presets.json        # generated: one Image preset per GIF + playlist
├── gfx/                       # scripts that render the GIFs/images in config/gifs/
│   ├── Makefile               # what to rebuild, and from what
│   ├── raw/                   # versioned SVG sources
│   └── out/                   # intermediates (git-ignored)
├── WLED/                      # upstream WLED checkout (git-ignored, separate repo)
│   └── platformio_override.ini -> ../config/platformio_override.ini
├── docs/SETUP.md              # the same settings as WLED UI fields, for setting a board up by hand
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

Some of the panel's settings are in neither `cfg.json` nor a build flag — gamma,
transition time, the UI preferences, and the gap file. `docs/SETUP.md` lists
every setting as the field it is in WLED's own pages, marks which of them
provisioning restores, and is the way back if a board has to be set up by hand.

## Presets and animated GIFs

WLED plays a GIF from its filesystem through the **Image** effect; the
segment *name* is the filename. The repo keeps the GIFs in `config/gifs/`
and generates the presets from them:

```bash
bin/gen-presets.sh [-d 10] [-b 128] [-s 128]   # validate GIFs, write config/presets.json,
                                                # set the playlist as boot preset in cfg.json
bin/provision.sh [<board-ip>]                   # uploads GIFs + presets.json, then the panel config
bin/provision.sh -g <board-ip>                  # GIFs + presets only (no cfg change, no reboot)
bin/provision.sh -v <board-ip>                  # verify only: compare the board with the repo
```

Rules the generator enforces (from WLED 16.0.1's loader): a GIF must not be
larger than the panel (smaller ones are scaled up by an integer factor),
filenames including `.gif` are limited to 32 characters, and only one GIF
plays at a time — hence one full-panel Image preset per GIF plus an
"All GIFs" playlist (`-d` seconds per GIF). `gen-presets.sh` overwrites
`config/presets.json`, so make preset changes by re-running it, and rebuild
whenever GIFs are added or removed.

GIFs and other panel images that are generated rather than downloaded come
from the scripts in `gfx/`, described below, which write their output into
`config/gifs/`. Re-run `bin/gen-presets.sh` afterwards so the presets match.

## Panel artwork

`gfx/` generates the artwork the panel shows: marquee animations of the Astryx
wordmark, and the gap file for the panel that sits behind the logo-shaped mask.

- `gfx/raw/` — versioned SVG sources
- `gfx/` — the generators
- `gfx/out/` — intermediates: the rasterized wordmark, the gap file (not versioned)
- `config/gifs/` — the finished GIFs, versioned, and what the board is given

Requirements, none of which the firmware build needs:

- [librsvg](https://wiki.gnome.org/Projects/LibRsvg) for `rsvg-convert` — `brew install librsvg`
- [ImageMagick](https://imagemagick.org) for `magick` (IM6 `convert` also works) — `brew install imagemagick`
- Python 3 with [Pillow](https://python-pillow.org) — `pip install pillow`

Every script takes `--help`, which lists its options and their defaults.

### Regenerating everything

```sh
gfx/generate-all.sh
```

Runs the invocations below through `gfx/Makefile`, from `gfx/` whatever the
current directory is. Only stale targets are rebuilt — a GIF is remade when
`gfx/out/astryx-word.png` or `gfx/make-marquee.sh` changed, and not otherwise,
which is worth caring about because each frame of a marquee is a separate
ImageMagick invocation.

`-f` rebuilds everything regardless, `-n` prints what would run without running
it, `-j N` builds N targets at a time, and `gfx/generate-all.sh clean` deletes
`gfx/out/` and the GIFs the Makefile writes — GIFs dropped into `config/gifs/`
by hand are left alone. Individual targets can be named too, e.g.
`gfx/generate-all.sh out/astryx-gap.json` (target paths are relative to `gfx/`).

Regenerating changes what is on the panel only once the presets are rebuilt and
the board is given the new files:

```sh
gfx/generate-all.sh && bin/gen-presets.sh && bin/provision.sh <board-ip>
```

### Tested (good) invocations

The steps `generate-all.sh` automates, if you want to run one by hand.
`gfx/out/` is not versioned, so create it first if it is missing:

```sh
mkdir -p gfx/out
```

#### Marquee

Rasterize the wordmark into a PNG file:

```sh
rsvg-convert -o gfx/out/astryx-word.png -w 64 -a gfx/raw/astryx-word.svg
```

Flat marquee:

```sh
gfx/make-marquee.sh gfx/out/astryx-word.png config/gifs/astryx-word.gif
```

Cylindrical marquee:

```sh
gfx/make-marquee.sh -c gfx/out/astryx-word.png config/gifs/astryx-word-c.gif
```

#### Letters

```sh
gfx/split-letters.py
```

Cuts `gfx/raw/astryx-word.svg` into `gfx/out/letters/01-A.svg` … `06-x.svg`,
one file per letter, for animating letters independently. The wordmark is a
single `<path>`, so this splits its subpaths, measures each by rendering it,
and puts the counters (the holes in the A and the R) back with the letter they
belong to. It then redraws the pieces and compares against the source, so a
mis-grouped counter fails loudly rather than quietly.

Each letter gets a viewBox tight around its own ink; `-k/--keep-canvas` gives
it the wordmark viewBox instead, so it renders in place. Either way
`gfx/out/letters/letters.json` records where each letter sits in the wordmark:

```json
{ "index": 1, "label": "A", "file": "01-A.svg",
  "bounds": [ 0.0, 4.5, 193.75, 192.5 ], "subpaths": 2 }
```

#### Assembling the word

```sh
gfx/make-assemble.py
```

Writes `config/gifs/astryx-assemble.gif`: the six letters fly in from the
edges, one after another, settle into the wordmark, and the finished word is
held before the loop restarts. Reads `gfx/out/letters/`, so run
`gfx/split-letters.py` first — or just `gfx/generate-all.sh`, which sequences
them.

Defaults give 3.6 seconds: 45 frames of flight, 45 held, at 4cs a frame. The
knobs worth reaching for are `--sides` (which edge each letter enters from,
cycled — `ltrb` by default), `--stagger` (frames between one letter setting off
and the next), `--overshoot` (how far a letter overruns before settling), and
`--hold`.

##### Diagonal variations

`--rotate` stands the whole word at an angle, letters turned with it:

```sh
gfx/make-assemble.py --rotate  45 gfx/out/letters config/gifs/astryx-assemble+45.gif
gfx/make-assemble.py --rotate -45 gfx/out/letters config/gifs/astryx-assemble-45.gif
```

A diagonal word is also a **bigger** word. The wordmark is 5.3:1, so lying flat
it runs out of room at the panel's edge, but on a diagonal it has the panel's
diagonal to use. The word is sized to fill whatever angle it is given:

| `--rotate` | word | letter height | panel lit |
|---|---|---|---|
| `0` | 64.0 × 12.1 px | 12.1 px | 622 px |
| `±45` | 76.1 × 14.4 px | 14.4 px | 893 px |

Any angle works — `--rotate 20` tilts it slightly and sizes it to match.
`--word-width` overrides the fit if you want it smaller. All three targets are
built by `gfx/generate-all.sh`.

A separate knob, `--angle`, turns the directions letters *arrive from* without
moving the word: at `--angle 45` they cross the corners instead of the edges.
It composes with `--rotate`.

#### Offsetting the logo mark

```sh
gfx/make-offset.py -d in   # -> config/gifs/astryx-inward.gif
gfx/make-offset.py -d out  # -> config/gifs/astryx-outward.gif
```

Takes `gfx/raw/astryx.svg` and walks its outline inward: the mark is held, then
thins until its four lobes come apart and dwindle away. **Outward is that same
run in reverse time**, holds included — the lobes appear out of an empty panel,
close up into the mark, and it is held. The two cut together back to back.

The offsets are exact, not pixel erosion: a stroke sits centred on an outline,
so stroking it in the background colour at twice the wanted distance eats
exactly that distance in from either side. The counters between the lobes need
no special handling, and joins are round, since that is what an offset outline
is at a corner.

How far to travel is measured, not guessed: the script bisects for the first
distance that leaves the panel empty — 14.06px for this mark. Set `--depth` to
override, `--scale` to inset the mark at rest, and `--frames` / `--hold` for
timing.

#### Gap file

```sh
python3 gfx/make-gap.py -t 255 -s 64 -b white
```

Reads `gfx/raw/astryx.svg` and writes `gfx/out/astryx-gap.json`, the defaults
for both positional arguments. WLED takes it through its own upload in the 2D
settings page; `bin/provision.sh` does not push it.

**Firmware caveat.** WLED documents `1` as a regular pixel and `0` as one that
is never painted. WLED 16.0.1 acts on the inverse: the entries written as `1`
are the ones it leaves dark, and the `0`s are the ones it paints. Presumed to
be a bug.

The invocation above is therefore written for the firmware rather than for the
documentation — it puts `0` on the logo shape and `1` on the ground around it,
which on 16.0.1 is what lights the shape and blanks the masked area. Do not
"correct" it to match the docs without re-testing on the panel. If a later
release fixes the bug, add `-n/--negative` to flip the polarity back.

### Extra animations

Eight more generators came over from the same project as work in progress. They
work and their defaults write straight into `config/gifs/`, but they are
deliberately **not** Makefile targets, so `gfx/generate-all.sh` leaves them
alone and the panel's set of GIFs does not grow by eight without a decision:

| Script | What it does |
|---|---|
| `gfx/make-spin.py` | spins the logo mark through a full turn |
| `gfx/make-breathe.py` | scales the mark up and down on a loop |
| `gfx/make-fade.py` | fades the mark in and out |
| `gfx/make-wipe.py` | reveals the mark behind a sweeping straight or curved edge |
| `gfx/make-explode.py` | scatters the mark's four lobes apart, or gathers them |
| `gfx/make-glitch.py` | leaves the mark up and glitches it: slice shifts, RGB split, flashes |
| `gfx/make-bounce.py` | letters bounce into place like rubber balls |
| `gfx/make-wave.py` | letters undulate through a sine wave |

The first six take the mark (`gfx/raw/astryx.svg`); `make-bounce.py` and
`make-wave.py` take the letters, so `gfx/split-letters.py` has to have run:

```sh
gfx/make-spin.py                       # -> config/gifs/astryx-spin.gif
gfx/make-wave.py gfx/out/letters       # -> config/gifs/astryx-wave.gif
```

To put one on the panel for good, give it a Makefile target next to the
animations above, so it is rebuilt when the mark or the script changes.

## Known quirks

- The first compile of a new env can occasionally die with
  `compilation terminated ... Error 1` and no diagnostic (memory pressure
  during parallel compilation). Re-running the build succeeds.
