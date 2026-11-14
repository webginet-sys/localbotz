@echo off
REM LocalBotz — Windows starter. Just install LocalBotz, that's it.
REM
REM Double-click this file (or install.bat, which calls this file).
REM The user does NOT download anything else separately — no Git,
REM no Python, no LM Studio, no model. This one step does it all:
REM   1. Python 3.12 — downloaded and installed if missing (per-user,
REM      no admin needed, added to PATH)
REM   2. LM Studio — installed if missing (winget, per-user)
REM   3. Qwen3.5 model — downloaded with LM Studio's own `lms` tool,
REM      then loaded, then the local server started on port 1234
REM   4. LocalBotz — virtual environment, ALL Python packages, then the
REM      app on http://127.0.0.1:8000
REM   5. Browser automation — Playwright + Chromium, installed upfront
REM      in this same install step, and verified (Chromium launches).
REM   6. Desktop control — pyautogui + pygetwindow (+ pywinauto on
REM      Windows), installed upfront in this same install step, so a
REM      bot can use the desktop apps on this computer.
REM      There is no light / optional install: if the user needs to run
REM      browser automation or use the desktop, whatever they need is
REM      installed before, in the installation. Nothing is left to
REM      install later.
REM
REM First run needs internet and takes a while (Python ~30 MB,
REM LM Studio several hundred MB, Qwen3.5 model ~6 GB, Chromium ~150 MB).
REM Later runs are fast — everything already installed is skipped.
REM
REM Usage:  start.bat                 (normal — full install, then run)
REM         start.bat --mock          (test without a model)
REM         start.bat --skip-setup    (skip Python / LM Studio / model setup,
REM                                    just start the app — use only if you
REM                                    already set Python + LM Studio up)
REM NOTE: --light / --no-browser are no longer supported. They used to
REM skip browser automation; now the full install always includes it,
REM so those flags are ignored with a warning.
REM The --skip-setup flag is consumed here and is NOT passed to app.py;
REM other flags (--mock, --port) are passed on.
REM In PowerShell, run:  .\start.bat  -- or double-click it in Explorer.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set SKIPSETUP=0
set APP_ARGS=
for %%A in (%*) do (
  if "%%A"=="--light" echo [LocalBotz] NOTE: --light is no longer supported — the full install always includes browser automation.
  if "%%A"=="--no-browser" echo [LocalBotz] NOTE: --no-browser is no longer supported — the full install always includes browser automation.
  if "%%A"=="--skip-setup" set SKIPSETUP=1
  if not "%%A"=="--light" if not "%%A"=="--no-browser" if not "%%A"=="--with-browser" if not "%%A"=="--skip-setup" set APP_ARGS=!APP_ARGS! %%A
)

if "%SKIPSETUP%"=="1" goto :have_python

REM ---------- Step 1: Python (auto-install if missing) ----------
where python >nul 2>&1
if not errorlevel 1 goto :have_python
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" goto :have_python
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" goto :have_python
echo [LocalBotz] Python was not found — installing it for you now.
echo [LocalBotz] This is part of the LocalBotz install. No separate download.
where winget >nul 2>&1
if not errorlevel 1 (
  echo [LocalBotz] Installing Python 3.12 with winget...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
  if not errorlevel 1 goto :python_installed
  echo [LocalBotz] winget install did not work, trying the direct download...
)
echo [LocalBotz] Downloading the Python installer...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\python-3.12.10-amd64.exe'"
if errorlevel 1 (
  echo [LocalBotz] Could not download Python. Check your internet connection,
  echo then run start.bat again. Or install Python 3.12 from python.org
  echo (tick "Add python.exe to PATH") and run start.bat again.
  pause
  exit /b 1
)
echo [LocalBotz] Installing Python 3.12 (quiet, for your user account only)...
"%TEMP%\python-3.12.10-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
if errorlevel 1 (
  echo [LocalBotz] Python install failed. Try running start.bat again,
  echo or install Python 3.12 from python.org and run start.bat again.
  pause
  exit /b 1
)
:python_installed
REM The new Python may not be on PATH in this window yet — use its
REM usual per-user location if it is there.
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PATH=%LOCALAPPDATA%\Programs\Python\Python312\;%LOCALAPPDATA%\Programs\Python\Python312\Scripts\;%PATH%"
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PATH=%LOCALAPPDATA%\Programs\Python\Python313\;%LOCALAPPDATA%\Programs\Python\Python313\Scripts\;%PATH%"
where python >nul 2>&1
if errorlevel 1 (
  echo [LocalBotz] Python was installed but is still not on PATH in this window.
  echo [LocalBotz] Close this window and double-click start.bat again.
  pause
  exit /b 1
)

:have_python
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [LocalBotz] %%v

if "%SKIPSETUP%"=="1" goto :venv

REM ---------- Step 2 + 3: LM Studio + Qwen3.5 (auto-install if missing) ----------
REM Check for LM Studio: the `lms` tool, or the app folder.
where lms >nul 2>&1
if not errorlevel 1 goto :have_lmstudio
if exist "%LOCALAPPDATA%\LM-Studio\LM Studio.exe" goto :have_lmstudio
if exist "%LOCALAPPDATA%\Programs\LM-Studio\LM Studio.exe" goto :have_lmstudio
echo [LocalBotz] LM Studio was not found — installing it for you now.
echo [LocalBotz] This is part of the LocalBotz install. No separate download.
where winget >nul 2>&1
if not errorlevel 1 (
  echo [LocalBotz] Installing LM Studio with winget (this takes a few minutes)...
  winget install --id=ElementLabs.LMStudio -e --silent --accept-package-agreements --accept-source-agreements
  if not errorlevel 1 goto :lmstudio_installed
  echo [LocalBotz] winget install did not work. Please install LM Studio
  echo [LocalBotz] once from https://lmstudio.ai/ and run start.bat again.
  echo [LocalBotz] Continuing without it for now — LocalBotz will start,
  echo [LocalBotz] but chat needs LM Studio running. Press any key to continue.
  pause
  goto :venv
)
echo [LocalBotz] winget was not found. Please install LM Studio once from
echo [LocalBotz] https://lmstudio.ai/ and run start.bat again.
echo [LocalBotz] Continuing without it for now — press any key to continue.
pause
goto :venv
:lmstudio_installed
echo [LocalBotz] LM Studio installed.

:have_lmstudio
REM Make `lms` available, then download the model and start the server.
REM All of these steps are best-effort: if one fails, LocalBotz still
REM starts, and its status line tells you LM Studio is not reachable yet.
where lms >nul 2>&1
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\LM-Studio\bin\lms.exe" set "PATH=%LOCALAPPDATA%\LM-Studio\bin\;%PATH%"
)
where lms >nul 2>&1
if errorlevel 1 goto :venv
echo [LocalBotz] Setting up LM Studio (model Qwen3.5 + local server)...
lms bootstrap >nul 2>&1
lms ls 2>nul | findstr /I "qwen3.5" >nul
if not errorlevel 1 goto :model_present
echo [LocalBotz] Downloading the Qwen3.5 model (~6 GB, first time only)...
lms get qwen/qwen3.5-9b --yes
if errorlevel 1 lms get qwen3.5-9b --yes
:model_present
echo [LocalBotz] Loading Qwen3.5 and starting the LM Studio local server...
lms load qwen3.5-9b --yes >nul 2>&1
if errorlevel 1 lms load qwen/qwen3.5-9b --yes >nul 2>&1
lms server start >nul 2>&1
echo [LocalBotz] LM Studio server should now be on http://localhost:1234

:venv
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

REM ---------- Browser automation — always installed upfront ----------
echo [LocalBotz] Installing browser automation (Playwright + Chromium)...
echo [LocalBotz] This is part of the full install, so browser automation
echo [LocalBotz] is ready before you need it — nothing to install later.
".venv\Scripts\python.exe" -m pip install -q -r requirements-browser.txt
if errorlevel 1 (
  echo [LocalBotz] Playwright install failed. See the error above.
  pause
  exit /b 1
)
echo [LocalBotz] Installing Playwright Chromium (skipped if already installed)...
".venv\Scripts\playwright.exe" install chromium
if errorlevel 1 (
  echo [LocalBotz] Chromium install failed. Browser automation will not work.
  echo [LocalBotz] Try running start.bat again, then check your internet.
  pause
  exit /b 1
)
REM ---------- Desktop control — always installed upfront ----------
echo [LocalBotz] Installing desktop control (mouse/keyboard/window tools)...
echo [LocalBotz] This is part of the full install, so a bot can use the
echo [LocalBotz] desktop apps on this computer — Excel, the BOQ, the old
echo [LocalBotz] accounting software — with nothing to install later.
".venv\Scripts\python.exe" -m pip install -q -r requirements-desktop.txt
if errorlevel 1 (
  echo [LocalBotz] Desktop control install failed. See the error above.
  pause
  exit /b 1
)
echo [LocalBotz] Verifying the full install (Python, packages, Chromium)...
".venv\Scripts\python.exe" scripts\check_install.py
if errorlevel 1 (
  echo [LocalBotz] Install check reported a problem above. Fix it and
  echo [LocalBotz] run start.bat again, or continue anyway — the app
  echo [LocalBotz] will start, but browser automation may not work.
  pause
)

echo [LocalBotz] Starting on http://127.0.0.1:8000 — open that in your browser.
".venv\Scripts\python.exe" app.py %APP_ARGS%
