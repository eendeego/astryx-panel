#!/usr/bin/env python3
"""make-glitch.py — occasional digital-glitch effect on the mark.

The mark stays on screen most of the time but periodically gets a "glitch":
horizontal slice displacement, colour channel offset (RGB split), and
sudden full-frame flashes. The glitch probability per frame is controlled
by --glitch-prob; when a glitch fires, it applies one or more of:
slice shift, channel split, and flash.

Usage:
  ./make-glitch.py [options] [input.svg] [output.gif]

  -f, --frames N            total frames                 (default: 60)
      --glitch-prob P       probability of a glitch per frame
                              0=never, 1=always            (default: 0.15)
      --flash-prob P        probability of a white flash on glitch
                              (default: 0.3)
  -s, --size N              canvas is NxN pixels         (default: 64)
      --supersample N       render at N× panel resolution (default: 4)
  -c, --fill COLOR          mark colour                  (default: blue)
  -b, --background C        canvas fill colour           (default: black)
      --delay N             per-frame delay in centiseconds (default: 4)
  -q, --quiet               suppress per-frame listing    (default: off)

  input.svg   source mark              (default: gfx/raw/astryx.svg)
  output.gif  file to write   (default: config/gifs/astryx-glitch.gif)

Missing parent directories are created for the GIF.
"""

import argparse
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageColor, ImageChops, ImageOps

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


def glitch_slice(frame, seed):
    """Cyclically shift horizontal slices — pixels wrap around, no gaps."""
    w, h = frame.size
    result = frame.copy()
    rng = random.Random(seed)
    num_slices = rng.randint(2, 5)
    for _ in range(num_slices):
        y_start = rng.randint(0, h - 2)
        y_end = rng.randint(y_start + 2, h)
        shift = rng.randint(-8, 8)
        if shift == 0:
            continue
        slice_img = frame.crop((0, y_start, w, y_end))
        if shift > 0:
            # Shift right: right part wraps to left
            left_part = slice_img.crop((0, 0, w - shift, h))
            right_part = slice_img.crop((w - shift, 0, w, h))
            padded = Image.new("RGBA", (w, y_end - y_start), (0, 0, 0, 0))
            padded.paste(right_part, (0, 0))
            padded.paste(left_part, (shift, 0))
            result.paste(padded, (0, y_start))
        else:
            # Shift left: left part wraps to right
            abs_shift = -shift
            left_part = slice_img.crop((0, 0, abs_shift, h))
            right_part = slice_img.crop((abs_shift, 0, w, h))
            padded = Image.new("RGBA", (w, y_end - y_start), (0, 0, 0, 0))
            padded.paste(left_part, (w - abs_shift, 0))
            padded.paste(right_part, (0, 0))
            result.paste(padded, (0, y_start))
    return result


def glitch_channels(frame, seed):
    """Shift R, G, B channels by different amounts — no black borders."""
    rng = random.Random(seed)
    r_off = rng.randint(-6, 6)
    g_off = rng.randint(-5, 5)
    b_off = rng.randint(-4, 4)

    if r_off == 0 and g_off == 0 and b_off == 0:
        return frame

    r, g, b, a = frame.split()
    w, h = frame.size

    # Shift each channel by cropping and re-pasting (no black borders)
    def shift_channel(ch, offset):
        if offset == 0:
            return ch
        # Crop shifted region and paste with appropriate padding
        if offset > 0:
            # Shift right: pixels move right, left edge gets background
            left = ch.crop((0, 0, w - offset, h))
            padded = Image.new("L", (w, h), 0)
            padded.paste(left, (offset, 0))
            return padded
        else:
            # Shift left
            left = ch.crop((-offset, 0, w, h))
            padded = Image.new("L", (w, h), 0)
            padded.paste(left, (0, 0))
            return padded

    r_shifted = shift_channel(r, r_off)
    g_shifted = shift_channel(g, g_off)
    b_shifted = shift_channel(b, b_off)
    return Image.merge("RGBA", (r_shifted, g_shifted, b_shifted, a))


def glitch(frame, frame_idx, seed, flash_prob):
    """Apply a single-frame glitch effect."""
    rng = random.Random(seed + frame_idx)

    if rng.random() < flash_prob:
        # Full frame white flash
        return Image.new("RGBA", frame.size, (255, 255, 255, 255)), "flash"

    result = frame.copy()

    if rng.random() < 0.6:
        result = glitch_slice(result, seed + frame_idx + 1)

    if rng.random() < 0.4:
        result = glitch_channels(result, seed + frame_idx + 2)

    return result, "glitch"


def main():
    p = argparse.ArgumentParser(
        description="Add glitch effects to the logo mark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG, help="source mark")
    p.add_argument("output", nargs="?", type=Path, help="GIF to write (default: config/gifs/astryx-glitch.gif)")
    p.add_argument("-f", "--frames", type=int, default=60, help="total frames")
    p.add_argument("--glitch-prob", type=float, default=0.15,
                   help="probability of a glitch per frame")
    p.add_argument("--flash-prob", type=float, default=0.3,
                   help="probability of a flash on a glitch frame")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("--supersample", type=int, default=4, help="render at this multiple of panel resolution")
    p.add_argument("-c", "--fill", default=BRAND, help="mark colour")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("--delay", type=int, default=4, help="per-frame delay in centiseconds")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress per-frame listing")
    args = p.parse_args()

    for err_check in [
        (args.size < 1, f"--size must be positive"),
        (args.frames < 1, f"--frames must be positive"),
        (args.supersample < 1, f"--supersample must be positive"),
        (args.delay < 1, f"--delay must be positive"),
        (not 0 <= args.glitch_prob <= 1, f"--glitch-prob must be 0..1"),
        (not 0 <= args.flash_prob <= 1, f"--flash-prob must be 0..1"),
    ]:
        if err_check[0]:
            p.error(err_check[1])
    if not args.svg.is_file():
        p.error(f"no such file: {args.svg}")
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found")

    for name in ("fill", "background"):
        try:
            setattr(args, f"{name}_rgb", ImageColor.getrgb(getattr(args, name)))
        except ValueError as exc:
            p.error(f"--{name}: {exc}")
    if args.output is None:
        args.output = OUT_DIR / "astryx-glitch.gif"

    render_size = args.size * args.supersample
    # Seed for reproducibility
    seed = 13

    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for f in range(args.frames):
            # Render the base mark once per frame (same every time — no movement)
            svg_content = (
                f'<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
                f'<g fill="{args.fill}"><path d="{PATH_D}"/></g></svg>'
            )
            dest = Path(tmp) / f"base_{f:04d}.png"
            proc = subprocess.run(
                ["rsvg-convert", "-w", str(render_size), "-h", str(render_size), "-", "-o", str(dest)],
                input=svg_content, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                sys.exit(f"rsvg-convert failed: {proc.stderr.strip()}")

            with Image.open(dest) as img:
                frame = img.convert("RGBA")
            flat = Image.new("RGBA", frame.size, args.background_rgb + (255,))
            flat.alpha_composite(frame)

            # Decide if this frame glitches
            # Use a separate RNG stream for glitch check vs flash check.
            check_rng = random.Random(seed + f * 1000)
            if check_rng.random() < args.glitch_prob:
                glitched, type_ = glitch(flat, f, seed, args.flash_prob)
                if not args.quiet:
                    print(f"  frame {f + 1}/{args.frames}  glitch: {type_}", file=sys.stderr)
            else:
                glitched = flat

            frames.append(glitched.resize((args.size,) * 2, Image.BOX).convert("RGB"))

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
          f"glitch-prob={args.glitch_prob} flash={args.flash_prob}, "
          f"{stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
