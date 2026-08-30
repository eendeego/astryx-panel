#!/usr/bin/env python3
"""make-wipe.py — reveal the mark with a sweeping edge.

A straight edge (or curved one) sweeps across the canvas, revealing the
mark beneath. --direction controls which way it sweeps; --curve bends the
wipe front into an arc (0 = straight, 1 = half-circle).

Usage:
  ./make-wipe.py [options] [input.svg] [output.gif]

  -d, --direction DIR  wipe direction: l2r, r2l, t2b, b2t
                       (default: l2r)
      --curve F        arc curvature 0 = straight, 1 = half-circle
                         (default: 0)
  -f, --frames N       frames of travel                (default: 25)
  -s, --size N         canvas is NxN pixels            (default: 64)
      --supersample N  render at N× panel resolution    (default: 4)
  -c, --fill COLOR     mark colour                     (default: blue)
  -b, --background C   canvas fill colour              (default: black)
      --delay N        per-frame delay in centiseconds  (default: 4)
  -q, --quiet          suppress per-frame listing       (default: off)

  input.svg   source mark           (default: gfx/raw/astryx.svg)
  output.gif  file to write  (default: config/gifs/astryx-wipe.gif)

Missing parent directories are created for the GIF.
"""

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

GFX_DIR = Path(__file__).resolve().parent
REPO_ROOT = GFX_DIR.parent
DEFAULT_SVG = GFX_DIR / "raw" / "astryx.svg"
OUT_DIR = REPO_ROOT / "config" / "gifs"

BRAND = "rgb(61, 135, 255)"

PATH_D = (
    "M11.2002 0C14.7347 0.000105757 17.6 2.8654 17.6001 6.3999V11.2002C"
    "17.6002 12.3047 18.4956 13.2002 19.6001 13.2002H20.3999C21.5044 "
    "13.2002 22.3998 12.3047 22.3999 11.2002V6.3999C22.4 2.8654 "
    "25.2653 0.000106275 28.7998 0H37.6001C38.9255 5.15369e-05 "
    "39.9999 1.07451 40 2.3999V11.2002C39.9999 14.7347 37.1346 17.6 "
    "33.6001 17.6001H28.7998C27.6953 17.6002 26.7998 18.4956 "
    "26.7998 19.6001V20.3999C26.7998 21.5044 27.6953 22.3998 "
    "28.7998 22.3999H33.6001C37.1346 22.4 39.9999 25.2653 40 "
    "28.7998V37.6001C40 38.9255 38.9255 39.9999 37.6001 40H28.7998C"
    "25.2653 39.9999 22.3999 37.1346 22.3999 33.6001V28.7998C"
    "22.3998 27.6953 21.5044 26.7998 20.3999 26.7998H19.6001C"
    "18.4956 26.7998 17.6002 27.6953 17.6001 28.7998V33.6001C"
    "17.6001 37.1346 14.7347 39.9999 11.2002 40H2.39991C1.07449 "
    "39.9999 3.97232e-05 38.9255 0 37.6001V28.7998C0.000118127 "
    "25.2653 2.86539 22.4 6.3999 22.3999H11.2002C12.3047 22.3998 "
    "13.2002 21.5044 13.2002 20.3999V19.6001C13.2002 18.4956 "
    "12.3047 17.6002 11.2002 17.6001H6.3999C2.86538 17.6 "
    "9.39063e-05 14.7347 0 11.2002V2.3999C6.46793e-05 1.07451 "
    "1.07451 5.28641e-05 2.39991 0H11.2002Z"
)

DIR_VECTORS = {
    "l2r": ("x", 1),   # sweep along x from left to right
    "r2l": ("x", -1),
    "t2b": ("y", 1),   # sweep along y from top to bottom
    "b2t": ("y", -1),
}


def main():
    p = argparse.ArgumentParser(
        description="Wipe-reveal the logo mark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG, help="source mark")
    p.add_argument("output", nargs="?", type=Path, help="GIF to write (default: config/gifs/astryx-wipe.gif)")
    p.add_argument("-d", "--direction", choices=list(DIR_VECTORS), default="l2r",
                   help="wipe direction")
    p.add_argument("--curve", type=float, default=0, help="arc curvature 0=straight, 1=half-circle")
    p.add_argument("-f", "--frames", type=int, default=25, help="frames of travel")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("--supersample", type=int, default=4, help="render at this multiple of panel resolution")
    p.add_argument("-c", "--fill", default=BRAND, help="mark colour")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("--delay", type=int, default=4, help="per-frame delay in centiseconds")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress per-frame listing")
    args = p.parse_args()

    if args.size < 1:
        p.error(f"--size must be positive, got {args.size}")
    if args.frames < 1:
        p.error(f"--frames must be positive, got {args.frames}")
    if args.supersample < 1:
        p.error(f"--supersample must be positive, got {args.supersample}")
    if args.delay < 1:
        p.error(f"--delay must be positive, got {args.delay}")
    if not args.svg.is_file():
        p.error(f"no such file: {args.svg}")
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found (brew install librsvg)")

    for name in ("fill", "background"):
        try:
            setattr(args, f"{name}_rgb", ImageColor.getrgb(getattr(args, name)))
        except ValueError as exc:
            p.error(f"--{name}: {exc}")
    if args.output is None:
        args.output = OUT_DIR / "astryx-wipe.gif"

    render_size = args.size * args.supersample
    sign = DIR_VECTORS[args.direction][1]

    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for f in range(args.frames):
            # The wipe front position 0..1
            pos = f / (args.frames - 1) if args.frames > 1 else 1

            # Render the mark.
            svg_content = (
                f'<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
                f'<g fill="{args.fill}"><path d="{PATH_D}"/></g></svg>'
            )
            mark_png = Path(tmp) / "mark.png"
            proc = subprocess.run(
                ["rsvg-convert", "-w", str(render_size), "-h", str(render_size), "-", "-o", str(mark_png)],
                input=svg_content, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                sys.exit(f"rsvg-convert failed: {proc.stderr.strip()}")

            with Image.open(mark_png) as img:
                mark = img.convert("RGBA")

            # Build the wipe mask.
            mask = Image.new("L", (render_size, render_size), 0)
            draw = ImageDraw.Draw(mask)

            if DIR_VECTORS[args.direction][0] == "x":
                # Horizontal sweep: the wipe edge is a vertical line at x = pos * width
                wipe_x = int(pos * render_size)
                if sign > 0:
                    # Left to right: left side is revealed (white), right is masked (black)
                    if wipe_x > 0:
                        draw.rectangle([0, 0, min(wipe_x - 1, render_size - 1), render_size - 1], 255)
                    # Apply curve: the wipe front is an arc bulging right
                    if args.curve > 0:
                        for y in range(render_size):
                            # Parabolic bulge: the edge at each y is shifted right
                            y_rel = (y - render_size / 2) / (render_size / 2)
                            bulge = int(args.curve * render_size / 4 * (1 - y_rel * y_rel))
                            dx = wipe_x + bulge
                            if dx > 0:
                                draw.rectangle([0, y, min(dx, render_size - 1), y], 255)
                            dx_left = wipe_x - int(args.curve * render_size / 4 * (1 - y_rel * y_rel))
                            if dx_left < 0:
                                draw.rectangle([0, y, render_size - 1, y], 255)
                else:
                    # Right to left
                    if wipe_x < render_size:
                        draw.rectangle([wipe_x, 0, render_size - 1, render_size - 1], 255)
                    if args.curve > 0:
                        for y in range(render_size):
                            y_rel = (y - render_size / 2) / (render_size / 2)
                            bulge = int(args.curve * render_size / 4 * (1 - y_rel * y_rel))
                            dx_left = wipe_x - bulge
                            if dx_left < render_size:
                                draw.rectangle([max(0, dx_left), y, render_size - 1, y], 255)
                            dx = wipe_x + int(args.curve * render_size / 4 * (1 - y_rel * y_rel))
                            if dx >= render_size:
                                draw.rectangle([0, y, render_size - 1, y], 255)
            else:
                # Vertical sweep
                wipe_y = int(pos * render_size)
                if sign > 0:
                    if wipe_y > 0:
                        draw.rectangle([0, 0, render_size - 1, min(wipe_y - 1, render_size - 1)], 255)
                    if args.curve > 0:
                        for x in range(render_size):
                            x_rel = (x - render_size / 2) / (render_size / 2)
                            bulge = int(args.curve * render_size / 4 * (1 - x_rel * x_rel))
                            dy = wipe_y + bulge
                            if dy > 0:
                                draw.rectangle([x, 0, x, min(dy, render_size - 1)], 255)
                else:
                    if wipe_y < render_size:
                        draw.rectangle([0, wipe_y, render_size - 1, render_size - 1], 255)
                    if args.curve > 0:
                        for x in range(render_size):
                            x_rel = (x - render_size / 2) / (render_size / 2)
                            bulge = int(args.curve * render_size / 4 * (1 - x_rel * x_rel))
                            dy = wipe_y - bulge
                            if dy < render_size:
                                draw.rectangle([x, max(0, dy), x, render_size - 1], 255)

            # Composite: where mask is white, show the mark.
            flat = Image.new("RGBA", (render_size, render_size), args.background_rgb + (255,))
            flat.paste(mark, (0, 0), mask)

            frames.append(flat.resize((args.size,) * 2, Image.BOX).convert("RGB"))

            if not args.quiet:
                print(f"  frame {f + 1}/{args.frames}  progress={pos:.2%}  {args.direction}", file=sys.stderr)

    richest = max(frames, key=lambda f: len(f.getcolors(maxcolors=1 << 16) or [1]))
    palette = richest.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        args.output, save_all=True, append_images=quantized[1:],
        duration=args.delay * 10, loop=0, disposal=1, optimize=False,
    )

    with Image.open(args.output) as written:
        stored = written.n_frames

    total_s = len(frames) * args.delay / 100
    print(f"Wrote {args.output} ({len(frames)} frames at {args.delay}cs = {total_s:.1f}s, "
          f"{args.direction} curve={args.curve}, {stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
