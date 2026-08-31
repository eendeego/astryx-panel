#!/usr/bin/env python3
"""make-assemble.py — fly the letters in, hold the word, scatter them again.

Each letter comes in from off-canvas at its own angle and its own speed,
travels to the place it occupies in the wordmark, and settles. Letters
set off in turn rather than together — see --stagger — so the word
assembles itself piece by piece; once the last one lands the finished
word is held for --hold frames, and then they leave the same way, in a
different order and in different directions, until the panel is empty
and the GIF loops.

Directions are random and so are the speeds, drawn from --seed, which
means a given seed always produces the same animation — the build has to
be able to reproduce it. --variation says how far the speeds spread.

Input is gfx/out/letters/, as written by split-letters.py: the SVGs supply
the shapes and letters.json says where in the wordmark each belongs, so
the held word is the wordmark, not an approximation of it.

--rotate stands the whole word at an angle, letters turned with it. The
wordmark is long and thin, so a diagonal one is also a bigger one: it
spans the panel corner to corner instead of edge to edge, and the word is
sized to fill whatever angle it is given. At 45 degrees that is 76 px
across where flat is 64: letters a fifth taller, and about 40% more of
the panel lit.

Nothing is eased by hand. On the way in a letter is on a spring: pulled
towards its place with a force proportional to how far it still has to
go, against a drag proportional to how fast it is going, so it leaves
quickly, slows as it arrives and settles with the small overshoot that
--damping sets. On the way out there is nothing pulling back — constant
acceleration from rest, so it drifts, then goes. Both are integrals of an
acceleration rather than curves chosen to look like one, which is what
makes the motion read as weight instead of as timing.

Frames are composed at --supersample times the panel resolution and boxed
down, so a letter can sit half a pixel into a position: at 64x64 a letter
is about 12 px tall, and without that its motion would visibly jump from
pixel to pixel.

Usage:
  ./make-assemble.py [options] [letters-dir] [output.gif]

  -s, --size N        canvas is NxN pixels                  (default: 64)
  -r, --rotate DEG    stand the word at this angle,
                      clockwise on screen                    (default: 0)
  -w, --word-width N  width of the assembled word, px
                                    (default: as wide as fits at --rotate)
  -f, --frames N      frames the assembly takes, first letter
                      setting off to last landing           (default: 60)
      --hold N        frames the finished word is held      (default: 25)
      --out N         frames the scattering takes, 0 for none
                                              (default: same as --frames)
      --stagger N     frames between one letter setting off
                      and the next                           (default: 4)
      --variation F   how much the speeds differ, 0..1     (default: 0.45)
      --damping F     spring damping on the way in: 1 settles
                      dead, lower overshoots               (default: 0.7)
      --seed N        seed for the directions and speeds      (default: 0)
      --supersample N compose at N times panel resolution     (default: 4)
  -d, --delay N       per-frame delay in centiseconds        (default: 4)
  -b, --background C  canvas fill colour                  (default: black)
  -q, --quiet         suppress the per-letter listing on stderr

  letters-dir  directory split-letters.py filled
                                          (default: gfx/out/letters)
  output.gif   file to write   (default: config/gifs/astryx-assemble.gif)

Missing parent directories are created for the GIF.
"""

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageColor

GFX_DIR = Path(__file__).resolve().parent
REPO_ROOT = GFX_DIR.parent
DEFAULT_LETTERS = GFX_DIR / "out" / "letters"
DEFAULT_OUT = REPO_ROOT / "config" / "gifs" / "astryx-assemble.gif"

def load_manifest(letters_dir, parser):
    """Read letters.json and check it describes what this script needs."""
    path = letters_dir / "letters.json"
    if not path.is_file():
        parser.error(f"no letters.json in {letters_dir}; run gfx/split-letters.py first")
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        parser.error(f"{path}: {exc}")

    if not manifest.get("tight", True):
        # With --keep-canvas every letter already carries the wordmark
        # viewBox, so its file cannot be placed by its bounds.
        parser.error(f"{path} was written with --keep-canvas; rerun "
                     f"gfx/split-letters.py without it")
    letters = manifest.get("letters") or []
    if not letters:
        parser.error(f"{path} lists no letters")
    for letter in letters:
        if not (letters_dir / letter["file"]).is_file():
            parser.error(f"{path} names {letter['file']}, which is not in {letters_dir}")
    return manifest, letters


# How many radians of the spring's own oscillation are fitted into a flight.
# At 9 the residual when the flight ends is under a thousandth of the travel,
# so a letter is on its mark by the time the word is held.
SWING = 9.0


def spring(u, zeta):
    """How far along a damped spring is, `u` of the way through the flight.

    The letter is pulled towards its place by a force proportional to the
    distance left, against a drag proportional to its speed: the step
    response of a second-order system. Below a damping ratio of 1 it arrives
    a little past the mark and settles back, which is what reads as weight.
    """
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0
    decay = math.exp(-zeta * SWING * u)
    if zeta >= 1:  # critically damped and beyond: no oscillation left in it
        return 1 - decay * (1 + zeta * SWING * u)
    ringing = SWING * math.sqrt(1 - zeta * zeta)
    return 1 - decay * (math.cos(ringing * u)
                        + (zeta * SWING / ringing) * math.sin(ringing * u))


def accelerate(u):
    """Constant acceleration from rest: distance as the square of time.

    The way out, where nothing is pulling back — the letter drifts off its
    mark, then goes.
    """
    return 0.0 if u <= 0 else 1.0 if u >= 1 else u * u


def bearing(rng):
    """A unit vector at a uniformly random angle."""
    theta = rng.uniform(0, 2 * math.pi)
    return (math.cos(theta), math.sin(theta))


def schedule(count, span, stagger, variation, rng):
    """(set off, take) per letter, everything finished within `span`.

    Departures are evenly spaced, so a phase still reads in order. What
    varies is how long each letter then takes over what is left of the
    phase, and that is where the difference in speed comes from: a letter
    given 0.6 of the time left covers the same ground half again as fast.
    """
    plan = []
    for i in range(count):
        start = round(i * stagger)
        plan.append((start, max(1, round((span - start) * rng.uniform(1 - variation, 1)))))
    return plan


def turn(vector, degrees):
    """Rotate an entry direction. Positive reads clockwise on screen."""
    theta = math.radians(degrees)
    cos, sin = math.cos(theta), math.sin(theta)
    dx, dy = vector
    return (dx * cos - dy * sin, dx * sin + dy * cos)


def fitted_width(canvas, aspect, degrees):
    """The widest the word can be and still fit, stood at `degrees`.

    Turning a W x H rectangle sweeps out a box of W|cos| + H|sin| by
    W|sin| + H|cos|, and it fits exactly when the larger of those reaches
    the canvas. The word is long and thin, so standing it on a diagonal
    lets it use the panel's diagonal and come out bigger than it can lying
    flat: at 45 degrees a 5.3:1 wordmark gains about a fifth.
    """
    theta = math.radians(degrees)
    cos, sin = abs(math.cos(theta)), abs(math.sin(theta))
    return canvas / max(cos + aspect * sin, sin + aspect * cos)


def compass(direction):
    """Name the direction a letter arrives from. Screen y grows downward."""
    points = ("E", "SE", "S", "SW", "W", "NW", "N", "NE")
    dx, dy = direction
    return points[round(math.degrees(math.atan2(dy, dx)) / 45) % 8]


def entry_point(direction, final, letter_size, canvas):
    """Where a letter sits, off-canvas, before it sets off.

    Back it away from its final position along `direction` until the
    canvas no longer holds any of it. Clearing one axis is enough, so the
    distance is the nearest of the crossings rather than the furthest —
    a letter entering diagonally does not start further out than it has
    to. At that distance the letter's box rests exactly against the edge
    it left by, which draws nothing, so it needs no clearance beyond.
    """
    dx, dy = direction
    (fx, fy), (w, h) = final, letter_size
    crossings = []
    if dx > 1e-9:
        crossings.append((canvas - fx) / dx)
    elif dx < -1e-9:
        crossings.append((fx + w) / -dx)
    if dy > 1e-9:
        crossings.append((canvas - fy) / dy)
    elif dy < -1e-9:
        crossings.append((fy + h) / -dy)
    distance = min(crossings)
    return (fx + dx * distance, fy + dy * distance)


def render_letter(svg, width, height, dest):
    proc = subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height), str(svg), "-o", str(dest)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"rsvg-convert failed on {svg}: {proc.stderr.strip()}")


def main():
    p = argparse.ArgumentParser(
        description="Fly the split letters in from the edges into the wordmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("letters", nargs="?", type=Path, default=DEFAULT_LETTERS,
                   help="directory split-letters.py filled")
    p.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUT,
                   help="GIF to write")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("-r", "--rotate", type=float, default=0,
                   help="degrees to stand the whole word at, clockwise on screen")
    p.add_argument("-w", "--word-width", type=float, default=0,
                   help="width of the assembled word in pixels "
                        "(default: 0, meaning as wide as fits at --rotate)")
    p.add_argument("-f", "--frames", type=int, default=60,
                   help="frames the assembly takes, first letter setting off "
                        "to last landing")
    p.add_argument("--hold", type=int, default=25,
                   help="frames the finished word is held")
    p.add_argument("--out", type=int, default=-1,
                   help="frames the scattering takes, 0 for none "
                        "(default: -1, meaning as many as --frames)")
    p.add_argument("--stagger", type=int, default=4,
                   help="frames between one letter setting off and the next")
    p.add_argument("--variation", type=float, default=0.45,
                   help="how much the speeds differ, 0..1")
    p.add_argument("--damping", type=float, default=0.7,
                   help="spring damping on the way in; 1 settles dead")
    p.add_argument("--seed", type=int, default=0,
                   help="seed for the directions and speeds")
    p.add_argument("--supersample", type=int, default=4,
                   help="compose at this multiple of the panel resolution")
    p.add_argument("-d", "--delay", type=int, default=4,
                   help="per-frame delay in centiseconds")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the per-letter listing")
    args = p.parse_args()

    if args.size < 1:
        p.error(f"--size must be positive, got {args.size}")
    if args.word_width < 0:
        p.error(f"--word-width must not be negative, got {args.word_width}")
    if args.frames < 1:
        p.error(f"--frames must be positive, got {args.frames}")
    if args.hold < 0:
        p.error(f"--hold must not be negative, got {args.hold}")
    if args.stagger < 0:
        p.error(f"--stagger must not be negative, got {args.stagger}")
    if not 0 <= args.variation < 1:
        p.error(f"--variation must be in 0..1, got {args.variation}")
    if args.damping <= 0:
        p.error(f"--damping must be positive, got {args.damping}")
    if args.out < -1:
        p.error(f"--out must not be negative, got {args.out}")
    if args.delay < 1:
        p.error(f"--delay must be positive, got {args.delay}")
    if args.supersample < 1:
        p.error(f"--supersample must be positive, got {args.supersample}")
    if not args.letters.is_dir():
        p.error(f"no such directory: {args.letters}")
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found (brew install librsvg)")

    manifest, letters = load_manifest(args.letters, p)
    try:
        background = ImageColor.getrgb(args.background)
    except ValueError as exc:
        p.error(f"--background: {exc}")

    ss = args.supersample
    canvas_px = args.size * ss

    # The word keeps the wordmark's proportions and is centred on the
    # panel, so a letter's place is its place in the wordmark, scaled and
    # then turned about the middle of the word by --rotate.
    _, _, view_w, view_h = manifest["viewBox"]
    word_width = args.word_width or fitted_width(args.size, view_h / view_w, args.rotate)
    scale = word_width / view_w
    word_centre = (word_width / 2, view_h * scale / 2)
    canvas_centre = (args.size / 2, args.size / 2)

    rng = random.Random(args.seed)
    out_span = args.frames if args.out < 0 else args.out
    if args.stagger * (len(letters) - 1) >= args.frames:
        p.error(f"--stagger {args.stagger} over {len(letters)} letters leaves the last "
                f"one no time to fly in --frames {args.frames}")
    if out_span and args.stagger * (len(letters) - 1) >= out_span:
        p.error(f"--stagger {args.stagger} over {len(letters)} letters leaves the last "
                f"one no time to leave in --out {out_span}")

    flights = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, letter in enumerate(letters):
            bx, by, bw, bh = letter["bounds"]
            width = max(1, round(bw * scale * ss))
            height = max(1, round(bh * scale * ss))
            png = Path(tmp) / f"{n}.png"
            render_letter(args.letters / letter["file"], width, height, png)
            with Image.open(png) as img:
                sprite = img.convert("RGBA").copy()
            if args.rotate:
                # Pillow turns anticlockwise; screen y grows downward, so
                # negate to keep --rotate reading clockwise like --angle.
                sprite = sprite.rotate(-args.rotate, resample=Image.BICUBIC, expand=True)

            # Turn the letter's middle about the middle of the word, then
            # hang the sprite off that point. Placing centres rather than
            # corners keeps the letter's own rotation and the word's the
            # same movement.
            middle = ((bx + bw / 2) * scale, (by + bh / 2) * scale)
            offset = turn((middle[0] - word_centre[0], middle[1] - word_centre[1]),
                          args.rotate)
            # Rotating expands the sprite about its middle, so the raster's
            # middle is the letter's. Left alone, the raster is the letter's
            # own box rounded out to whole pixels, and measuring from the
            # exact box instead is what keeps an unrotated animation
            # pixel-for-pixel what it was before rotation existed.
            raster = (sprite.width / ss, sprite.height / ss)
            span = raster if args.rotate else (bw * scale, bh * scale)
            final = (canvas_centre[0] + offset[0] - span[0] / 2,
                     canvas_centre[1] + offset[1] - span[1] / 2)

            # In and out are drawn separately, so a letter rarely leaves the
            # way it came. Both are backed off along their own bearing until
            # the canvas no longer holds any of the letter.
            arrives_from = bearing(rng)
            leaves_towards = bearing(rng)
            start = entry_point(arrives_from, final, raster, args.size)
            exit_at = entry_point(leaves_towards, final, raster, args.size)
            flights.append((letter, sprite, start, final, exit_at,
                            arrives_from, leaves_towards))

    # When each letter sets off and how long it is given, in and out. The
    # order is redrawn for the scattering, so the word does not come apart in
    # the order it was built.
    arrive = schedule(len(flights), args.frames, args.stagger, args.variation, rng)
    depart = [None] * len(flights)
    if out_span:
        order = list(range(len(flights)))
        rng.shuffle(order)
        leaving = schedule(len(flights), out_span, args.stagger, args.variation, rng)
        for slot, n in enumerate(order):
            depart[n] = leaving[slot]

    if not args.quiet:
        for n, (letter, _, start, final, exit_at, came, went) in enumerate(flights):
            took = f"{arrive[n][1]:3d}f from frame {arrive[n][0]:3d}"
            gone = (f", out over {depart[n][1]:3d}f from {depart[n][0]:3d} to "
                    f"{compass(went):>2}") if out_span else ""
            print(f"  {letter['file']}  in from {compass(came):>2} {took}"
                  f"  {start[0]:7.1f},{start[1]:6.1f} -> {final[0]:6.1f},{final[1]:6.1f}"
                  f"{gone}", file=sys.stderr)

    held_until = args.frames + args.hold
    total = held_until + out_span
    frames = []
    for f in range(total):
        canvas = Image.new("RGBA", (canvas_px, canvas_px), background + (255,))
        for n, (_, sprite, start, final, exit_at, _, _) in enumerate(flights):
            if f < args.frames:                      # on the spring, coming in
                begins, takes = arrive[n]
                progress = spring((f - begins) / takes, args.damping)
                here, there = start, final
            elif f < held_until or not out_span:     # the word, held
                progress, here, there = 0.0, final, final
            else:                                    # accelerating away
                begins, takes = depart[n]
                progress = accelerate((f - held_until - begins) / takes)
                here, there = final, exit_at
            x = here[0] + (there[0] - here[0]) * progress
            y = here[1] + (there[1] - here[1]) * progress
            canvas.alpha_composite(sprite, (round(x * ss), round(y * ss)))
        frames.append(canvas.resize((args.size, args.size), Image.BOX).convert("RGB"))

    # One palette for every frame, taken from the busiest one: frame palettes
    # of their own would swap colours around as letters land. It cannot be the
    # last frame any more — that one is an empty panel once the word scatters.
    richest = max(frames, key=lambda f: len(f.getcolors(maxcolors=1 << 16) or [1]))
    palette = richest.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(args.output, save_all=True, append_images=quantized[1:],
                      duration=args.delay * 10, loop=0, disposal=1, optimize=False)

    # Runs of identical frames are stored once with their delays summed,
    # so what lands on disk is shorter than what was composed.
    with Image.open(args.output) as written:
        stored = written.n_frames

    print(f"Wrote {args.output} ({total} frames at {args.delay}cs = "
          f"{total * args.delay / 100:.1f}s, {args.frames} in + {args.hold} held"
          f"{f' + {out_span} out' if out_span else ''}, "
          f"word {word_width:.1f}x{view_h * scale:.1f}px"
          f"{f' at {args.rotate:g}°' if args.rotate else ''}, "
          f"{len(flights)} letters, seed {args.seed}, damping {args.damping:g}, "
          f"{stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
