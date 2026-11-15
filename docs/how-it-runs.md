# How LocalBotz runs

> Use the subscriptions you already pay for to run agents in your
> personal office. Works with Claude, ChatGPT, Grok, Gemini and more.
> Give your agents your computer — or rent one from us.

There are three ways your agents run. Pick one, or mix them — a
different bot can use a different one.

## 1. Your computer (free)

Your agents run on your own computer, on your downloaded local
model. Install once and LocalBotz sets it up: Python, LM Studio,
and Qwen3.5, plus browser automation. Nothing leaves the computer,
no account, no key, no bill.

- Default provider: **LM Studio** (`http://localhost:1234/v1`),
  model **Qwen3.5**. Ollama works the same way.
- Set it in the app: Settings → General → "Use my computer".
- This is the default. If the local model is not running, the app
  says so and falls back to mock mode — it never pretends a real
  model answered.

## 2. Your subscriptions (bring your own keys)

Use the provider accounts you already pay for. Works with Claude,
ChatGPT (OpenAI / Codex), Grok (xAI), Gemini, DeepSeek, Kimi, GLM,
OpenRouter, Groq, Mistral and Cerebras — see the providers table in
the README.

- Add each key once in Settings → Secure store (or `.env`). A key
  is sent only to its own provider, never to anyone else, and is
  never committed or logged.
- Provider status shows **Not connected / Saved, not checked /
  Saved / Connected** — the same wording as your own list.
- The model list is availability-driven: a model only appears as
  usable when its provider is actually reachable or its key is set.
- Honest note: "your subscriptions" here means your **API keys**
  for those providers. LocalBotz does not wrap the terminal CLIs
  (Claude Code, Codex, Gemini CLI…) the way Munder Difflin does —
  it talks to each provider's API directly. If you already pay for
  one of those subscriptions, its API key is what you add here.

## 3. Rent one from us (premium, metered)

No keys of your own? Rent our computer instead. Premium models —
Claude Sonnet, GPT, Gemini — run on the LocalBotz server (the VPS
gateway, run by the service owner), using the owner's provider keys,
which stay on the server and never reach your computer.

- Register on the server: in the app, Settings → Connectors →
  VPS Premium → "Register on the VPS" (name + email), or the
  sign-up page `https://api.localbotz.io/register`. The server
  creates your account and gives you your own token.
- Your token goes in Settings → Connectors → VPS Premium. Then
  pick provider **VPS Premium** per bot.
- Usage is metered by the server — that is the "rent": you pay
  for what the premium models use, nothing else. The app's
  Wallet page (Settings → Wallet) tracks your estimated spend.

## Your office runs on any of the three

The Office (Sidebar → Office) is the personal office the agents
work in: boss + team, shared memory, blackboard. A team member is
a normal bot, so each member can run a different way — the
Researcher on your computer, the Writer on your Claude
subscription, the Analyst on the rented server. The boss assigns
the work; how each member runs is its own provider setting.
