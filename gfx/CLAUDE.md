# CLAUDE.md

Context for Claude Code sessions working in `gfx/`.

Generators that produce artwork for the 64x64 HUB75 panel, plus a
`Makefile` that wires them together. There is no package manifest and no test
suite — the scripts here are the deliverable, and verification is visual (look
at the GIF, look at the ASCII mask preview).

External tools: `rsvg-convert` (librsvg), `magick` (ImageMagick 7; IM6
`convert` is accepted as a fallback), and Python 3 with Pillow. None of them
are needed to build or flash the firmware, so they are not in
`bin/check-env.sh`; `generate-all.sh` checks for them itself.

## Commands

```sh
gfx/generate-all.sh                       # rebuild whatever artwork is stale
gfx/generate-all.sh -n                    # dry run: print the recipes that would run
gfx/generate-all.sh -f -j 4               # force a full rebuild, 4 targets at a time
gfx/generate-all.sh clean                 # delete gfx/out/ and the generated GIFs
gfx/generate-all.sh out/astryx-gap.json   # one target (paths are relative to gfx/)
```

It wraps the `Makefile`, whose recipes are the invocations known to produce
good output. Run one by hand only when iterating on flags; a repeat build is
otherwise skipped, which matters because each marquee frame is a separate
ImageMagick invocation.

```sh
mkdir -p gfx/out                          # gitignored, and rsvg won't create it
rsvg-convert -o gfx/out/astryx-word.png -w 64 -a gfx/raw/astryx-word.svg

gfx/make-marquee.sh gfx/out/astryx-word.png config/gifs/astryx-word.gif        # flat
gfx/make-marquee.sh -c gfx/out/astryx-word.png config/gifs/astryx-word-c.gif   # cylinder

python3 gfx/make-gap.py -t 255 -s 64 -b white   # raw/astryx.svg -> out/astryx-gap.json
python3 gfx/split-letters.py                    # -> out/letters/NN-<letter>.svg
python3 gfx/make-assemble.py                    # -> config/gifs/astryx-assemble.gif
```

These invocations exist in three places — the root `README.md`, the `Makefile`,
and this file. Change one, change all three.

Inspecting results: every script prints its options and their defaults under
`--help`; `make-gap.py` draws the mask on stderr unless `-q`, and `--png FILE`
writes the thresholded mask as an image; `magick identify -format '%wx%h %n
frames\n' config/gifs/astryx-word.gif` confirms a GIF's geometry and frame count.

## Architecture

**The physical build explains both tools.** The panel sits behind a mask cut in
the shape of the Astryx logo. The mask material is slightly see-through, so
LEDs behind it glow instead of staying dark — `make-gap.py` produces the WLED
gap file that switches those LEDs off for good. `make-marquee.sh` produces the
animation shown on the part of the panel that is visible.

**Two sources, no shared code between the generators.** `raw/astryx.svg` (the
square mark) feeds the gap file; `raw/astryx-word.svg` (1060x200 wordmark)
feeds the marquee, via a PNG, and the letter split that the per-letter
animations build on.

**Finished GIFs go to `config/gifs/`, intermediates to `out/`.** `config/gifs/`
is what `bin/gen-presets.sh` turns into presets and what `bin/provision.sh`
uploads, so a generated GIF belongs there and is versioned; the PNG and the gap
file are workings and stay in `out/`, which is gitignored. `make clean` removes
`out/` and the GIFs this Makefile writes, never the whole of `config/gifs/` —
GIFs also arrive there by hand.

**64 is hardcoded in three places** and must agree: `CANVAS_W`/`CANVAS_H` in
`make-marquee.sh`, the `--size` default in `make-gap.py`, and `SIZE` in the
`Makefile` (which feeds both the rasterize step and `-s`). It is the panel
size, so it also has to match `config/cfg.json` (`panels[0].w/h`) — a GIF wider
or taller than the panel is refused by WLED's loader, and by `gen-presets.sh`
ahead of it.

**The dependency graph lives only in the `Makefile`.** Each output depends on
its source *and* on the script that produces it, so editing a generator
invalidates what it made. `generate-all.sh` adds a preflight check for the
external tools and an unconditional `make -C gfx`, so it behaves the same from
any directory; it holds no build logic of its own. New outputs get a target
there, not a line appended to the shell script.

### CLI conventions are deliberately mirrored across the two tools

`make-gap.py` gets its shape from argparse with
`ArgumentDefaultsHelpFormatter`. `make-marquee.sh` hand-rolls the identical UX,
and edits to either should preserve it:

- `usage()` (a heredoc built on `$SYNOPSIS`) is printed, exit 0, for `--help`
  *and* for a bare invocation with no arguments.
- `die()` emits `usage: …` then `<prog>: error: <msg>` to stderr and exits 2 —
  the same two-line shape argparse's `p.error()` produces.
- All validation happens before any rendering: unknown flags, flags missing
  their value, out-of-range values, extra positionals, and a nonexistent input
  file (`no such file: X` in both tools).
- Missing parent directories of an output path are created.
- The final line is `Wrote <path> (…)` summarizing the settings actually used.

The shell script's option list lives only in the `usage()` heredoc — the file
header describes behavior and points at `--help`, deliberately not repeating
the options, because a comment copy would drift. `make-gap.py`'s docstring can
list them because argparse regenerates `--help` independently.

### make-marquee.sh

Source dimensions are read from the file at runtime; the image is used at its
own size, vertically centered, so its width sets the frame count. Flat mode is
one composite per frame at one pixel of travel, `TRAVEL = 64 + IMG_W`.

Cylinder mode (`-c`) maps the image onto a drum whose front half spans the
canvas (`R = 32`, visible arc `ARC = ceil(pi*R)`, so `TRAVEL = ARC + IMG_W`).
It first builds `strip.png`, the unrolled surface — the image with one full arc
of background on each side — then renders each frame with a single `-fx` pass
where output column `i` reads source column `o + HALF_ARC + R*asin(xx)` for
`xx` in `[-1, 1]`, dimmed by `(1-shade) + shade*sqrt(1-xx*xx)` — full `sqrt`
falloff at `--shade 1`, no dimming at all at 0. Frames are rendered at 4x
horizontal supersampling and boxed down, because near the rim many source
columns collapse into one output pixel and point sampling shimmers. These
frames are opaque, so this mode wants an opaque background.

### split-letters.py

Feeds the per-letter animation work. The wordmark is one `<path>`, so letters
exist only as subpaths of a single `d`; the split happens at each moveto.

Three things there are easy to get wrong, and the code exists to handle them:

- **Not every subpath starts absolute.** The A's counter opens with a relative
  `m` (`…z m2.36 117.77…`), so its position depends on where the previous
  subpath ended. Because these subpaths all close with `z`, the previous end is
  that subpath's own start, so no full path walk is needed — but the rewrite to
  absolute `M` must also turn the moveto's trailing implicit linetos into an
  explicit relative `l`, or they change meaning.
- **Counters must stay with their letter.** A subpath contained by another is
  folded into it and kept in source order inside one `d`, so the fill rule
  still cuts the hole. Bounds come from rendering each subpath and measuring
  ink with Pillow, which accounts for curve extrema that reading control points
  would miss.
- **Rewritten path data needs proof.** `verify()` redraws all the pieces on the
  source canvas and compares against the source. Compare alpha and colour
  flattened over an opaque backdrop, never raw RGBA: the RGB of a transparent
  pixel is arbitrary and differs by up to 255 between renders that look
  identical.

Letter geometry lives in `out/letters/letters.json` — index, label, file, and
the letter's box in wordmark coordinates. Animation code should read placement
from there rather than re-deriving it. The letters are an intermediate, not
artwork, so they stay in `out/`.

### make-assemble.py

The first consumer of the split letters, and the pattern for animations that
follow. It never re-derives layout: `letters.json` bounds, scaled by
`word_width / viewBox width` and centred, put each letter exactly where the
wordmark has it, so the held frame is the wordmark (verified to within
antialiasing — worst 25/255, nothing above 32).

Two independent angles, easily confused: `--rotate` stands the *word* at an
angle (letters turned with it), `--angle` turns the directions letters *arrive
from* without moving the word. The ±45 variants use `--rotate`.

`--word-width` defaults to 0, meaning `fitted_width()` — the largest word that
fits at the current rotation. A turned W×H rectangle sweeps `W|cos| + H|sin|`
by `W|sin| + H|cos|`, so a 5.3:1 wordmark on a diagonal gets the panel's
diagonal instead of its edge and comes out about a fifth larger. Verified not
to clip: the same word on a 96px canvas has the identical 893 lit pixels.

Entry direction is a vector, not one of four sides. A letter starts at the
*nearest* distance along it that clears the canvas — clearing one axis is
enough — and at exactly that distance its box rests against the edge and draws
nothing, so no clearance margin is wanted. Adding one shifts every in-flight
position and changes animations that are already approved.

Placement is by centre, because that is what rotation preserves; but an
unrotated sprite is measured by its *exact* ink box rather than its rounded
raster. Without that split, adding rotation silently shifted the flat animation
by a tenth of a pixel — invisible, but it made `--rotate 0` stop reproducing
the approved GIF. Both regimes are checked with `cmp` against a stored copy.

Two more details that are easy to get wrong here:

- **Compose above panel resolution.** Letters are ~12 px tall at 64x64, so
  integer-pixel motion visibly stair-steps. Frames are built at
  `--supersample` times the panel size and boxed down, which buys sub-pixel
  travel. This is the same trick the cylinder mode in `make-marquee.sh` uses
  for a different reason.
- **One palette for the whole GIF.** Frames are quantized against a palette
  taken from the finished word; per-frame adaptive palettes make colours crawl
  as letters land. Pillow also merges runs of identical frames and sums their
  delays, so a 90-frame animation is stored as ~44 — the total duration is
  unchanged, and the summary line reports both numbers so the difference does
  not read as a bug.

### make-gap.py

Output values are WLED's documented ones: 1 = regular pixel, 0 = never paint.
-1 (physically missing) is never emitted, since the panel is a solid
rectangle. The JSON is written one matrix row per line.

**WLED 16.0.1 acts on the inverse of that documentation** — it leaves the 1s
dark and paints the 0s — which is presumed to be a firmware bug. The script
keeps emitting the documented polarity, so the gap file has to be authored
inverted for the panel to look right: the tested invocation deliberately puts
0 on the logo shape and 1 on the ground. Anything that looks like a polarity
mistake in the tested invocation, `README.md`, or `threshold()` is load-bearing
until the firmware is fixed; a fix would mean adding `-n/--negative`.

The `--channel auto` default prefers alpha and falls back to luma only when the
render is fully opaque. The tested invocation therefore behaves quite
differently from the defaults: `-b white` makes the render opaque and forces
the luma path, and `raw/astryx.svg` paints with `currentColor` against a CSS
variable rsvg cannot resolve, so the mark rasterizes pure black on white.
`-t 255` then demands pure white, which puts the shape *and* its antialiased
edge pixels at 0 — the conservative choice, since a partially masked LED should
be off. Running with the defaults instead (alpha, threshold 128) yields close
to the complement of that mask, so don't treat default output as the intended
gap file.
