#!/usr/bin/env bash
# Build WLED firmware (and optionally upload it to the board).
#
# Usage: ./build.sh [options]
#   -e, --env <name>    PlatformIO environment (default: adafruit_matrixportal_esp32s3)
#   -u, --upload        Upload the firmware after building
#   -p, --port <dev>    Serial port for upload (e.g. /dev/ttyACM0; auto-detect if omitted)
#   -c, --clean         Clean PlatformIO build artifacts first
#   -h, --help          Show this help

set -euo pipefail
cd "$(dirname "$0")/../../WLED"

ENV_NAME="adafruit_matrixportal_esp32s3"
UPLOAD=0
PORT=""
CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)    ENV_NAME="$2"; shift 2 ;;
    -u|--upload) UPLOAD=1; shift ;;
    -p|--port)   PORT="$2"; shift 2 ;;
    -c|--clean)  CLEAN=1; shift ;;
    -h|--help)   sed -n '2,9{s/^# \{0,1\}//p}' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done

# Make sure node/npm and pio are resolvable in non-interactive shells.
if ! command -v npm >/dev/null 2>&1; then
  for d in "$HOME"/.local/share/fnm/node-versions/*/installation/bin; do
    [[ -x "$d/npm" ]] && PATH="$d:$PATH" && break
  done
fi
if ! command -v pio >/dev/null 2>&1 && [[ -x "$HOME/.platformio/penv/bin/pio" ]]; then
  PATH="$HOME/.platformio/penv/bin:$PATH"
fi
export PATH
command -v npm >/dev/null || { echo "ERROR: npm not found (need Node.js >= 20)" >&2; exit 1; }
command -v pio >/dev/null || { echo "ERROR: pio not found (need PlatformIO)" >&2; exit 1; }

# Web UI: install deps once, regenerate wled00/html_*.h / js_*.h (cdata.js skips if up to date).
[[ -d node_modules ]] || npm ci
npm run build

[[ $CLEAN -eq 1 ]] && pio run -e "$ENV_NAME" -t clean

PIO_ARGS=(run -e "$ENV_NAME")
if [[ $UPLOAD -eq 1 ]]; then
  PIO_ARGS+=(-t upload)
  [[ -n "$PORT" ]] && PIO_ARGS+=(--upload-port "$PORT")
fi
pio "${PIO_ARGS[@]}"

echo
echo "Done. Firmware: .pio/build/$ENV_NAME/firmware.bin"
