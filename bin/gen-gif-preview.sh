#!/usr/bin/env bash
# Generate docs/gif-preview.md from the GIFs in config/gifs/: one section per
# GIF showing it, with its geometry, frame count, duration, size, preset number
# and the command that rebuilds it.
#
# Usage: ./gen-gif-preview.sh [options]
#   -o, --output <file>  Write here instead of docs/gif-preview.md
#   -w, --width <px>     Displayed width of each preview     (default: 192)
#       --check          Write nothing; exit 1 if the file is out of date
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
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUT="$2"; shift 2 ;;
    -w|--width)  WIDTH="$2"; shift 2 ;;
    --check)     CHECK=1; shift ;;
    -h|--help)   sed -n '2,20{s/^# \{0,1\}//p;}' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done
[[ "$WIDTH" =~ ^[0-9]+$ ]] && (( 10#$WIDTH > 0 )) || { echo "ERROR: --width must be a positive integer, got: $WIDTH" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 is required" >&2; exit 1; }
python3 -c 'import PIL' 2>/dev/null || { echo "ERROR: Pillow is required (pip install pillow)" >&2; exit 1; }

python3 - "$REPO_DIR" "$OUT" "$WIDTH" "$CHECK" <<'GENPREVIEW'
import json, os, re, subprocess, sys, textwrap
from pathlib import Path
from PIL import Image

repo, out_path, width, check = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1"
gif_dir = repo / "config" / "gifs"
STUB = "_No description yet — write one here; this script keeps it._"

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
            alt = re.search(r'alt="([^"]*)"', line)
            if alt and alt.group(1) != name:
                alts[name] = alt.group(1)
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

    doc += [f"## {name}", "",
            f'<img src="../config/gifs/{name}" width="{width}" '
            f'alt="{alts.get(name, name)}">', "",
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
    current = out_path.read_text() if out_path.is_file() else ""
    if current == rendered:
        print(f"{out_path.relative_to(repo)} is up to date ({len(gifs)} GIFs)")
        sys.exit(0)
    print(f"{out_path.relative_to(repo)} is out of date — re-run bin/gen-gif-preview.sh")
    sys.exit(1)

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(rendered)
missing = [g for g in gifs if g not in kept]
note = f"; {len(missing)} without a description ({', '.join(missing)})" if missing else ""
print(f"Wrote {out_path.relative_to(repo)}: {len(gifs)} GIF(s), {total / 1024:.0f} KB{note}")
GENPREVIEW
