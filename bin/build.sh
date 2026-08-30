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

REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
WLED_DIR=$REPO_DIR/WLED                       # upstream checkout, git-ignored here
OVERRIDE_SRC=$REPO_DIR/config/platformio_override.ini
OVERRIDE_LINK=$WLED_DIR/platformio_override.ini

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

if [[ ! -f "$WLED_DIR/platformio.ini" ]]; then
  echo "ERROR: WLED checkout not found at $WLED_DIR" >&2
  echo "       run bin/check-env.sh for the fix (git clone https://github.com/wled/WLED \"$WLED_DIR\")" >&2
  exit 1
fi

# The tracked config/platformio_override.ini is the board-config source of
# truth; WLED only sees it through this (untracked) symlink, so keep it right.
if [[ -L "$OVERRIDE_LINK" || ! -e "$OVERRIDE_LINK" ]]; then
  if [[ ! "$OVERRIDE_LINK" -ef "$OVERRIDE_SRC" ]]; then
    ln -sfn ../config/platformio_override.ini "$OVERRIDE_LINK"
    echo "Linked $OVERRIDE_LINK -> ../config/platformio_override.ini"
  fi
elif [[ ! "$OVERRIDE_LINK" -ef "$OVERRIDE_SRC" ]]; then
  echo "WARNING: $OVERRIDE_LINK is a regular file, not a link to config/platformio_override.ini;" >&2
  echo "         the tracked board config is NOT being used." >&2
fi

cd "$WLED_DIR"

# Make sure pio is resolvable in non-interactive shells. Node/npm must already
# be on PATH — how they are installed is up to the user.
if ! command -v pio >/dev/null 2>&1 && [[ -x "$HOME/.platformio/penv/bin/pio" ]]; then
  PATH="$HOME/.platformio/penv/bin:$PATH"
fi
export PATH
command -v npm >/dev/null || { echo "ERROR: npm not found (need Node.js >= 20; run bin/check-env.sh)" >&2; exit 1; }
command -v pio >/dev/null || { echo "ERROR: pio not found (need PlatformIO; run bin/check-env.sh)" >&2; exit 1; }

# Web UI: install deps once, regenerate wled00/html_*.h / js_*.h (cdata.js skips if up to date).
[[ -d node_modules ]] || npm ci
npm run build

if [[ $CLEAN -eq 1 ]]; then
  pio run -e "$ENV_NAME" -t clean
fi

PIO_ARGS=(run -e "$ENV_NAME")
if [[ $UPLOAD -eq 1 ]]; then
  PIO_ARGS+=(-t upload)
  [[ -n "$PORT" ]] && PIO_ARGS+=(--upload-port "$PORT")
elif [[ -n "$PORT" ]]; then
  echo "WARNING: --port given without --upload; ignoring it" >&2
fi
pio "${PIO_ARGS[@]}"

echo
echo "Done. Firmware: WLED/.pio/build/$ENV_NAME/firmware.bin"
