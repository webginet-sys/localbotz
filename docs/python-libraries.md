# Python libraries — all bundled in the installation

LocalBotz is a Python app, so it needs Python libraries to run: the web
server (FastAPI), the browser (Playwright), the desktop tools
(PyAutoGUI), the document writers (python-docx, openpyxl, python-pptx),
the live voice (google-genai) and a few more. **The user never finds or
installs any of them.** They are all in the installation step.

## How it works

There are four requirements files, one per job, each pinned to an exact
version so every install gets the same libraries:

| File | What it is |
|---|---|
| `requirements.txt` | Core: FastAPI, uvicorn, httpx, pypdf, python-docx, openpyxl, python-pptx, python-multipart |
| `requirements-browser.txt` | Browser automation: Playwright (+ Chromium, downloaded by `playwright install chromium`) |
| `requirements-desktop.txt` | Desktop control: PyAutoGUI, PyGetWindow, pywinauto (Windows only) |
| `requirements-live.txt` | Live voice: google-genai, websockets (best-effort only — the app starts without them) |

`start.bat` installs all four in the one install step, in that order.
The core, browser and desktop packs are a hard stop if they fail; the
live-voice pack is best-effort (Talk still works without it).

## The bundled pack (offline install)

`LocalBotz-Setup.exe` carries every library with it in `vendor/wheels/`
(59 wheels, ~65 MB, Windows CPython 3.12). When that folder is present,
`start.bat` installs from it **offline** — no PyPI download at all. If
the pack is missing (ZIP install) or does not cover a file, it falls
back to downloading from PyPI once. Either way the user does nothing.

The pack is built by `scripts/fetch_wheels.py`:

```
python scripts/fetch_wheels.py            # into vendor/wheels/
```

It downloads the full dependency closure for Windows (win_amd64,
CPython 3.12). The Windows installer workflow runs it before staging,
so the Setup.exe always carries the current pack. The wheels are NOT
committed to the repo (`.gitignore` excludes `vendor/`).

Two quirks the script handles, so you do not have to:

- **Markers:** pip evaluates `sys_platform` markers against the build
  machine, not the `--platform` target, so the script strips markers
  before downloading (the download is already targeted at Windows).
- **No-wheel libraries:** the whole PyAutoGUI family (PyAutoGUI,
  PyGetWindow, PyRect, PyScreeze, MouseInfo, PyTweening) ships
  sdist-only — no wheel on PyPI at all. The script builds universal
  wheels from the sdists with `pip wheel` (all pure Python) and fetches
  their wheel'd deps (PyMsgBox, pyperclip) explicitly. If another
  library ever ships no wheel, add it to `SDIST_ONLY` in the script.

## What is NOT bundled

- **faster-whisper** — used only by the optional `/api/talk/transcribe`
  endpoint, when installed. It is large, and Talk works through the
  browser's speech recognition without it. The endpoint returns an
  honest 501 when it is not installed.
- **Python itself, LM Studio, the Qwen3.5 model, Chromium** — these are
  downloaded by `start.bat` in the same install step (Python via winget
  or python.org, LM Studio via winget, the model via `lms get`,
  Chromium via `playwright install chromium`). They are separate
  programs, not Python libraries, so they cannot ride in the wheels
  pack.

## Refreshing the pins

To move to newer library versions: change the `==` pins in the four
requirements files, run `scripts/fetch_wheels.py` into a scratch folder,
install from it offline in a fresh venv (`pip install --no-index
--find-links=<dir> -r requirements.txt ...`), run
`scripts/check_install.py` and the app in mock mode, then commit the
pins. Never change a pin without testing the offline install — the pack
is what the user's computer actually installs from.
