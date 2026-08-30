#!/usr/bin/env bash
# Check that everything needed to compile WLED is present.
# Works on Linux and macOS. Exits non-zero if a hard requirement is missing.
#
# Usage: ./check-env.sh [-q]
#   -q   quiet: only print problems

set -u

QUIET=0
[ "${1:-}" = "-q" ] && QUIET=1

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WLED_DIR=$SCRIPT_DIR/../../WLED

FAILURES=0
WARNINGS=0

pass() { [ "$QUIET" -eq 1 ] || printf 'PASS  %s\n' "$1"; }
warn() { printf 'WARN  %s\n' "$1"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

# --- PATH self-heal (same locations build.sh uses; harmless if absent) -------
if ! command -v node >/dev/null 2>&1; then
  for d in "$HOME"/.local/share/fnm/node-versions/*/installation/bin \
           "$HOME/Library/Application Support/fnm"/node-versions/*/installation/bin; do
    if [ -x "$d/node" ]; then PATH="$d:$PATH"; break; fi
  done
fi
if ! command -v pio >/dev/null 2>&1 && [ -x "$HOME/.platformio/penv/bin/pio" ]; then
  PATH="$HOME/.platformio/penv/bin:$PATH"
fi
export PATH

# --- WLED checkout ------------------------------------------------------------
if [ -f "$WLED_DIR/platformio.ini" ]; then
  pass "WLED checkout found at $WLED_DIR"
else
  fail "WLED checkout not found (expected $WLED_DIR with platformio.ini)"
fi

if [ -f "$WLED_DIR/platformio_override.ini" ]; then
  pass "platformio_override.ini present in WLED checkout"
else
  warn "platformio_override.ini missing in WLED checkout — custom envs unavailable; recreate with: ln -s ../astryx-panel/platformio_override.ini $WLED_DIR/platformio_override.ini"
fi

# --- Node.js ------------------------------------------------------------------
REQUIRED_NODE_MAJOR=20
if [ -f "$WLED_DIR/.nvmrc" ]; then
  REQUIRED_NODE_MAJOR=$(sed 's/^v//; s/\..*//' "$WLED_DIR/.nvmrc")
fi
if command -v node >/dev/null 2>&1; then
  NODE_VERSION=$(node --version | sed 's/^v//')
  NODE_MAJOR=${NODE_VERSION%%.*}
  if [ "$NODE_MAJOR" -ge "$REQUIRED_NODE_MAJOR" ] 2>/dev/null; then
    pass "Node.js v$NODE_VERSION (>= $REQUIRED_NODE_MAJOR required)"
  else
    fail "Node.js v$NODE_VERSION is too old (>= $REQUIRED_NODE_MAJOR required)"
  fi
else
  fail "Node.js not found (need >= $REQUIRED_NODE_MAJOR; install via fnm/nvm or https://nodejs.org)"
fi
if command -v npm >/dev/null 2>&1; then
  pass "npm $(npm --version)"
else
  fail "npm not found (ships with Node.js)"
fi

# --- Python / PlatformIO ------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  pass "$(python3 --version 2>&1)"
else
  fail "python3 not found (PlatformIO requires Python 3)"
fi
if command -v pio >/dev/null 2>&1; then
  pass "$(pio --version 2>/dev/null)"
else
  fail "PlatformIO not found (pip3 install -r $WLED_DIR/requirements.txt, or https://platformio.org/install)"
fi

# --- Misc tools ---------------------------------------------------------------
if command -v git >/dev/null 2>&1; then
  pass "git $(git --version | awk '{print $3}')"
else
  fail "git not found (PlatformIO needs it to fetch libraries from GitHub)"
fi

# --- Repo bootstrap state (fixable by bin/build.sh, hence warnings) -----------
if [ -d "$WLED_DIR/node_modules" ]; then
  pass "Node dependencies installed (node_modules)"
else
  warn "node_modules missing — bin/build.sh will run 'npm ci' on first build"
fi
if ls "$WLED_DIR"/wled00/html_*.h >/dev/null 2>&1; then
  pass "Web UI headers generated (wled00/html_*.h)"
else
  warn "Web UI headers not generated yet — bin/build.sh will run 'npm run build'"
fi

# --- Serial access for flashing (Linux only; macOS needs no group) ------------
if [ "$(uname)" = "Linux" ]; then
  if id -nG 2>/dev/null | tr ' ' '\n' | grep -qx dialout; then
    pass "User is in the dialout group (USB flashing)"
  else
    warn "User not in dialout group — flashing over USB may fail (sudo usermod -aG dialout \$USER, then re-login)"
  fi
fi

# --- Summary ------------------------------------------------------------------
echo
if [ "$FAILURES" -gt 0 ]; then
  echo "Result: $FAILURES failure(s), $WARNINGS warning(s) — build will NOT work."
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo "Result: OK with $WARNINGS warning(s) — bin/build.sh should handle the rest."
else
  echo "Result: all checks passed."
fi
