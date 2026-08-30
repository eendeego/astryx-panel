#!/usr/bin/env bash
# Flash a WLED image onto the MatrixPortal S3 with esptool: bootloader (0x0),
# partition table (0x8000), boot_app0 (0xe000) and the firmware (0x10000),
# optionally after a full chip erase. Use this for a from-scratch install (e.g.
# a board still running TinyUF2/CircuitPython or a release image); for routine
# reflashing of a board already running WLED, `bin/build.sh -u` is enough.
#
# Usage: ./flash.sh [options]
#   -e, --env <name>       PlatformIO env whose build to flash (default: adafruit_matrixportal_esp32s3)
#   -f, --firmware <bin>   Flash this image instead of the env's build output
#   -p, --port <dev>       Serial port (auto-detected if exactly one candidate exists)
#   -n, --no-erase         Skip the full chip erase (keeps WiFi settings/presets)
#   -d, --download         Use the boot files from WLED's web installer (downloaded
#                          once into .cache/boot) instead of the local build's
#   --dry-run              Print the esptool command instead of running it
#   -h, --help             Show this help
#
# Without -f the boot files come from the same PlatformIO build as the firmware.
# With -f (an image built elsewhere) the web-installer boot files are used, as
# WLED's own installer does for release binaries.

set -euo pipefail

ORIG_ARGS=$*
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
WLED_DIR=$REPO_DIR/WLED
CACHE_DIR=$REPO_DIR/.cache/boot

# Where WLED's web installer keeps its ESP32-S3 (8 MB, QIO) boot files.
BOOT_BASE_URL=https://raw.githubusercontent.com/wled/WLED-WebInstaller/master/bin/boot
BOOT_URL_BOOTLOADER=$BOOT_BASE_URL/bootloaders/esp32-s3/bootloader_s3.bin
BOOT_URL_PARTITIONS=$BOOT_BASE_URL/partitions/partitions_s3_8m.bin
BOOT_URL_BOOT_APP0=$BOOT_BASE_URL/boot_app0.bin

ENV_NAME="adafruit_matrixportal_esp32s3"
FIRMWARE=""
PORT=""
ERASE=1
DOWNLOAD=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)      ENV_NAME="$2"; shift 2 ;;
    -f|--firmware) FIRMWARE="$2"; DOWNLOAD=1; shift 2 ;;
    -p|--port)     PORT="$2"; shift 2 ;;
    -n|--no-erase) ERASE=0; shift ;;
    -d|--download) DOWNLOAD=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     sed -n '2,20{s/^# \{0,1\}//p;}' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

# --- esptool ------------------------------------------------------------------
# Prefer whatever is on PATH; fall back to the copy PlatformIO ships.
if ! command -v esptool >/dev/null 2>&1 && ! command -v esptool.py >/dev/null 2>&1 \
   && [[ -x "$HOME/.platformio/penv/bin/pio" ]]; then
  PATH="$HOME/.platformio/penv/bin:$PATH"
fi
export PATH
if command -v esptool >/dev/null 2>&1; then
  ESPTOOL=(esptool)
elif command -v esptool.py >/dev/null 2>&1; then
  ESPTOOL=(esptool.py)
elif [[ -x "$HOME/.platformio/penv/bin/python" && -d "$HOME/.platformio/packages/tool-esptoolpy" ]]; then
  ESPTOOL=("$HOME/.platformio/penv/bin/python" "$HOME/.platformio/packages/tool-esptoolpy/esptool.py")
  [[ -f "${ESPTOOL[1]}" ]] || ESPTOOL=("$HOME/.platformio/penv/bin/python" -m esptool)
else
  die "esptool not found (pip install esptool, or install PlatformIO which bundles it)"
fi
# esptool >= 5 renamed write_flash -> write-flash (old names still work but warn).
ESPTOOL_MAJOR=$("${ESPTOOL[@]}" version 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo 0)
if [[ "${ESPTOOL_MAJOR:-0}" -ge 5 ]]; then WRITE_CMD=write-flash; ERASE_OPT=--erase-all
else WRITE_CMD=write_flash; ERASE_OPT=--erase-all; fi

# --- Firmware -----------------------------------------------------------------
if [[ -z "$FIRMWARE" ]]; then
  FIRMWARE=$WLED_DIR/.pio/build/$ENV_NAME/firmware.bin
  [[ -f "$FIRMWARE" ]] || die "no build output at $FIRMWARE — run bin/build.sh -e $ENV_NAME first"
else
  [[ -f "$FIRMWARE" ]] || die "firmware image not found: $FIRMWARE"
fi

# --- Boot files ---------------------------------------------------------------
download() {  # download <url> <dest>
  if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1"
  else die "need curl or wget to download $1"; fi
}

if [[ $DOWNLOAD -eq 0 ]]; then
  BUILD_DIR=$WLED_DIR/.pio/build/$ENV_NAME
  BOOTLOADER=$BUILD_DIR/bootloader.bin
  PARTITIONS=$BUILD_DIR/partitions.bin
  BOOT_APP0=$(ls "$HOME"/.platformio/packages/framework-arduinoespressif32*/tools/partitions/boot_app0.bin 2>/dev/null | head -1 || true)
  if [[ ! -f "$BOOTLOADER" || ! -f "$PARTITIONS" || -z "$BOOT_APP0" ]]; then
    echo "Local build boot files incomplete; using WLED web-installer boot files instead." >&2
    DOWNLOAD=1
  fi
fi
if [[ $DOWNLOAD -eq 1 ]]; then
  mkdir -p "$CACHE_DIR"
  BOOTLOADER=$CACHE_DIR/bootloader_s3.bin
  PARTITIONS=$CACHE_DIR/partitions_s3_8m.bin
  BOOT_APP0=$CACHE_DIR/boot_app0.bin
  for pair in "$BOOT_URL_BOOTLOADER|$BOOTLOADER" "$BOOT_URL_PARTITIONS|$PARTITIONS" "$BOOT_URL_BOOT_APP0|$BOOT_APP0"; do
    url=${pair%%|*}; dest=${pair#*|}
    if [[ ! -s "$dest" ]]; then
      echo "Downloading $(basename "$dest") ..."
      download "$url" "$dest.tmp" || { rm -f "$dest.tmp"; die "download failed: $url"; }
      mv "$dest.tmp" "$dest"
    fi
  done
fi

# --- Serial port --------------------------------------------------------------
if [[ -z "$PORT" ]]; then
  if [[ "$(uname)" = "Darwin" ]]; then
    candidates=(/dev/cu.usbmodem* /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART*)
  else
    candidates=(/dev/ttyACM* /dev/ttyUSB*)
  fi
  found=()
  for c in "${candidates[@]}"; do [[ -e "$c" ]] && found+=("$c"); done
  case ${#found[@]} in
    0) die "no serial port found. Put the board in ROM bootloader mode (1. hold BOOT, 2. tap RESET, 3. release BOOT) and re-run, or pass -p <port>" ;;
    1) PORT=${found[0]} ;;
    *) die "several serial ports found (${found[*]}); choose one with -p <port>" ;;
  esac
fi
[[ -e "$PORT" || $DRY_RUN -eq 1 ]] || die "$PORT does not exist. Is the board plugged in and in bootloader mode?"

# --- Flash --------------------------------------------------------------------
CMD=("${ESPTOOL[@]}" --chip esp32s3 --port "$PORT" "$WRITE_CMD")
[[ $ERASE -eq 1 ]] && CMD+=("$ERASE_OPT")
CMD+=(0x0 "$BOOTLOADER" 0x8000 "$PARTITIONS" 0xe000 "$BOOT_APP0" 0x10000 "$FIRMWARE")

echo "Firmware:    $FIRMWARE"
echo "Boot files:  $(dirname "$BOOTLOADER")  (+ $BOOT_APP0)"
echo "Port:        $PORT"
echo "Chip erase:  $([[ $ERASE -eq 1 ]] && echo yes || echo no)"
echo
if [[ $DRY_RUN -eq 1 ]]; then
  printf '%q ' "${CMD[@]}"; echo
  exit 0
fi
if ! "${CMD[@]}"; then
  echo >&2
  echo "Flashing failed. Put the board in ROM bootloader mode:" >&2
  echo "  1. Hold BOOT" >&2
  echo "  2. Tap RESET" >&2
  echo "  3. Release BOOT" >&2
  echo "then re-run: $0 $ORIG_ARGS" >&2
  exit 1
fi
echo
echo "Done. If the board does not restart on its own, press its RESET button to boot WLED."
echo "Next: apply the panel config with bin/provision.sh (targets the WLED-AP at 4.3.2.1; pass the LAN IP once it is on WiFi)"
