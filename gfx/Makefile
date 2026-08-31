# Rebuilds the panel artwork from the sources in raw/.
#
# Prefer gfx/generate-all.sh, which checks the external tools are present
# and runs this from gfx/ whatever the current directory is.
#
# Every recipe below is one of the tested (good) invocations documented in
# README.md; keep the two in step. A target is remade when its source, the
# script that produces it, or this file changes — the flags here are as much
# a part of the output as the script is, and a recipe edit that quietly
# rebuilt nothing has caught us twice. A repeat run is still free, which is
# the point: each marquee GIF is one ImageMagick invocation per frame.
#
# Finished GIFs land in config/gifs/, where bin/gen-presets.sh and
# bin/provision.sh pick them up, and are versioned with the rest of the
# panel's artwork; the gap file lands in config/ under the name the
# firmware reads it by. Everything else is an intermediate and stays in
# out/, which is not versioned.

RAW  := raw
OUT  := out
GIFS := ../config/gifs
CFG  := ../config

MARQUEE  := make-marquee.sh
GAP      := make-gap.py
SPLIT    := split-letters.py
ANGLE := 45

ASSEMBLE := make-assemble.py
OFFSET   := make-offset.py
RETIME   := retime.py

# Panel edge, in pixels. Also hardcoded as the canvas size in make-marquee.sh.
SIZE := 64

# Every animation runs for exactly this long, so a playlist slot holds a
# whole number of passes. At 4cs a frame that is 125 frames, which is what
# the flag arithmetic below is for; a marquee's frame count is its geometry
# instead, one frame per pixel of travel, so retime.py adjusts its delays.
SECONDS := 5

# The same fly-in, with the word standing at the angle each target
# carries below.
ASSEMBLIES := $(GIFS)/astryx-assemble.gif \
              $(GIFS)/astryx-assemble+45.gif \
              $(GIFS)/astryx-assemble-45.gif

# The logo mark's outline walked in until the panel is empty, then back
# out until the mark has it again — one loop, not two files.
OFFSET_GIF := $(GIFS)/astryx-inout.gif

# The gap file is named for the board, not for us: WLED 16.0.1 reads
# /2d-gaps.json off its filesystem and no config field points at it, so
# the name is the whole interface (wled00/FX_2Dfcn.cpp).
GAPFILE := $(CFG)/2d-gaps.json

GENERATED := $(GAPFILE) \
             $(GIFS)/astryx-word.gif \
             $(GIFS)/astryx-word-c.gif \
             $(ASSEMBLIES) \
             $(OFFSET_GIF)

TARGETS := $(OUT)/astryx-word.png \
           $(OUT)/letters/letters.json \
           $(GENERATED)

.PHONY: all clean
all: $(TARGETS)

# The wordmark, rasterized to panel width. Only the width is pinned: -a
# keeps the aspect ratio, and the marquee script reads the height it gets.
#
# Both marquees then run it at ANGLE. Turning a 64x12 word 45 degrees needs
# 56x57, which still fits the panel, and the travel grows with it: 120 frames
# flat and 157 round the drum, both brought to SECONDS by retime.py.
$(OUT)/astryx-word.png: $(RAW)/astryx-word.svg Makefile | $(OUT)
	rsvg-convert -o $@ -w $(SIZE) -a $<

$(GIFS)/astryx-word.gif: $(OUT)/astryx-word.png $(MARQUEE) $(RETIME) Makefile | $(GIFS)
	./$(MARQUEE) -r $(ANGLE) $< $@
	python3 $(RETIME) -q -t $(SECONDS) $@

# The drum turned 45° spans the panel's diagonal, so its arc — and its frame
# count — grows to 209. Five seconds would mean 2-3cs a frame, forty-odd frames
# a second, which the panel will not keep up with and so would not honour; ten
# keeps it near the 4cs everything else runs at, and is still a whole number of
# passes in a playlist slot.
$(GIFS)/astryx-word-c.gif: SECONDS := 10
$(GIFS)/astryx-word-c.gif: $(OUT)/astryx-word.png $(MARQUEE) $(RETIME) Makefile | $(GIFS)
	./$(MARQUEE) -c -r $(ANGLE) $< $@
	python3 $(RETIME) -q -t $(SECONDS) $@

# -n -t 255 -b white is the combination verified on the panel: -b white
# renders the mark black on white, so the shape sits at 0 coverage, and -n
# flips the threshold's result to put 1 (WLED's "paint this pixel") on the
# shape and 0 on the ground. See the polarity note in README.md before
# touching it. The explicit paths are the same files make-gap.py defaults to.
$(GAPFILE): $(RAW)/astryx.svg $(GAP) Makefile
	python3 $(GAP) -n -t 255 -s $(SIZE) -b white $< $@

# One SVG per letter, for animating them independently. The manifest
# stands in for the whole directory: the script writes it last, and it
# lists every letter file, so if it is current they all are.
$(OUT)/letters/letters.json: $(RAW)/astryx-word.svg $(SPLIT) Makefile | $(OUT)
	python3 $(SPLIT) $< $(dir $@)

# The letters flying in from the edges and settling into the word, which
# stands at the angle each target carries. On a diagonal the word may be
# larger, since it then spans the panel's diagonal rather than its edge,
# and make-assemble.py sizes it to fit whatever angle it is given.
#
# 60 frames of flight staggered 4 apart over six letters is 80 frames of
# travel, and 45 held makes 125 — five seconds at 4cs, so the retime below
# has nothing to do.
$(GIFS)/astryx-assemble.gif:     ROTATE := 0
$(GIFS)/astryx-assemble+45.gif:  ROTATE := 45
$(GIFS)/astryx-assemble-45.gif:  ROTATE := -45

$(ASSEMBLIES): $(OUT)/letters/letters.json $(ASSEMBLE) $(RETIME) Makefile | $(GIFS)
	python3 $(ASSEMBLE) --rotate $(ROTATE) -f 60 --stagger 4 --hold 45 $(dir $<) $@
	python3 $(RETIME) -q -t $(SECONDS) $@

# 50 frames each way with the turn and the loop point not drawn twice is
# 98, and 27 held makes 125 — five seconds, as above.
$(OFFSET_GIF): $(RAW)/astryx.svg $(OFFSET) $(RETIME) Makefile | $(GIFS)
	python3 $(OFFSET) -d both -f 50 --hold 27 $< $@
	python3 $(RETIME) -q -t $(SECONDS) $@

$(OUT) $(GIFS):
	mkdir -p $@

# Only what this Makefile writes: config/gifs/ also holds GIFs that were
# dropped there by hand, and clean must not take those with it. The gap
# file goes too — it is provisioned from config/, but it is generated,
# and generate-all.sh puts it straight back.
clean:
	rm -rf $(OUT)
	rm -f $(GENERATED)
