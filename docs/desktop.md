# Desktop control — "use the computer"

A bot that can see and use the desktop apps on this computer — Excel
and the BOQ, the company's old accounting software that has no API,
a supplier portal. Playwright already covers the web; this covers
the desktop. (The idea, learned from public computer-use projects
like Cua Driver and Agent Desktop. LocalBotz's own code — no copied
code, no external CLI, no cloud, no screenshot-based clicking.)

## How it works — observe, act, verify

1. **Inspect first.** `desktop_inspect` reads the desktop as a short
   structured list — windows (refs `w1`, `w2`…) and the controls in
   the focused window (refs `e1`, `e2`…: name, type, position). No
   screenshot, no pixels — a list is far cheaper than a picture.
2. **Act by ref.** `desktop_activate` (bring a window forward),
   `desktop_click` (a control, or x,y from the snapshot),
   `desktop_type` (type into a control, or the focused window),
   `desktop_key` (enter, tab, ctrl+s…).
3. **Verify.** After every click/type/key, LocalBotz re-reads the
   desktop and reports whether the target is still there / the
   window changed. The result says "Verified — …" or honestly
   "Could not verify — …".
4. **Screenshot when needed.** `desktop_screenshot` saves a picture
   of the whole desktop to `data/screenshots/desktop-<time>.png`
   — for apps whose controls the snapshot cannot see.

## Safety — the same rules as everywhere else

- **Permission-gated.** Desktop control is a global permission
  (Settings > Permissions, on by default, like browser automation).
  Turn it off and every desktop tool and desktop step is blocked
  with a clear message.
- **Ask by default.** Clicking, typing, activating and pressing
  keys are mutating, so a bot on **Ask** approval mode is blocked
  from them — switch the bot to Auto/Full in Settings >
  Permissions to allow changes. `desktop_inspect` and
  `desktop_screenshot` are read-only and still work on Ask.
- **No password fields.** Typing or clicking into a control whose
  type or name contains "password" is refused, always.
- **No coordinates outside the screen.** A click outside the
  screen size is refused.
- **Every action is logged.** `data/desktop_log.json` (last 200):
  time, action, target, source (bot / workflow / routine /
  manual), result, verified. See it on the Desktop page or
  `GET /api/desktop/log`. The typed text itself is not logged
  when it looks like a password — in fact the action is refused
  before it happens.
- **Nothing is sent out by a desktop step on its own.** A desktop
  step in a workflow or routine does what it says on the desktop
  — it does not email, message or publish anything.

## The Desktop page

Sidebar → 🖥️ Desktop — use the computer. Status (available?
which backend? which libraries?), the windows open now, the
controls in the focused window, a "do something" form (action,
target, text, keys), and the desktop log.

## API

| Endpoint | What it does |
|---|---|
| `GET /api/desktop/status` | available, platform, backend, libraries, mock, enabled |
| `GET /api/desktop/snapshot` | the structured snapshot (windows + controls) |
| `POST /api/desktop/action` | `{action, target?, text?, keys?, x?, y?}` — same permission checks as the tools; returns `{action, result, snapshot}` |
| `GET /api/desktop/log` | the desktop log, newest first |
| `GET /api/devices` | now includes a `desktop` status object |

## Tools (for bots)

`desktop_inspect`, `desktop_activate`, `desktop_click`,
`desktop_type`, `desktop_key`, `desktop_screenshot` — in
`TOOL_DEFS` like the browser tools, with descriptions that tell
the model to inspect first, act by ref, then check the verified
result. `desktop_inspect` is added to every bot's tools
automatically (read-only); clicking and typing stay opt-in —
the **Desktop Helper** template has all six, or turn them on
per bot in Library > Tools.

## Install

Desktop control is part of the one full install, up front:
`requirements-desktop.txt` — `pyautogui` (mouse, keyboard,
screenshots, all OS), `pygetwindow` (window list, all OS),
`pywinauto` (Windows only: the accessibility tree — buttons
and fields inside a window). `start.bat` / `start.sh` install
it in the same step as Playwright + Chromium, and
`scripts/check_install.py` checks the libraries import
(import-only on a headless machine — no display is reported
honestly, not as a failure).

## Honest limits

- **No real Windows desktop was verified from here.** This was
  built and tested in mock mode (the sandbox has no desktop).
  On Thomas's Windows PC it will use the real window list and
  the accessibility tree; the first real run is the real test.
- **The controls list depends on the backend.** On Windows,
  pywinauto's accessibility tree sees most buttons and fields.
  On macOS/Linux you mostly get the window list — activate a
  window, then click by coordinates from a screenshot. The
  macOS window list comes from AppleScript; Linux tries
  `wmctrl -l` if it is installed.
- **Custom-drawn apps may be invisible.** An app that draws its
  own buttons (games, some custom UIs) has no accessibility
  tree — the bot can see its window, not its buttons.
- **macOS needs an Accessibility permission grant** before any
  desktop control works there — macOS asks for it the first
  time, and the user grants it in System Settings > Privacy &
  Security > Accessibility.
- **No full-auto clicking without approval.** A bot on Ask
  cannot click. A workflow or routine desktop step runs as
  configured — it checks the global desktop permission, but
  there is no interactive "are you sure?" in the middle of a
  chain. Keep desktop steps in workflows to things you would
  happily let run on their own.
