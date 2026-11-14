# Hermes Agent features in LocalBotz

Modelled on Hermes Agent (Nous Research, MIT) — the open-source
agent that runs as a persistent process on your computer, works
through multi-step tasks, keeps memory between sessions, and
answers on Telegram. LocalBotz does the same things, its own way:
no separate CLI, no second app — it is built into the bot you
already have.

## 1. Persistent agents — keep working in the background

Open a bot and turn on **"Keep working in the background"**.
A persistent bot is a standing agent: give it goals and it works
through them one at a time, even while you are doing something
else. A non-persistent bot only works when you chat with it.

- The background worker checks every 30 seconds for the oldest
  pending task of each persistent bot and runs it.
- You can also run any task right now with **Run now**.
- The bot's provider, model, tools and permissions all apply
  exactly as they do in chat — Permissions is still the leash.

## 2. Autonomous tasks — give it a goal, not a message

On the bot's page, under **Persistent agent**, type a goal —
e.g. "Research competitors and save a brief in workspace" — and
**Add task**. The agent works through it with its normal tool
loop (web search, browser, files, safe commands — up to 8 steps),
then the task shows as **done** with its tool steps and result,
or **failed** with the reason.

Tasks live in `data/agent_tasks.json` (one entry per task: goal,
status, steps, result, created/finished times). Delete a task any
time; deleting the bot does not delete its finished tasks.

## 3. Memory between sessions — it remembers what it did

Bots already had long-term memory (facts you add, shown under
**Memory** and included in every reply). Hermes-style, the agent
now also writes its own memory: after every finished task it
appends one line — "Completed task '…' (done): …" — so the next
task, the next chat, and the next session all start from what it
already learned. Nothing is sent anywhere; memory is a local file.

## 4. Telegram — a real listener

Hermes connects to Telegram and Discord. LocalBotz connects to
Telegram for real:

1. Talk to @BotFather, create a bot, copy its token.
2. Settings → Secure store → add it as `TELEGRAM_BOT_TOKEN`
   (or paste it in Messaging → Telegram → Bot token).
3. Library → Messaging → Telegram: enable the channel, turn on
   inbound replies, add approved senders (Telegram user id or
   username), and pick which bot answers.
4. Done. LocalBotz polls Telegram every few seconds and answers
   approved senders with that bot. No webhook, no public URL,
   nothing to expose.

Only approved senders ever get a reply. Anyone else is ignored
silently. The Messaging page shows the listener state
(listening / ready / no token), messages answered, and the last
error. `GET /api/messaging/telegram/status` returns the same.

## What it is not yet

- **Discord is not live.** It needs a websocket gateway, not
  polling. Its page is still config-only, honestly labelled.
- **WhatsApp is not live.** It needs a public webhook URL.
  Config-only for now.
- **No 64K-context requirement.** Hermes Agent refuses models
  under 64K context because its tool definitions are large.
  LocalBotz's tool loop is smaller, so it works with the local
  Qwen3.5 default — but a bigger context still helps a persistent
  agent on long tasks. In LM Studio, set the model's context
  length to 64K or more if you can.
- **No separate Hermes CLI.** LocalBotz does not wrap the
  `hermes` command — these features are built into the app
  itself, on the local model by default.
