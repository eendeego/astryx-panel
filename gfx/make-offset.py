#!/usr/bin/env python3
"""make-offset.py — walk the logo's outline inward, or run that backwards.

Inward, the mark is held for --hold frames and then its edge steps in:
it thins, comes apart into its four lobes, and they dwindle away to
nothing. Outward is that same run played in reverse — the lobes appear
out of an empty panel, swell, close up into the mark, and it is held.
The two are one animation read in either direction, so they cut together
back to back.

Offsetting is done by stroking, not by any pixel erosion: a stroke sits
centred on the outline, so painting the outline in the background colour
with a stroke twice as wide as the wanted distance eats exactly that
distance into the shape from either side. The counters between the lobes
are handled by the same stroke without any special case, and joins are
round, which is what an offset outline actually is at a corner.

How far there is to go is measured rather than guessed: --depth 0, the
default, renders the shape at trial distances and bisects for the first
one that leaves the panel empty.

Usage:
  ./make-offset.py [options] [input.svg] [output.gif]

  -d, --direction WAY  in to shrink the mark away, out for the same
                       frames in reverse time                 (default: in)
      --depth N        how far to travel, in panel pixels
                             (default: 0, meaning until the panel is empty)
  -s, --size N         canvas is NxN pixels                    (default: 64)
      --scale F        fraction of the canvas the mark spans
                       at rest                                  (default: 1)
  -f, --frames N       frames of travel                        (default: 30)
      --hold N         frames holding the mark, before it goes
                       or after it arrives                     (default: 15)
      --supersample N  render at N times panel resolution        (default: 4)
  -c, --fill COLOR     the mark's colour       (default: rgb(61, 135, 255))
  -b, --background C   canvas fill colour                   (default: black)
      --delay N        per-frame delay in centiseconds          (default: 4)
  -q, --quiet          suppress the per-frame listing on stderr

  input.svg   source mark        (default: gfx/raw/astryx.svg)
  output.gif  file to write
                  (default: config/gifs/astryx-<direction>ward.gif)

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

# gfx/raw/astryx.svg paints with currentColor against a CSS variable that
# rsvg cannot resolve, so it would come out black. The wordmark's own
# fill is the brand blue, and using it here keeps the two in step.
BRAND = "rgb(61, 135, 255)"

SVG_NS = "http://www.w3.org/2000/svg"
IGNORED = {f"{{{SVG_NS}}}title", f"{{{SVG_NS}}}desc", f"{{{SVG_NS}}}metadata"}


def read_shape(path):
    """Return (viewBox 4-tuple, list of path data) from an SVG of paths."""
    from xml.etree import ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        sys.exit(f"{path}: not parseable as XML: {exc}")

    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) != 4:
        sys.exit(f"{path}: need a viewBox with four numbers, got {root.get('viewBox')!r}")
    viewbox = tuple(float(v) for v in box)
    if viewbox[2] <= 0 or viewbox[3] <= 0:
        sys.exit(f"{path}: viewBox has no area: {root.get('viewBox')!r}")

    shapes = []
    for el in root.iter():
        if el is root or el.tag in IGNORED:
            continue
        if el.tag != f"{{{SVG_NS}}}path":
            sys.exit(f"{path}: don't know how to offset {el.tag}, only <path>")
        shapes.append(el.get("d") or "")
    if not shapes:
        sys.exit(f"{path}: no path data found")
    return viewbox, shapes


def build_svg(shapes, viewbox, fill, stroke, width):
    """The shape, optionally with an outline stroked around it."""
    box = " ".join(f"{v:.6g}" for v in viewbox)
    pen = ""
    if width > 0:
        pen = (f' stroke="{stroke}" stroke-width="{width:.6g}"'
               f' stroke-linejoin="round" stroke-linecap="round"')
    paths = "".join(f'<path d="{d}"/>' for d in shapes)
    return (f'<svg viewBox="{box}" xmlns="{SVG_NS}">'
            f'<g fill="{fill}"{pen}>{paths}</g></svg>')


def render(svg_text, size, dest):
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as fh:
        fh.write(svg_text)
        src = fh.name
    try:
        proc = subprocess.run(
            ["rsvg-convert", "-w", str(size), "-h", str(size), src, "-o", str(dest)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.exit(f"rsvg-convert failed: {proc.stderr.strip()}")
    finally:
        Path(src).unlink(missing_ok=True)


class Offsetter:
    """Renders the mark with its outline moved a given distance."""

    def __init__(self, shapes, viewbox, args, tmp):
        self.shapes, self.args, self.tmp = shapes, args, tmp
        self.png = Path(tmp) / "frame.png"

        vx, vy, vw, vh = viewbox
        # Fit the source box into the canvas, shrunk by --scale, and read
        # the canvas back out in the source's own units so that a
        # distance in panel pixels can be turned into a stroke width.
        self.per_unit = args.size * args.scale / max(vw, vh)
        span = args.size / self.per_unit
        self.viewbox = (vx + vw / 2 - span / 2, vy + vh / 2 - span / 2, span, span)

    def at(self, distance):
        """The panel with the outline eaten `distance` pixels inward."""
        render(build_svg(self.shapes, self.viewbox, self.args.fill,
                         self.args.background, 2 * distance / self.per_unit),
               self.args.size * self.args.supersample, self.png)
        with Image.open(self.png) as img:
            frame = img.convert("RGBA")
            flat = Image.new("RGBA", frame.size, self.args.background_rgb + (255,))
            flat.alpha_composite(frame)
            return flat.resize((self.args.size,) * 2, Image.BOX).convert("RGB")


def travelled(frame, background):
    """How much of the panel the mark covers, 0..1."""
    lit = sum(1 for px in frame.get_flattened_data() if px != background)
    return lit / (frame.width * frame.height)


def probe_depth(offsetter, background, quiet):
    """Bisect for the first distance that leaves the panel empty."""
    def empty(distance):
        return travelled(offsetter.at(distance), background) <= 0.0005

    high = 1.0
    limit = 4 * offsetter.args.size
    while not empty(high):
        high *= 2
        if high > limit:
            sys.exit(f"the mark still has ink {limit}px in; give --depth explicitly")
    low = 0.0
    for _ in range(12):
        mid = (low + high) / 2
        low, high = (low, mid) if empty(mid) else (mid, high)
    if not quiet:
        print(f"  measured empty at {high:.2f}px", file=sys.stderr)
    return high


def main():
    p = argparse.ArgumentParser(
        description="Walk the logo's outline inward or outward.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG, help="source mark")
    p.add_argument("output", nargs="?", type=Path,
                   help="GIF to write (default: config/gifs/astryx-<direction>ward.gif)")
    p.add_argument("-d", "--direction", choices=("in", "out"), default="in",
                   help="in shrinks the mark away, out is the same frames reversed")
    p.add_argument("--depth", type=float, default=0,
                   help="how far to travel in panel pixels, 0 to measure it")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("--scale", type=float, default=1.0,
                   help="fraction of the canvas the mark spans at rest")
    p.add_argument("-f", "--frames", type=int, default=30, help="frames of travel")
    p.add_argument("--hold", type=int, default=15,
                   help="frames holding the mark, before it goes or after it arrives")
    p.add_argument("--supersample", type=int, default=4,
                   help="render at this multiple of the panel resolution")
    p.add_argument("-c", "--fill", default=BRAND, help="the mark's colour")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("--delay", type=int, default=4,
                   help="per-frame delay in centiseconds")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the per-frame listing")
    args = p.parse_args()

    if args.size < 1:
        p.error(f"--size must be positive, got {args.size}")
    if not 0 < args.scale <= 1:
        p.error(f"--scale must be in 0..1, got {args.scale}")
    if args.frames < 2:
        p.error(f"--frames must be at least 2, got {args.frames}")
    if args.hold < 0:
        p.error(f"--hold must not be negative, got {args.hold}")
    if args.depth < 0:
        p.error(f"--depth must not be negative, got {args.depth}")
    if args.supersample < 1:
        p.error(f"--supersample must be positive, got {args.supersample}")
    if args.delay < 1:
        p.error(f"--delay must be positive, got {args.delay}")
    if not args.svg.is_file():
        p.error(f"no such file: {args.svg}")
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found (brew install librsvg)")

    # The colours go two ways: into the SVG as written, and into Pillow as
    # numbers. Keep both — handing the parsed tuple back to the SVG makes
    # a fill of "(61, 135, 255)", which renders as nothing at all.
    for name in ("fill", "background"):
        try:
            setattr(args, f"{name}_rgb", ImageColor.getrgb(getattr(args, name)))
        except ValueError as exc:
            p.error(f"--{name}: {exc}")
    if args.output is None:
        args.output = OUT_DIR / f"astryx-{args.direction}ward.gif"

    viewbox, shapes = read_shape(args.svg)
    with tempfile.TemporaryDirectory() as tmp:
        offsetter = Offsetter(shapes, viewbox, args, tmp)
        depth = args.depth or probe_depth(offsetter, args.background_rgb, args.quiet)

        frames = []
        for n in range(args.frames):
            distance = depth * n / (args.frames - 1)
            frame = offsetter.at(distance)
            frames.append(frame)
            if not args.quiet:
                print(f"  frame {n + 1:3}/{args.frames}  {distance:5.2f}px  "
                      f"{travelled(frame, args.background_rgb) * 100:5.1f}% lit",
                      file=sys.stderr)

    # Held mark first, then the shape eating itself away. Outward is that
    # whole run in reverse time, holds included, so the mark arrives and
    # then sits rather than sitting and then leaving.
    frames = [frames[0]] * args.hold + frames
    if args.direction == "out":
        frames.reverse()

    # One palette for the run, taken from the busiest frame; see the same
    # reasoning in make-assemble.py.
    richest = max(frames, key=lambda f: len(f.getcolors(maxcolors=1 << 16) or [1]))
    palette = richest.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(args.output, save_all=True, append_images=quantized[1:],
                      duration=args.delay * 10, loop=0, disposal=1, optimize=False)
    with Image.open(args.output) as written:
        stored = written.n_frames

    order = "held then shrinking" if args.direction == "in" else "growing then held"
    print(f"Wrote {args.output} ({len(frames)} frames at {args.delay}cs = "
          f"{len(frames) * args.delay / 100:.1f}s, {args.hold} held + {args.frames} "
          f"over {depth:.2f}px, {order}, {stored} stored)")


if __name__ == "__main__":
    main()
