#!/usr/bin/env bash
# Generate docs/gif-preview.md from the GIFs in config/gifs/: one section per
# GIF showing it, with its geometry, frame count, duration, size, preset number
# and the command that rebuilds it.
#
# Each GIF is shown twice: as generated, and as the panel wears it, with
# config/2d-gaps.json applied so the LEDs the mask covers are painted flat.
# The masked copy is given a border in the same colour and its corners are
# rounded, so it reads as the panel behind its mask rather than as a second
# animation. They are written to docs/masked/ and are versioned, since the
# document has to render from the repository.
#
# Usage: ./gen-gif-preview.sh [options]
#   -o, --output <file>  Write here instead of docs/gif-preview.md
#   -w, --width <px>     Displayed width of each preview     (default: 192)
#   -m, --mask-color <c> Colour for pixels the gap file disables, and for the
#                        border around them                (default: #c0c0c0)
#       --border <px>    Border around the masked copy          (default: 3)
#       --radius <px>    Corner radius of that border           (default: 2)
#       --no-mask        Skip the masked copies entirely
#       --check          Write nothing; exit 1 if anything is out of date
#   -h, --help           Show this help
#
# What a GIF *is* cannot be measured, so the description under each heading is
# carried over from the existing file and a new GIF gets a stub to fill in.
# Everything else is derived: the numbers from the files themselves, the preset
# numbers from config/presets.json, and the rebuild command from gfx/Makefile
# via `make -Bn`, so this file and the build cannot drift apart.
#
# Rerun it after gfx/generate-all.sh or bin/gen-presets.sh. --check says whether
# it is stale without touching anything.

set -euo pipefail
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
OUT=$REPO_DIR/docs/gif-preview.md
WIDTH=192
CHECK=0
MASK_COLOR="#c0c0c0"
DO_MASK=1
BORDER=3
RADIUS=2
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUT="$2"; shift 2 ;;
    -w|--width)  WIDTH="$2"; shift 2 ;;
    -m|--mask-color) MASK_COLOR="$2"; shift 2 ;;
    --border)    BORDER="$2"; shift 2 ;;
    --radius)    RADIUS="$2"; shift 2 ;;
    --no-mask)   DO_MASK=0; shift ;;
    --check)     CHECK=1; shift ;;
    -h|--help)   sed -n '2,29{s/^# \{0,1\}//p;}' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done
[[ "$WIDTH" =~ ^[0-9]+$ ]] && (( 10#$WIDTH > 0 )) || { echo "ERROR: --width must be a positive integer, got: $WIDTH" >&2; exit 1; }
[[ "$BORDER" =~ ^[0-9]+$ ]] || { echo "ERROR: --border must be a whole number of pixels, got: $BORDER" >&2; exit 1; }
[[ "$RADIUS" =~ ^[0-9]+$ ]] || { echo "ERROR: --radius must be a whole number of pixels, got: $RADIUS" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 is required" >&2; exit 1; }
python3 -c 'import PIL' 2>/dev/null || { echo "ERROR: Pillow is required (pip install pillow)" >&2; exit 1; }

python3 - "$REPO_DIR" "$OUT" "$WIDTH" "$CHECK" "$MASK_COLOR" "$DO_MASK" "$BORDER" "$RADIUS" <<'GENPREVIEW'
import io, json, os, re, subprocess, sys, textwrap
from pathlib import Path
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageSequence

repo, out_path, width, check = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1"
do_mask = sys.argv[6] == "1"
border, radius = int(sys.argv[7]), int(sys.argv[8])
try:
    mask_colour = ImageColor.getrgb(sys.argv[5])
except ValueError as exc:
    sys.exit(f"ERROR: --mask-color: {exc}")
gif_dir = repo / "config" / "gifs"
mask_dir = out_path.parent / "masked"
mask_hex = "#%02x%02x%02x" % mask_colour
STUB = "_No description yet — write one here; this script keeps it._"
MASK_ALT = ", behind the mask"

# --- what the board is being given -------------------------------------------
cfg = json.loads((repo / "config" / "cfg.json").read_text())
panels = cfg.get("hw", {}).get("led", {}).get("matrix", {}).get("panels") or [{}]
pw, ph = panels[0].get("w", 0), panels[0].get("h", 0)
boot_ps = cfg.get("def", {}).get("ps")

presets, playlist, playlist_name = {}, None, "playlist"
presets_file = repo / "config" / "presets.json"
if presets_file.is_file():
    for pid, p in json.loads(presets_file.read_text()).items():
        if pid == "0":
            continue
        if "playlist" in p:
            playlist = (pid, p["playlist"])
            playlist_name = p.get("n") or playlist_name
        for seg in p.get("seg", []):
            if seg.get("n"):
                presets[seg["n"]] = pid

# --- the panel as the mask leaves it -----------------------------------------
def shown(path):
    """Repo-relative when it is in the repo, absolute when -o points elsewhere."""
    try:
        return str(Path(path).relative_to(repo))
    except ValueError:
        return str(path)

gap_dark = 0
def load_gap():
    """A mask image, white where the gap file says the LED is never painted."""
    path = repo / "config" / "2d-gaps.json"
    if not (do_mask and path.is_file() and pw and ph):
        return None
    try:
        gaps = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(gaps, list) or len(gaps) < pw * ph:
        return None
    # 1 is painted; 0 (never paint) and -1 (no LED there) both read as off
    global gap_dark
    gap_dark = sum(1 for v in gaps[:pw * ph] if v <= 0)
    img = Image.new("L", (pw, ph))
    img.putdata([0 if v > 0 else 255 for v in gaps[:pw * ph]])
    return img

# The corners are cut out of every frame with one shared mask, and the index
# they are set to is left out of the palette so it can carry transparency.
CLEAR = 255
framed = (pw + 2 * border, ph + 2 * border)
outside = None
if radius:
    inside = Image.new("L", framed, 0)
    ImageDraw.Draw(inside).rounded_rectangle(
        [(0, 0), (framed[0] - 1, framed[1] - 1)], radius=radius, fill=255)
    outside = ImageChops.invert(inside)

def render_masked(src, dest, mask):
    """Write src with the disabled pixels painted flat. -> written|unchanged."""
    frames, durations = [], []
    flat = Image.new("RGB", (pw, ph), mask_colour)
    with Image.open(src) as im:
        for frame in ImageSequence.Iterator(im):
            panel = Image.composite(flat, frame.convert("RGB"), mask)
            if border:
                # the border is the mask carrying on past the edge of the panel
                bezel = Image.new("RGB", framed, mask_colour)
                bezel.paste(panel, (border, border))
                panel = bezel
            frames.append(panel)
            durations.append(frame.info.get("duration", 40))

    # One palette for the run, taken from the busiest frame, as the generators
    # in gfx/ do: per-frame palettes make the flat area crawl.
    richest = max(frames, key=lambda f: len(f.getcolors(maxcolors=1 << 16) or [1]))
    colours = CLEAR if outside is not None else 256
    palette = richest.quantize(colors=colours, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    if outside is not None:
        for q in quantized:
            q.paste(CLEAR, mask=outside)

    # Fewer frames may reach the file than went in: flattening the masked pixels
    # makes neighbouring frames identical, and Pillow merges a run of those into
    # one with their delays summed. The duration is unchanged, which is what counts.
    buf = io.BytesIO()
    # disposal 1 throughout: the cut corners are transparent in every frame, so
    # "leave what was there" leaves the page showing, where "restore to the
    # background colour" invites a flash of palette index 0 between frames
    extra = {"transparency": CLEAR} if outside is not None else {}
    quantized[0].save(buf, format="GIF", save_all=True, append_images=quantized[1:],
                      duration=durations, loop=0, disposal=1, optimize=False, **extra)
    data = buf.getvalue()
    if dest.is_file() and dest.read_bytes() == data:
        return "unchanged"
    if not check:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return "written"

gap_mask = load_gap()
masked_written, masked_same = [], 0

# --- descriptions already written, kept across runs --------------------------
def existing_descriptions(path):
    """Map filename -> prose, and filename -> alt text, already written here."""
    if not path.is_file():
        return {}, {}
    kept, alts, name, buf = {}, {}, None, []
    def flush():
        if name:
            text = "\n".join(buf).strip()
            if text and text != STUB:
                kept[name] = text
    for line in path.read_text().splitlines():
        head = re.match(r"^#{2,4}\s+(\S+\.gif)\s*$", line)
        if head:
            flush(); name, buf = head.group(1), []; continue
        if name is None:
            continue
        # the description is what sits between the image and the facts line
        if line.startswith("<img "):
            # two images per section now; only the first describes the GIF
            # itself, and the second's alt is derived from it
            alt = re.search(r'alt="([^"]*)"', line)
            if alt and alt.group(1) != name and not alt.group(1).endswith(MASK_ALT):
                alts.setdefault(name, alt.group(1))
            continue
        if line.startswith("```"):
            continue
        if re.match(r"^`\d+ frames", line):
            flush(); name, buf = None, []; continue
        buf.append(line)
    flush()
    return kept, alts

kept, alts = existing_descriptions(out_path)

# --- the command that rebuilds each one, straight from the Makefile ----------
def rebuild_command(name):
    """The recipe gfx/Makefile would run for this GIF, or None if it has none."""
    target = f"../config/gifs/{name}"
    try:
        proc = subprocess.run(["make", "-C", str(repo / "gfx"), "-Bn", target],
                              capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None  # no rule at all: make says so and exits non-zero
    # A GIF dropped into config/gifs/ by hand is a target that exists with no
    # rule, which make reports as "Nothing to be done" on a zero exit — so the
    # absence of a recipe, not the exit status, is what identifies it.
    lines = [l.strip() for l in proc.stdout.splitlines()
             if l.strip() and not l.startswith(("make[", "make:", "mkdir "))]
    # prerequisites are printed first, so this GIF's own recipe is the last line
    return lines[-1] if lines else None

def measure(path):
    with Image.open(path) as im:
        frames, (w, h) = getattr(im, "n_frames", 1), im.size
        ms = 0
        for i in range(frames):
            im.seek(i)
            ms += im.info.get("duration", 0)
    return w, h, frames, ms / 1000

gifs = sorted(f for f in os.listdir(gif_dir) if f.lower().endswith(".gif"))
if not gifs:
    sys.exit(f"ERROR: no .gif files in {gif_dir}")

# --- compose ------------------------------------------------------------------
doc = ["<!-- Generated by bin/gen-gif-preview.sh. Edit the descriptions here;",
       "     everything else is rewritten from the files on the next run. -->", "",
       "# GIF preview", ""]

total = sum(os.path.getsize(gif_dir / g) for g in gifs)
doc += [f"Every animation in `config/gifs/`, which is what `bin/provision.sh` puts on the",
        f"panel and `bin/gen-presets.sh` turns into presets. {len(gifs)} of them, "
        f"{total / 1024:.0f} KB in total.", ""]
if pw and ph:
    doc += [f"All of them are {pw}×{ph}, the panel's own size: WLED clips anything larger and",
            "scales smaller ones up by whole numbers only.", ""]
doc += ["Frame counts are what is *stored* — runs of identical frames are merged with",
        "their delays summed, so the duration is the number that matters. The commands",
        "run from `gfx/`; `gfx/generate-all.sh <target>` runs one from anywhere, and",
        "`gfx/generate-all.sh` rebuilds whatever is stale.", ""]
if gap_mask is not None:
    doc += [f"Each one is shown twice: **as generated** on the left, and **behind the mask**",
            f"on the right, where the {gap_dark} pixels `config/2d-gaps.json` switches off are",
            f"painted `{mask_hex}` — what the logo-shaped cut-out leaves visible. The masked",
            f"copy carries {border}px of the same colour around it, corners rounded {radius}px, so it",
            "reads as a panel behind a mask rather than as a second animation. Those copies",
            "live in `docs/masked/` and are rewritten by this script.", ""]

hand_dropped = []
for name in gifs:
    path = gif_dir / name
    w, h, frames, seconds = measure(path)
    kb = os.path.getsize(path) / 1024
    facts = [f"{frames} frames", f"{seconds:.1f} s", f"{kb:.1f} KB"]
    if name in presets:
        facts.append(f"preset {presets[name]}")
    if (w, h) != (pw, ph):
        facts.insert(0, f"{w}×{h}")

    images = [f'<img src="../config/gifs/{name}" width="{width}" '
              f'alt="{alts.get(name, name)}">']
    if gap_mask is not None and (w, h) == (pw, ph):
        status = render_masked(path, mask_dir / name, gap_mask)
        if status == "written":
            masked_written.append(name)
        else:
            masked_same += 1
        # shown at the same scale as the panel beside it, border included
        images.append(f'<img src="masked/{name}" width="{round(width * framed[0] / pw)}" '
                      f'alt="{alts.get(name, name)}{MASK_ALT}">')

    doc += [f"## {name}", ""] + images + ["",
            kept.get(name, STUB), "",
            "`" + " · ".join(facts) + "`", ""]

    command = rebuild_command(name)
    if command:
        doc += ["```sh", command, "```", ""]
    else:
        hand_dropped.append(name)
        doc += ["Not built by `gfx/Makefile` — this one was dropped into `config/gifs/`", ""]

doc += ["---", "", "## How they play", ""]
if playlist:
    pid, pl = playlist
    durs = {d / 10 for d in pl.get("dur", [])}
    each = f"{durs.pop():g} seconds each" if len(durs) == 1 else "a per-GIF duration"
    line = (f"`bin/gen-presets.sh` gives each GIF an Image-effect preset, numbered in "
            f"the order above, and collects them into the \"{playlist_name}\" playlist "
            f"as preset {pid} — {each}.")
    doc += textwrap.wrap(line, 78)
    if str(boot_ps) == str(pid):
        doc += ["", f"That playlist is the boot preset (`def.ps` in `config/cfg.json`), so it is what",
                "the panel comes up playing."]
    elif boot_ps is not None:
        doc += ["", f"The boot preset (`def.ps` in `config/cfg.json`) is preset {boot_ps}."]
    doc += [""]
if hand_dropped:
    doc += [f"Dropped in by hand, not generated: {', '.join('`' + n + '`' for n in hand_dropped)}.", ""]
doc += ["Add a GIF by writing one into `config/gifs/` — no larger than the panel, name",
        "of 32 characters or fewer including `.gif` — then re-run `bin/gen-presets.sh`,",
        "this script, and `bin/provision.sh <board-ip>`.", "",
        "More generators sit in `gfx/` unwired from the build; see *Extra animations*",
        "in `README.md`. Running one writes straight into `config/gifs/`, so it turns",
        "up here on the next pass.", ""]

rendered = "\n".join(doc)
if check:
    stale = []
    if (out_path.read_text() if out_path.is_file() else "") != rendered:
        stale.append(shown(out_path))
    stale += [shown(mask_dir / n) for n in masked_written]
    if not stale:
        print(f"{shown(out_path)} is up to date ({len(gifs)} GIFs, "
              f"{masked_same} masked copies)")
        sys.exit(0)
    print("out of date — re-run bin/gen-gif-preview.sh:")
    for f in stale:
        print(f"  {f}")
    sys.exit(1)

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(rendered)
missing = [g for g in gifs if g not in kept]
note = f"; {len(missing)} without a description ({', '.join(missing)})" if missing else ""
print(f"Wrote {shown(out_path)}: {len(gifs)} GIF(s), {total / 1024:.0f} KB{note}")
if gap_mask is None:
    reason = "--no-mask" if not do_mask else "no usable config/2d-gaps.json"
    print(f"Masked copies: skipped ({reason})")
else:
    print(f"Masked copies in {shown(mask_dir)}/: {len(masked_written)} written, "
          f"{masked_same} already current"
          + (f" — {', '.join(masked_written)}" if masked_written else ""))

# A stale masked copy of a GIF that is no longer there is just litter.
if gap_mask is not None and not check and mask_dir.is_dir():
    for f in sorted(os.listdir(mask_dir)):
        if f.lower().endswith(".gif") and f not in gifs:
            (mask_dir / f).unlink()
            print(f"Removed {shown(mask_dir / f)} (no such GIF any more)")
GENPREVIEW
