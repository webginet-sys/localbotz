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
REM      install later. Live voice (Gemini Live) is installed
REM      best-effort in the same step — if it fails, the app still
REM      starts and Talk still works.
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

REM If this file was run from inside the ZIP without extracting, the app
REM files are not really here — tell the user to extract first.
if not exist "requirements.txt" (
  echo [LocalBotz] The app files are not here — the ZIP was not extracted.
  echo [LocalBotz] Right-click the LocalBotz ZIP, choose "Extract All",
  echo [LocalBotz] then double-click install.bat inside the extracted folder.
  pause
  exit /b 1
)
echo [LocalBotz] %DATE% %TIME% - start.bat started %* >> install.log

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
REM A real Python 3.11+ is required, and `where python` alone is not
REM enough to prove it: on Windows the Microsoft Store shim answers
REM `where python` but is not Python at all (it just opens the Store),
REM and an old Python (3.9/3.10) cannot run the app — it crashes on
REM start and the window closes before you can read the error.
set PYOK=0
set PYVER=
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
if defined PYVER (
  for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do set PYMAJ=%%a& set PYMIN=%%b
  if "!PYMAJ!"=="3" if defined PYMIN if !PYMIN! GEQ 11 set PYOK=1
)
if "%PYOK%"=="1" goto :have_python
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" goto :have_python
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" goto :have_python
echo [LocalBotz] Python 3.11 or newer was not found — installing Python 3.12 for you now.
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
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [LocalBotz] %%v >> install.log

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

REM ---------- Where should the data live? Asked once, on first install. ----------
REM The app's memory — bots, memory, offices, workrooms, documents — can
REM live in the app folder (C: drive) or on the D: drive, so the C: drive
REM stays light. Asked once only: skipped when LOCALBOTZ_DATA_DIR is
REM already set, or when the data folder already has content.
findstr /B /C:"LOCALBOTZ_DATA_DIR=" .env >nul 2>&1
if not errorlevel 1 goto :venv
if exist "data\settings.json" goto :venv
if exist "data\bots.json" goto :venv
echo.
echo [LocalBotz] Where should LocalBotz keep its data — your bots, memory,
echo [LocalBotz] offices, workrooms and documents? The app itself stays
echo [LocalBotz] here; only the data moves. Pick D: to keep C: light.
echo [LocalBotz]   [1] C: drive - in the LocalBotz folder
echo [LocalBotz]   [2] D: drive - D:\LocalBotzData
echo [LocalBotz]   [3] Another folder - type the path
choice /C 123 /N /M "[LocalBotz] Choose 1, 2 or 3: "
if errorlevel 3 goto :ask_data_custom
if errorlevel 2 goto :ask_data_d
goto :venv
:ask_data_d
if not exist "D:\" (
  echo [LocalBotz] There is no D: drive on this computer - using the C: drive folder.
  goto :venv
)
echo LOCALBOTZ_DATA_DIR=D:\LocalBotzData>> .env
echo [LocalBotz] Data will be kept in D:\LocalBotzData
goto :venv
:ask_data_custom
set /p CUSTOMDATA=[LocalBotz] Type the full folder path (for example E:\MyData\LocalBotz): 
if "%CUSTOMDATA%"=="" goto :venv
echo LOCALBOTZ_DATA_DIR=%CUSTOMDATA%>> .env
echo [LocalBotz] Data will be kept in %CUSTOMDATA%
goto :venv

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

REM ---------- Python libraries: bundled pack first, PyPI as fallback ----------
REM LocalBotz-Setup.exe ships every Python library the app needs in
REM vendor\wheels, so the install does not have to download them.
REM When that folder is here, install from it (offline). Otherwise
REM download from PyPI once, as before. Either way the user installs
REM nothing by hand — it is all in this one install step.
set PIP_OFFLINE=0
set PIP_TOOLS_DONE=0
if exist "vendor\wheels\*.whl" (
  set PIP_OFFLINE=1
  echo [LocalBotz] Found the bundled library pack — installing Python libraries offline.
)

echo [LocalBotz] Installing core dependencies (lightweight)...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
call :pip_req requirements.txt
if errorlevel 1 (
  echo [LocalBotz] pip install failed. See the error above.
  pause
  exit /b 1
)

REM ---------- Browser automation — always installed upfront ----------
echo [LocalBotz] Installing browser automation (Playwright + Chromium)...
echo [LocalBotz] This is part of the full install, so browser automation
echo [LocalBotz] is ready before you need it — nothing to install later.
call :pip_req requirements-browser.txt
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
call :pip_req requirements-desktop.txt
if errorlevel 1 (
  echo [LocalBotz] Desktop control install failed. See the error above.
  pause
  exit /b 1
)
REM ---------- Live voice — best-effort, never a hard stop ----------
echo [LocalBotz] Installing live voice support (Gemini Live + WebSocket)...
echo [LocalBotz] Best-effort only: if this fails, LocalBotz still starts,
echo [LocalBotz] and Talk still works — the Live Voice page will say so.
call :pip_req requirements-live.txt
if errorlevel 1 echo [LocalBotz] NOTE: live voice install did not work. Chat and Talk still work; live voice needs a Gemini key and this package.
echo [LocalBotz] Verifying the full install (Python, packages, Chromium)...
".venv\Scripts\python.exe" scripts\check_install.py
if errorlevel 1 (
  echo [LocalBotz] Install check reported a problem above. Fix it and
  echo [LocalBotz] run start.bat again, or continue anyway — the app
  echo [LocalBotz] will start, but browser automation may not work.
  pause
)

REM If port 8000 is already in use by another program, start on 8001
REM instead of crashing. Only when the user did not pass their own --port.
set APP_URL=http://127.0.0.1:8000
set HAVEPORT=0
for %%A in (%*) do if "%%A"=="--port" set HAVEPORT=1
if "%HAVEPORT%"=="0" (
  netstat -ano 2>nul | findstr /R /C:"TCP.*:8000 .*LISTENING" >nul
  if not errorlevel 1 (
    echo [LocalBotz] Port 8000 is already in use — starting on port 8001 instead.
    set APP_ARGS=!APP_ARGS! --port 8001
    set APP_URL=http://127.0.0.1:8001
  )
)
echo [LocalBotz] Starting on %APP_URL% — open that in your browser.
echo [LocalBotz] Keep this black window open — LocalBotz runs inside it.
echo [LocalBotz] Your app opens in the browser in a few seconds. If it
echo [LocalBotz] does not open by itself, type %APP_URL% into Chrome or Edge.
REM Open the browser a few seconds after the app starts, so the user
REM actually sees the app instead of just a black window. This runs in
REM its own tiny window and never stops the app if it fails.
start "" /min cmd /c "ping -n 6 127.0.0.1 >nul & start %APP_URL%"
".venv\Scripts\python.exe" app.py %APP_ARGS%
set APP_EXIT=%ERRORLEVEL%
echo [LocalBotz] %DATE% %TIME% - LocalBotz stopped, exit code %APP_EXIT% >> install.log
echo.
echo [LocalBotz] LocalBotz stopped (exit code %APP_EXIT%).
echo [LocalBotz] If it stopped with an error, the error is above — send a
echo [LocalBotz] screenshot of it, or the file install.log, and it can be fixed.
echo [LocalBotz] To start LocalBotz again, double-click start.bat.
pause
goto :eof

REM Install one requirements file. When the bundled library pack is
REM here (vendor\wheels, shipped inside LocalBotz-Setup.exe), install
REM from it offline; otherwise download from PyPI. If the pack does
REM not cover the file, fall back to PyPI for the rest. Build tools
REM (setuptools + wheel) are installed from the pack first, once, so
REM a library that ships without a wheel can still be built offline.
REM Usage: call :pip_req requirements.txt — exit code 0 on success.
:pip_req
if "%PIP_OFFLINE%"=="1" (
  if "%PIP_TOOLS_DONE%"=="0" (
    ".venv\Scripts\python.exe" -m pip install -q --no-index --find-links=vendor\wheels setuptools wheel
    set PIP_TOOLS_DONE=1
  )
  ".venv\Scripts\python.exe" -m pip install -q --no-index --no-build-isolation --find-links=vendor\wheels -r "%~1"
  if not errorlevel 1 exit /b 0
  echo [LocalBotz] The bundled pack did not cover %~1 — downloading the rest...
)
".venv\Scripts\python.exe" -m pip install -q -r "%~1"
exit /b %ERRORLEVEL%
