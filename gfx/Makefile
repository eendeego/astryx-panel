# Rebuilds the panel artwork from the sources in raw/.
#
# Prefer gfx/generate-all.sh, which checks the external tools are present
# and runs this from gfx/ whatever the current directory is.
#
# Every recipe below is one of the tested (good) invocations documented in
# README.md; keep the two in step. A target is remade when its source or
# the script that produces it changes, which is what keeps a repeat run
# cheap: each marquee GIF is one ImageMagick invocation per frame.
#
# Finished GIFs land in config/gifs/, where bin/gen-presets.sh and
# bin/provision.sh pick them up, and are versioned with the rest of the
# panel's artwork. Everything else is an intermediate and stays in out/,
# which is not versioned.

RAW  := raw
OUT  := out
GIFS := ../config/gifs

MARQUEE := make-marquee.sh
GAP     := make-gap.py

# Panel edge, in pixels. Also hardcoded as the canvas size in make-marquee.sh.
SIZE := 64

GENERATED := $(GIFS)/astryx-word.gif \
             $(GIFS)/astryx-word-c.gif

TARGETS := $(OUT)/astryx-word.png \
           $(OUT)/astryx-gap.json \
           $(GENERATED)

.PHONY: all clean
all: $(TARGETS)

# The wordmark, rasterized to panel width. Only the width is pinned: -a
# keeps the aspect ratio, and the marquee script reads the height it gets.
$(OUT)/astryx-word.png: $(RAW)/astryx-word.svg | $(OUT)
	rsvg-convert -o $@ -w $(SIZE) -a $<

$(GIFS)/astryx-word.gif: $(OUT)/astryx-word.png $(MARQUEE) | $(GIFS)
	./$(MARQUEE) $< $@

$(GIFS)/astryx-word-c.gif: $(OUT)/astryx-word.png $(MARQUEE) | $(GIFS)
	./$(MARQUEE) -c $< $@

# -t 255 -b white, and the inverted polarity it produces, are deliberate:
# see the firmware caveat in README.md before touching this recipe. The
# explicit paths are the same files make-gap.py would default to.
$(OUT)/astryx-gap.json: $(RAW)/astryx.svg $(GAP) | $(OUT)
	python3 $(GAP) -t 255 -s $(SIZE) -b white $< $@

$(OUT) $(GIFS):
	mkdir -p $@

# Only what this Makefile writes: config/gifs/ also holds GIFs that were
# dropped there by hand, and clean must not take those with it.
clean:
	rm -rf $(OUT)
	rm -f $(GENERATED)
