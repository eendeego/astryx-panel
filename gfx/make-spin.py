#!/usr/bin/env python3
"""make-spin.py — spin the logo mark.

The mark rotates 360° smoothly and loops. Speed is controlled by how many
frames cover one full rotation; a longer cycle gives a slower, heavier
spin. The mark is held at rest for --hold frames before spinning starts
(0 means jump straight into it), and held at rest again after one full
rotation for --hold-back frames.

Usage:
  ./make-spin.py [options] [input.svg] [output.gif]

  -f, --frames N     frames per full rotation       (default: 30)
      --hold N       frames at rest before spin     (default: 10)
      --hold-back N  frames at rest after spin      (default: 10)
  -s, --size N       canvas is NxN pixels           (default: 64)
      --supersample N render at N× panel resolution  (default: 4)
  -c, --fill COLOR   mark colour                    (default: blue)
  -b, --background C canvas fill colour             (default: black)
      --delay N      per-frame delay in centiseconds (default: 4)
  -q, --quiet        suppress per-frame listing      (default: off)

  input.svg   source mark            (default: gfx/raw/astryx.svg)
  output.gif  file to write  (default: config/gifs/astryx-spin.gif)

Missing parent directories are created for the GIF.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageColor

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


def main():
    p = argparse.ArgumentParser(
        description="Spin the logo mark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG, help="source mark")
    p.add_argument("output", nargs="?", type=Path, help="GIF to write (default: config/gifs/astryx-spin.gif)")
    p.add_argument("-f", "--frames", type=int, default=30, help="frames per full rotation")
    p.add_argument("--hold", type=int, default=10, help="frames at rest before spin")
    p.add_argument("--hold-back", type=int, default=10, help="frames at rest after spin")
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
    if args.hold < 0:
        p.error(f"--hold must not be negative, got {args.hold}")
    if args.hold_back < 0:
        p.error(f"--hold-back must not be negative, got {args.hold_back}")
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
        args.output = OUT_DIR / "astryx-spin.gif"

    render_size = args.size * args.supersample

    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        total = args.hold + args.frames + args.hold_back
        for f in range(total):
            if f < args.hold:
                angle = 0
            elif f < args.hold + args.frames:
                angle = 360 * (f - args.hold) / (args.frames - 1) if args.frames > 1 else 0
            else:
                angle = 360  # same as 0

            # Render at viewBox size, then rotate in Pillow to avoid clipping.
            svg_content = (
                f'<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
                f'<g fill="{args.fill}"><path d="{PATH_D}"/></g></svg>'
            )
            dest = Path(tmp) / f"frame_{f:04d}.png"
            proc = subprocess.run(
                ["rsvg-convert", "-w", str(render_size), "-h", str(render_size), "-", "-o", str(dest)],
                input=svg_content, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                sys.exit(f"rsvg-convert failed: {proc.stderr.strip()}")

            with Image.open(dest) as img:
                sprite = img.convert("RGBA")
            # Rotate around centre with Pillow for unclipped output.
            rotated = sprite.rotate(angle, resample=Image.BICUBIC, expand=True)
            # Centre-pad to render_size × render_size.
            padded = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
            ox = (render_size - rotated.width) // 2
            oy = (render_size - rotated.height) // 2
            padded.alpha_composite(rotated, (ox, oy))

            flat = Image.new("RGBA", padded.size, args.background_rgb + (255,))
            flat.alpha_composite(padded)
            frames.append(flat.resize((args.size,) * 2, Image.BOX).convert("RGB"))

            if not args.quiet:
                phase = "hold" if f < args.hold else "spin" if f < args.hold + args.frames else "back"
                print(f"  frame {f + 1}/{total}  {phase:5s}  angle={angle:.1f}°", file=sys.stderr)

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
          f"{args.hold} hold + {args.frames} spin + {args.hold_back} back, "
          f"{stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
