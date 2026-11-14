#!/bin/sh
# LocalBotz — macOS / Linux starter. Just install LocalBotz, that's it.
# The user downloads nothing else separately — no Git, no Python,
# no LM Studio, no model. This one step does it all where it can:
#   1. Python 3.11+ — installed if missing (brew on macOS, apt/dnf on Linux)
#   2. LM Studio — installed if missing (official install script, gives `lms`)
#   3. Qwen3.5 model — downloaded with `lms get`, loaded, server started
#   4. LocalBotz — virtual environment, Python packages, then the app
#      on http://127.0.0.1:8000
# First run needs internet and takes a while (Qwen3.5 model ~6 GB).
# Later runs are fast — everything already installed is skipped.
# Usage:
#   chmod +x start.sh   # first time only
#   ./start.sh                    # normal — full auto-setup, then run
#   ./start.sh --mock             # test without a model
#   ./start.sh --light            # lightweight: core only, no browser
#   ./start.sh --no-browser       # same as --light
#   ./start.sh --with-browser     # explicit: install browser deps too
#   ./start.sh --skip-setup       # skip Python / LM Studio / model setup
# The --light / --no-browser / --with-browser / --skip-setup flags are
# consumed here and are NOT passed to app.py; other flags (--mock,
# --port) are passed on.
set -e
cd "$(dirname "$0")"

BROWSER=1
SKIPSETUP=0
APP_ARGS=""
for a in "$@"; do
  case "$a" in
    --light|--no-browser) BROWSER=0 ;;
    --with-browser) BROWSER=1 ;;
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

if [ ! -x ".venv/bin/python" ]; then
  echo "[LocalBotz] Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi

echo "[LocalBotz] Installing core dependencies (lightweight)..."
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

if [ "$BROWSER" = "1" ]; then
  echo "[LocalBotz] Installing browser dependencies (Playwright + Chromium)..."
  .venv/bin/python -m pip install -q -r requirements-browser.txt
  echo "[LocalBotz] Installing Playwright Chromium (skipped if already installed)..."
  .venv/bin/playwright install chromium || echo "[LocalBotz] NOTE: Chromium install failed — browser tools will report 'not installed'. The rest of the app still works."
else
  echo "[LocalBotz] Lightweight install: browser automation skipped."
  echo "[LocalBotz] Browser tools will say 'Playwright is not installed' until you run ./start.sh --with-browser"
fi

echo "[LocalBotz] Starting on http://127.0.0.1:8000 — open that in your browser."
echo "[LocalBotz] Python, LM Studio and Qwen3.5 were set up by this script —"
echo "[LocalBotz] no separate downloads were needed."
# shellcheck disable=SC2086
exec .venv/bin/python app.py $APP_ARGS
