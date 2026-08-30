#!/usr/bin/env python3
"""make-assemble.py — fly the letters in from the edges into the word.

Each letter enters from one side of the 64x64 canvas, travels to the
place it occupies in the wordmark, and stops. Letters leave in turn
rather than together — see --stagger — so the word assembles itself
piece by piece; once the last one lands the finished word is held for
--hold frames before the GIF loops.

Input is gfx/out/letters/, as written by split-letters.py: the SVGs supply
the shapes and letters.json says where in the wordmark each belongs, so
the held word is the wordmark, not an approximation of it.

--rotate stands the whole word at an angle, letters turned with it. The
wordmark is long and thin, so a diagonal one is also a bigger one: it
spans the panel corner to corner instead of edge to edge, and the word is
sized to fill whatever angle it is given. At 45 degrees that is 76 px
across where flat is 64: letters a fifth taller, and about 40% more of
the panel lit.

Motion is eased out — quick away from the edge, settling as it arrives —
with a --overshoot fraction of the travel overrun and drawn back, which
gives the landing some weight. Frames are composed at --supersample times
the panel resolution and boxed down, so a letter can sit half a pixel
into a position: at 64x64 a letter is about 12 px tall, and without that
its motion would visibly jump from pixel to pixel.

Usage:
  ./make-assemble.py [options] [letters-dir] [output.gif]

  -s, --size N        canvas is NxN pixels                  (default: 64)
  -r, --rotate DEG    stand the word at this angle,
                      clockwise on screen                    (default: 0)
  -w, --word-width N  width of the assembled word, px
                                    (default: as wide as fits at --rotate)
  -f, --frames N      frames each letter spends flying      (default: 30)
      --hold N        frames the finished word is held      (default: 45)
      --stagger N     frames between one letter leaving and
                      the next                              (default: 3)
      --sides ORDER   sides letters enter from, cycled: any
                      of l, r, t, b                        (default: ltrb)
      --angle DEG     turn every entry direction by this
                      much, clockwise on screen; +/-45
                      brings letters across the corners       (default: 0)
      --overshoot F   fraction of the travel overrun on
                      arrival, 0 for none                  (default: 0.05)
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

SIDES = "lrtb"


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


def solve_overshoot(excess):
    """Back-easing strength whose overrun is `excess` of the travel.

    easeOutBack peaks at 4s^3/(27(s+1)^2) past the target, which has no
    tidy inverse; the curve rises with s, so bisect it.
    """
    if excess <= 0:
        return 0.0
    low, high = 0.0, 40.0
    for _ in range(60):
        mid = (low + high) / 2
        peak = 4 * mid ** 3 / (27 * (mid + 1) ** 2)
        low, high = (mid, high) if peak < excess else (low, mid)
    return (low + high) / 2


def ease(t, strength):
    """Cubic ease-out, overrunning the target when strength > 0."""
    u = t - 1
    if strength <= 0:
        return 1 + u ** 3
    return 1 + (strength + 1) * u ** 3 + strength * u ** 2


BASE = {"l": (-1.0, 0.0), "r": (1.0, 0.0), "t": (0.0, -1.0), "b": (0.0, 1.0)}


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
    p.add_argument("-f", "--frames", type=int, default=30,
                   help="frames each letter spends flying")
    p.add_argument("--hold", type=int, default=45,
                   help="frames the finished word is held")
    p.add_argument("--stagger", type=int, default=3,
                   help="frames between one letter leaving and the next")
    p.add_argument("--sides", default="ltrb",
                   help="sides letters enter from, cycled (l, r, t, b)")
    p.add_argument("--angle", type=float, default=0,
                   help="degrees to turn every entry direction, clockwise on "
                        "screen; 45 brings letters in across the corners")
    p.add_argument("--overshoot", type=float, default=0.05,
                   help="fraction of the travel overrun on arrival")
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
    if args.delay < 1:
        p.error(f"--delay must be positive, got {args.delay}")
    if args.supersample < 1:
        p.error(f"--supersample must be positive, got {args.supersample}")
    if not 0 <= args.overshoot < 1:
        p.error(f"--overshoot must be in 0..1, got {args.overshoot}")
    bad = sorted(set(args.sides) - set(SIDES))
    if not args.sides or bad:
        p.error(f"--sides takes a non-empty run of {', '.join(SIDES)}; got {args.sides!r}")
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

    strength = solve_overshoot(args.overshoot)
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

            side = args.sides[n % len(args.sides)]
            direction = turn(BASE[side], args.angle)
            start = entry_point(direction, final, raster, args.size)
            flights.append((letter, sprite, start, final, side))

            if not args.quiet:
                print(f"  {letter['file']}  from {compass(direction):>2}"
                      f"  {start[0]:7.1f},{start[1]:6.1f}"
                      f" -> {final[0]:6.1f},{final[1]:6.1f}", file=sys.stderr)

    travel = args.frames + args.stagger * (len(flights) - 1)
    total = travel + args.hold
    frames = []
    for f in range(total):
        canvas = Image.new("RGBA", (canvas_px, canvas_px), background + (255,))
        for n, (_, sprite, start, final, _) in enumerate(flights):
            t = (f - n * args.stagger) / args.frames
            progress = 0.0 if t <= 0 else 1.0 if t >= 1 else ease(t, strength)
            x = start[0] + (final[0] - start[0]) * progress
            y = start[1] + (final[1] - start[1]) * progress
            canvas.alpha_composite(sprite, (round(x * ss), round(y * ss)))
        frames.append(canvas.resize((args.size, args.size), Image.BOX).convert("RGB"))

    # One palette for every frame, taken from the assembled word: frame
    # palettes of their own would swap colours around as letters land.
    palette = frames[-1].quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(args.output, save_all=True, append_images=quantized[1:],
                      duration=args.delay * 10, loop=0, disposal=1, optimize=False)

    # Runs of identical frames are stored once with their delays summed,
    # so what lands on disk is shorter than what was composed.
    with Image.open(args.output) as written:
        stored = written.n_frames

    print(f"Wrote {args.output} ({total} frames at {args.delay}cs = "
          f"{total * args.delay / 100:.1f}s, {travel} in flight + {args.hold} held, "
          f"word {word_width:.1f}x{view_h * scale:.1f}px"
          f"{f' at {args.rotate:g}°' if args.rotate else ''}, "
          f"{len(flights)} letters from {args.sides}"
          f"{f' turned {args.angle:g}°' if args.angle else ''}, {stored} stored, "
          f"bg={args.background})")


if __name__ == "__main__":
    main()
