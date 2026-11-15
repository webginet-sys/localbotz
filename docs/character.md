# Muse, the character who lives in your PC — speaks first, phone link, Home

LocalBotz's own take on the "assistant that lives in the computer" idea:
one named character — **Muse** — who greets you, remembers what you tell
it, and can speak first when you ask it to. It is the experience side of
LocalBotz; the capability side (browser automation, desktop control,
routines, deals, WhatsApp with approval) already existed.

This is LocalBotz-native code, written from scratch. No Stonic or JARVIS
names, branding, sci-fi HUD look, pricing or code is used anywhere.

## 1. The character — Muse

Settings → Character, or step 4 of the first-run wizard.

- **Name** (default `Muse`), **style**: Mentor (default), Friend,
  Professional, or Custom (write the way of speaking yourself).
- **Your name**, so Muse greets you by name, and an optional custom
  greeting (use `{user}` for your name, `{name}` for the character).
- **Voice prefs**: speed 0.5–2.0, pitch 0.5–2.0, voice name (part of a
  voice name your browser offers). Talk, Live Voice and the Hear buttons
  use these; the speaker toggle in chat uses them too.
- **Things Muse remembers**: short notes you teach it ("My company is
  Al Rayyan Trading — we do MEP in Doha"). Add and forget them in
  Settings → Character. They are injected into every bot's prompt, after
  memory and learnings, alongside the business profile.
- Switch the character off and bots speak as themselves again.
- Storage: `data/character.json`. Endpoints: `GET/PUT /api/character`,
  `POST /api/character/remember`, `DELETE /api/character/remember/{i}`,
  `POST /api/character/greet` (greeting + today's brief headline).

## 2. Speaks first — permission-gated, never unsolicited audio

All three switches live in Settings → Character and are **off by default**.

- **Morning brief** (`morning_brief_enabled` + time, default 08:00):
  the 30-second background worker prepares today's brief once a day, at
  that time, and only once (`last_brief_date`). The brief is built only
  from real data — routines due today, deals Quoted/Negotiation with no
  movement for 3+ days, new leads, pending background tasks — and says
  plainly when nothing needs attention. Nothing is invented: no number
  or date appears unless the stored data has it.
- **Spoken nudges**: when a deal monitor fires for a deal today, the
  worker leaves one nudge on the Home brief — once per deal per day.
- **Honest limit — browsers do not allow a page to play audio without
  you tapping first.** So "speaks first" never means sound out of
  nowhere: the Home page shows the brief and the nudge with a
  "🔊 Hear …" button, and you tap it. If the app was closed at brief
  time, the brief is prepared when you next open it (the worker checks
  the time, not a missed alarm).
- Endpoints: `GET /api/brief` (live, from real data), `POST /api/brief/prepare`.

## 3. Phone link — the bridge to the mobile app

Settings → Phone link. "Call Muse from your phone while this PC is on."

- **Pairing**: `POST /api/phone/pair` makes a one-time 6-digit code
  (10 minutes, one use). The code is shown once on the PC and stored
  only as a SHA-256 hash. `POST /api/phone/verify` with the code returns
  a session token (7 days, stored only as a hash).
  `GET /api/phone/status`, `POST /api/phone/revoke` (unlinks every phone).
- **Phone page** (`GET /phone`): enter the code once, then talk (mic via
  the browser's speech recognition, Chrome/Edge) or type to Muse — the
  same character, the same chat history, spoken replies after you tap
  "Hear replies". No audio is saved, on the phone or on the PC.
- **Honest limits, shown on the page**: the PC must stay on and
  LocalBotz open; the phone must be on the same Wi-Fi and able to reach
  the PC (the page shows the PC's local address + port); there is **no
  cloud relay** — this is your Wi-Fi only, on purpose, so voice and
  chats stay on your own machines. If the phone cannot reach the PC,
  the phone page says so plainly.
- This is LocalBotz's own pairing code — **not WhatsApp pairing** and
  nothing to do with WhatsApp Web (QR pairing is a ban risk and is not
  used anywhere in LocalBotz).
- Known limit: the pairing code gates entry to the phone page. The
  local app's own API has no login (same as the main app on your PC),
  so anyone already on your Wi-Fi who knows the address can open the
  app — the code keeps casual access out of the phone page, it is not
  a password for your network.

## 4. Home — your day at a glance

The 🏠 Home button (top of the sidebar) is the default view once setup
is done. Teal LocalBotz design, functional — not a sci-fi HUD copy.

- Character greeting card (avatar, "Good morning, Thomas", Hear my
  brief / Talk / Live Voice buttons).
- Today's brief card (with Hear + Refresh).
- Spoken nudge card, only when one is waiting.
- Deals needing attention (stuck / quoted, with Open buttons),
  routines due today, quick stats (bots, deals, leads, workrooms,
  learnings), what the team has learned lately.
- Every number comes from `GET /api/home`, which reads the real stores;
  empty states say plainly "nothing needs attention".

## 5. Floating bar + live overlay with a real Stop

- **Floating bar**: a small bar at the top of the app, always there —
  Muse's status (**Idle / Listening / Working**), one-tap 🎙️ Talk, and
  a ⏹ Stop button. Minimise it with `—` on the bar (it collapses to a
  small "🤖 Muse" notch); switch it off entirely in Settings →
  Character ("Show the floating bar"). The status follows real work:
  Working while a chat reply or a desktop job runs, Listening while
  the mic is open.
- **Desktop jobs**: the 🖥️ Desktop page has "Run a desktop job" — one
  step per line (`inspect`, `activate w1`, `click e1`,
  `type e1 2,390,907`, `key ctrl+s`, `screenshot`), up to 10 steps.
  Steps run one at a time with a short pause between them, through the
  same permission gate as a single desktop action (Desktop toggle +
  per-tool toggles must allow every step's tool).
- **Live overlay + Stop**: while a job runs, a card at the top of the
  app says "Working on step X of Y — [plain step text]" with a ⏹ Stop
  button; **Esc stops it too**. Stop sets the job to `stopped` on the
  server and the runner checks before every step — no further step
  runs, and the stop is written to the desktop log with the step it
  stopped at. The single "Do it on the desktop" action shows the same
  overlay while it runs; Stop there cancels the wait (if the click
  already happened, it cannot be undone — the overlay says so).
  Stop also cancels a spoken reply, the mic, and a live voice session.
- Endpoints: `POST /api/desktop/job`, `GET /api/desktop/jobs`,
  `GET /api/desktop/job/{id}`, `POST /api/desktop/job/{id}/stop`.
- **Honest limits**: this is an in-app bar and overlay, **not** a
  separate always-on-top OS window — that would need a desktop shell
  change and is not built here. When you leave the LocalBotz tab the
  bar goes with it. A chat message already sent cannot be unsent by
  Stop; Stop ends the desktop work, the voice, and the speech.
- **Pre-existing bug fixed in this copy (also in the live repo, not
  introduced here)**: `q` and `msg` were only defined inside
  `bindPage`, but the wizard wiring, `wfStepsRender`, the persistent
  toggle and `wizFinish` use them at top level — so the whole page
  script died on load with `q is not defined` and nothing (bots,
  status, wizard) ever ran. Both are now defined once at top level
  in `static/index.html`. The parent should apply this fix to the
  live repo even apart from this build — it is a one-line-each fix.

## API summary

| Endpoint | What it does |
|---|---|
| `GET/PUT /api/character` | Read / save the character |
| `POST /api/character/remember`, `DELETE /api/character/remember/{i}` | Teach / forget a fact |
| `POST /api/character/greet` | Greeting + brief headline |
| `GET /api/brief`, `POST /api/brief/prepare` | Today's brief, from real data |
| `GET /api/home` | Everything the Home page shows |
| `GET /api/phone/status`, `POST /api/phone/pair`, `POST /api/phone/verify`, `POST /api/phone/revoke` | Phone pairing |
| `GET /phone` | Phone-friendly Talk page |
| `POST /api/desktop/job`, `GET /api/desktop/jobs`, `GET /api/desktop/job/{id}`, `POST /api/desktop/job/{id}/stop` | Desktop jobs with a real Stop |

## What was NOT verified here

- Real-model replies as Muse (mock mode only in testing).
- Real browser speech recognition / voices (browser- and OS-dependent).
- A real phone on a real Wi-Fi network reaching the PC (tested with
  HTTP calls to the pairing endpoints, not a handset).
- Real Gemini Live sessions with the character (needs a Gemini key).
- A real Windows desktop job (mock desktop only here); the Stop path
  was tested against the mock desktop, where each step is a fast local
  call with a 1.5 s pause between steps.
