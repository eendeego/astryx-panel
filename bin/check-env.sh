#!/usr/bin/env bash
# Check that everything needed to compile WLED is present.
# Works on Linux and macOS. Exits non-zero if a hard requirement is missing.
# Every problem is printed together with a "fix:" command that resolves it.
#
# Usage: ./check-env.sh [-q]
#   -q   quiet: only print problems

set -u

QUIET=0
[ "${1:-}" = "-q" ] && QUIET=1

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
WLED_DIR=$REPO_DIR/WLED                     # in-repo checkout, git-ignored
WLED_REPO_URL=https://github.com/wled/WLED
WLED_VERSION=
# shellcheck source=../config/wled.conf
[ -f "$REPO_DIR/config/wled.conf" ] && . "$REPO_DIR/config/wled.conf"

FAILURES=0
WARNINGS=0

pass() { [ "$QUIET" -eq 1 ] || printf 'PASS  %s\n' "$1"; }
warn() { printf 'WARN  %s\n' "$1"; WARNINGS=$((WARNINGS + 1)); fix "${2:-}"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); fix "${2:-}"; }

# fix <text>: print a (possibly multi-line) remedy indented under the issue.
fix() {
  [ -n "$1" ] || return 0
  local first=1 line
  while IFS= read -r line; do
    if [ "$first" -eq 1 ]; then printf '      fix: %s\n' "$line"; first=0
    else printf '           %s\n' "$line"; fi
  done <<< "$1"
}

# --- Package-manager hint for system tools ------------------------------------
if [ "$(uname)" = "Darwin" ]; then
  PKG_INSTALL="brew install"
elif command -v apt-get >/dev/null 2>&1; then
  PKG_INSTALL="sudo apt-get install -y"
elif command -v dnf >/dev/null 2>&1; then
  PKG_INSTALL="sudo dnf install -y"
elif command -v pacman >/dev/null 2>&1; then
  PKG_INSTALL="sudo pacman -S --needed"
else
  PKG_INSTALL="<your package manager> install"
fi

# --- PATH self-heal for PlatformIO (same location build.sh uses) --------------
if ! command -v pio >/dev/null 2>&1 && [ -x "$HOME/.platformio/penv/bin/pio" ]; then
  PATH="$HOME/.platformio/penv/bin:$PATH"
fi
export PATH

# --- WLED checkout ------------------------------------------------------------
if [ -f "$WLED_DIR/platformio.ini" ]; then
  pass "WLED checkout found at $WLED_DIR"
  if [ -n "$WLED_VERSION" ]; then
    HEAD_SHA=$(git -C "$WLED_DIR" rev-parse HEAD 2>/dev/null || true)
    WANT_SHA=$(git -C "$WLED_DIR" rev-parse --verify -q "$WLED_VERSION^{commit}" 2>/dev/null || true)
    HAVE_DESC=$(git -C "$WLED_DIR" describe --tags --always 2>/dev/null || echo unknown)
    if [ -n "$HEAD_SHA" ] && [ "$HEAD_SHA" = "$WANT_SHA" ]; then
      pass "WLED checkout is at $WLED_VERSION (config/wled.conf)"
    else
      warn "WLED checkout is at $HAVE_DESC, config/wled.conf wants $WLED_VERSION" \
           "git -C \"$WLED_DIR\" fetch --tags origin && git -C \"$WLED_DIR\" checkout $WLED_VERSION"
    fi
  fi
else
  fail "WLED checkout not found (expected $WLED_DIR with platformio.ini)" \
       "git clone${WLED_VERSION:+ --branch $WLED_VERSION} $WLED_REPO_URL \"$WLED_DIR\""
fi

# --- Node.js ------------------------------------------------------------------
REQUIRED_NODE_VERSION=20
if [ -f "$WLED_DIR/.nvmrc" ]; then
  REQUIRED_NODE_VERSION=$(sed 's/^v//' "$WLED_DIR/.nvmrc" | tr -d '[:space:]')
fi
REQUIRED_NODE_MAJOR=${REQUIRED_NODE_VERSION%%.*}

# Node installation method is the user's choice (nodejs.org, distro package,
# any version manager); we only state the version and that it must be on PATH.
NODE_FIX="install Node.js $REQUIRED_NODE_VERSION (pinned by WLED/.nvmrc) using your preferred method
and make sure 'node' and 'npm' are on PATH — see https://nodejs.org/en/download"

if command -v node >/dev/null 2>&1; then
  NODE_VERSION=$(node --version | sed 's/^v//')
  NODE_MAJOR=${NODE_VERSION%%.*}
  if [ "$NODE_MAJOR" -ge "$REQUIRED_NODE_MAJOR" ] 2>/dev/null; then
    pass "Node.js v$NODE_VERSION (>= $REQUIRED_NODE_MAJOR required)"
  else
    fail "Node.js v$NODE_VERSION is too old (>= $REQUIRED_NODE_MAJOR required)" "$NODE_FIX"
  fi
else
  fail "Node.js not found (need >= $REQUIRED_NODE_MAJOR)" "$NODE_FIX"
fi
if command -v npm >/dev/null 2>&1; then
  pass "npm $(npm --version)"
else
  fail "npm not found (ships with Node.js — reinstall Node)" "$NODE_FIX"
fi

# --- Python / PlatformIO ------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  pass "$(python3 --version 2>&1)"
else
  if [ "$(uname)" = "Darwin" ]; then
    fail "python3 not found (PlatformIO requires Python 3)" "$PKG_INSTALL python"
  else
    fail "python3 not found (PlatformIO requires Python 3)" "$PKG_INSTALL python3 python3-venv"
  fi
fi

# Install PlatformIO into ~/.platformio/penv: that is where build.sh and this
# script look for it, and the WLED requirements.txt pins the tested version.
PIO_PENV="$HOME/.platformio/penv"
if [ -f "$WLED_DIR/requirements.txt" ]; then
  PIO_PKGS="-r \"$WLED_DIR/requirements.txt\""
else
  PIO_PKGS="platformio"
fi
PIO_FIX="python3 -m venv \"$PIO_PENV\" && \"$PIO_PENV/bin/pip\" install $PIO_PKGS"
if command -v pio >/dev/null 2>&1; then
  pass "$(pio --version 2>/dev/null)"
else
  fail "PlatformIO not found" "$PIO_FIX"
fi

# --- Misc tools ---------------------------------------------------------------
if command -v git >/dev/null 2>&1; then
  pass "git $(git --version | awk '{print $3}')"
else
  fail "git not found (PlatformIO needs it to fetch libraries from GitHub)" "$PKG_INSTALL git"
fi

# --- Serial access for flashing (Linux only; macOS needs no group) ------------
if [ "$(uname)" = "Linux" ]; then
  if id -nG 2>/dev/null | tr ' ' '\n' | grep -qx dialout; then
    pass "User is in the dialout group (USB flashing)"
  else
    warn "User not in dialout group — flashing over USB may fail" \
         "sudo usermod -aG dialout \"\$USER\"   # then log out and back in"
  fi
fi

# --- Summary ------------------------------------------------------------------
echo
if [ "$FAILURES" -gt 0 ]; then
  echo "Result: $FAILURES failure(s), $WARNINGS warning(s) — build will NOT work."
  echo "Run the 'fix:' commands above, then re-run $0."
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo "Result: OK with $WARNINGS warning(s)."
else
  echo "Result: all checks passed."
fi
