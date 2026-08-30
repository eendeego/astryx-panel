#!/usr/bin/env bash
# Generate config/presets.json from the animated GIFs in config/gifs/: one
# "Image" preset per GIF plus a playlist cycling through all of them, and set
# that playlist as the boot preset in config/cfg.json.
#
# Usage: ./gen-presets.sh [options]
#   -d, --duration <s>   Seconds each GIF plays in the playlist (default: 10)
#   -b, --bri <0-255>    Preset brightness (default: 128)
#   -s, --speed <0-255>  Playback speed: 128 = GIF's own timing (default: 128)
#   --max-frames <n>     Warn when a GIF has more frames (default: 200)
#   --max-kb <n>         Warn when a GIF is larger (default: 512)
#   --no-boot            Do not touch config/cfg.json (boot preset)
#   -h, --help           Show this help
#
# GIFs must not exceed the panel size from config/cfg.json (smaller GIFs are
# scaled up by WLED); filenames incl. ".gif" are limited to 32 characters.
# Note: this overwrites config/presets.json — hand edits do not survive.

set -euo pipefail
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
DURATION=10; BRI=128; SPEED=128; MAX_FRAMES=200; MAX_KB=512; BOOT=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--duration) DURATION="$2"; shift 2 ;;
    -b|--bri)      BRI="$2"; shift 2 ;;
    -s|--speed)    SPEED="$2"; shift 2 ;;
    --max-frames)  MAX_FRAMES="$2"; shift 2 ;;
    --max-kb)      MAX_KB="$2"; shift 2 ;;
    --no-boot)     BOOT=0; shift ;;
    -h|--help)     sed -n '2,18{s/^# \{0,1\}//p;}' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done
command -v python3 >/dev/null || { echo "ERROR: python3 is required" >&2; exit 1; }

python3 - "$REPO_DIR" "$DURATION" "$BRI" "$SPEED" "$MAX_FRAMES" "$MAX_KB" "$BOOT" <<'PY'
import json, os, struct, sys
repo, duration, bri, speed, max_frames, max_kb, boot = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7] == "1"
gif_dir, cfg_path, out_path = f"{repo}/config/gifs", f"{repo}/config/cfg.json", f"{repo}/config/presets.json"
FX_IMAGE, MAX_NAME = 53, 32

def parse_gif(path):
    """Return (width, height, frames) using the GIF block structure; raises ValueError on malformed input."""
    with open(path, "rb") as f: b = f.read()
    if b[:6] not in (b"GIF87a", b"GIF89a"): raise ValueError("not a GIF file")
    w, h, packed = struct.unpack("<HHB", b[6:11]); pos = 13
    if packed & 0x80: pos += 3 * (2 << (packed & 7))
    def skip_subblocks(p):
        while True:
            n = b[p]; p += 1
            if n == 0: return p
            p += n
    frames = 0
    while pos < len(b):
        tag = b[pos]; pos += 1
        if tag == 0x3B: break
        if tag == 0x21: pos = skip_subblocks(pos + 1)
        elif tag == 0x2C:
            lp = b[pos + 8]; pos += 9
            if lp & 0x80: pos += 3 * (2 << (lp & 7))
            pos = skip_subblocks(pos + 1); frames += 1
        else: raise ValueError(f"unexpected block 0x{tag:02x} at offset {pos-1}")
    if frames == 0: raise ValueError("no image frames")
    return w, h, frames

cfg = json.load(open(cfg_path))
panels = cfg.get("hw", {}).get("led", {}).get("matrix", {}).get("panels") or []
if not panels: sys.exit("ERROR: config/cfg.json has no hw.led.matrix.panels — cannot determine panel size")
PW, PH = panels[0]["w"], panels[0]["h"]

gifs = sorted(f for f in os.listdir(gif_dir) if f.lower().endswith(".gif"))
if not gifs: sys.exit(f"ERROR: no .gif files in {gif_dir}")
errors = 0
presets = {"0": {}}
print(f"Panel {PW}x{PH}; {len(gifs)} GIF(s) in config/gifs/")
for i, name in enumerate(gifs, start=1):
    path = f"{gif_dir}/{name}"; size = os.path.getsize(path); notes = []
    try: w, h, frames = parse_gif(path)
    except ValueError as e:
        print(f"  ERROR {name}: {e}"); errors += 1; continue
    if len(name) > MAX_NAME: notes.append(f"ERROR name longer than {MAX_NAME} chars (WLED segment-name limit)"); errors += 1
    if w > PW or h > PH: notes.append(f"ERROR {w}x{h} exceeds the {PW}x{PH} panel (WLED clips, never downscales)"); errors += 1
    elif (w, h) != (PW, PH): notes.append(f"warn {w}x{h} will be scaled up by WLED")
    if frames > max_frames: notes.append(f"warn {frames} frames > {max_frames}")
    if size > max_kb * 1024: notes.append(f"warn {size//1024} KB > {max_kb} KB")
    print(f"  {i:3d}  {name:32s} {w:3d}x{h:<3d} {frames:4d} frames {size//1024:4d} KB  {'; '.join(notes)}")
    presets[str(i)] = {
        "n": os.path.splitext(name)[0][:32], "on": True, "bri": bri, "transition": 7, "mainseg": 0,
        "seg": [{"id": 0, "start": 0, "stop": PW, "startY": 0, "stopY": PH, "grp": 1, "spc": 0, "of": 0,
                 "on": True, "frz": False, "bri": 255, "n": name,
                 "col": [[255, 255, 255], [0, 0, 0], [0, 0, 0]], "fx": FX_IMAGE, "sx": speed, "ix": 0, "pal": 0,
                 "sel": True, "rev": False, "mi": False, "rY": False, "mY": False, "tp": False}]}
if errors: sys.exit(f"ERROR: {errors} problem(s) above — fix the GIFs first (nothing written)")
pl_id = len(gifs) + 1
presets[str(pl_id)] = {"n": "All GIFs", "playlist": {"ps": list(range(1, len(gifs) + 1)), "dur": [int(duration * 10)] * len(gifs),
                                                     "transition": [7], "repeat": 0, "end": 0}}
json.dump(presets, open(out_path, "w"), indent=2); open(out_path, "a").write("\n")
print(f"Wrote config/presets.json: {len(gifs)} Image preset(s) + playlist #{pl_id} ({duration:g} s each)")
if boot:
    cfg.setdefault("def", {})["ps"] = pl_id
    json.dump(cfg, open(cfg_path, "w"), indent=2); open(cfg_path, "a").write("\n")
    print(f"Set boot preset def.ps={pl_id} in config/cfg.json")
PY
