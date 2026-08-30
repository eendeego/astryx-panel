#!/usr/bin/env python3
"""make-wave.py — letters undulate in a sine wave.

Each letter oscillates up and down with a phase offset proportional to its
horizontal position in the word, so the assembled wordmark ripples like
a sine wave. The wave amplitude, speed, and wavelength are adjustable.

Letters are placed exactly as make-assemble.py does — bounds from
letters.json, scaled about the word centre, then rotated about the
panel centre if --rotate is given.

Usage:
  ./make-wave.py [options] [letters-dir] [output.gif]

  -s, --size N         canvas is NxN pixels             (default: 64)
  -r, --rotate DEG     stand the word at an angle       (default: 0)
  -w, --word-width N   width of the assembled word       (default: fitted)
  -f, --frames N       frames per wave cycle             (default: 30)
      --hold N         frames held before/after wave     (default: 10)
  -a, --amplitude N    peak-to-trough amplitude, px      (default: 3)
  -l, --wavelength N   horizontal wavelength, px         (default: 40)
      --supersample N  compose at N× panel resolution    (default: 4)
  -d, --delay N        per-frame delay in centiseconds   (default: 4)
  -b, --background C   canvas fill colour               (default: black)
  -q, --quiet          suppress per-letter listing       (default: off)

  letters-dir  directory split-letters.py filled (default: gfx/out/letters)
  output.gif   file to write       (default: config/gifs/astryx-wave.gif)

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
DEFAULT_OUT = REPO_ROOT / "config" / "gifs" / "astryx-wave.gif"


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


def fitted_width(canvas, aspect, degrees):
    theta = math.radians(degrees)
    cos, sin = abs(math.cos(theta)), abs(math.sin(theta))
    return canvas / max(cos + aspect * sin, sin + aspect * cos)


def turn(vector, degrees):
    """Rotate a 2D vector clockwise by `degrees`."""
    theta = math.radians(degrees)
    cos, sin = math.cos(theta), math.sin(theta)
    dx, dy = vector
    return (dx * cos - dy * sin, dx * sin + dy * cos)


def render_letter(svg, width, height, dest):
    proc = subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height), str(svg), "-o", str(dest)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"rsvg-convert failed on {svg}: {proc.stderr.strip()}")


def main():
    p = argparse.ArgumentParser(
        description="Wave the letters in a sine wave.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("letters", nargs="?", type=Path, default=DEFAULT_LETTERS, help="letters dir")
    p.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUT, help="GIF to write")
    p.add_argument("-s", "--size", type=int, default=64, help="canvas edge in pixels")
    p.add_argument("-r", "--rotate", type=float, default=0, help="degrees to stand the word at")
    p.add_argument("-w", "--word-width", type=float, default=0, help="word width in px")
    p.add_argument("-f", "--frames", type=int, default=30, help="frames per wave cycle")
    p.add_argument("--hold", type=int, default=10, help="frames held before/after wave")
    p.add_argument("-a", "--amplitude", type=float, default=3, help="peak-to-trough amplitude px")
    p.add_argument("-l", "--wavelength", type=float, default=40, help="horizontal wavelength px")
    p.add_argument("--supersample", type=int, default=4, help="compose at this multiple of panel res")
    p.add_argument("-d", "--delay", type=int, default=4, help="per-frame delay in centiseconds")
    p.add_argument("-b", "--background", default="black", help="canvas fill colour")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress listing")
    args = p.parse_args()

    for err_check in [
        (args.size < 1, f"--size must be positive"),
        (args.frames < 1, f"--frames must be positive"),
        (args.hold < 0, f"--hold must not be negative"),
        (args.supersample < 1, f"--supersample must be positive"),
        (args.delay < 1, f"--delay must be positive"),
        (args.amplitude <= 0, f"--amplitude must be positive"),
    ]:
        if err_check[0]:
            p.error(err_check[1])
    if not args.letters.is_dir():
        p.error(f"no such directory: {args.letters}")
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found")

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

    # Pre-render all letter sprites and compute their final (assembled) positions.
    sprites = []
    finals = []
    spans = []
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

            # Assemble position: same as make-assemble.py.
            middle = ((bx + bw / 2) * scale, (by + bh / 2) * scale)
            offset = turn((middle[0] - word_centre[0], middle[1] - word_centre[1]),
                          args.rotate)
            raster = (sprite.width / ss, sprite.height / ss)
            span = raster if args.rotate else (bw * scale, bh * scale)
            final = (canvas_centre[0] + offset[0] - span[0] / 2,
                     canvas_centre[1] + offset[1] - span[1] / 2)

            sprites.append(sprite)
            finals.append(final)
            spans.append(span)

    total = args.hold + args.frames + args.hold
    frames = []
    for f in range(total):
        canvas = Image.new("RGBA", (canvas_px, canvas_px), background + (255,))

        # Wave phase: 0→1 over the wave phase, hold the rest.
        if f < args.hold:
            wave_t = 0  # before wave
        elif f < args.hold + args.frames:
            wave_t = (f - args.hold) / (args.frames - 1) if args.frames > 1 else 0
        else:
            wave_t = 1  # after wave

        for n, (sprite, final, span) in enumerate(zip(sprites, finals, spans)):
            fx, fy = final
            # Phase offset: proportional to horizontal position relative to word width.
            # A full wavelength across the word means the wave repeats every `wavelength` px.
            phase = (fx / word_width) * (word_width / args.wavelength)

            # Sine displacement: y oscillates around fy, phase-shifted.
            wave_y = fy + (args.amplitude / 2) * math.sin(2 * math.pi * (wave_t - phase))

            canvas.alpha_composite(sprite, (round(fx * ss), round(wave_y * ss)))

        frames.append(canvas.resize((args.size, args.size), Image.BOX).convert("RGB"))

    palette = frames[-1].quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(args.output, save_all=True, append_images=quantized[1:],
                      duration=args.delay * 10, loop=0, disposal=1, optimize=False)

    with Image.open(args.output) as written:
        stored = written.n_frames

    total_s = len(frames) * args.delay / 100
    print(f"Wrote {args.output} ({len(frames)} frames at {args.delay}cs = {total_s:.1f}s, "
          f"word {word_width:.1f}x{view_h * scale:.1f}px"
          f"{f' at {args.rotate:g}°' if args.rotate else ''}, "
          f"amp={args.amplitude}px wave={args.wavelength}px, "
          f"{stored} stored, bg={args.background})")


if __name__ == "__main__":
    main()
