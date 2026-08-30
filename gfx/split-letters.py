#!/usr/bin/env python3
"""split-letters.py — cut the wordmark SVG into one SVG per letter.

gfx/raw/astryx-word.svg draws the whole word as a single <path>, so the
letters are only subpaths of one "d" attribute. This splits that "d" at
its moveto commands, measures what each subpath covers, reunites the
counters (the hole in the A, the hole in the R) with the letter they
belong to, and writes each letter as a standalone SVG. That is the input
for animating letters independently.

Subpaths are measured by rendering: each one is rasterized on its own at
-r/--resolution pixels per user unit and the ink is measured with Pillow.
That costs one rsvg-convert call per subpath, but it accounts for curve
extrema, which reading the control points out of the path data does not.

A subpath whose bounds sit inside another's is treated as a counter of
that one. Counters stay in their letter's "d", in their original order,
so each letter renders exactly as it does in the wordmark — the fill rule
still sees the outline and its hole as one path.

By default each letter gets a viewBox tight around its own ink, so
rendering it at a given width yields just that letter. -k/--keep-canvas
keeps the wordmark's viewBox instead, which renders each letter in the
place it occupies in the word. Either way letters.json records where
every letter sits in the original, so the word can be reassembled.

Usage:
  ./split-letters.py [options] [input.svg] [outdir]

  -l, --labels TEXT   name the letters after these characters
                      (default: the source's aria-label)
  -r, --resolution N  px per user unit when measuring     (default: 4)
  -p, --padding N     user units to add around each letter (default: 0)
  -k, --keep-canvas   give every letter the wordmark viewBox instead of
                      one tight around it
  -q, --quiet         suppress the per-letter listing on stderr

  input.svg   source wordmark  (default: gfx/raw/astryx-word.svg)
  outdir      directory to fill (default: gfx/out/letters)

Written into outdir: one SVG per letter, named <NN>-<label>.svg in
left-to-right order, plus letters.json. Existing files of that name are
overwritten; unrelated files are left alone. outdir is created if needed.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

GFX_DIR = Path(__file__).resolve().parent
REPO_ROOT = GFX_DIR.parent
DEFAULT_SVG = GFX_DIR / "raw" / "astryx-word.svg"
DEFAULT_OUT = GFX_DIR / "out" / "letters"

SVG_NS = "http://www.w3.org/2000/svg"
SVG = f"{{{SVG_NS}}}"

# Elements that carry no geometry, and so can be ignored rather than
# refused. Anything else drawable would be silently dropped, which is
# worse than stopping.
IGNORED = {f"{SVG}title", f"{SVG}desc", f"{SVG}metadata"}

# Root attributes worth carrying over to each letter. viewBox and
# aria-label are rewritten per letter; the rest would only confuse a
# single-letter file.
CARRIED = ("fill", "fill-rule", "fill-opacity", "stroke", "stroke-width")

TEMPLATE = """<svg
  viewBox="{viewbox}"
{attrs}  xmlns="{ns}"
  role="img"
  aria-label="{label}">
  <path d="{d}"/>
</svg>
"""


def parse_source(path):
    """Return (root attributes, viewBox 4-tuple, list of subpath strings)."""
    from xml.etree import ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        sys.exit(f"{path}: not parseable as XML: {exc}")
    if root.tag != f"{SVG}svg":
        sys.exit(f"{path}: root element is {root.tag}, expected an <svg>")

    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) != 4:
        sys.exit(f"{path}: need a viewBox with four numbers, got {root.get('viewBox')!r}")
    try:
        viewbox = tuple(float(v) for v in box)
    except ValueError:
        sys.exit(f"{path}: viewBox is not numeric: {root.get('viewBox')!r}")
    if viewbox[2] <= 0 or viewbox[3] <= 0:
        sys.exit(f"{path}: viewBox has no area: {root.get('viewBox')!r}")

    subpaths = []
    for el in root.iter():
        if el is root or el.tag in IGNORED:
            continue
        if el.tag != f"{SVG}path":
            sys.exit(f"{path}: don't know how to split {el.tag}, only <path>")
        extra = set(el.attrib) - {"d"}
        if extra:
            # A per-path fill or transform would have to be applied to
            # the letters it covers; refuse rather than lose it.
            sys.exit(f"{path}: <path> carries {sorted(extra)}, only 'd' is handled")
        subpaths += split_subpaths(el.get("d") or "", path)

    if not subpaths:
        sys.exit(f"{path}: no path data found")
    return {k: v for k, v in root.attrib.items() if k in CARRIED}, viewbox, subpaths


NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def num(v):
    """Format a coordinate without inventing or losing precision."""
    return f"{v:.6f}".rstrip("0").rstrip(".") or "0"


def split_subpaths(d, path):
    """Cut a path's "d" at its movetos, each rewritten to start absolute.

    M and m only ever appear as commands — a number cannot contain
    either, exponents being written with e — so every occurrence starts a
    subpath. A subpath that opens with a relative m, as the counter of
    the A does, begins wherever the previous one left off, which is its
    own start point when that one closed with z. Rewriting those to an
    absolute M is what makes the pieces independent of each other.
    """
    chunks = [c.strip() for c in re.split(r"(?=[Mm])", d) if c.strip()]
    if chunks and not chunks[0].startswith(("M", "m")):
        sys.exit(f"{path}: path data does not start with a moveto")

    out = []
    start = None  # where the subpath being read began, once it is known
    for n, chunk in enumerate(chunks):
        relative = chunk.startswith("m")
        body = chunk[1:]
        pair = list(NUMBER.finditer(body))[:2]
        if len(pair) != 2:
            sys.exit(f"{path}: subpath {n + 1} has no moveto coordinates")
        x, y = (float(m.group()) for m in pair)
        rest = body[pair[1].end():]

        if relative and n > 0:
            # A leading m on the first subpath is absolute per the spec;
            # any later one needs the point the last subpath ended on.
            if start is None:
                sys.exit(f"{path}: subpath {n + 1} starts with a relative moveto, but "
                         f"subpath {n} does not close with z, so its end is unknown")
            x, y = start[0] + x, start[1] + y

        # Coordinate pairs following a moveto are implicit linetos, and
        # they were relative when the moveto was. Say so explicitly, now
        # that the moveto in front of them is not.
        if relative and NUMBER.match(rest.lstrip(" ,\t\r\n")):
            rest = "l" + rest

        out.append(f"M{num(x)} {num(y)}{rest}")
        start = (x, y) if chunk.rstrip().endswith(("z", "Z")) else None
    return out


def render(svg_text, width, height, dest):
    """Rasterize svg_text to dest at width x height."""
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as fh:
        fh.write(svg_text)
        src = fh.name
    try:
        proc = subprocess.run(
            ["rsvg-convert", "-w", str(width), "-h", str(height), src, "-o", str(dest)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.exit(f"rsvg-convert failed: {proc.stderr.strip()}")
    finally:
        Path(src).unlink(missing_ok=True)


def ink_bounds(subpaths, attrs, viewbox, resolution, tmp):
    """Measure each subpath, in user units, as (x0, y0, x1, y1)."""
    vx, vy, vw, vh = viewbox
    width, height = max(1, round(vw * resolution)), max(1, round(vh * resolution))
    png = Path(tmp) / "subpath.png"
    bounds = []

    for i, d in enumerate(subpaths):
        render(build_svg(d, viewbox, attrs, str(i)), width, height, png)
        with Image.open(png) as img:
            box = img.convert("RGBA").getchannel("A").getbbox()
        if box is None:
            sys.exit(f"subpath {i + 1} renders nothing; cannot place it")
        # Grow by a pixel before converting back: antialiasing puts the
        # edge of the shape inside the outermost lit pixel.
        left, top, right, bottom = box
        bounds.append((
            max(vx, vx + (left - 1) / resolution),
            max(vy, vy + (top - 1) / resolution),
            min(vx + vw, vx + (right + 1) / resolution),
            min(vy + vh, vy + (bottom + 1) / resolution),
        ))
    return bounds


def group_letters(bounds, tolerance):
    """Group subpath indices into letters, counters folded into their letter.

    Returns a list of index lists, ordered left to right, each holding
    one outline first and then whatever sits inside it, in the order the
    source drew them.
    """
    def inside(inner, outer):
        return (outer[0] - tolerance <= inner[0] and outer[1] - tolerance <= inner[1]
                and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)

    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    # Each subpath belongs to the smallest box that contains it, if any.
    # Smallest, so an island inside a counter lands on the counter and
    # walks up from there rather than jumping to the outline.
    parent = [None] * len(bounds)
    for i, box in enumerate(bounds):
        candidates = [j for j, other in enumerate(bounds)
                      if j != i and inside(box, other) and area(other) > area(box)]
        if candidates:
            parent[i] = min(candidates, key=lambda j: area(bounds[j]))

    def outline_of(i):
        seen = {i}
        while parent[i] is not None:
            i = parent[i]
            if i in seen:  # a containment cycle should be impossible
                sys.exit("subpath containment is circular; cannot group letters")
            seen.add(i)
        return i

    letters = {}
    for i in range(len(bounds)):
        letters.setdefault(outline_of(i), []).append(i)
    return sorted(letters.values(), key=lambda members: bounds[members[0]][0])


def verify(subpaths, attrs, viewbox, resolution, source, tmp):
    """Check the rewritten subpaths still draw the original wordmark.

    Splitting turns relative movetos into absolute ones, so the letters
    are not quite the bytes the source held. Draw them all back onto the
    source canvas and compare with the source itself; a counter attached
    to the wrong letter, or a moveto rebased wrongly, shows up here.
    """
    vw, vh = viewbox[2], viewbox[3]
    width, height = max(1, round(vw * resolution)), max(1, round(vh * resolution))
    before, after = Path(tmp) / "before.png", Path(tmp) / "after.png"

    render(source.read_text(), width, height, before)
    render(build_svg("".join(subpaths), viewbox, attrs, "check"), width, height, after)

    from PIL import ImageChops
    with Image.open(before) as a, Image.open(after) as b:
        if a.size != b.size:
            sys.exit(f"verification render is {b.size}, source is {a.size}")
        a, b = a.convert("RGBA"), b.convert("RGBA")
        # Compare coverage, and colour flattened onto an opaque backdrop.
        # The raw RGB of a transparent pixel is free to be anything, so
        # differencing it straight would report noise nobody can see.
        opaque = Image.new("RGBA", a.size, (255, 255, 255, 255))
        worst = max(
            ImageChops.difference(a.getchannel("A"), b.getchannel("A")).getextrema()[1],
            max(ImageChops.difference(Image.alpha_composite(opaque, a),
                                      Image.alpha_composite(opaque, b))
                .convert("L").getextrema()),
        )
    # Rounding a coordinate can shift an antialiased edge by a hair; a
    # subpath left out or hung on the wrong letter cannot hide in that.
    if worst > 8:
        sys.exit(f"the split letters do not redraw {source}: differs by {worst}/255")


def build_svg(d, viewbox, attrs, label):
    box = " ".join(f"{v:g}" for v in viewbox)
    lines = "".join(f'  {k}="{v}"\n' for k, v in attrs.items())
    label = label.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return TEMPLATE.format(viewbox=box, attrs=lines, ns=SVG_NS, label=label, d=d)


def main():
    p = argparse.ArgumentParser(
        description="Cut a wordmark SVG into one SVG per letter.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG,
                   help="source wordmark")
    p.add_argument("outdir", nargs="?", type=Path, default=DEFAULT_OUT,
                   help="directory to fill")
    p.add_argument("-l", "--labels", metavar="TEXT",
                   help="name the letters after these characters "
                        "(default: the source's aria-label)")
    p.add_argument("-r", "--resolution", type=float, default=4,
                   help="px per user unit when measuring subpaths")
    p.add_argument("-p", "--padding", type=float, default=0,
                   help="user units to add around each letter")
    p.add_argument("-k", "--keep-canvas", action="store_true",
                   help="give every letter the wordmark viewBox")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the per-letter listing")
    args = p.parse_args()

    if args.resolution <= 0:
        p.error(f"--resolution must be positive, got {args.resolution}")
    if args.padding < 0:
        p.error(f"--padding must not be negative, got {args.padding}")
    if args.padding and args.keep_canvas:
        p.error("--padding has nothing to pad with --keep-canvas: the viewBox "
                "is the whole wordmark either way")
    if not args.svg.is_file():
        p.error(f"no such file: {args.svg}")
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found (brew install librsvg)")

    attrs, viewbox, subpaths = parse_source(args.svg)
    with tempfile.TemporaryDirectory() as tmp:
        bounds = ink_bounds(subpaths, attrs, viewbox, args.resolution, tmp)
        verify(subpaths, attrs, viewbox, args.resolution, args.svg, tmp)

    letters = group_letters(bounds, tolerance=1 / args.resolution)
    if sorted(i for members in letters for i in members) != list(range(len(subpaths))):
        sys.exit("grouping lost or duplicated a subpath; refusing to write")

    from xml.etree import ElementTree as ET
    labels = args.labels
    if labels is None:
        labels = ET.parse(args.svg).getroot().get("aria-label") or ""
    if labels and len(labels) != len(letters):
        message = (f"found {len(letters)} letters but {len(labels)} labels "
                   f"in {labels!r}")
        if args.labels is not None:
            p.error(message)
        print(f"warning: {message}; numbering without labels", file=sys.stderr)
        labels = ""

    args.outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for n, members in enumerate(letters, start=1):
        label = labels[n - 1] if labels else ""
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", label)
        name = f"{n:02d}-{safe}.svg" if safe else f"{n:02d}.svg"

        x0, y0, x1, y1 = bounds[members[0]]
        box = (x0 - args.padding, y0 - args.padding,
               x1 - x0 + 2 * args.padding, y1 - y0 + 2 * args.padding)
        d = "".join(subpaths[i] for i in sorted(members))
        (args.outdir / name).write_text(
            build_svg(d, viewbox if args.keep_canvas else box, attrs, label or str(n)))

        manifest.append({
            "index": n,
            "label": label,
            "file": name,
            "bounds": [round(v, 3) for v in box],
            "subpaths": len(members),
        })
        if not args.quiet:
            print(f"  {name}  at {box[0]:8.3f},{box[1]:7.3f}"
                  f"  {box[2]:8.3f}x{box[3]:<8.3f}"
                  f"  {len(members)} subpath{'s' if len(members) > 1 else ''}",
                  file=sys.stderr)

    source = args.svg.resolve()
    source = source.relative_to(REPO_ROOT) if source.is_relative_to(REPO_ROOT) else source
    report = json.dumps({
        "source": str(source),
        "viewBox": [round(v, 3) for v in viewbox],
        "tight": not args.keep_canvas,
        "letters": manifest,
    }, indent=2)
    # Keep each box on one line; indent=2 would give every number its own.
    report = re.sub(r"\[[\d\s.,eE+-]*\]", lambda m: " ".join(m.group().split()), report)
    (args.outdir / "letters.json").write_text(report + "\n")

    print(f"Wrote {args.outdir} ({len(letters)} letters"
          f"{', ' + ' '.join(labels) if labels else ''}, "
          f"{len(subpaths)} subpaths, "
          f"{'wordmark' if args.keep_canvas else 'tight'} viewBox)")


if __name__ == "__main__":
    main()
