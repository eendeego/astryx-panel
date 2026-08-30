#!/usr/bin/env python3
"""make-explode.py — the mark's four lobes break apart and scatter.

Each of the four quadrants of the mark moves outward from the centre by up
to --separation pixels. The result is a shatter / dissolve effect where the
mark falls apart into its corners. In reverse (default "out") the pieces
gather into the mark.

Usage:
  ./make-explode.py [options] [input.svg] [output.gif]

  -d, --direction WAY  in=lobes scatter, out=lobes gather
                         (default: out)
      --separation N   max lobe displacement, px            (default: 6)
  -f, --frames N       frames of travel                    (default: 30)
      --hold N         frames holding the mark            (default: 15)
  -s, --size N         canvas is NxN pixels               (default: 64)
      --supersample N  render at N× panel resolution       (default: 4)
  -c, --fill COLOR     mark colour                        (default: blue)
  -b, --background C   canvas fill colour                 (default: black)
      --delay N        per-frame delay in centiseconds     (default: 4)
  -q, --quiet          suppress per-frame listing          (default: off)

  input.svg   source mark             (default: gfx/raw/astryx.svg)
  output.gif  file to write  (default: config/gifs/astryx-explode.gif)

Missing parent directories are created for the GIF.
"""

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageColor

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


def ease_out_cubic(t):
    u = t - 1
    return 1 + u * u * u


def quadrant_mask(mask_size, quadrant):
    """Return an L-mode mask isolating one quadrant."""
    q = Image.new("L", (mask_size, mask_size), 0)
    x0 = mask_size // 2 if quadrant in (1, 3) else 0
    y0 = mask_size // 2 if quadrant in (2, 3) else 0
    q.paste(255, (x0, y0, mask_size, mask_size))
    return q


def main():
    p = argparse.ArgumentParser(
        description="Explode the mark's four lobes apart.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("svg", nargs="?", type=Path, default=DEFAULT_SVG, help="source mark")
    p.add_argument("output", nargs="?", type=Path, help="GIF to write")
    p.add_argument("-d", "--direction", choices=("in", "out"), default="out",
                   help="in=lobes scatter, out=lobes gather")
    p.add_argument("--separation", type=float, default=20, help="max lobe displacement px")
    p.add_argument("-f", "--frames", type=int, default=30, help="frames of travel")
    p.add_argument("--hold", type=int, default=15, help="frames holding the mark")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("--supersample", type=int, default=4, help="render at this multiple of panel resolution")
    p.add_argument("-c", "--fill", default=BRAND, help="mark colour")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("--delay", type=int, default=4, help="per-frame delay in centiseconds")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress per-frame listing")
    args = p.parse_args()

    for err_check in [
        (args.size < 1, f"--size must be positive"),
        (args.frames < 2, f"--frames must be ≥ 2"),
        (args.hold < 0, f"--hold must not be negative"),
        (args.supersample < 1, f"--supersample must be positive"),
        (args.delay < 1, f"--delay must be positive"),
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
        args.output = OUT_DIR / "astryx-explode.gif"
    args.output.parent.mkdir(parents=True, exist_ok=True)

    render_size = args.size * args.supersample

    # Render the full mark once at supersampled resolution.
    svg_content = (
        f'<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
        f'<g fill="{args.fill}"><path d="{PATH_D}"/></g></svg>'
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        result = subprocess.run(
            ["rsvg-convert", "-w", str(render_size), "-h", str(render_size), "-", "-o", f.name],
            input=svg_content.encode(), capture_output=True,
        )
        if result.returncode != 0:
            sys.exit(f"rsvg-convert failed: {result.stderr.decode().strip()}")
        full_mark = Image.open(f.name).convert("RGBA")
        f.close()

    # Split into 4 quadrant layers.
    quad_size = render_size // 2
    quads = []
    for q in range(4):
        mask = quadrant_mask(render_size, q)
        # Extract quadrant pixels
        quad = full_mark.copy()
        quad.putalpha(Image.new("L", (render_size, render_size), 0))
        quad.putalpha(mask)
        quads.append(quad)

    # Total frames = travel + hold
    total_frames = args.frames + args.hold
    direction = -1 if args.direction == "in" else 1  # -1=scatter, +1=gather

    frames = []
    bg_img = Image.new("RGBA", (render_size, render_size), args.background_rgb + (255,))

    for n in range(total_frames):
        if n < args.frames:
            t = n / (args.frames - 1) if args.frames > 1 else 0
            travel = ease_out_cubic(t)  # 0 at t=0, 1 at t=1
            # Scale down as pieces fly apart
            quad_scale = max(0.0, 1.0 - travel)
            # Move each quad away from centre by up to --separation px
            cx, cy = render_size / 2, render_size / 2
            offsets = []
            for q in range(4):
                sign_x = 1 if q in (1, 3) else -1
                sign_y = 1 if q in (2, 3) else -1
                # direction: +1=gather (out), -1=scatter (in)
                offsets.append((
                    sign_x * args.separation * travel * direction,
                    sign_y * args.separation * travel * direction,
                ))
            # Composite quads with offsets and scaling
            frame = bg_img.copy()
            for q, quad in enumerate(quads):
                dx, dy = offsets[q]
                if quad_scale <= 0:
                    continue
                s = max(1, int(quad_size * quad_scale))
                scaled = quad.resize((s, s), Image.LANCZOS)
                ox = int(cx + dx) - s // 2
                oy = int(cy + dy) - s // 2
                frame.paste(scaled, (ox, oy), scaled)
        else:
            # Hold frame
            frame = bg_img.copy()
            if direction == -1:  # "in" = gather, hold the assembled mark
                frame.alpha_composite(full_mark)

        # Downscale to panel resolution
        down = frame.resize((args.size, args.size), Image.LANCZOS)
        # Convert to P mode with median-cut
        down = down.convert("RGB")
        gif_frame = down.quantize(method=Image.MEDIANCUT)
        frames.append(gif_frame)

        if not args.quiet:
            # Count pixels that differ from the background
            bg_rgb = Image.new("RGB", frame.size, args.background_rgb)
            diff = ImageChops.difference(frame.convert("RGB"), bg_rgb)
            gray = diff.convert("L")
            # Non-zero pixels in the histogram at index 0 = background pixels
            histo = gray.histogram()
            zero_count = histo[0]
            lit = gray.width * gray.height - zero_count
            total_px = frame.width * frame.height
            pct = lit / total_px * 100
            print(f"  frame {n + 1}/{total_frames}  travel={travel:.2f}  {pct:5.1f}% lit")

    # Write GIF
    out_path = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bg_rgb = args.background_rgb
    # Prepare palette: start with background
    pal_img = Image.new("RGB", (1, 1), bg_rgb)
    # Add mark color
    mark_img = Image.new("RGB", (1, 1), args.fill_rgb)
    combined = Image.new("P", (2, 1))
    combined.paste(pal_img, (0, 0))
    combined.paste(mark_img, (1, 0))
    palette = combined.getpalette()

    # Quantize frames with this palette
    for i, fr in enumerate(frames):
        frames[i] = fr.quantize(palette=palette)

    frames[0].save(
        str(out_path),
        save_all=True,
        append_images=frames[1:],
        duration=args.delay * 10,
        loop=0,
        disposal=1,
        optimize=False,
    )

    held = total_frames - args.frames
    flight = args.frames
    print(f"Wrote {out_path} ({total_frames} frames at {args.delay}cs = {total_frames * args.delay / 100:.1f}s, {flight} travel + {held} held, {args.direction}, sep={args.separation:.1f}px)")


if __name__ == "__main__":
    main()
