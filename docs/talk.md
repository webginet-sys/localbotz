# Talk + Show-me-how

The mission: everyone should be able to talk to their computer in
plain words — no prompting, no tutorials, no keyboard and menus to
learn. The bot shows them how, on their own screen, in the moment,
in their own context. This is for office, sales and marketing work,
for non-technical people.

Talk is the **one** voice mode in LocalBotz. It is not a separate
voice-agent product, and it does not change the earlier rule that
voice agents, image/video generation, game bots and fine-tuning are
out of scope.

## Talk — voice in, voice out

### In the browser (no install, no keys)

Sidebar → chat. In the chat header:

- **🎙️ Talk** — tap it and speak in plain words. The browser's
  built-in speech recognition (Chrome/Edge) types what you said
  into the chat box and sends it as a normal chat message. You
  see the words appear as you speak (interim results); tap again
  to stop.
- **🔊 Listen** — when on, the bot's replies are read out loud
  with the browser's built-in speech synthesis. Short replies
  only (first two sentences, ~600 characters). Tap it again to
  stop — it stops mid-sentence. The setting is remembered on
  this computer (localStorage).

Both degrade honestly: a browser with no speech recognition
says so when you tap Talk ("Talk needs Chrome or Edge — your
browser has no speech recognition") and never crashes the chat.
No audio is recorded by LocalBotz, no key is needed, nothing is
uploaded for the browser path — the browser's own speech service
does the listening.

### Plain-language rule

When Talk is on — the mic was used, the speaker is on, or the
bot has **Talk mode** on — the bot's instructions gain:

> The user is talking, not typing. Reply in short plain
> sentences, no jargon, no menus, no tutorials. If something is
> unclear, ask ONE simple question in plain words. Never ask the
> user to write a better prompt.

**Talk mode** is a per-bot setting: Make-a-bot → "Talk mode"
checkbox, or `talk_mode: "on"` in the bot. The **Desktop
Helper** template has it on. A bot with Talk mode on always
answers in plain words, even when you type.

### Server transcription (optional, local only)

`POST /api/talk/transcribe` — upload an audio file
(multipart, max 25 MB). It transcribes locally with
`faster-whisper` **only if it is installed**; otherwise it
returns an honest **501** — "Local transcription is not
installed — Talk in the browser works without it."

`faster-whisper` is deliberately **not** in
`requirements.txt` — the install stays light. To add it:
`pip install faster-whisper` (optional, see the 501 message).
No cloud speech-to-text, no key, no audio saved: the bytes are
read into memory and transcribed from an in-memory file that is
deleted immediately — no audio file is ever written to
`data/`. No audio → 400.

## Show-me-how — visible steps on your screen

**👀 Show me how** in the chat header flips it on for the
current bot (and saves it on the bot, like Smart routing).
Or Make-a-bot → "Show me how" checkbox, or
`show_me_how: "on"`. The Desktop Helper template has it on.

When it is on, the bot still does the work — it just shows
each step:

1. **It explains before it acts.** The bot's instructions gain:
   "Show, don't just do: explain each step in plain words
   BEFORE you do it, one step at a time, and say what you are
   about to click or type and where, so the user can follow on
   their own screen."
2. **Each tool call becomes a visible step.** The chat reply
   carries a `steps` list: `{n, tool, plain, target,
   result_summary, screenshot}` — "plain" is one plain
   sentence, e.g. "Now I'll open Excel and look at the BOQ
   total." The chat shows it as **"Here's how I did it —
   step 1… step 2…"** under the reply, with a 📷 link per step.
3. **A picture after each desktop/browser step.** After a
   `desktop_*` or `browser_*` action, LocalBotz takes a
   screenshot and attaches it to that step — with a short
   pause (~1 second) between steps, so the user can follow.
   This happens **only** in Show-me-how mode, never in normal
   mode, and normal chats return no steps list.
4. **"Do it for me" vs "Show me how" is just the toggle.**
   Same bot, same work — off, it does it quietly; on, it shows
   every step. Nothing else changes.

### API

| Endpoint | What it does |
|---|---|
| `POST /api/bots/{bot_id}/chat` | `{message, talk?, show_me_how?}` — `talk: true` turns on the plain-language rule for that chat; `show_me_how: true` turns on visible steps for that chat. Returns `steps` in the response when on. |
| `POST /api/bots/{bot_id}/show-me-how` | `{task, talk?}` — runs the bot with Show-me-how on and returns `{reply, steps, tools}`. Reuses `run_agent`; the loop is not duplicated. |
| `POST /api/talk/transcribe` | Local transcription (see above) — 501 without faster-whisper, 400 with no audio. |

Chat history saves the steps with the assistant message, so
re-opening a chat still shows how it was done.

## Honest limits

- **Browser speech recognition needs Chrome or Edge**, and its
  speech service needs the internet — it is not fully local.
  Firefox/Safari have no built-in recognition in the browser,
  so Talk there says so plainly. The speaker (speech
  synthesis) works in most browsers; which voices you get
  depends on the OS and browser.
- **Local transcription is optional and not installed by
  default.** Without faster-whisper, `POST /api/talk/transcribe`
  is a 501 — by design, to keep the install light.
- **Show-me-how screenshots need the desktop/browser to be
  available.** In mock mode the steps are labelled
  `[MOCK MODE]` and the screenshots are mock desktop pictures.
  On a headless machine there is no real desktop to photograph.
- **Talk mode is plain words, not a different model.** The bot
  still uses its configured provider/model; Talk only changes
  how it talks to you.
