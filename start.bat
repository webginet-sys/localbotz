@echo off
REM LocalBotz — Windows starter (Command Prompt or PowerShell).
REM Installs the lightweight core first (fastapi, uvicorn, httpx), then
REM browser automation (Playwright + Chromium) unless you ask for light.
REM Usage:  start.bat                 (normal, needs LM Studio running)
REM         start.bat --mock          (test without a model)
REM         start.bat --light         (lightweight: core only, no browser)
REM         start.bat --no-browser    (same as --light)
REM         start.bat --with-browser  (explicit: install browser deps too)
REM The --light / --no-browser / --with-browser flags are consumed here
REM and are NOT passed to app.py; other flags (--mock, --port) are passed on.
REM In PowerShell, run:  .\start.bat  -- or:  .\start.bat --mock
REM (If PowerShell blocks scripts, this is a .bat file, not a .ps1, so
REM  it runs normally; you can also double-click it in Explorer.)

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set BROWSER=1
set APP_ARGS=
for %%A in (%*) do (
  if "%%A"=="--light" set BROWSER=0
  if "%%A"=="--no-browser" set BROWSER=0
  if "%%A"=="--with-browser" set BROWSER=1
  if not "%%A"=="--light" if not "%%A"=="--no-browser" if not "%%A"=="--with-browser" set APP_ARGS=!APP_ARGS! %%A
)

where python >nul 2>&1
if errorlevel 1 (
  echo [LocalBotz] Python was not found. Install Python 3.11+ from
  echo https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo then close and reopen this window and run start.bat again.
  pause
  exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [LocalBotz] %%v

if not exist ".venv\Scripts\python.exe" (
  echo [LocalBotz] Creating virtual environment (.venv)...
  python -m venv .venv
  if errorlevel 1 (
    echo [LocalBotz] Failed to create .venv. Try: python -m venv .venv
    pause
    exit /b 1
  )
)

echo [LocalBotz] Installing core dependencies (lightweight)...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [LocalBotz] pip install failed. See the error above.
  pause
  exit /b 1
)

if "%BROWSER%"=="1" (
  echo [LocalBotz] Installing browser dependencies (Playwright + Chromium)...
  ".venv\Scripts\python.exe" -m pip install -q -r requirements-browser.txt
  echo [LocalBotz] Installing Playwright Chromium (skipped if already installed)...
  ".venv\Scripts\playwright.exe" install chromium
  if errorlevel 1 echo [LocalBotz] NOTE: Chromium install failed — browser tools will report 'not installed'. The rest of the app still works.
) else (
  echo [LocalBotz] Lightweight install: browser automation skipped.
  echo [LocalBotz] Browser tools will say 'Playwright is not installed' until you run start.bat --with-browser
)

echo [LocalBotz] Starting on http://127.0.0.1:8000 — open that in your browser.
echo [LocalBotz] Make sure LM Studio is running with Qwen3.5 loaded and its
echo [LocalBotz] local server started (Developer tab, Start Server).
".venv\Scripts\python.exe" app.py %APP_ARGS%
