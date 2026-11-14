# Scheduled routines — work that runs itself

A routine is a bot + a job + a clock. It closes the oldest gap in
LocalBotz: until now a bot's schedule (e.g. `daily 07:00`) was only a
label that was stored and shown — nothing ran it. Routines run it.

## What it is

- **Create a routine.** Sidebar → Routines → name, bot, what the bot
  should do every time, and when:
  - **Daily** at a time (HH:MM, your computer's local time)
  - **Weekly** on a weekday at a time
  - **Every N minutes** (1 to 10080 — 15 min, 30 min, 1 hour, 2 hours, 4 hours, 1 day in the form)
  - **Once** at a time (today if it is still ahead, otherwise tomorrow; switches itself off after it runs)
- **It runs on its own.** A background worker checks every 30 seconds
  (the same worker that runs persistent agents' tasks) and runs the
  first routine whose time has arrived, one per check. The run is the
  bot doing its job with `run_agent` — same tools, same Permissions
  rules as a chat. The result is recorded on the routine (time,
  done/failed, a short summary) and the bot remembers it: a one-line
  fact goes into the bot's long-term memory, like a Hermes task.
- **Late catch-up, once.** If LocalBotz was closed when a routine was
  due, the next start runs it **once**, then puts it back on its
  normal schedule. It never fires a backlog of missed runs.
- **Pause / resume / run now / delete** from the Routines page.
  "Run now" runs the routine immediately and does not move its next
  scheduled run. Pausing keeps the next run time, so resuming catches
  up once if the time passed while it was paused.

## Desktop step (optional)

A routine can do one thing on the desktop as well as — or instead
of — the bot task. On the Routines page, under "Desktop step
(optional)": pick an action (inspect the desktop, activate a
window, click a control, type text, press keys, take a
screenshot), a target (a window/control ref from the Desktop
page, e.g. w1 or e1), text to type, and keys to press. Example:
every morning at 08:00, activate Excel and press ctrl+s — or
leave the task empty and the routine is the desktop step alone.

It runs after the bot task (or alone), through the same desktop
runner as the tools: Desktop control must be on in Settings >
Permissions, and the action is logged in the desktop log with
source=routine. If the desktop step fails (refused, not
available, blocked), the run is recorded as failed, so it is not
silently lost. The bot can already use desktop tools inside its
task — the direct step is for a fixed action you always want,
e.g. "open the BOQ in Excel and read the total" as a task, plus
"press ctrl+s" as the fixed step. See `docs/desktop.md`.

## What it is not (yet)

- **Not a system service.** Nothing runs while LocalBotz is closed.
  A routine runs only while the app is running (or once, as a
  catch-up, on the next start). If you need a routine to run while
  the computer is off, that is a different thing — a server job on
  the VPS, not a local routine.
- **No office routines yet.** A routine runs one bot. Running a
  whole Office team job on a clock is the natural next step — the
  routine runner (`_run_routine`) and the office job runner
  (`run_office_job`) are separate today.
- **No outbound approval step.** A routine runs with the bot's
  Permissions mode (Ask / Auto / Full). If a routine's job would
  send something out (email, message), give that bot Auto or Full —
  or keep it on Ask and the outward step will be held. The Auditor
  + approval gate is for Office jobs, not routines.
- **Times are local.** Daily/weekly/once times are your computer's
  local time. There is no timezone picker yet.

## API

| Endpoint | What it does |
|---|---|
| `GET /api/routines` | List routines (with `schedule_text`, next run, last run) |
| `POST /api/routines` | Create — `{name, bot_id, task, kind, time?, weekday?, interval_minutes?, desktop_action?, desktop_target?, desktop_text?, desktop_keys?}` — task may be empty when a desktop action is given. |
| `GET /api/routines/{id}` | One routine, with its run history (last 20) |
| `PATCH /api/routines/{id}` | Change fields, or `{enabled: false}` to pause / `{enabled: true}` to resume |
| `DELETE /api/routines/{id}` | Delete the routine |
| `POST /api/routines/{id}/run` | Run it now (does not move the next scheduled run) |

Routines live in `data/routines.json`. A routine whose bot was
deleted is switched off and its last run says so.

## Rules that stay in place

- **Local first.** Routines and their run history live on your
  computer. Nothing leaves it except a model call the bot already
  makes (local model, or a provider key you set / VPS Premium).
- **One at a time.** The worker runs one routine per 30-second
  check, so two routines due at the same minute run one after the
  other, in next-run order — never at the same instant.
- **No silent failures.** A failed run is recorded with its reason
  on the routine, and the next run still happens on schedule.
