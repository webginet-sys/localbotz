# Live Voice — real-time conversation

Talk (the mic button in chat) is turn-by-turn: you speak, it types,
it answers. Live Voice is the next step: a live conversation. Tap
**Start live voice**, talk in plain words, and the bot answers out
loud while you speak — interrupt it any time, and it can do things
on the desktop when you ask ("look at the BOQ", "click the total").

## How it works

1. **Start.** Sidebar → 🔴 Live Voice. Pick the bot, tap **Start
   live voice**. The browser asks for the microphone. The mic is live
   **only** while this page is open and you tapped Start.
2. **Talk.** Your voice streams to the server as raw 16kHz PCM
   (what Gemini Live needs) over the Live Voice WebSocket
   (`/ws/live-voice`). The model answers with spoken audio (24kHz
   PCM) and a live transcript on the page — your lines and its lines
   as they arrive.
3. **Interrupt.** Tap **✋ Interrupt**, or just start talking while
   it speaks — playback stops at once, the model is told to stop,
   and it waits for what you say next.
4. **Stop.** Tap **■ Stop**, or leave the page, or say nothing for
   2 minutes — the session stops itself, the mic closes, and the
   words (text only, no audio) are saved into the bot's chat history.

## The engine — and what it costs

Live voice runs on **Google Gemini Live** (`gemini-3.8-live`, the
current model from Google AI Studio's Live API docs, checked
2026-11-14; override with `GEMINI_LIVE_MODEL` in `.env` if Google
moves on), through the `google-genai` SDK. It needs:

- **Internet** — Gemini Live is an online service.
- **A Gemini key** (`GEMINI_API_KEY` in Secure store). Live usage
  is **billed to the key owner** — it is not free and it is not
  local. Without a key the Live page says so honestly and refuses
  to start a session. It never fakes a live session.
- **The live install** — `google-genai` + `websockets`
  (`requirements-live.txt`), installed best-effort by start.bat /
  start.sh. If that install fails, the app still starts, Talk
  still works, and the Live page says what is missing.

The local LM Studio model is text-only and **cannot** do live
audio. That is why live voice uses Gemini, while everything else
in LocalBotz still defaults to the free local model.

## Desktop tools in live voice

When you ask the live bot to do something on the computer, it can
call the desktop tools — `desktop_inspect`, `desktop_click`,
`desktop_type` — declared as Gemini Live function calls. They run
through the same permission gate as every other tool: Desktop
control off in Settings → Permissions blocks them, and a bot on
**Ask** blocks clicking/typing. Every live desktop action is logged
to `data/desktop_log.json` with source `live-voice`, and the result
shows in the live transcript.

## Safety and privacy

- Mic only in a started session. Leaving the page stops the
  session and closes the mic. Nothing streams while stopped.
- Auto-stop after 2 minutes of silence (`LIVE_SILENCE_SECONDS`
  in `.env` changes it, 5–1800 seconds).
- **No audio is ever saved** — audio is streamed and discarded.
  Only the text transcript is kept, in the bot's chat history.
- Every live session is logged (`data/live_sessions.json`:
  start/stop, duration, turns, interrupted count — no audio).
- The Gemini key is read from `.env` / Secure store only, never
  logged, never sent to the browser.

## Honest limits

- Real Gemini Live was **not verified from here** — there is no
  Gemini key in this environment, so the live session was tested
  in mock mode only. First real run needs Thomas's Gemini key.
- Latency depends on the network — Gemini says under 200ms
  round-trip on a good connection; on a slow one it will be slower.
- The browser mic needs Chrome or Edge and a mic permission.
- A live audio session is capped by Gemini (about 15 minutes for
  audio-only); the page will end the session when Gemini does, and
  the transcript is still saved.
- Live voice is conversation + desktop tools only. It does not do
  video, screen sharing, or image generation.
