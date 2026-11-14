# Model list — reference names

LocalBotz keeps a reference catalogue of model names in `models.json`
(compiled from public model lists, November 2026). Some of those names
are **marketing names**, not provider API model IDs. LocalBotz only sends
a model ID to a provider when that provider's own API accepts it.

## Reference names, and what LocalBotz actually calls

| Reference name | LocalBotz provider | API model actually used | Status |
|---|---|---|---|
| GPT 6.1 Sol / GPT 6 Astra / GPT 6 Luna | OpenAI | `gpt-4o`, `gpt-4o-mini` | Verified — GPT 6 IDs not published yet |
| Fable 5.2 / Sonnet 5.5 / Opus 5.5 | Claude | `claude-sonnet-4-5`, `claude-opus-4-1` | Verified — 5.x IDs not published yet |
| Gemini 4 Carbon / Flash 3.8 | Gemini | `gemini-2.5-flash`, `gemini-2.5-pro` | Verified — Gemini 4 IDs not published yet |
| DeepSeek | DeepSeek | `deepseek-chat`, `deepseek-reasoner` | Verified |
| GPT-6.1 Terra | OpenAI | `gpt-4o`, `gpt-4o-mini` | Verified — GPT 6.1 Terra ID not published yet |
| Gemini Omni Flash 1.2 | Gemini | `gemini-2.5-flash`, `gemini-2.5-pro` | Verified — Omni Flash 1.2 ID not published yet |
| Kimi | Kimi (Moonshot AI) | `kimi-k2` | Reference-only — needs `MOONSHOT_API_KEY`, confirm ID in Moonshot docs |
| Kimi K3.1 Pro | Kimi (Moonshot AI) | `kimi-k2` | Reference-only — K3.1 Pro ID not published yet, confirm in Moonshot docs |
| GLM | GLM (Zhipu AI) | `glm-4.5` | Reference-only — needs `ZHIPU_API_KEY`, confirm ID in Zhipu docs |
| Grok-4.7 | Grok (xAI) | `grok-4` | Reference-only — needs `XAI_API_KEY`, confirm ID in xAI docs |
| Muse Wonder / Spark 1.3 / Wonder 1.0 | — | — | Reference-only — no public API, no provider yet |
| Nano Banana Pro / GPT Image 2.6 | — | — | Reference-only — image models, LocalBotz does not generate images yet |
| Seedance 2.5 / Kling 4.0 / Veo 3.1 | — | — | Reference-only — video models, LocalBotz does not generate videos yet |
| Local models | LM Studio / Ollama | whatever is live, default `qwen3.5` | Verified |

The image and video models are **not chat models** — LocalBotz does not
generate images or videos yet, so they are reference-only in `models.json`,
listed for comparison and never sent to an API.

## Rules that stay in place

- **Availability-driven, not a fixed list.** The Available-models picker
  only shows a model as usable when its source is actually reachable
  (LM Studio / Ollama live probe, VPS gateway live probe, or a direct
  provider with a key set). A reference-only model with no key is shown
  as unavailable with the reason, never as if it works.
- **No fake models.** A marketing name is never sent to a
  provider API as if it were a real model ID. When a provider publishes
  the matching ID, update `models.json` and `KNOWN_DEFAULT_MODELS` in
  `app.py` to that exact ID.
- **Keys.** New providers need their own key in Settings → Secure store
  or `.env`: `XAI_API_KEY` (Grok), `MOONSHOT_API_KEY` (Kimi),
  `ZHIPU_API_KEY` (GLM). No key, no use.
