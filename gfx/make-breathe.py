#!/usr/bin/env python3
"""make-breathe.py — breathe life into the logo mark.

The mark scales up and down on a smooth loop, like breathing or a heartbeat.
It is a single continuous animation: grow → hold peak → shrink → hold rest →
repeat. The timing is controlled by --frames-per-phase and --hold-peak /
--hold-rest to set how long each phase lasts.

Usage:
  ./make-breathe.py [options] [input.svg] [output.gif]

      --min-scale F  smallest scale factor (relative to fit)
                       (default: 0.75)
      --max-scale F  largest scale factor (relative to fit)
                       (default: 1.1)
  -f, --frames N     frames per phase (grow, shrink)
                       (default: 20)
      --hold-peak N  frames at max scale              (default: 5)
      --hold-rest N  frames at min scale              (default: 5)
  -s, --size N       canvas is NxN pixels             (default: 64)
      --supersample N render at N× panel resolution   (default: 4)
  -c, --fill COLOR   mark colour                     (default: blue)
  -b, --background C canvas fill colour              (default: black)
      --delay N      per-frame delay in centiseconds  (default: 4)
  -q, --quiet        suppress per-frame listing       (default: off)

  input.svg   source mark           (default: gfx/raw/astryx.svg)
  output.gif  file to write         (default: config/gifs/astryx-breathe.gif)

Missing parent directories are created for the GIF.
"""

import argparse
import math
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


def read_scale_factor(path):
    """Read the viewBox to compute the mark's intrinsic aspect ratio."""
    from xml.etree import ElementTree as ET

    root = ET.parse(path).getroot()
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) != 4:
        sys.exit(f"{path}: need a viewBox with four numbers, got {root.get('viewBox')!r}")
    vx, vy, vw, vh = (float(v) for v in box)
    return vw, vh


def breathe_factor(t, min_s, max_s):
    """A smooth breathing factor.

    t ∈ [0, 1]: 0 = rest (min), 0.5 = peak (max), 1 = rest again.
    Uses cos for a smooth ease-in-out curve: cos(π·t) goes -1→1.
    """
    return (max_s + min_s) / 2 + (max_s - min_s) / 2 * math.cos(math.pi * t)


def main():
    p = argparse.ArgumentParser(
        description="Breathe the logo mark in and out.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG, help="source mark")
    p.add_argument("output", nargs="?", type=Path, help="GIF to write (default: config/gifs/astryx-breathe.gif)")
    p.add_argument("--min-scale", type=float, default=0.75, help="smallest scale factor")
    p.add_argument("--max-scale", type=float, default=1.1, help="largest scale factor")
    p.add_argument("-f", "--frames", type=int, default=20, help="frames per phase")
    p.add_argument("--hold-peak", type=int, default=5, help="frames at max scale")
    p.add_argument("--hold-rest", type=int, default=5, help="frames at min scale")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("--supersample", type=int, default=4, help="render at this multiple of panel resolution")
    p.add_argument("-c", "--fill", default=BRAND, help="mark colour")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("--delay", type=int, default=4, help="per-frame delay in centiseconds")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress per-frame listing")
    args = p.parse_args()

    if args.size < 1:
        p.error(f"--size must be positive, got {args.size}")
    if args.min_scale <= 0 or args.min_scale > 1:
        p.error(f"--min-scale must be in (0, 1], got {args.min_scale}")
    if args.max_scale < args.min_scale:
        p.error(f"--max-scale must be ≥ --min-scale, got {args.max_scale}")
    if args.frames < 1:
        p.error(f"--frames must be positive, got {args.frames}")
    if args.hold_peak < 0:
        p.error(f"--hold-peak must not be negative, got {args.hold_peak}")
    if args.hold_rest < 0:
        p.error(f"--hold-rest must not be negative, got {args.hold_rest}")
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
        args.output = OUT_DIR / "astryx-breathe.gif"

    vw, vh = read_scale_factor(args.svg)
    span = max(vw, vh)

    with tempfile.TemporaryDirectory() as tmp:
        # Build base SVG with original viewBox
        path_d = 'M11.2002 0C14.7347 0.000105757 17.6 2.8654 17.6001 6.3999V11.2002C17.6002 12.3047 18.4956 13.2002 19.6001 13.2002H20.3999C21.5044 13.2002 22.3998 12.3047 22.3999 11.2002V6.3999C22.4 2.8654 25.2653 0.000106275 28.7998 0H37.6001C38.9255 5.15369e-05 39.9999 1.07451 40 2.3999V11.2002C39.9999 14.7347 37.1346 17.6 33.6001 17.6001H28.7998C27.6953 17.6002 26.7998 18.4956 26.7998 19.6001V20.3999C26.7998 21.5044 27.6953 22.3998 28.7998 22.3999H33.6001C37.1346 22.4 39.9999 25.2653 40 28.7998V37.6001C40 38.9255 38.9255 39.9999 37.6001 40H28.7998C25.2653 39.9999 22.3999 37.1346 22.3999 33.6001V28.7998C22.3998 27.6953 21.5044 26.7998 20.3999 26.7998H19.6001C18.4956 26.7998 17.6002 27.6953 17.6001 28.7998V33.6001C17.6001 37.1346 14.7347 39.9999 11.2002 40H2.39991C1.07449 39.9999 3.97232e-05 38.9255 0 37.6001V28.7998C0.000118127 25.2653 2.86539 22.4 6.3999 22.3999H11.2002C12.3047 22.3998 13.2002 21.5044 13.2002 20.3999V19.6001C13.2002 18.4956 12.3047 17.6002 11.2002 17.6001H6.3999C2.86538 17.6 9.39063e-05 14.7347 0 11.2002V2.3999C6.46793e-05 1.07451 1.07451 5.28641e-05 2.39991 0H11.2002Z'
        base_svg = f'<svg viewBox="0 0 {vw} {vh}" xmlns="http://www.w3.org/2000/svg">' \
                   f'<g fill="{args.fill}"><path d="{path_d}"/></g></svg>'

        # Render once at fixed supersampled size
        rs = args.size * args.supersample
        dest0 = Path(tmp) / "base.png"
        subprocess.run(
            ["rsvg-convert", "-w", str(rs), "-h", str(rs), "-", "-o", str(dest0)],
            input=base_svg.encode(), capture_output=True,
        )
        if subprocess.run(["true"], capture_output=True).returncode != 0:
            pass  # rsvg-convert already checked by shutil.which in CLI
        with Image.open(dest0) as img:
            base = img.convert("RGBA")

        frames = []
        phases = (args.hold_rest, args.frames, args.hold_peak, args.frames, args.hold_rest)
        total = sum(max(0, p) for p in phases)
        idx = 0
        for phase_n, phase_len in enumerate(phases):
            for f in range(phase_len):
                if phase_len == 0:
                    continue
                if phase_n == 0:  # hold rest
                    t = 1.0
                elif phase_n == 1:  # grow
                    t = 1.0 - f / (phase_len - 1) if phase_len > 1 else 1.0
                elif phase_n == 2:  # hold peak
                    t = 0.0
                elif phase_n == 3:  # shrink
                    t = f / (phase_len - 1) if phase_len > 1 else 0.0
                else:  # hold rest again
                    t = 1.0

                scale = breathe_factor(t, args.min_scale, args.max_scale)
                # Scale the mark within the canvas using Pillow (not rsvg)
                scaled = base.resize((int(rs * scale),) * 2, Image.LANCZOS)
                # Centre on the canvas
                bg = Image.new("RGBA", (rs, rs), args.background_rgb + (255,))
                ox = (rs - scaled.width) // 2
                oy = (rs - scaled.height) // 2
                bg.paste(scaled, (ox, oy), scaled)
                # Downscale to panel
                down = bg.resize((args.size,) * 2, Image.BOX).convert("RGB")
                frames.append(down)

                idx += 1
                if not args.quiet:
                    pct = round(scale / args.max_scale * 100)
                    print(f"  frame {idx}/{total}  scale={scale:.3f}  {pct}%", file=sys.stderr)

    richest = max(frames, key=lambda f: len(f.getcolors(maxcolors=1 << 16) or [1]))
    palette = richest.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(args.output, save_all=True, append_images=quantized[1:],
                      duration=args.delay * 10, loop=0, disposal=1, optimize=False)

    with Image.open(args.output) as written:
        stored = written.n_frames

    total_s = len(frames) * args.delay / 100
    print(f"Wrote {args.output} ({len(frames)} frames at {args.delay}cs = {total_s:.1f}s, "
          f"min={args.min_scale:.2f}· max={args.max_scale:.2f}·, "
          f"{stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
