#!/bin/sh
# LocalBotz — macOS / Linux starter.
# Installs the lightweight core first (fastapi, uvicorn, httpx), then
# browser automation (Playwright + Chromium) unless you ask for light.
# Usage:
#   chmod +x start.sh   # first time only
#   ./start.sh                    # normal, needs LM Studio running
#   ./start.sh --mock             # test without a model
#   ./start.sh --light            # lightweight: core only, no browser
#   ./start.sh --no-browser       # same as --light
#   ./start.sh --with-browser     # explicit: install browser deps too
# The --light / --no-browser / --with-browser flags are consumed here
# and are NOT passed to app.py; other flags (--mock, --port) are passed on.
set -e
cd "$(dirname "$0")"

BROWSER=1
APP_ARGS=""
for a in "$@"; do
  case "$a" in
    --light|--no-browser) BROWSER=0 ;;
    --with-browser) BROWSER=1 ;;
    *) APP_ARGS="$APP_ARGS $a" ;;
  esac
done

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
echo "[LocalBotz] Make sure LM Studio is running with Qwen3.5 loaded and its"
echo "[LocalBotz] local server started (Developer tab, Start Server)."
# shellcheck disable=SC2086
exec .venv/bin/python app.py $APP_ARGS
