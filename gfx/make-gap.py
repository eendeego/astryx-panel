#!/usr/bin/env python3
"""make-gap.py — rasterize an SVG logo into a WLED gap file.

The 64x64 HUB75 panel sits behind a physical mask cut in the shape of the
logo. The mask material is slightly see-through, so the LEDs behind it
glow faintly instead of staying dark. A gap file switches those LEDs off
for good.

The SVG is rasterized with rsvg-convert at the panel resolution, and the
resulting coverage (0..255, antialiased edges included) is thresholded:
every pixel at or above -t/--threshold becomes 1 (regular pixel), the
rest become 0 (never paint). Use -n/--negative when it is the *other*
side of the shape that sits behind the mask.

WLED also defines -1 (pixel physically missing) for gap files. A solid
rectangular panel has no missing pixels, so this script never emits it.

Firmware caveat: WLED 16.0.1 acts on the inverse of the documented
meaning — on that build the entries written as 1 are the ones left dark,
and the 0s are the ones painted. This script emits the documented
polarity, so on 16.0.1 the file has to be authored "backwards": the
tested invocation (see README.md) leaves the logo shape at 0 and the
surrounding ground at 1, which is what actually lights the shape and
blanks the masked area on that firmware. Assumed to be a bug; if a later
release corrects it, flip the polarity back by adding -n/--negative.

Usage:
  ./make-gap.py [options] [input.svg] [output.json]

  -t, --threshold N   coverage at or above N becomes 1  (default: 128)
  -n, --negative      invert the result: shape becomes 0, ground becomes 1
  -s, --size N        panel is NxN pixels                (default: 64)
      --channel C     coverage source: auto|alpha|luma   (default: auto)
  -a, --keep-aspect-ratio
                      letterbox a non-square SVG instead of stretching it
  -b, --background C  render onto this background instead of transparent
      --png FILE      also write the thresholded mask as a PNG, to eyeball
  -q, --quiet         suppress the ASCII preview on stderr

  input.svg   source logo   (default: gfx/raw/astryx.svg)
  output.json gap file      (default: gfx/out/astryx-gap.json)

Generated files land in gfx/out/, which is not versioned. Missing parent
directories are created for both the gap file and --png.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

GFX_DIR = Path(__file__).resolve().parent
DEFAULT_SVG = GFX_DIR / "raw" / "astryx.svg"
DEFAULT_OUT = GFX_DIR / "out" / "astryx-gap.json"


def rasterize(svg, size, keep_aspect_ratio, background, dest):
    """Render `svg` to a size x size PNG at `dest` via rsvg-convert."""
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found (brew install librsvg)")

    cmd = ["rsvg-convert", "-w", str(size), "-h", str(size)]
    if keep_aspect_ratio:
        cmd.append("--keep-aspect-ratio")
    if background:
        cmd += ["-b", background]
    cmd += [str(svg), "-o", str(dest)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"rsvg-convert failed: {proc.stderr.strip()}")


def coverage(png, size, channel):
    """Return a size x size list of rows of 0..255 shape coverage.

    "auto" prefers the alpha channel, which is what carries the shape when
    the SVG paints onto a transparent background — the usual case, and the
    one where luminance would see a black shape on black. It falls back to
    luminance for a fully opaque render.
    """
    img = Image.open(png).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)

    alpha = img.getchannel("A")
    if channel == "auto":
        channel = "alpha" if alpha.getextrema()[0] < 255 else "luma"

    band = alpha if channel == "alpha" else img.convert("RGB").convert("L")
    px = band.tobytes()
    rows = [list(px[y * size:(y + 1) * size]) for y in range(size)]
    return rows, channel


def threshold(rows, t, negative):
    """Map 0..255 coverage to WLED 1 (regular) / 0 (never paint).

    Documented polarity — WLED 16.0.1 acts on its inverse; see the module
    docstring before changing this or the invocation in README.md.
    """
    return [[1 if (v >= t) != negative else 0 for v in row] for row in rows]


def dump_json(grid, path):
    """Write the flattened grid as a JSON array, one matrix row per line."""
    body = ",\n".join(",".join(str(v) for v in row) for row in grid)
    path.write_text(f"[\n{body}\n]\n")


def dump_png(grid, path):
    data = bytes(255 * v for row in grid for v in row)
    Image.frombytes("L", (len(grid[0]), len(grid)), data).save(path)


def preview(grid):
    """Draw the mask on stderr, two characters per pixel so it stays square."""
    for row in grid:
        print("".join("##" if v else ".." for v in row), file=sys.stderr)


def main():
    p = argparse.ArgumentParser(
        description="Rasterize an SVG logo into a WLED gap file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG,
                   help="source SVG")
    p.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUT,
                   help="gap file to write")
    p.add_argument("-t", "--threshold", type=int, default=128,
                   help="coverage at or above this becomes 1")
    p.add_argument("-n", "--negative", action="store_true",
                   help="invert: shape becomes 0, ground becomes 1")
    p.add_argument("-s", "--size", type=int, default=64,
                   help="panel edge in pixels")
    p.add_argument("--channel", choices=("auto", "alpha", "luma"),
                   default="auto", help="which channel carries the shape")
    p.add_argument("-a", "--keep-aspect-ratio", action="store_true",
                   help="letterbox a non-square SVG instead of stretching")
    p.add_argument("-b", "--background", metavar="COLOR",
                   help="render onto this background instead of transparent")
    p.add_argument("--png", type=Path, help="also write the mask as a PNG")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the ASCII preview")
    args = p.parse_args()

    if not 0 <= args.threshold <= 255:
        p.error(f"--threshold must be in 0..255, got {args.threshold}")
    if args.size < 1:
        p.error(f"--size must be positive, got {args.size}")
    if not args.svg.is_file():
        p.error(f"no such file: {args.svg}")

    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "logo.png"
        rasterize(args.svg, args.size, args.keep_aspect_ratio,
                  args.background, png)
        rows, used = coverage(png, args.size, args.channel)

    grid = threshold(rows, args.threshold, args.negative)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dump_json(grid, args.output)
    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        dump_png(grid, args.png)
    if not args.quiet:
        preview(grid)

    on = sum(sum(row) for row in grid)
    total = args.size * args.size
    print(f"Wrote {args.output} ({total} entries, {on} on / {total - on} off, "
          f"threshold={args.threshold}, channel={used}"
          f"{', negative' if args.negative else ''})")


if __name__ == "__main__":
    main()
