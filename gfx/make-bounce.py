#!/usr/bin/env python3
"""make-bounce.py — letters bounce into place like rubber balls.

Same letter-assembly concept as make-assemble.py but with high elasticity:
each letter bounces off its landing position multiple times before settling.
The bounces decay exponentially, giving a natural rubber-ball feel.

Usage:
  ./make-bounce.py [options] [letters-dir] [output.gif]

  -s, --size N        canvas is NxN pixels                  (default: 64)
  -r, --rotate DEG    stand the word at this angle,
                      clockwise on screen                    (default: 0)
  -w, --word-width N  width of the assembled word, px
                                    (default: as wide as fits at --rotate)
  -f, --frames N      frames per letter flight              (default: 25)
      --hold N        frames the finished word is held      (default: 30)
      --stagger N     frames between one letter setting off (default: 4)
      --bounces N     number of visible bounces (0 = no bounce) (default: 4)
      --spring F      bounciness 0=dead, 1=super bouncy    (default: 0.7)
      --sides ORDER   sides letters enter from, cycled:
                      l, r, t, b                           (default: ltrb)
      --angle DEG     turn every entry direction clockwise (default: 0)
      --supersample N compose at N times panel resolution   (default: 4)
  -d, --delay N       per-frame delay in centiseconds       (default: 4)
  -b, --background C  canvas fill colour                  (default: black)
  -q, --quiet         suppress per-letter listing on stderr

  letters-dir  directory split-letters.py filled (default: gfx/out/letters)
  output.gif   file to write          (default: config/gifs/astryx-bounce.gif)

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
DEFAULT_OUT = REPO_ROOT / "config" / "gifs" / "astryx-bounce.gif"

SIDES = "lrtb"


def load_manifest(letters_dir, parser):
    path = letters_dir / "letters.json"
    if not path.is_file():
        parser.error(f"no letters.json in {letters_dir}; run gfx/split-letters.py first")
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        parser.error(f"{path}: {exc}")
    letters = manifest.get("letters") or []
    if not letters:
        parser.error(f"{path} lists no letters")
    for letter in letters:
        if not (letters_dir / letter["file"]).is_file():
            parser.error(f"{path} names {letter['file']}, which is not in {letters_dir}")
    return manifest, letters


def bounce(t, bounces, spring):
    """Bounce profile: t ∈ [0, 1].

    Scales the envelope of bounces down over time using an exponential
    decay. The contact points are at t = 0, 1/(n+1), ..., 1 where n = bounces.
    Between contacts the ball arcs up to a height proportional to the
    remaining energy.
    """
    if bounces <= 0 or t <= 0:
        return 0.0
    if t >= 1:
        return 1.0

    # Position within the travel — 0 = start, 1 = end.
    # We'll use a linear interpolation for the base, then add bounce arcs.
    dt = 1.0 / (bounces + 1)
    # Which bounce phase are we in?
    phase = int(t / dt) if t > 0 else 0
    if phase >= bounces:
        return 1.0

    t_in_phase = (t - phase * dt) / dt
    # Arc height for this bounce — decays exponentially.
    energy = math.exp(-spring * (phase + 1))
    arc = 4 * t_in_phase * (1 - t_in_phase) * energy

    # Interpolate between rest and target, offset by arc.
    base = (phase + 1) * dt + phase * dt  # not quite right
    # Simpler: just the arc offset on a linear ramp
    t_linear = t * (bounces + 1) / bounces if bounces > 0 else t
    # Clamp to [0, 1] and add arc
    result = t_linear + arc
    return min(1.0, max(0.0, result))


def ease_bounce(t, bounces, spring):
    """Complete bounce easing: position 0→1 with bounces.

    Uses a linear progression through bounces, each as a parabola.
    """
    if bounces <= 0:
        return t if 0 <= t <= 1 else (1.0 if t > 1 else 0.0)

    dt = 1.0 / bounces
    phase = min(int(t / dt), bounces - 1) if t < 1 else bounces - 1
    t_in_phase = min((t - phase * dt) / dt, 1.0) if t < 1 else 1.0

    # Energy at this phase
    energy = math.exp(-0.5 * (phase + 1)) * spring
    # Parabolic arc
    arc = 4 * t_in_phase * (1 - t_in_phase) * energy

    # Linear base + arc
    base = (phase + 1) * dt  # where we'd be without arcs
    result = base * (1 - spring) + (base + arc) * spring
    return min(1.0, max(0.0, result))


BASE = {"l": (-1.0, 0.0), "r": (1.0, 0.0), "t": (0.0, -1.0), "b": (0.0, 1.0)}


def turn(vector, degrees):
    theta = math.radians(degrees)
    cos, sin = math.cos(theta), math.sin(theta)
    dx, dy = vector
    return (dx * cos - dy * sin, dx * sin + dy * cos)


def fitted_width(canvas, aspect, degrees):
    theta = math.radians(degrees)
    cos, sin = abs(math.cos(theta)), abs(math.sin(theta))
    return canvas / max(cos + aspect * sin, sin + aspect * cos)


def compass(direction):
    points = ("E", "SE", "S", "SW", "W", "NW", "N", "NE")
    dx, dy = direction
    return points[round(math.degrees(math.atan2(dy, dx)) / 45) % 8]


def entry_point(direction, final, letter_size, canvas):
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
        description="Bounce letters into place.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("letters", nargs="?", type=Path, default=DEFAULT_LETTERS, help="letters directory")
    p.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUT, help="GIF to write")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("-r", "--rotate", type=float, default=0, help="degrees to stand the word at")
    p.add_argument("-w", "--word-width", type=float, default=0, help="word width in pixels")
    p.add_argument("-f", "--frames", type=int, default=25, help="frames per letter flight")
    p.add_argument("--hold", type=int, default=30, help="frames the word is held")
    p.add_argument("--stagger", type=int, default=4, help="frames between letters")
    p.add_argument("--bounces", type=int, default=4, help="number of visible bounces")
    p.add_argument("--spring", type=float, default=0.7, help="bounciness 0=dead, 1=super")
    p.add_argument("--sides", default="ltrb", help="sides letters enter from, cycled")
    p.add_argument("--angle", type=float, default=0, help="turn entry direction clockwise")
    p.add_argument("--supersample", type=int, default=4, help="compose at this multiple of panel resolution")
    p.add_argument("-d", "--delay", type=int, default=4, help="per-frame delay in centiseconds")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress listing")
    args = p.parse_args()

    for err_check in [
        (args.size < 1, f"--size must be positive, got {args.size}"),
        (args.frames < 1, f"--frames must be positive, got {args.frames}"),
        (args.hold < 0, f"--hold must not be negative"),
        (args.stagger < 0, f"--stagger must not be negative"),
        (args.supersample < 1, f"--supersample must be positive"),
        (args.delay < 1, f"--delay must be positive"),
        (not 0 <= args.spring <= 1, f"--spring must be 0..1, got {args.spring}"),
        (not 0 <= args.bounces, f"--bounces must be non-negative"),
    ]:
        if err_check[0]:
            p.error(err_check[1])
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

    _, _, view_w, view_h = manifest["viewBox"]
    word_width = args.word_width or fitted_width(args.size, view_h / view_w, args.rotate)
    scale = word_width / view_w
    word_centre = (word_width / 2, view_h * scale / 2)
    canvas_centre = (args.size / 2, args.size / 2)

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
                sprite = sprite.rotate(-args.rotate, resample=Image.BICUBIC, expand=True)

            middle = ((bx + bw / 2) * scale, (by + bh / 2) * scale)
            offset = turn((middle[0] - word_centre[0], middle[1] - word_centre[1]), args.rotate)
            raster = (sprite.width / ss, sprite.height / ss) if not args.rotate else (
                sprite.width / ss, sprite.height / ss)
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
            if t <= 0:
                continue
            if t >= 1:
                progress = 1.0
            else:
                progress = ease_bounce(t, args.bounces, args.spring)
            x = start[0] + (final[0] - start[0]) * progress
            y = start[1] + (final[1] - start[1]) * progress
            canvas.alpha_composite(sprite, (round(x * ss), round(y * ss)))
        frames.append(canvas.resize((args.size, args.size), Image.BOX).convert("RGB"))

    palette = frames[-1].quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(args.output, save_all=True, append_images=quantized[1:],
                      duration=args.delay * 10, loop=0, disposal=1, optimize=False)

    with Image.open(args.output) as written:
        stored = written.n_frames

    print(f"Wrote {args.output} ({total} frames at {args.delay}cs = "
          f"{total * args.delay / 100:.1f}s, {travel} in flight + {args.hold} held, "
          f"word {word_width:.1f}x{view_h * scale:.1f}px"
          f"{f' at {args.rotate:g}°' if args.rotate else ''}, "
          f"{len(flights)} letters {args.bounces} bounces spring={args.spring}, "
          f"{stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
