@echo off
REM LocalBotz - one-click installer for Windows.
REM
REM This is the ONLY thing you need to download separately:
REM   the LocalBotz ZIP from GitHub, extracted to a folder.
REM Everything else is downloaded and set up by this installer,
REM in this one step - no separate downloads:
REM   1. Python 3.12 (if not already installed)
REM   2. LM Studio (if not already installed)
REM   3. The Qwen3.5 model, downloaded with LM Studio's own `lms` tool
REM   4. LocalBotz itself (Python packages, then the app on localhost:8000)
REM   5. Browser automation - Playwright + Chromium, installed upfront
REM      and verified, so it is ready before you need it. There is no
REM      light / optional install any more: everything is installed
REM      in this one step, nothing is left to install later.
REM
REM Just double-click install.bat. It needs internet the first time:
REM Python is ~30 MB, LM Studio is several hundred MB, and the Qwen3.5
REM model is ~6 GB, so the first run takes a while. Later runs are fast.
REM No Git is needed. No admin rights are needed (per-user installs).
REM
REM To skip the Python / LM Studio / model setup and just start the app:
REM   start.bat --skip-setup
REM To test the app without any model:
REM   start.bat --mock

cd /d "%~dp0"
echo ============================================================
echo   LocalBotz - one-click install
echo   This step downloads Python, LM Studio and Qwen3.5 for you.
echo   No separate downloads. No Git needed.
echo ============================================================
echo.
call start.bat %*
echo.
echo LocalBotz install finished. If the window above shows an error,
echo read it now - the window stays open on purpose. Press any key to close it.
pause
