# GIF preview

Every animation in `config/gifs/`, which is what `bin/provision.sh` puts on the
panel and what `bin/gen-presets.sh` turns into presets. All of them are 64×64 —
the panel's own size, since WLED clips anything larger and scales smaller ones
up by whole numbers only.

Rebuild them all with `gfx/generate-all.sh`; the command under each one rebuilds
just that. Frame counts below are what is *stored*: runs of identical frames are
merged with their delays summed, so the duration is the number that matters.

Seven GIFs, 437 KB in total, against roughly 1.6 MB of filesystem on the board.

---

## The wordmark, scrolling

### astryx-word.gif

<img src="../config/gifs/astryx-word.gif" width="192" alt="The Astryx wordmark scrolling right to left across the panel">

The wordmark enters from the right, crosses, and leaves at the left before
starting again — a flat marquee, no wrap-around. The word is rasterized to the
panel's width, so it is 64×12 and rides the middle of the panel.

`128 frames · 5.1 s · 99.5 KB · preset 7`

```sh
gfx/make-marquee.sh gfx/out/astryx-word.png config/gifs/astryx-word.gif
```

### astryx-word-c.gif

<img src="../config/gifs/astryx-word-c.gif" width="192" alt="The wordmark wrapped around a rotating drum, foreshortening at the edges">

The same word on the surface of a drum turning towards you: columns bunch up and
dim at the rim where the surface angles away, and move fastest across the
middle. The longest of the set, because a full turn is the visible arc plus the
word's own width.

`165 frames · 6.6 s · 138.5 KB · preset 6`

```sh
gfx/make-marquee.sh -c gfx/out/astryx-word.png config/gifs/astryx-word-c.gif
```

---

## The letters, assembling

Each of these flies the six letters in from the panel edges, one after another,
and holds the finished wordmark before looping. Letter positions come from
`gfx/out/letters/letters.json`, so the held frame *is* the wordmark rather than
an approximation of it.

### astryx-assemble.gif

<img src="../config/gifs/astryx-assemble.gif" width="192" alt="Letters flying in from the edges to form the horizontal wordmark">

Flat: the word lies across the panel, 64×12, letters about 12 px tall.

`44 frames · 3.6 s · 46.8 KB · preset 3`

```sh
gfx/make-assemble.py --rotate 0 gfx/out/letters config/gifs/astryx-assemble.gif
```

### astryx-assemble+45.gif

<img src="../config/gifs/astryx-assemble+45.gif" width="192" alt="The same assembly with the word standing at 45 degrees">

The word stands at 45°, which also makes it bigger: on the diagonal it has the
panel's diagonal to fill, so it comes out 76×14 and the letters gain a fifth in
height.

`45 frames · 3.6 s · 55.0 KB · preset 1`

```sh
gfx/make-assemble.py --rotate 45 gfx/out/letters config/gifs/astryx-assemble+45.gif
```

### astryx-assemble-45.gif

<img src="../config/gifs/astryx-assemble-45.gif" width="192" alt="The same assembly tilted 45 degrees the other way">

The mirror of the one above, tilted the other way. The two cut together well
back to back.

`44 frames · 3.6 s · 53.0 KB · preset 2`

```sh
gfx/make-assemble.py --rotate -45 gfx/out/letters config/gifs/astryx-assemble-45.gif
```

---

## The mark, eaten away

One animation, played in both directions. They are frame-for-frame reverses of
each other, holds included, so they also cut together back to back.

### astryx-inward.gif

<img src="../config/gifs/astryx-inward.gif" width="192" alt="The logo mark thinning until its four lobes come apart and vanish">

The mark is held, then its outline steps inward: it thins, comes apart into its
four lobes, and they dwindle to nothing. 14.06 px of travel, which is measured
rather than guessed — the script bisects for the first distance that leaves the
panel empty.

`30 frames · 1.8 s · 22.4 KB · preset 4`

```sh
gfx/make-offset.py -d in gfx/raw/astryx.svg config/gifs/astryx-inward.gif
```

### astryx-outward.gif

<img src="../config/gifs/astryx-outward.gif" width="192" alt="Four lobes appearing from an empty panel and closing up into the logo mark">

The same run in reverse time: lobes appear out of an empty panel, swell, close
up into the mark, and it is held.

`30 frames · 1.8 s · 22.2 KB · preset 5`

```sh
gfx/make-offset.py -d out gfx/raw/astryx.svg config/gifs/astryx-outward.gif
```

---

## How they play

`bin/gen-presets.sh` gives each GIF an Image-effect preset, numbered in the
alphabetical order above, and adds an "All GIFs" playlist as preset 8. That
playlist is the boot preset (`def.ps` in `config/cfg.json`), and it gives every
GIF **10 seconds** before moving on — so the short ones repeat several times
and `astryx-word-c` gets through one and a half passes.

Add a GIF by dropping a 64×64 file into `config/gifs/` (filename ≤ 32
characters including `.gif`), then re-run `bin/gen-presets.sh` and
`bin/provision.sh <board-ip>`.

Eight more generators are sitting in `gfx/` unwired — spin, breathe, fade, wipe,
explode, glitch, bounce and wave. See *Extra animations* in the `README.md`;
running one writes straight into `config/gifs/` and it shows up here on the next
pass.
