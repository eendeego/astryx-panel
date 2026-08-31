#!/usr/bin/env bash
#
# make-marquee.sh — turn a PNG into a 64x64 animated marquee GIF.
#
# The image scrolls leftward across the canvas: it enters from the right
# edge, travels across, disappears completely off the left edge, then
# reappears from the right (classic marquee, no wrap-around).
#
# The source is used at its own size, vertically centered on the canvas;
# its dimensions are read from the file, and its width sets how many
# frames a full pass takes. Anything taller than 64 px is cropped evenly
# top and bottom.
#
# -r/--rotate turns the whole marquee: the word, the direction it travels
# and, in cylinder mode, the axis the drum turns about. It is done by
# rendering onto a canvas big enough that the panel still sits inside it
# once turned — 64 * (|cos| + |sin|), so 91x91 at 45 degrees — and then
# turning each finished frame and cropping the panel out of the middle.
# The travel grows with that canvas, and with it the frame count.
#
# With -c/--cylinder the image instead rides the surface of a vertical
# drum whose front half spans the canvas: columns foreshorten toward the
# edges where the surface turns away from the viewer, move fastest at
# the center, and are shaded darker toward the rim (depth set by
# --shade). Frames come out opaque in this mode, so use an opaque
# background with it.
#
# Run with no arguments, or with --help, to print the options and their
# defaults. Missing parent directories are created for the output GIF.
#
set -euo pipefail

PROG=$(basename "$0")
SYNOPSIS="usage: $PROG [options] input.png [output.gif] [delay] [background]"

usage() {
  cat <<EOF
$SYNOPSIS

Turn a PNG into a 64x64 animated marquee GIF.

  -c, --cylinder      render on a rotating drum instead of a flat surface
  -r, --rotate DEG    turn the marquee this many degrees, clockwise on
                      screen: the word, its direction of travel, and the
                      drum's axis under --cylinder             (default: 0)
  -s, --shade N       rim shading depth for --cylinder, 0..1  (default: 0.8)
                      0 disables shading
  -h, --help          show this help and exit

  input.png   source image, used at its own size, vertically centered
  output.gif  GIF to write                                (default: marquee.gif)
  delay       per-frame delay in centiseconds, lower = faster       (default: 4)
  background  canvas fill color                                 (default: black)
EOF
}

die() {
  printf '%s\n%s: error: %s\n' "$SYNOPSIS" "$PROG" "$*" >&2
  exit 2
}

(( $# )) || { usage; exit 0; }

CYLINDER=0
SHADE=0.8
ROTATE=0
while (( $# )); do
  case "$1" in
    -c|--cylinder) CYLINDER=1; shift ;;
    -r|--rotate) (( $# >= 2 )) || die "--rotate requires a value"
                 ROTATE="$2"; shift 2 ;;
    -s|--shade) (( $# >= 2 )) || die "--shade requires a value"
                SHADE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unrecognized option: $1" ;;
    *) break ;;
  esac
done

[[ "$SHADE" =~ ^(0(\.[0-9]+)?|1(\.0+)?)$ ]] \
  || die "--shade must be a number in 0..1, got: $SHADE"
[[ "$ROTATE" =~ ^[+-]?[0-9]+(\.[0-9]+)?$ ]] \
  || die "--rotate must be a number of degrees, got: $ROTATE"

(( $# )) || die "the following argument is required: input.png"
(( $# <= 4 )) || die "unrecognized arguments: ${*:5}"

IN="$1"
OUT="${2:-marquee.gif}"
DELAY="${3:-4}"
BG="${4:-black}"

[[ -f "$IN" ]] || die "no such file: $IN"
[[ "$DELAY" =~ ^[0-9]+$ ]] && (( 10#$DELAY > 0 )) \
  || die "delay must be a positive integer, got: $DELAY"

CANVAS_W=64
CANVAS_H=64

# Use IM7 "magick" if present, fall back to IM6 "convert"
if command -v magick >/dev/null 2>&1; then
  IM=magick
else
  IM=convert
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Everything is rendered on a square big enough to still cover the panel once
# it is turned — 64 * (|cos| + |sin|) — and the panel is cropped out of the
# middle at the end. Rounded up to an even number so the drum's radius stays
# whole.
WORK=$(awk -v s="$CANVAS_W" -v deg="$ROTATE" 'BEGIN {
  r = deg * atan2(0, -1) / 180; c = cos(r); n = sin(r)
  if (c < 0) c = -c; if (n < 0) n = -n
  w = int(s * (c + n) + 0.999); if (w % 2) w++
  print w
}')

# Source image dimensions
DIMS=$($IM "$IN" -format '%w %h' info: 2>/dev/null || identify -format '%w %h' "$IN")
read -r IMG_W IMG_H <<< "$DIMS"

# Vertically centered on the working canvas
Y=$(( (WORK - IMG_H) / 2 ))

if (( CYLINDER )); then
  # Drum radius: the visible front half (pi*R of surface arc) projects
  # onto the full canvas width, since x = R*sin(angle) spans [-R, R].
  R=$(( WORK / 2 ))
  ARC=$(awk -v r="$R" 'BEGIN { pi = atan2(0, -1); printf "%d", int(pi*r) + 1 }')
  HALF_ARC=$(awk -v r="$R" 'BEGIN { pi = atan2(0, -1); printf "%.6f", pi*r/2 }')

  # Render frames horizontally supersampled, then box down to canvas
  # width: near the rim several source columns squeeze into one output
  # pixel, and point sampling there would shimmer.
  SS=4
  SSW=$(( WORK * SS ))
  SS_CX=$(awk -v w="$SSW" 'BEGIN { printf "%.1f", (w - 1)/2 }')
  SS_HW=$(( SSW / 2 ))

  # Full travel along the surface: from just past the right rim to just
  # past the left rim, one pixel of arc per frame.
  TRAVEL=$(( ARC + IMG_W ))

  # The unrolled drum surface: the image with one visible-arc of
  # background on each side. Frame o views the window [o, o+ARC).
  STRIP_W=$(( 2*ARC + IMG_W ))
  $IM -size "${STRIP_W}x${WORK}" xc:"$BG" \
      "$IN" -geometry "$(printf '%+d%+d' "$ARC" "$Y")" -composite \
      "$TMP/strip.png"

  # Rim shading dims each column by the cosine of the surface angle,
  # sqrt(1-xx^2), mixed against full brightness by SHADE.
  SHADE_FLOOR=$(awk -v s="$SHADE" 'BEGIN { printf "%.6f", 1 - s }')

  # Each output pixel looks up its arc position on the strip (fx's i/j
  # are the output pixel coordinates; o is the shell frame counter):
  #   xx = position across the drum face in [-1, 1]
  #   src column = o + HALF_ARC + R*asin(xx)
  for ((o = 0; o < TRAVEL; o++)); do
    $IM -size "${SSW}x${WORK}" xc: "$TMP/strip.png" \
        -virtual-pixel edge -channel RGB \
        -fx "xx=(i-${SS_CX})/${SS_HW}; v.p{ ${o}+${HALF_ARC}+${R}*asin(xx), j } * (${SHADE_FLOOR}+${SHADE}*sqrt(1-xx*xx))" \
        +channel -resize "${WORK}x${WORK}!" \
        "$TMP/frame_$(printf '%04d' "$o").png"
  done
else
  # Full travel: from just off the right edge to fully off the left edge
  TRAVEL=$(( WORK + IMG_W ))

  for ((i = 0; i < TRAVEL; i++)); do
    X=$(( WORK - 1 - i ))   # starts at the right edge, ends fully off the left
    $IM -size "${WORK}x${WORK}" xc:"$BG" \
        "$IN" -geometry "$(printf '%+d%+d' "$X" "$Y")" -composite \
        "$TMP/frame_$(printf '%04d' "$i").png"
  done
fi

# Assemble frames into a looping GIF. Turning happens here, on every frame at
# once: the marquee was rendered square and oversized, so a turn followed by a
# centre crop leaves the panel covered to the corners whatever the angle.
mkdir -p "$(dirname "$OUT")"
if [[ "$ROTATE" != 0 ]]; then
  $IM -delay "$DELAY" -loop 0 "$TMP"/frame_*.png \
      -background "$BG" -rotate "$ROTATE" \
      -gravity center -extent "${CANVAS_W}x${CANVAS_H}" "$OUT"
else
  $IM -delay "$DELAY" -loop 0 "$TMP"/frame_*.png "$OUT"
fi

MODE=""
if (( CYLINDER )); then MODE=", cylinder, shade=$SHADE"; fi
if [[ "$ROTATE" != 0 ]]; then MODE="$MODE, turned ${ROTATE}° on a ${WORK}x${WORK} canvas"; fi
echo "Wrote $OUT ($TRAVEL frames, ${DELAY}cs/frame, bg=$BG$MODE)"