# Model list — reference: ChatLLM (Abacus.AI)

Source: https://chatllm.abacus.ai/ — ChatLLM Teams page, read 2026-11-14.
Used as a **reference for the model list only**. LocalBotz is a separate,
local-first app — it does not use ChatLLM, and it does not copy ChatLLM's
code or branding.

## What ChatLLM lists

> "Every top AI model. One assistant." — 100+ top AI models.

- **GPT** — GPT 6.1 Sol, GPT 6 Astra + Luna
- **Claude** — Fable 5.2, Sonnet 5.5 + Opus 5.5
- **Gemini** — Gemini 4 Carbon + Flash 3.8
- **DeepSeek + Kimi + GLM**
- **Grok** — Grok-4.7
- **Muse** — Muse Wonder + Spark 1.3

## How LocalBotz uses this list

The full mapping lives in `models.json` at the repo root.

**Important:** most of those names are marketing names on the ChatLLM
page, not provider API model IDs. LocalBotz only sends a model ID to a
provider when that provider's own API accepts it.

| ChatLLM name | LocalBotz provider | API model actually used | Status |
|---|---|---|---|
| GPT 6.1 Sol / GPT 6 Astra / GPT 6 Luna | OpenAI | `gpt-4o`, `gpt-4o-mini` | Verified — GPT 6 IDs not published yet |
| Fable 5.2 / Sonnet 5.5 / Opus 5.5 | Claude | `claude-sonnet-4-5`, `claude-opus-4-1` | Verified — 5.x IDs not published yet |
| Gemini 4 Carbon / Flash 3.8 | Gemini | `gemini-2.5-flash`, `gemini-2.5-pro` | Verified — Gemini 4 IDs not published yet |
| DeepSeek | DeepSeek | `deepseek-chat`, `deepseek-reasoner` | Verified |
| Kimi | Kimi (Moonshot AI) | `kimi-k2` | Reference-only — needs `MOONSHOT_API_KEY`, confirm ID in Moonshot docs |
| GLM | GLM (Zhipu AI) | `glm-4.5` | Reference-only — needs `ZHIPU_API_KEY`, confirm ID in Zhipu docs |
| Grok-4.7 | Grok (xAI) | `grok-4` | Reference-only — needs `XAI_API_KEY`, confirm ID in xAI docs |
| Muse Wonder / Spark 1.3 | — | — | Reference-only — no public API, no provider yet |
| Local models | LM Studio / Ollama | whatever is live, default `qwen3.5` | Verified |

## Rules that stay in place

- **Availability-driven, not a fixed list.** The Available-models picker
  only shows a model as usable when its source is actually reachable
  (LM Studio / Ollama live probe, VPS gateway live probe, or a direct
  provider with a key set). A reference-only model with no key is shown
  as unavailable with the reason, never as if it works.
- **No fake models.** A ChatLLM marketing name is never sent to a
  provider API as if it were a real model ID. When a provider publishes
  the matching ID, update `models.json` and `KNOWN_DEFAULT_MODELS` in
  `app.py` to that exact ID.
- **Keys.** New providers need their own key in Settings → Secure store
  or `.env`: `XAI_API_KEY` (Grok), `MOONSHOT_API_KEY` (Kimi),
  `ZHIPU_API_KEY` (GLM). No key, no use.
