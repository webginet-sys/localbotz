![LocalBotz — animated logo](assets/logo-animated.gif)
<!-- Static logo: assets/logo.png. Short video version: assets/logo-animated.mp4 -->

# LocalBotz — a personal AI assistant that runs on your computer

A personal-agent app you run on your own computer. No Electron, no cloud,
no API keys. Bots have their own name, instructions/persona, model, chat
history and memory file. The agent can search the web, drive a real browser
(Playwright/Chromium), read/write files in `./workspace`, and run safe shell
commands — driven by a downloaded local model in **LM Studio**.

> **MIT licensed and built in the open.** [Read the code](https://github.com/webginet-sys/localbotz), run it from source, or [send a pull request](https://github.com/webginet-sys/localbotz/pulls).
>
> **Website:** [localbotz.io](https://localbotz.io) — hero, try-it prompts, what you can build, open source, and download. (The website lives on our VPS; this repo holds only the application.)

## Download — for everyone

**You do not need to know how to use a terminal.** If you have never
downloaded an app from GitHub before, start here:

- **Open the download page:** [localbotz.io/download.html](https://localbotz.io/download.html) — or read the plain-language
  steps in [DOWNLOAD.md](DOWNLOAD.md).
- **🪟 [Download for Windows](https://github.com/webginet-sys/localbotz)** — Windows 10 / 11. On GitHub, click **Code → Download ZIP**, extract it, then double-click `start.bat`.
- **🍎 [Download for Mac](https://github.com/webginet-sys/localbotz)** — Apple Silicon (M1 / M2 / M3 / M4) and Intel. On GitHub, click **Code → Download ZIP**, open the ZIP, then double-click `start.command`.
- Then open your browser to `http://localhost:8000`. **Just install LocalBotz — that's it.** Double-click `install.bat` (Windows) or `start.command` (Mac) and it downloads and sets up Python, LM Studio and the Qwen3.5 model for you in that one step. No Git, no separate Python download, no separate LM Studio download. Every Python library the app needs is in that same step too — the Windows installer even carries them all offline, so nothing is left to find or install later.
- **Windows installer (recommended):** a proper `LocalBotz-Setup.exe` is built automatically from this repo (`installer/windows-installer.iss`, GitHub Actions) — get it from [Releases](https://github.com/webginet-sys/localbotz/releases) when available. It walks you through install like any professional app, asks where your data should live (C: or D: drive), and adds Start Menu and Desktop shortcuts. Until it is code-signed, Windows SmartScreen shows "Windows protected your PC" — click "More info" → "Run anyway".

GitHub repo: https://github.com/webginet-sys/localbotz

## Install — no Git needed

**You do not need Git, and you do not need a terminal.** Git is only for
developers who want to clone the code — normal users never need it.

1. Download the ZIP: https://github.com/webginet-sys/localbotz/archive/refs/heads/main.zip
   — or go to https://github.com/webginet-sys/localbotz and click
   **Code → Download ZIP**.
2. Extract the ZIP.
3. Run it — Windows: double-click `start.bat`, macOS: double-click
   `start.command`, Linux: `./start.sh`
   (first run: `chmod +x start.sh start.command`). The starter creates a
   venv, installs the dependencies and starts the app on
   http://localhost:8000. It only needs Python — no Git anywhere.

For developers only (optional, needs Git installed):

```bash
git clone https://github.com/webginet-sys/localbotz.git
cd localbotz
```

If `git clone` says `'git' is not recognized as an internal or external
command`, Git is simply not installed on that computer — that is normal,
and it is not a problem with LocalBotz. **Do not install Git to fix it:**
use the ZIP download above instead. LocalBotz runs without Git.

**Full install — everything upfront.** There is no lightweight install
any more. The installer always installs browser automation (Playwright
+ Chromium) in the same step, and verifies Chromium launches, so it is
ready before you need it. Nothing is left to install later — if you
need to run browser automation, whatever it needs is already there.
`--light` / `--no-browser` are no longer supported and are ignored.

**Works on Windows, macOS and Linux.** The code uses `pathlib` throughout,
no hardcoded OS paths and no OS-only shell commands — the file commands in
`run_command` (`ls`/`dir`, `cat`/`type`, `grep`, `find`, …) are implemented
in Python, so they behave the same on all three.

LocalBotz is written from scratch in Python — a deliberately small,
local-first personal assistant. No Electron, no cloud account needed.

## What it does

- **Bots** — create / list / select / delete bots, each with name,
  instructions, model, own chat (`data/chats/<id>.json`) and memory
  (`data/memory/<id>.json`). Starter templates: **Chief of Staff** and
  **Research Scout**. Stored as plain JSON in `data/` (`bots.json`).
- **Local model (LM Studio, default)** — talks to LM Studio's
  OpenAI-compatible local server at `http://localhost:1234/v1` via
  `/chat/completions`. Default model: **Qwen3.5** — set with
  `MODEL` / `LLM_MODEL` in `.env`, or per bot in the UI. You can use
  **any local model** you have in LM Studio or Ollama: the app asks the
  local server what it actually has (`GET /v1/models`) and lists those
  models in the **Available models** dropdown — Qwen3.5 is only the
  fallback when the list cannot be fetched.
  > If LM Studio shows a fuller identifier for your model, e.g.
  > `qwen/qwen3.5-...`, copy that **exact** identifier into `MODEL`
  > (or into the bot's Model field in the UI). The app sends whatever
  > is configured — it does not guess the identifier.
- **Agent tool loop** — up to 8 tool turns per reply, shown in the chat UI:
  `web_search` / `browser_search` (DuckDuckGo), `browser_open`,
  `browser_read`, `browser_screenshot` (saved to `data/screenshots/`),
  `browser_click`, `browser_type`, `list_files`, `read_file`, `write_file`
  (restricted to `./workspace`, never outside), `run_command` (allowlisted
  commands only, 30 s timeout, workspace as cwd, cross-platform).
- **Web UI** — http://localhost:8000 — sidebar with bots + New Bot form
  (including an editable Model field per bot), main chat, model + status
  indicator (LM Studio reachable / not reachable / mock), memory view,
  tool-output display. Plain HTML/JS, no build step.
- **Mock mode** — `python app.py --mock` or `MOCK_MODE=1`: test the UI,
  bots and tools without any model running.

## Quick start (all OS)

The start scripts do everything: check Python, create a venv, install
dependencies, install Playwright Chromium, then run the app.

- **Windows:** double-click `start.bat`, or in Command Prompt / PowerShell:
  `start.bat` (test mode: `start.bat --mock`)
- **macOS / Linux:** `chmod +x start.sh` (first time only), then
  `./start.sh` (test mode: `./start.sh --mock`)

Then open **http://localhost:8000**. LM Studio must be running first
(see step 2 in your OS section below).

**First time you open it**, a short setup wizard asks three things:
how LocalBotz should run (on your computer, with your subscriptions,
or rented from us), your first bot, and your first office — and
whether LocalBotz should start when the computer starts, so routines,
jobs and workflows keep running while the computer is on. You can
skip it and change everything later in Settings → General.

---

## Smart routing — simple questions free, hard work premium

In **Make a bot**, set **Smart routing** to Auto and the bot answers
simple questions (short, and asking for no drafting, research,
analysis or quotations) free on the local model, and only sends hard
work to its configured premium provider — so the wallet lasts longer.
The chat footer says when a question was routed ("routed free to
local (from claude)"). See `docs/routing.md`.

---

## Windows

### 1. Install Python 3.11+
Download the installer from https://www.python.org/downloads/windows/
and run it. **Tick "Add python.exe to PATH"** on the first screen, then
Install. Check it worked — in Command Prompt *or* PowerShell:

```cmd
python --version
```

You should see `Python 3.11` or newer. If `python` is not recognised,
close and reopen the terminal (or reinstall with the PATH box ticked).

> PowerShell vs Command Prompt: both work for everything below.
> The only difference is running the script: in PowerShell type
> `.\start.bat` (the `.\` is required); in Command Prompt just
> `start.bat`. Double-clicking `start.bat` in Explorer also works.

### 2. LM Studio + Qwen3.5
1. Download LM Studio from https://lmstudio.ai/ and install it
   (the Windows `.exe` installer).
2. In LM Studio, search for and download the **Qwen3.5** model.
3. Load Qwen3.5 (open it in a chat, or load it from the model list).
4. Go to the **Developer tab** (left sidebar, `</>` icon) and press
   **Start Server**. It serves on `http://localhost:1234` by default.
   Leave LM Studio running while you use LocalBotz.
5. Note the exact model identifier LM Studio shows. The default in this
   app is `qwen3.5`. If LM Studio shows a fuller identifier, e.g.
   `qwen/qwen3.5-...`, set it exactly — copy `.env.example` to `.env`
   and set `MODEL=qwen/qwen3.5-...`, or set the Model field in the UI.

### 3. Run it

```cmd
start.bat
```

The script creates `.venv`, installs `requirements.txt`, installs
Playwright Chromium, and starts the app on http://localhost:8000.
To test without a model: `start.bat --mock`.

If you prefer manual steps, the equivalents are:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python app.py
```

---

## macOS

### 1. Install Python 3.11+
Either download it from https://www.python.org/downloads/macos/,
or with Homebrew:

```bash
brew install python
```

Check it:

```bash
python3 --version
```

You should see `Python 3.11` or newer. (macOS ships an old system
`python3` — the steps below always use `python3` explicitly, and the
start script creates its own venv, so the system Python is not used
to run the app.)

### 2. LM Studio + Qwen3.5
1. Download LM Studio from https://lmstudio.ai/ (macOS `.dmg`) and
   drag it to Applications.
2. In LM Studio, search for and download the **Qwen3.5** model.
3. Load Qwen3.5 (open it in a chat, or load it from the model list).
4. Go to the **Developer tab** (left sidebar, `</>` icon) and press
   **Start Server**. It serves on `http://localhost:1234` by default.
   Leave LM Studio running while you use LocalBotz.
5. Note the exact model identifier LM Studio shows. The default in this
   app is `qwen3.5`. If LM Studio shows a fuller identifier, e.g.
   `qwen/qwen3.5-...`, set it exactly — copy `.env.example` to `.env`
   and set `MODEL=qwen/qwen3.5-...`, or set the Model field in the UI.

### 3. Run it

```bash
chmod +x start.sh   # first time only
./start.sh
```

The script creates `.venv`, installs `requirements.txt`, installs
Playwright Chromium, and starts the app on http://localhost:8000.
To test without a model: `./start.sh --mock`.

Manual equivalent:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python app.py
```

---

## Linux

### 1. Install Python 3.11+
Ubuntu / Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

Fedora:

```bash
sudo dnf install python3
```

Arch:

```bash
sudo pacman -S python
```

Check it:

```bash
python3 --version
```

You need `Python 3.11` or newer. If your distro ships an older Python,
install a newer one from https://www.python.org/downloads/ (or deadsnakes
on Ubuntu: `sudo add-apt-repository ppa:deadsnakes/ppa`).

### 2. LM Studio + Qwen3.5
1. Download LM Studio from https://lmstudio.ai/ (Linux AppImage) and
   make it executable / run it.
2. In LM Studio, search for and download the **Qwen3.5** model.
3. Load Qwen3.5 (open it in a chat, or load it from the model list).
4. Go to the **Developer tab** (left sidebar, `</>` icon) and press
   **Start Server**. It serves on `http://localhost:1234` by default.
   Leave LM Studio running while you use LocalBotz.
5. Note the exact model identifier LM Studio shows. The default in this
   app is `qwen3.5`. If LM Studio shows a fuller identifier, e.g.
   `qwen/qwen3.5-...`, set it exactly — copy `.env.example` to `.env`
   and set `MODEL=qwen/qwen3.5-...`, or set the Model field in the UI.

### 3. Run it

```bash
chmod +x start.sh   # first time only
./start.sh
```

The script creates `.venv`, installs `requirements.txt`, installs
Playwright Chromium, and starts the app on http://localhost:8000.
To test without a model: `./start.sh --mock`.

Manual equivalent:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python app.py
```

Note: `playwright install chromium` may ask for system libraries on
Linux; if it does, run `playwright install-deps chromium` (needs sudo)
or install the missing packages your distro suggests.

---

## Templates — Make a Bot

Click **＋ Make a bot** in the sidebar:

> A bot is a standing agent with its own instructions, schedule, memory and chats. Start from a template, or name one and describe the job.

- **Avatar picker** — 8 choices (🤖 👔 🔬 🌅 📰 📝 💬 👀), stored per bot.
- **Name your bot** + **Describe the job** — the job becomes part of the bot's instructions when you create it from scratch.
- **Template tabs** — Featured, Personal Assistant, Productivity, Research, Sectors, More (More shows all 46 templates).
- **Template cards** — each has an icon, name and short description. Clicking one pre-fills name, instructions, avatar, provider/model (default LM Studio / Qwen3.5), enabled tools and schedule — all still editable before you press Create bot.

Templates (in `templates.json`, copied to `data/templates.json` on first run):

| Tab | Templates |
|---|---|
| Research | Deep Researcher, Competitor Watch, News Radar, Research Paper Scout, Decision Researcher, VC Due Diligence, Journalist, Earnings Call Analyst, HN Briefing, Release Radar, Legal Researcher, Document Reviewer, Tender Comparator, Contract Checker, Evidence Checker, Independent Auditor |
| Personal Assistant | Chief of Staff, Email Drafting, Morning Brief, Meeting Prep, Follow-Up Tracker, WhatsApp Agent, Travel Planner, Health & Fitness Coach, Financial Coach, Business Consultant, Teacher |
| Productivity | Task Planner, Meeting Notes, Research Scout, Inbox Triage, Data Analyst, System Architect, Sales Intelligence, Doc Q&A |
| Sectors | Construction Office, MEP Office, Electrical Engineering Office, IT Services Office, E-commerce Office, Real Estate Office, Clinic & Healthcare Office, Logistics Office, Manufacturing Office, Hotel & Hospitality Office, BOQ Reviewer |
| Featured | Deep Researcher, News Radar, Chief of Staff, Morning Brief, Task Planner, Research Scout, Data Analyst, Travel Planner, HN Briefing, Construction Office, IT Services Office, E-commerce Office |

LocalBotz is built for **office, sales and marketing work — in every
sector**. The Sectors tab has a ready-made office assistant for each
kind of company: construction, MEP, electrical engineering, IT services,
e-commerce, real estate, healthcare, logistics, manufacturing and
hospitality. Each one knows the trade's own documents and words —
BOQs and tenders, SOWs and SLAs, listings and campaigns — and never
invents a price, a measurement or a date that is not confirmed.

Each template stores its full instructions, default tools and a schedule (e.g. `daily 07:00`, `on_demand`). The schedule is stored per bot and shown in the sidebar; to make a bot actually run on a clock, use **Routines** (sidebar → Routines) — daily, weekly, every N minutes, or once. See "Scheduled routines" below.

## Library

The **Library** section in the sidebar has 5 pages, sharing the same data files as Settings (no duplicate stores):

- **Connectors** — all model providers (LM Studio, Ollama, Claude, OpenAI, Gemini, OpenRouter, Groq, Mistral, Cerebras) plus 25 popular service connectors, grouped by category: Email & productivity (Gmail, Google Drive, Google Calendar, Outlook, Dropbox), Chat (Slack, Telegram, Discord, WhatsApp, Microsoft Teams), Work (Notion, Trello, Asana, Jira, Linear, Airtable, Google Sheets), Dev (GitHub, GitLab), CRM & sales (HubSpot, Salesforce), Payments (Stripe), Video & meetings (Zoom), Social & publishing (X, LinkedIn). Enable/disable, Test connection, status **Not connected / Saved, not checked / Connected / Failed**. Test is real for token-based connectors — it calls the service's own "who am I" endpoint with your saved token. OAuth-only connectors are config + setup instructions in v1, with status **Not connected** — never faked. Full list: `docs/connectors.md`.
- **Messaging** — WhatsApp, Telegram, Discord. Same data as Settings > Messaging channels: config, inbound-replies toggle (off by default), approved senders, status **Not connected** in v1.
- **MCP servers** — add/remove a server by name + command or URL (and env), enable/disable, Test. The test really runs the server (stdio JSON-RPC or HTTP `tools/list`) and lists its tools when it answers; if it cannot be reached, the error is shown. Stored in `data/mcp_servers.json`.
- **Skills** — built-in skills (Research, File help, Browser help, Coding help, Email drafting, Morning Brief, Project Graveyard, First Reader, Scope Creep Detector, Commit Archaeologist, Dependency Doctor, Self-Improving Skill) plus custom skills you add (name + instructions + optional source folder/file). Enable/disable per bot, delete custom ones. Stored in `data/skills.json`. Enabled skills are added to the bot's system prompt.
- **Tools** — the full built-in tool list (`browser_open`, `browser_read`, `browser_screenshot`, `browser_click`, `browser_type`, `browser_search`, `web_search`, `list_files`, `read_file`, `write_file`, `run_command`) with descriptions, global enable/disable, per-bot toggles, and which bots use each. Toggles are enforced in the agent loop.

## How LocalBotz runs

Use the subscriptions you already pay for to run agents in your
personal office. Works with Claude, ChatGPT, Grok, Gemini and more.
Give your agents your computer — or rent one from us.

1. **Your computer (free)** — your agents run on your own computer,
   on your downloaded local model (LM Studio / Qwen3.5). Nothing
   leaves the computer. Settings → General → "Use my computer".
2. **Your subscriptions (bring your own keys)** — Claude, ChatGPT,
   Grok, Gemini, DeepSeek, Kimi, GLM, OpenRouter, Groq, Mistral,
   Cerebras. Add each key once in Settings → Secure store; it is
   sent only to its own provider. (These are API keys, not the
   terminal CLIs — see `docs/how-it-runs.md`.)
3. **Rent one from us (premium, metered)** — no keys of your own?
   Premium models (Claude Sonnet, GPT, Gemini) from our server:
   register on the VPS (Settings → Connectors → VPS Premium →
   "Register on the VPS"), pick provider **VPS Premium** per bot,
   and usage is metered by the server — you pay for what you use.

A different bot — or a different member of your Office team — can
run a different way. See `docs/how-it-runs.md`.

## Hermes Agent features — persistent agents, tasks, Telegram

Modelled on Hermes Agent (Nous Research, MIT). A bot can be a
**persistent agent**: turn on "Keep working in the background"
on its page, give it goals as **tasks**, and it works through
them one at a time on its own (multi-step tool loop), remembers
what it did in its long-term memory, and moves on to the next
one. **Telegram is live too**: save a bot token from @BotFather,
enable Telegram in Library → Messaging with approved senders,
and LocalBotz polls Telegram and answers them — no webhook or
public URL needed. Discord and WhatsApp are still config-only.
See `docs/hermes.md`.

## Office — your AI team, on your own computer

Sidebar → **Office**. Modelled on Munder Difflin
(HarnessMD/munder-difflin): an office of agents running locally.
Create your office, hire an AI team with roles (Researcher, Writer,
Developer, Analyst, Assistant, Sales, Finance, Legal, Recruiter,
Teacher — plus 132 sector roles: every job title a construction, MEP,
electrical engineering, IT services or e-commerce company hires, from
Construction Manager and Cloud Architect down to HVAC Technician,
Plumber and Steel Fixer, plus 42 more from NaukriGulf's
jobs-by-category (the office, sales and marketing functions an AI
agent can actually do), and give the team a job. One boss
agent (the Office Manager) plans the work and assigns it — you only
brief the boss. The team shares one office memory (`memory.md`) that
survives sessions, passes work to each other on a blackboard, and
writes every finished job into the memory. Every job is checked by
an independent Auditor first (prices, dates, facts — verdict pass,
pass with fixes, or fail) and held as a draft until you approve it;
only an approved job goes into the memory. Runs on the local model
by default. See `docs/office.md`.

## Office documents — real Word, Excel and PowerPoint files

A finished job can be exported as a real file: **Word (.docx)** —
title, Auditor verdict, one headed section per team member, and any
`| pipe |` tables as real Word tables; **Excel (.xlsx)** — a Summary
sheet plus one sheet per member, with money kept as numbers so you
can sum a column; **PowerPoint (.pptx)** — a title slide plus one
slide per step, up to 12 slides. Files live under
`data/documents/<office_id>/<job_id>/` and are listed on the Office
page with download links. Nothing is invented in them — only what
the job actually produced, and an empty step says so. See
`docs/documents.md`.

15 of the templates, 5 office roles and 6 skills come from
[awesome-llm-apps](https://github.com/shubhamsaboo/awesome-llm-apps)
(100+ open-source AI agents, Apache-2.0) — rebuilt as LocalBotz-native
templates, roles and skills. See `docs/awesome-llm-apps.md` for the full
mapping, and what we deliberately did not take (voice, image/video
generation, game agents, fine-tuning).

## Scheduled routines — work that runs itself

A **routine** is a bot + a job + a clock. Sidebar → Routines → give
it a name, pick a bot, write what the bot should do every time, and
pick when: **daily at a time** (e.g. 09:00), **weekly** on a weekday
at a time, **every N minutes**, or **once**. A background worker
checks every 30 seconds and runs any routine whose time has arrived
— the same worker that runs persistent agents' tasks. Each run is
recorded (time, done/failed, a short summary) and the bot remembers
it in its own memory, like a Hermes task.

If LocalBotz was closed when a routine was due, it runs **once**
when you open the app again, then goes back to its normal time —
it never fires a backlog of missed runs. Nothing runs while the app
is closed: routines are not a system service. Pause, resume, run
now, or delete a routine from the same page. See `docs/routines.md`.

The team also **learns from daily work**: a routine that ran and an
office job you approved are recorded as learnings — what you want
done regularly, what passed the audit — and shown back to the bot
every time it works, so it presents what it learned when you need
it (e.g. your pricing when it drafts a quotation). You can also
teach the team directly ("Always add 12% margin to Cisco quotes")
and delete any learning that is wrong. See `docs/learnings.md`.

## Desktop control — "use the computer"

A bot that can see and use the desktop apps on this computer —
Excel and the BOQ, the company's old accounting software that has
no API, a supplier portal. Sidebar → 🖥️ Desktop — use the
computer. It works observe → act → verify: first it **inspects**
the desktop (a short list of windows and controls, with refs like
w1 and e1), then it clicks or types on a ref, then it looks again
to check the result. Clicking and typing need Desktop control on
in Settings > Permissions, and a bot on Ask asks before it clicks
anything. Every action is logged, it never types or clicks into a
password field, and it never clicks from a screenshot — only from
the list it just read. Desktop control is installed up front in
the one full install (`requirements-desktop.txt`: pyautogui,
pygetwindow, pywinauto on Windows). The **Desktop Helper**
template has all six desktop tools, Talk mode and Show-me-how on.
Deal workflows can have desktop steps too (inspect, activate,
click, type, press keys, screenshot), and a routine can have one
direct desktop step after its bot task — or on its own. See
`docs/desktop.md`. Honest limit: built and tested in mock mode
here — no real Windows desktop was available in this sandbox, so
the first real run on your computer is the real test; on macOS
and Linux you mostly get the window list, not the controls
inside a window.

## Talk + Show-me-how

Everyone should be able to talk to their computer in plain
words — no prompting, no tutorials. In the chat header: **🎙️
Talk** (tap, speak, it types what you said — Chrome/Edge,
browser speech recognition, no install, no keys), **🔊
Listen** (reads the bot's replies out loud, short replies only),
and **👀 Show me how** (the bot explains each step in plain
words before it does it, and shows a picture of each step —
"Here's how I did it"). Talk mode is also a per-bot setting
(Make-a-bot → Talk mode): short plain sentences, no jargon, no
menus, and if something is unclear it asks ONE simple question.
`POST /api/bots/{bot_id}/show-me-how` runs a task with visible
steps; `POST /api/talk/transcribe` transcribes audio locally
only if faster-whisper is installed, otherwise an honest 501 —
it is deliberately not in the install, so the install stays
light. See `docs/talk.md`. Honest limits: browser speech
recognition needs Chrome/Edge and internet for its speech
service; show-me-how screenshots need the desktop/browser to be
available; in mock mode steps are labelled [MOCK MODE].

## Live Voice — real-time conversation

Sidebar → 🔴 Live Voice. Tap **Start live voice** and talk in plain
words — the bot answers out loud while you speak, and you can
interrupt it any time. It can also do things on the desktop when you
ask ("look at the BOQ"). The mic is live only while the page is open
and you tapped Start; it stops itself after 2 minutes of silence,
and the words (text only, no audio) are saved into the bot's chat
history. It runs on Google Gemini Live (`gemini-3.8-live`), so it
needs internet and a Gemini key in Secure store — live usage is
billed to the key owner. Without a key the page says so honestly and
refuses to start. Full details: `docs/live-voice.md`.

## Muse — the character who lives in your PC

Sidebar → 🏠 Home. **Muse** is the one character who lives on this
computer — the name Thomas chose. Muse greets you by name, remembers
what you teach it, and speaks as one voice across every bot. Pick how
Muse speaks (Mentor, Friend, Professional, or your own words) and your
voice speed and pitch in Settings → Character, or in step 4 of the
first-run wizard.

Home is your day at a glance: today's brief (routines due, deals gone
quiet, new leads — built only from your real data, never invented),
deals needing attention, and what the team has learned. **Speaks first**
is off by default: switch on the morning brief and spoken nudges and
Home prepares them for you to hear with one tap — browsers do not let
a page speak without you tapping first, so Muse never talks out of
nowhere on its own.

**Phone link** (Settings → Phone link) is the bridge to the future
mobile app: make a one-time 6-digit code on the PC, open the phone page
on your phone, enter the code, and talk or type to the same Muse while
the PC is on and the phone is on the same Wi-Fi. No cloud relay, no
audio saved. Full details and honest limits: `docs/character.md`.

**Floating bar**: a small bar at the top of the app always shows what
Muse is doing (Idle / Listening / Working), with one-tap Talk and a
⏹ Stop button. The 🖥️ Desktop page can run a short job of desktop
steps; while it runs, a live card says "Working on step X of Y" and
Stop (or Esc) really cancels it — no further step runs, and the stop
is logged. This is an in-app bar, not a separate always-on-top window.

## Languages — every country, every language

LocalBotz knows **199 countries and 186 languages** (`languages.json`:
ISO 3166 countries with their official languages, ISO 639-1 languages
with native names). Pick a language per bot (Make a bot), per chat (the
language menu at the top of the chat), or as the global default
(Settings → General). “Auto” replies in the language the user wrote in.
Talk follows the language too — the mic listens in it, and spoken
replies use a matching voice when the browser has one. The 🌍 Languages
page lists every country and language with search, and “Use” sets the
open bot's language. Honest limits: a language being listed means
LocalBotz knows it — not that every model speaks it equally well.
Local Qwen3.5 is strong in English, Chinese, Arabic and many others;
speech recognition and voices depend on the browser and OS, not on
LocalBotz. See `docs/languages.md`.

## Clients & Deals — deal workflows

A small local CRM for sales work. A **deal** is a client, a value,
a **department** and a stage in that department's pipeline — every
department has its own stages (Construction: Tender → BOQ →
Submitted → Awarded; IT Services: Discovery → Proposal → Signed;
and so on for all 10 sectors + General), with one timeline per deal
(stage moves, notes, drafts, workflow runs). A **workflow** fires
when a deal moves stage, and runs a **chain of steps, in order**:
create a task for a bot, run an office job with the team (Auditor +
approval gate applies), write a draft, add a note, **wait** (the
chain pauses and resumes on its own), or **IF** (stop the chain
here if the deal's value or stage doesn't match — e.g. wait 3 days,
then chase only if the deal is still Quoted), or a **desktop step** (inspect the desktop, activate a window, click, type, press keys, take a screenshot — e.g. type the follow-up into the open quotation). Chains are limited to
one department, or any. Write the steps with `{deal}`, `{client}`,
`{value}`, `{currency}`, `{stage}` and they are filled in from the
deal. Every department ships with two starter workflows (a handover
draft when a deal is won, a note when one is lost), plus a ready-made
chase chain for General. Nothing is sent out by a workflow on its
own — drafts stay drafts until you send them. **📋 Runs** lists
every chain and routine that ran, with its steps — a finished chain
can be re-run from step 1 on the same deal. See
`docs/deal-workflows.md`.

## Leads, business profile, WhatsApp agent, monitors, marketing

Five more ways LocalBotz works for a business, all of them approval-first:

- **🎯 Leads — find new clients.** Hunt for businesses by area and sector
  (public sources only, never Google Maps scraping). Each lead shows its
  tier — Hot, Warm or Cold — with the evidence and the source page, so you
  can check it. Turn a lead into a deal, or build it a proposal pack
  (`.docx` + `.xlsx`). See `docs/leads.md`.
- **Business profile — your company, once.** Settings → General →
  Business profile: company, services, sectors, tone, FAQs and quotation
  notes. Bots, office jobs, deal drafts (`{company}`) and proposal packs
  all use it; when it is empty, nothing is invented. See
  `docs/business-profile.md`.
- **WhatsApp sales agent.** Official WhatsApp Business API only — no QR
  pairing. Customers message your business number, the bot drafts a reply,
  and nothing is sent until you approve it in Messaging channels. Senders
  not on the allowlist get nothing. See `docs/whatsapp-agent.md`.
- **WhatsApp + Marketing from the VPS.** The same agent also
  runs on our server, so approvals work even when your computer is
  off. Connect your WhatsApp Business number + Meta tokens and
  your Facebook / LinkedIn / X / Instagram accounts from the user
  panel at https://api.localbotz.io/account (WhatsApp and
  Marketing pages). Tokens are masked everywhere and never logged.
  Posting still happens in the app for now. See
  `docs/whatsapp-agent.md`.
  for 7) gets a chase draft and a task, once per deal. See the "Always-on
  monitors" section of `docs/deal-workflows.md`.
- **📣 Marketing — write, approve, post.** Compose a post, approve it,
  post it now or on schedule. Telegram posts for real; Facebook, LinkedIn,
  X and Instagram report honestly when they are not connected or not wired
  up yet — a post is never shown as posted when it was not. See
  `docs/marketing.md`.

## Document workroom — documents with proof

Sidebar → **Workroom**. Modelled on the TeamOffice idea of a
private AI workroom for document-heavy teams. One workroom is a
vault of project documents for one job — BOQs, tenders, contracts,
SOWs, SLAs, invoices, correspondence. Search them and ask
questions, and every answer comes back with its sources: the
document name and the exact passage it came from. If the answer is
not in the documents, it says so — prices, measurements and dates
are never invented. Before anything goes to an online model,
emails, IBANs and your private terms are redacted, with a record
of what was hidden (never the values themselves); local models
never leave your computer. Export the whole workroom as one JSON
handoff package — documents, questions and answers with sources,
redaction log and reviewer notes — so another reviewer can pick
the work up. Five new templates work with it: Document Reviewer,
Tender Comparator, Contract Checker, BOQ Reviewer and Evidence
Checker. See `docs/workroom.md`.

## Settings

The **Settings** section in the sidebar has 7 pages, in this order:

1. **General** — default provider (LM Studio) + default model (Qwen3.5), workspace folder, theme (light/dark), data location, app version, reset settings. Persisted to `data/settings.json`.
2. **Connectors** — same provider/service connector list as Library > Connectors (shared store).
3. **Wallet** — local API spend tracking only, no real payments. Usage log per provider/model (calls, est. cost where known), monthly budget + alert, reset. Stored in `data/wallet.json`. Local models cost $0.
4. **Secure store** — local vault for API keys. Add/edit/delete a key per provider; stored in `.env` (gitignored). Keys are displayed **masked only** (e.g. `sk-...abcd`), never shown in full and never logged.
5. **Permissions** — global toggles (file read/write, shell, browser, web search, network) + per-bot approval mode (Ask / Auto / Full) + blocked paths. Enforced in the agent tool loop: Ask blocks mutating tools (write, shell, click/type); turning network off blocks online providers; blocked paths are refused by the file tools.
6. **Messaging channels** — same data as Library > Messaging (shared store).
7. **Devices** — this computer (hostname, OS, Python version, Playwright Chromium installed or not, LM Studio reachable or not), browser automation status, plus extra devices you add; remove extra devices (this computer cannot be removed).

## Using online providers (DeepSeek, Claude, OpenAI, Gemini, OpenRouter...)

Local mode works fully offline with no keys: LM Studio + Qwen3.5 is the default. When you have internet, you can also use online providers:

1. Get an API key from the provider (e.g. Anthropic Console for Claude, platform.openai.com for OpenAI, Google AI Studio for Gemini, openrouter.ai, console.groq.com, console.mistral.ai, cloud.cerebras.ai).
2. Add it in **Settings > Secure store** (masked, stored in `.env`), or add the line to `.env` yourself — see `.env.example` for the variable names (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `CEREBRAS_API_KEY`). Keys are never hardcoded or committed.
3. Pick the provider + model per bot — in the **Make a Bot** form, or in the chat header (provider dropdown + model field, then Apply), or from the **Available models** dropdown, which only lists models that can actually work right now. Defaults: DeepSeek `deepseek-chat`, Claude `claude-sonnet-4-5`, OpenAI `gpt-4o-mini` (Codex: `gpt-5-codex` / `codex-mini-latest` if available on your account), Gemini `gemini-2.5-flash`, OpenRouter `openrouter/auto`, Groq `llama-3.3-70b-versatile`, Mistral `mistral-small-latest`, Cerebras `llama-3.3-70b`.
4. Check status in the sidebar status line or Library > Connectors > Test: it shows configured / missing key / reachable for the selected provider, without ever displaying the key.

The tool loop works the same for every provider. Claude uses its native Messages API (tool calls are translated to/from its format in `app.py`); the others use the standard OpenAI-compatible `/chat/completions` format.

**Fallback:** if an online provider fails (no key, no internet, API error), the chat shows a clear error and, if LM Studio is reachable, offers a one-click switch back to LM Studio (local, Qwen3.5). Usage (calls/tokens/est. cost) is recorded in the Wallet.

## Providers

| Provider | Key (env var) | Models | Notes |
|---|---|---|---|
| LM Studio (local) | — | any model in LM Studio (listed live) | Default. Offline, no key. |
| Ollama (local) | — | any model in Ollama (listed live) | Fallback local server. |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` (default), `deepseek-reasoner` | OpenAI-compatible, https://api.deepseek.com/v1 |
| Claude | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` (default), `claude-opus-4-1` | Native Messages API. |
| OpenAI / Codex | `OPENAI_API_KEY` | `gpt-4o-mini` (default), `gpt-4o`, plus Codex models `gpt-5-codex` / `codex-mini-latest` if available on your account | Codex models need Codex access on the OpenAI account; if they are not available to you, pick `gpt-4o` / `gpt-4o-mini`. |
| Google Gemini (AI Studio) | `GEMINI_API_KEY` | `gemini-2.5-flash` (default), `gemini-2.5-pro` | Get a key in Google AI Studio. |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter/auto` (default) | One key, many models. |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | |
| Mistral | `MISTRAL_API_KEY` | `mistral-small-latest` | |
| Cerebras | `CEREBRAS_API_KEY` | `llama-3.3-70b` | |
| Grok (xAI) | `XAI_API_KEY` | `grok-4` | Reference-only, from the reference model list — confirm the ID in xAI's docs. |
| Kimi (Moonshot AI) | `MOONSHOT_API_KEY` | `kimi-k2` | Reference-only, from the reference model list — confirm the ID in Moonshot's docs. |
| GLM (Zhipu AI) | `ZHIPU_API_KEY` | `glm-4.5` | Reference-only, from the reference model list — confirm the ID in Zhipu's docs. |
| VPS Premium | `VPS_API_TOKEN` (your token, not a provider key) | Claude Sonnet, GPT, Gemini — whatever the VPS offers | See below. No provider keys in the client. |

Model list reference: see `models.json` and
`docs/model-reference.md`. Their marketing names (GPT 6 Astra,
Fable 5.2, Gemini 4 Carbon, Grok-4.7, Kimi K3.1 Pro, GPT-6.1 Terra, …) are
**not** provider API IDs, so LocalBotz maps them to the closest real API IDs
above and only lists a model as usable when its provider is actually
available. Image models (Nano Banana Pro, GPT Image 2.6) and video models
(Seedance 2.5, Kling 4.0, Veo 3.1) are reference-only —
LocalBotz does not generate images or videos yet.
**No Git is needed to run LocalBotz** — download the ZIP, extract it,
double-click `start.bat` (Windows) or `start.command` (Mac).

**Provider status** (Library / Settings → Connectors, and the Test button)
uses these exact states, stored with the last-checked time in
`data/connectors.json`:

- **Not connected** — no key is saved.
- **Saved, not checked** — a key is saved but has not been tested yet.
- **Connected** — the last Test succeeded (shown as "Saved" / "Connected").
- **Failed** — the last Test failed, with the error shown.

Keys are shown masked only (e.g. `sk-...abcd`) and never in full.

## Whichever model is available

You do not have to decide up front which model to use — the app shows
you what is actually usable **right now**:

- The **Available models** dropdown (chat header, and Make a Bot) is
  grouped by source — Local — LM Studio, Local — Ollama, Premium — VPS,
  Claude, OpenAI, Gemini, … — and is filled live from
  `GET /api/models/available`, which probes every source: LM Studio's
  `GET /v1/models`, Ollama's `GET /api/tags`, the VPS gateway's
  `GET /v1/models`, and the direct providers (listed only when their
  API key is configured). Press **↻ Models** to refresh it.
- A source that cannot work right now appears **greyed out with the
  reason** — e.g. "LM Studio not running", "no key", "VPS offline" —
  so you cannot pick a model that can't work without being told why.
- If a bot's saved model becomes unavailable (you unloaded it in LM
  Studio, the VPS went down, a key was removed), the chat says so
  plainly and suggests the nearest available model, with a **one-click
  switch** button. Local models work when LM Studio/Ollama is running,
  premium models when the VPS is reachable, direct providers when a
  key is set — use whichever is available.

## Premium models from a VPS

The premium models — **Claude Sonnet, GPT, Gemini** — run on our
server, so you can use them without putting any provider API key
on your own computer. The gateway lives on the VPS (it is not part
of this download); you only need the base URL and your token:

1. **Register:** in the app, Settings → Connectors → **VPS
   Premium** → "Register on the VPS" (name + email), or the
   sign-up page `https://api.localbotz.io/register`. The server
   gives you your own token.
2. **In the app:** Settings → Connectors → **VPS Premium** — paste the
   gateway base URL (e.g. `https://YOUR-VPS/v1`) and the token the VPS
   owner issued you, then **List premium models**. Or set in `.env`:
   `VPS_BASE_URL=https://YOUR-VPS/v1` and `VPS_API_TOKEN=<your token>`.
3. Pick provider **VPS Premium** per bot and choose a model from the
   live list the gateway returns.

Your provider keys stay on the VPS only — the client never holds them,
and the gateway never sends them back or writes them to logs. The
client only sends its own user token. If the VPS is unreachable or the
token is wrong, the app shows a clear error and falls back to the
local model (LM Studio).

## Your keys, your choice

LocalBotz is a single-user app — one person, one computer, your data.

- **Your computer (free):** the local model (LM Studio / Qwen3.5)
  costs nothing and needs no key.
- **Your subscriptions:** your own provider API keys live in
  Settings → Secure store (or `.env`), shown masked only, never
  logged. Add a key, pick the provider per bot, and chat.
- **Rent one from us:** premium models from our server, with your
  own VPS token (see "Premium models from a VPS" above).
- **Cost estimates:** every chat footer shows the estimated cost
  of that reply, and Settings → Wallet tracks your total estimated
  spend against a monthly budget you set. There is no billing in
  this app.
- **Voice:** text-to-speech (`POST /api/voice/tts`) works with your
  own OpenAI-compatible key; when no key is configured it returns
  an honest "not configured" error — audio is never faked.

## If LM Studio is not running

The status indicator in the UI turns red and chat replies explain how to
start it (load Qwen3.5, Start Server in the Developer tab, check the model
id). Nothing is sent to any cloud service — the model, files and browser
all stay local.

## Ollama (alternative, fallback only)

If you prefer Ollama instead of LM Studio, set in `.env`:

```bash
LLM_BASE_URL=http://localhost:11434/v1
MODEL=<the model you pulled, e.g. qwen3.5 or llama3.1:8b>
```

then `ollama serve` and `ollama pull <model>`. LM Studio remains the
default; Ollama is not required.

## Configuration

| Setting | Default | Notes |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio; Ollama fallback: `http://localhost:11434/v1` |
| `MODEL` / `LLM_MODEL` | `qwen3.5` | Exact id shown in LM Studio; per-bot model overrides this in the UI |
| `MOCK_MODE` | off | `1` or `--mock` to test without a model |
| `PORT` | `8000` | `python app.py --port 8000` |
| `HOST` | `127.0.0.1` | Local only by default |

Copy `.env.example` to `.env` to set these persistently.

## API (for scripts / curl)

```
GET  /health                    # status, provider, model, LM Studio reachability
GET  /api/status                # {provider, llm_base_url, model, llm_reachable, lm_studio_reachable}
GET  /api/templates
GET  /api/models/available     # live probe: only models usable right now, grouped by source
GET  /api/providers/{id}/models # live list for one provider (LM Studio/Ollama/VPS/…)
GET  /api/vps/config           # VPS Premium base URL + token status (masked)
GET  /api/vps/models           # premium models the VPS gateway offers
GET  /api/tools
GET  /api/bots                  # list bots
POST /api/bots                  # {"name","instructions","model","template"}
GET  /api/bots/{id}/chat
POST /api/bots/{id}/chat        # {"message": "..."} -> {"reply","tools"}
POST /api/bots/{id}/chat/reset
GET  /api/bots/{id}/memory
POST /api/bots/{id}/memory      # {"fact": "..."}
GET  /screenshots/<file>        # browser screenshots
```

The status check probes `GET {LLM_BASE_URL}/models` and reports whether
LM Studio (or the configured provider) is reachable.

## Project layout

```
app.py                 FastAPI app + agent tool loop + LLM client (pathlib, cross-platform)
static/index.html      Single-page UI: chat, Make a Bot, Library, Settings (no build step)
static/logo.png        LocalBotz logo (also in assets/logo.png)
static/logo-animated.svg  Animated logo used in the app header (robot blinks, letters rise in)
static/logo-animated.gif  Animated logo (pulse, shimmer, dot bounce, blink)
assets/logo.png        LocalBotz logo for the GitHub repo / README
assets/logo-animated.svg  Animated wordmark (SVG, standalone in a browser)
assets/logo-animated.gif  Animated logo for the README top
assets/logo-animated.mp4  Animated logo, 4 s video (also .webm) for social / README
templates.json         15 shipped bot templates (copied to data/templates.json)
start.bat              Windows starter (venv + core deps, browser optional + run)
start.sh               macOS/Linux starter (venv + core deps, browser optional + run)
requirements.txt       Core: fastapi, uvicorn, httpx (full install also adds requirements-browser.txt: Playwright + Chromium)
requirements-browser.txt  Optional: playwright (browser automation)
.env.example           LLM_BASE_URL / MODEL (qwen3.5) / VPS_BASE_URL + VPS_API_TOKEN /
                       all optional provider API keys
LICENSE                MIT — copyright Thomas
CONTRIBUTING.md        How to contribute (no secrets in commits, local-first)
SECURITY.md            How keys are protected, how to report a vulnerability
workspace/             The ONLY folder bots can read/write (welcome.txt inside)
data/                  bots.json, chats/, memory/, screenshots/, templates.json,
                       settings.json, connectors.json, mcp_servers.json, skills.json,
                       wallet.json, permissions.json, messaging.json, devices.json
                       (created at runtime; .env holds keys, gitignored)
```

## Safety notes

- Bots run with the tools above, but files are sandboxed to `./workspace`
  and shell commands are allowlisted with shell metacharacters
  (`; & | \` $ > <`) rejected and a 30 s timeout. File commands are
  implemented in Python, so they cannot invoke a platform shell at all.
- The server binds to `127.0.0.1` by default — only your computer can reach it.
- Keep it that way if you connect messaging apps later; do not expose it
  publicly without authentication.

## What this is NOT (yet)

No live WhatsApp/Telegram/Discord messaging
(config + approved senders only, status Not connected), no live
Gmail/Drive/Calendar connectors (config + setup instructions only).
MCP servers *are* in v1: add one in Library > MCP servers and Test really
runs it (stdio JSON-RPC or HTTP `tools/list`) and lists its tools.
Those gaps are the natural next steps — the bot/tool structure in `app.py`
(`TOOLS`, `run_agent`) is where they would plug in.

---

LocalBotz is a product of WEBGINET ENTERPRISE PRIVATE LIMITED. MIT licensed (© WEBGINET ENTERPRISE PRIVATE LIMITED) and built in the open. [Read the code](https://github.com/webginet-sys/localbotz), run it from source, or [send a pull request](https://github.com/webginet-sys/localbotz/pulls).
