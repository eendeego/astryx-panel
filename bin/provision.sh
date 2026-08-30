#!/usr/bin/env bash
# Apply config/cfg.json (HUB75 panel + 2D matrix layout, anything build flags
# can't bake) to a running WLED board over HTTP, then reboot it.
#
# Usage: ./provision.sh [options] [host]
#   [host]                 Board IP or hostname (default: 4.3.2.1, the WLED setup-AP address;
#                          use the board's LAN IP or wled-xxxxxx.local once it has joined WiFi)
#   -f, --file <cfg.json>  Config to apply (default: config/cfg.json)
#   -u, --upload           Replace the board's cfg.json with the file instead of merging
#                          (fresh boards only — discards any settings not in the file)
#   -n, --no-reboot        Skip the reboot (HUB75/matrix changes only apply after one)
#   -P, --pin <pin>        Settings PIN, if the board has one
#   -h, --help             Show this help
#
# Default mode POSTs the file to /json/cfg: WLED merges it into the live config
# field by field and saves it, so it is safe on an already-configured board.

set -euo pipefail

REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
CFG=$REPO_DIR/config/cfg.json
DEFAULT_HOST=4.3.2.1   # WLED-AP address of an unconfigured board
HOST=""
MODE=merge
REBOOT=1
PIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--file)      CFG="$2"; shift 2 ;;
    -u|--upload)    MODE=upload; shift ;;
    -n|--no-reboot) REBOOT=0; shift ;;
    -P|--pin)       PIN="$2"; shift 2 ;;
    -h|--help)      sed -n '2,16{s/^# \{0,1\}//p}' "$0"; exit 0 ;;
    -*) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
    *)  [[ -z "$HOST" ]] || { echo "Unexpected argument: $1" >&2; exit 1; }; HOST="$1"; shift ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
HOST=${HOST:-$DEFAULT_HOST}
command -v curl >/dev/null || die "curl is required"
command -v python3 >/dev/null || die "python3 is required"
[[ -f "$CFG" ]] || die "config file not found: $CFG"
python3 -m json.tool "$CFG" >/dev/null 2>&1 || die "$CFG is not valid JSON"

HOST=${HOST#http://}; HOST=${HOST%/}
BASE="http://$HOST"
CURL=(curl -sS --connect-timeout 5 --max-time 30)

json_field() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {"d": d}))' "$1" 2>/dev/null; }

# --- Preflight ----------------------------------------------------------------
INFO=$("${CURL[@]}" "$BASE/json/info") || die "cannot reach $BASE (is the board on the network?)"
echo "Board:  $(json_field 'd.get("name","?")' <<<"$INFO") — WLED $(json_field 'd.get("ver","?")' <<<"$INFO") ($(json_field 'd.get("arch","?")' <<<"$INFO"))"
echo "Config: $CFG"

# --- Apply --------------------------------------------------------------------
if [[ $MODE = upload ]]; then
  echo "Replacing /cfg.json on the board (upload mode) ..."
  RESP=$("${CURL[@]}" -F "data=@$CFG;filename=/cfg.json" "$BASE/upload") || die "upload failed"
  [[ "$RESP" == *"Config restore ok"* ]] || die "unexpected response from /upload: $RESP"
  echo "Uploaded; the board reboots on its own."
  REBOOT=0
else
  echo "Merging into the live config (/json/cfg) ..."
  BODY=$(python3 - "$CFG" "$PIN" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if sys.argv[2]: d["pin"] = sys.argv[2]
print(json.dumps(d))
PY
)
  HTTP=$("${CURL[@]}" -o /tmp/provision_resp.$$ -w '%{http_code}' -H 'Content-Type: application/json' --data "$BODY" "$BASE/json/cfg") || die "POST /json/cfg failed"
  RESP=$(cat /tmp/provision_resp.$$); rm -f /tmp/provision_resp.$$
  [[ "$HTTP" == 401 ]] && die "board rejected the request (settings PIN?) — pass -P <pin>"
  [[ "$HTTP" == 200 && "$RESP" == *'"success":true'* ]] || die "unexpected response from /json/cfg (HTTP $HTTP): $RESP"
  echo "Merged and saved."
  if [[ $REBOOT -eq 1 ]]; then
    echo "Rebooting ..."
    "${CURL[@]}" -o /dev/null -H 'Content-Type: application/json' --data '{"rb":true}' "$BASE/json/state" || die "reboot request failed"
  else
    echo "Not rebooting (-n); HUB75/matrix changes take effect after the next reboot."
    exit 0
  fi
fi

# --- Wait for the board and verify --------------------------------------------
echo -n "Waiting for the board to come back "
sleep 3
for i in $(seq 1 30); do
  if "${CURL[@]}" --max-time 3 -o /dev/null "$BASE/json/info" 2>/dev/null; then echo " up."; break; fi
  echo -n "."; sleep 3
  [[ $i -eq 30 ]] && { echo; die "board did not come back within 90 s"; }
done
LIVE=$("${CURL[@]}" "$BASE/json/cfg") || die "cannot read back /json/cfg"
LIVE_JSON="$LIVE" python3 - "$CFG" <<'PY'
import json, os, sys
want = json.load(open(sys.argv[1])).get("hw", {}).get("led", {})
live = json.loads(os.environ["LIVE_JSON"]).get("hw", {}).get("led", {})
ok = True
def subset(w, l):  # every value in the file must appear on the board; the board may carry extra keys (e.g. panel b/r/v/s)
    if isinstance(w, dict): return isinstance(l, dict) and all(subset(v, l.get(k)) for k, v in w.items())
    if isinstance(w, list): return isinstance(l, list) and len(w) == len(l) and all(subset(a, b) for a, b in zip(w, l))
    return w == l
def show(label, w, l):
    global ok
    same = subset(w, l); ok &= same
    print(f"  {'OK  ' if same else 'DIFF'} {label}: board={l}" + ("" if same else f"  wanted={w}"))
for i, ins in enumerate(want.get("ins", [])):
    l = (live.get("ins") or [{}])[i] if i < len(live.get("ins") or []) else {}
    show(f"output {i} type", ins.get("type"), l.get("type"))
    show(f"output {i} pin/params", ins.get("pin"), l.get("pin"))
if "matrix" in want:
    show("matrix panels", want["matrix"].get("mpc"), live.get("matrix", {}).get("mpc"))
    show("matrix layout", want["matrix"].get("panels"), live.get("matrix", {}).get("panels"))
print("Provisioning complete." if ok else "WARNING: board config differs from the file (see DIFF lines).")
sys.exit(0 if ok else 2)
PY
