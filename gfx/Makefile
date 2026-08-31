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
ASSEMBLE := make-assemble.py
OFFSET   := make-offset.py

# Panel edge, in pixels. Also hardcoded as the canvas size in make-marquee.sh.
SIZE := 64

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
$(OUT)/astryx-word.png: $(RAW)/astryx-word.svg Makefile | $(OUT)
	rsvg-convert -o $@ -w $(SIZE) -a $<

$(GIFS)/astryx-word.gif: $(OUT)/astryx-word.png $(MARQUEE) Makefile | $(GIFS)
	./$(MARQUEE) $< $@

$(GIFS)/astryx-word-c.gif: $(OUT)/astryx-word.png $(MARQUEE) Makefile | $(GIFS)
	./$(MARQUEE) -c $< $@

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
$(GIFS)/astryx-assemble.gif:     ROTATE := 0
$(GIFS)/astryx-assemble+45.gif:  ROTATE := 45
$(GIFS)/astryx-assemble-45.gif:  ROTATE := -45

$(ASSEMBLIES): $(OUT)/letters/letters.json $(ASSEMBLE) Makefile | $(GIFS)
	python3 $(ASSEMBLE) --rotate $(ROTATE) $(dir $<) $@

$(OFFSET_GIF): $(RAW)/astryx.svg $(OFFSET) Makefile | $(GIFS)
	python3 $(OFFSET) -d both -f 60 --hold 30 $< $@

$(OUT) $(GIFS):
	mkdir -p $@

# Only what this Makefile writes: config/gifs/ also holds GIFs that were
# dropped there by hand, and clean must not take those with it. The gap
# file goes too — it is provisioned from config/, but it is generated,
# and generate-all.sh puts it straight back.
clean:
	rm -rf $(OUT)
	rm -f $(GENERATED)
