#!/bin/sh
# LocalBotz — macOS / Linux starter. Just install LocalBotz, that's it.
# The user downloads nothing else separately — no Git, no Python,
# no LM Studio, no model. This one step does it all where it can:
#   1. Python 3.11+ — installed if missing (brew on macOS, apt/dnf on Linux)
#   2. LM Studio — installed if missing (official install script, gives `lms`)
#   3. Qwen3.5 model — downloaded with `lms get`, loaded, server started
#   4. LocalBotz — virtual environment, ALL Python packages, then the app
#      on http://127.0.0.1:8000
#   5. Browser automation — Playwright + Chromium, installed upfront
#      in this same install step, and verified (Chromium launches).
#      There is no light / optional install: if the user needs to run
#      browser automation, whatever they need is installed before,
#      in the installation. Nothing is left to install later.
# First run needs internet and takes a while (Qwen3.5 model ~6 GB,
# Chromium ~150 MB). Later runs are fast — everything already
# installed is skipped.
# Usage:
#   chmod +x start.sh   # first time only
#   ./start.sh                    # normal — full install, then run
#   ./start.sh --mock             # test without a model
#   ./start.sh --skip-setup       # skip Python / LM Studio / model setup
# NOTE: --light / --no-browser are no longer supported. They used to
# skip browser automation; now the full install always includes it,
# so those flags are ignored with a warning.
# The --skip-setup flag is consumed here and is NOT passed to app.py;
# other flags (--mock, --port) are passed on.
set -e
cd "$(dirname "$0")"

SKIPSETUP=0
APP_ARGS=""
for a in "$@"; do
  case "$a" in
    --light|--no-browser) echo "[LocalBotz] NOTE: $a is no longer supported — the full install always includes browser automation." ;;
    --skip-setup) SKIPSETUP=1 ;;
    *) APP_ARGS="$APP_ARGS $a" ;;
  esac
done

if [ "$SKIPSETUP" = "0" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[LocalBotz] Python was not found — installing it for you now."
    if command -v brew >/dev/null 2>&1; then
      brew install python
    elif command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y python3
    else
      echo "[LocalBotz] Could not install Python automatically. Install Python 3.11+ from https://www.python.org/downloads/ and run ./start.sh again."
      exit 1
    fi
  fi

  # LM Studio + Qwen3.5, best-effort: if any step fails, LocalBotz still
  # starts and its status line tells you LM Studio is not reachable yet.
  if ! command -v lms >/dev/null 2>&1; then
    echo "[LocalBotz] LM Studio was not found — installing it for you now."
    if curl -fsSL https://lmstudio.ai/install.sh | sh; then
      echo "[LocalBotz] LM Studio installed."
    else
      echo "[LocalBotz] Could not install LM Studio automatically. Install it once from https://lmstudio.ai/ and run ./start.sh again."
    fi
  fi
  if command -v lms >/dev/null 2>&1; then
    echo "[LocalBotz] Setting up LM Studio (model Qwen3.5 + local server)..."
    lms bootstrap >/dev/null 2>&1 || true
    if ! lms ls 2>/dev/null | grep -qi "qwen3.5"; then
      echo "[LocalBotz] Downloading the Qwen3.5 model (~6 GB, first time only)..."
      lms get qwen/qwen3.5-9b --yes || lms get qwen3.5-9b --yes || true
    fi
    lms load qwen3.5-9b --yes >/dev/null 2>&1 || lms load qwen/qwen3.5-9b --yes >/dev/null 2>&1 || true
    lms server start >/dev/null 2>&1 || true
    echo "[LocalBotz] LM Studio server should now be on http://localhost:1234"
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[LocalBotz] python3 was not found. Install Python 3.11+ first:"
  echo "  macOS:   brew install python   (or https://www.python.org/downloads/macos/)"
  echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
  echo "  Fedora:  sudo dnf install python3"
  exit 1
fi

echo "[LocalBotz] $(python3 --version)"

# Where should the data live? Asked once, on first install. On Mac/Linux
# there are no C:/D: drives — type a folder path, or press Enter to keep
# the data in the app folder. (On Windows, start.bat asks C: or D:.)
if ! grep -q "^LOCALBOTZ_DATA_DIR=" .env 2>/dev/null && [ ! -f data/settings.json ] && [ ! -f data/bots.json ]; then
  printf '[LocalBotz] Where should LocalBotz keep its data (bots, memory, offices, documents)?\n'
  printf '[LocalBotz] Press Enter for the app folder, or type a full folder path: '
  read -r DATA_ANSWER || true
  if [ -n "$DATA_ANSWER" ]; then
    echo "LOCALBOTZ_DATA_DIR=$DATA_ANSWER" >> .env
    echo "[LocalBotz] Data will be kept in $DATA_ANSWER"
  fi
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[LocalBotz] Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi

echo "[LocalBotz] Installing core dependencies (lightweight)..."
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

# Browser automation — always installed upfront, in the full install.
echo "[LocalBotz] Installing browser automation (Playwright + Chromium)..."
echo "[LocalBotz] This is part of the full install, so browser automation"
echo "[LocalBotz] is ready before you need it — nothing to install later."
.venv/bin/python -m pip install -q -r requirements-browser.txt
echo "[LocalBotz] Installing Playwright Chromium (skipped if already installed)..."
.venv/bin/playwright install chromium
# On Linux, Chromium also needs system libraries; try to install them.
# stdin is closed and a timeout is used so this can never hang waiting
# for a sudo password — if it cannot install them, the check below
# reports whether Chromium still launches, and the app still starts.
if [ "$(uname)" = "Linux" ]; then
  (timeout 180 .venv/bin/playwright install-deps chromium </dev/null >/dev/null 2>&1 || echo "[LocalBotz] NOTE: could not install Chromium system libraries automatically — if Chromium fails to launch, run: .venv/bin/playwright install-deps chromium") || true
fi
# Desktop control — always installed upfront, in the full install.
echo "[LocalBotz] Installing desktop control (mouse/keyboard/window tools)..."
echo "[LocalBotz] This is part of the full install, so a bot can use the"
echo "[LocalBotz] desktop apps on this computer — with nothing to install later."
.venv/bin/python -m pip install -q -r requirements-desktop.txt
# Live voice — best-effort only: if this fails, the app still starts
# and Talk still works; the Live Voice page says what is missing.
echo "[LocalBotz] Installing live voice support (Gemini Live + WebSocket)..."
.venv/bin/python -m pip install -q -r requirements-live.txt || echo "[LocalBotz] NOTE: live voice install did not work. Chat and Talk still work; live voice needs a Gemini key and this package."
echo "[LocalBotz] Verifying the full install (Python, packages, Chromium)..."
.venv/bin/python scripts/check_install.py || echo "[LocalBotz] Install check reported a problem above — browser automation may not work yet. The app will still start."

echo "[LocalBotz] Starting on http://127.0.0.1:8000 — open that in your browser."
echo "[LocalBotz] Python, LM Studio and Qwen3.5 were set up by this script —"
echo "[LocalBotz] no separate downloads were needed."
# shellcheck disable=SC2086
exec .venv/bin/python app.py $APP_ARGS
