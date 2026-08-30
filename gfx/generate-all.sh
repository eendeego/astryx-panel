#!/usr/bin/env bash
#
# generate-all.sh — regenerate the panel artwork from the sources in gfx/raw/.
#
# A thin wrapper around the Makefile in gfx/: it checks that the external
# tools are installed, then builds from gfx/ whatever the current
# directory is. Work is skipped when a target is already newer than its
# source and than the script that produces it, which is the point of
# going through make — a marquee GIF costs one ImageMagick invocation
# per frame, so rebuilding it for nothing is expensive.
#
# Run with --help for the options and their defaults.
#
set -euo pipefail

PROG=$(basename "$0")
SYNOPSIS="usage: $PROG [options] [target...]"
GFX=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  cat <<EOF
$SYNOPSIS

Regenerate the panel artwork that is out of date.

  -f, --force         rebuild every target, including the up-to-date ones
  -n, --dry-run       print the commands instead of running them
  -j, --jobs N        build up to N targets at a time            (default: 1)
  -h, --help          show this help and exit

  target...   make targets to build                            (default: all)
              "clean" deletes gfx/out/ and the generated GIFs
EOF
}

die() {
  printf '%s\n%s: error: %s\n' "$SYNOPSIS" "$PROG" "$*" >&2
  exit 2
}

MAKE_ARGS=(-C "$GFX")
JOBS=1
while (( $# )); do
  case "$1" in
    -f|--force) MAKE_ARGS+=(-B); shift ;;
    -n|--dry-run) MAKE_ARGS+=(-n); shift ;;
    -j|--jobs) (( $# >= 2 )) || die "--jobs requires a value"
               JOBS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unrecognized option: $1" ;;
    *) break ;;
  esac
done

[[ "$JOBS" =~ ^[0-9]+$ ]] && (( 10#$JOBS > 0 )) \
  || die "--jobs must be a positive integer, got: $JOBS"
MAKE_ARGS+=(-j "$JOBS")

# Fail on a missing tool here rather than halfway through a build.
need() { command -v "$1" >/dev/null 2>&1 || die "$1 not found ($2)"; }
need make "install the Xcode command line tools"
need rsvg-convert "brew install librsvg"
need python3 "brew install python"
command -v magick >/dev/null 2>&1 || command -v convert >/dev/null 2>&1 \
  || die "ImageMagick not found (brew install imagemagick)"
python3 -c 'import PIL' >/dev/null 2>&1 \
  || die "Pillow not found (pip install pillow)"

make "${MAKE_ARGS[@]}" "$@"
