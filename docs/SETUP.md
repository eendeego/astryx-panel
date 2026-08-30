# Manual panel setup

What to type into WLED's own settings pages to reach the state this repo
provisions. It is the recovery path, not the normal one — the normal one is:

```sh
bin/flash.sh -e matrixportal_s3_custom   # firmware
bin/provision.sh <board-ip>              # cfg.json, GIFs, presets
```

Reach for this page when that is not available: a board being set up from
another machine, a settings page that has to be checked by eye, or a config
that has drifted and needs comparing against what it should be.

Hardware: [Adafruit Matrix Portal S3](https://www.adafruit.com/product/5778),
one 64×64 HUB75 panel, and the board's own status NeoPixel.

## Where each setting comes from

| Set by | What it covers | Survives a factory reset? |
|---|---|---|
| Build flags (`config/platformio_override.ini`) | buttons, I2C pins | Yes — they are the defaults a fresh config is built from |
| `config/cfg.json` via `bin/provision.sh` | HUB75 bus, the NeoPixel, 2D layout, ESP-NOW, boot preset | No — re-run `bin/provision.sh` |
| `bin/gen-presets.sh` + `bin/provision.sh` | the GIFs and their presets | No — re-run both |
| Nothing in this repo | gamma, transitions, UI preferences, the gap file | No — the settings below are the only record |

That last row is why this page exists: those values are not in `cfg.json` and
no script restores them.

## WiFi & Network Settings

Enable **ESP-NOW** (needed for a remote). `cfg.json` carries this as
`nw.espnow`.

## LED & Hardware

Maximum PSU Current: **4000 mA**

> `cfg.json` ships `maxpwr: 0` — the limiter off — and provisioning will set it
> back to that. WLED's estimate does not model a HUB75 panel's draw anyway;
> the panel's own supply is what protects it. Set 4000 here only if you want
> the UI's estimate to mean something.

LED outputs:

**1: HUB75 (Half Scan)** — `cfg.json` `hw.led.ins[0]`

> Start: 0
> Panel (width x height): 64 64
> No. of Panels: 1 rows x cols: 1 1
> Reversed: Panel [ ] (unchecked)

**2: WS281x RGB** — the status NeoPixel, `cfg.json` `hw.led.ins[1]`

> mA/LED: 55mA (typ. 5V WS281x)
> Color Order: GRB
> Start: 4096
> Length: 1
> Data GPIO: 4
> Driver: RMT
> Reversed: [ ] (unchecked)
> Skip first LEDs: 0
> Off Refresh: [ ] (unchecked)

The two buses together are `total: 4097` LEDs — 4096 for the matrix plus the
one NeoPixel, which is why its start index is 4096.

----

Show Advanced Settings [x]
Make a segment for each output: [ ] (unchecked)
Custom bus start indices: [ ] (unchecked)

----

Use Gamma correction for color: [x] (strongly recommended)
Use Gamma correction for brightness: [ ] (not recommended)
Use Gamma value: 2.2
White Balance correction: [ ] (unchecked)

> Not in `cfg.json`. Set by hand after a factory reset.

### Hardware setup

#### Buttons

#0 GPIO: 6 | Pushbutton
#1 GPIO: 7 | Pushbutton

Disable internal pull-up/down: [ ] (unchecked)
Touch threshold: 32

> These are the front Up/Down buttons, baked into the firmware as
> `-D BTNPIN=6,7 -D BTNTYPE=2,2`, so a fresh config already has them. They only
> need typing in if a saved config has them wrong.

#### IR Remote

IR GPIO: unused | Remote disabled
Apply IR change to main segment only: [ ] (unchecked)

#### Relay

Relay GPIO: unused
Invert [x] Open drain  [ ]

### General settings

#### Transitions

Default transition time: 750 ms (Maybe 700 ?)

> Not in `cfg.json`. The presets `bin/gen-presets.sh` writes carry
> `"transition": 7` (700 ms) each, which overrides this while a preset is
> loaded — so 700 here keeps a manual change looking the same as a preset.

## 2D setup

### Panel set-up

Number of panels: 1

### LED Panel layout

Panel 0
1st LED: Top Left
Orientation: Horizontal

Serpentine: [ ] (unchecked)
Dimensions (WxH): 64 x 64
Offset X: 0 Y: 0

(offset from top-left corner in # LEDs)

> `cfg.json` `hw.led.matrix.panels[0]`. WLED 16.0.1 mangles HUB75 bus
> parameters on first boot, so this is the section to check first if the panel
> comes up scrambled.

### Gap file

(upload)

> Generated: `python3 gfx/make-gap.py -t 255 -s 64 -b white` writes
> `gfx/out/astryx-gap.json`. Upload it here by hand — `bin/provision.sh` does
> not push it. Mind the inverted polarity the invocation deliberately produces;
> the firmware caveat in `README.md` explains why.

## User Interface

Color Wheel: [x]
RGB sliders: [x]
Quick color selectors: [x]
HEX color input: [x]

> Not in `cfg.json`. Set by hand after a factory reset.

## Presets

The boot preset is `cfg.json` `def.ps` — the "All GIFs" playlist
`bin/gen-presets.sh` writes as the last preset. Upload the GIFs and
`presets.json` with `bin/provision.sh -g <board-ip>` rather than adding presets
by hand: `gen-presets.sh` overwrites `config/presets.json`, so hand edits on
the board are lost the next time it is provisioned.
