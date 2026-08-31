#!/usr/bin/env python3
"""retime.py — set a GIF's total running time exactly.

The panel's animations are all meant to run for the same length, so that
a playlist slot holds a whole number of passes. Most of them get there by
choosing a frame count: at 4cs a frame, 125 frames is 5 seconds. A
marquee cannot — its frame count is its geometry, one frame per pixel of
travel — so its delays have to be adjusted instead.

Delays are scaled, not equalized. A GIF that holds still for a while
stores that as one frame with a long delay (Pillow merges runs of
identical frames and sums their delays), and spreading the target evenly
over the stored frames would flatten the hold into an ordinary frame.
Scaling keeps every pause the same fraction of the whole.

Rounding is cumulative, so the delays add up to exactly the target rather
than to within a centisecond of it. What is left is frames a centisecond
apart — 10 ms at 25 fps, which nothing can see.

The frames themselves are untouched: they are read and written back in
their own palettes, never converted, so nothing is requantized. A file
already running to time is left alone.

Usage:
  ./retime.py [options] file.gif [file.gif ...]

  -t, --seconds N   running time to hit, in seconds        (default: 5)
  -q, --quiet       say nothing about files already to time
  -h, --help        show this help
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageSequence


def spread(delays, target):
    """Scale `delays` (centiseconds) so they sum to exactly `target`.

    Each frame keeps its share of the running time. Rounding the running
    total rather than each delay is what makes the sum come out exact:
    the error never accumulates past one centisecond.
    """
    current = sum(delays)
    out, cumulative, placed = [], 0, 0
    for delay in delays:
        cumulative += delay
        want = round(cumulative * target / current)
        out.append(max(1, want - placed))
        placed += out[-1]
    # clamping at 1cs, on a frame that scaled to nothing, can leave the sum
    # short or long; the last frame absorbs whatever is left over
    out[-1] = max(1, out[-1] + target - sum(out))
    return out


def retime(path, target, quiet):
    """Rewrite path's delays to total `target` centiseconds. -> changed?"""
    with Image.open(path) as im:
        frames = [f.copy() for f in ImageSequence.Iterator(im)]
        delays = [f.info.get("duration", 0) or 10 for f in ImageSequence.Iterator(im)]
    delays = [d // 10 for d in delays]  # GIF stores centiseconds; Pillow reports ms

    if target < len(frames):
        sys.exit(f"{path}: {len(frames)} frames cannot fit in {target}cs "
                 f"at one centisecond each")
    if sum(delays) == target:
        if not quiet:
            print(f"{path} already runs {target / 100:g}s ({len(frames)} frames)")
        return False

    was = sum(delays)
    delays = spread(delays, target)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=[d * 10 for d in delays], loop=0, disposal=1,
                   optimize=False)
    lo, hi = min(delays), max(delays)
    span = f"{lo}cs" if lo == hi else f"{lo}-{hi}cs"
    print(f"Retimed {path} ({len(frames)} frames, {was / 100:g}s -> "
          f"{target / 100:g}s, delays {span})")
    return True


def main():
    p = argparse.ArgumentParser(
        description="Set a GIF's total running time exactly.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("gifs", nargs="+", type=Path, metavar="file.gif",
                   help="GIFs to retime in place")
    p.add_argument("-t", "--seconds", type=float, default=5,
                   help="running time to hit")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="say nothing about files already to time")
    args = p.parse_args()

    if args.seconds <= 0:
        p.error(f"--seconds must be positive, got {args.seconds}")
    target = round(args.seconds * 100)
    if abs(target - args.seconds * 100) > 1e-9:
        p.error(f"--seconds must land on a whole centisecond, got {args.seconds}")
    for gif in args.gifs:
        if not gif.is_file():
            p.error(f"no such file: {gif}")

    for gif in args.gifs:
        retime(gif, target, args.quiet)


if __name__ == "__main__":
    main()
