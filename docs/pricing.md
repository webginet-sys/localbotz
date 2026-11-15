# Pricing — the pricing panel

LocalBotz has three ways to run, and only one of them costs
anything through LocalBotz itself. See `docs/how-it-runs.md`.

| Way to run | Who you pay | Price |
|---|---|---|
| **Your computer** (local model) | Nobody | **$0** — free, unlimited |
| **Your subscriptions** (your own API keys) | Your provider (Anthropic, OpenAI, xAI, Google…) | Whatever your provider charges. LocalBotz adds nothing. |
| **Rent one from us** (VPS Premium) | The LocalBotz server owner | Pay-as-you-go, per 1M tokens — see below |

## Rent-from-us prices (USD per 1M tokens)

These are the defaults, the providers' public list prices. The
server owner can change any of them in the VPS admin panel
(https://api.localbotz.io/admin), and the new price applies to
later requests.

| Model | Input / 1M | Output / 1M |
|---|---|---|
| Claude Sonnet 4.5 | $3.00 | $15.00 |
| Claude Opus 4.1 | $15.00 | $75.00 |
| GPT-4o | $2.50 | $10.00 |
| GPT-4o mini | $0.15 | $0.60 |
| Gemini 2.5 Flash | $0.30 | $2.50 |
| Gemini 2.5 Pro | $1.25 | $10.00 |
| DeepSeek Chat | $0.27 | $1.10 |
| DeepSeek Reasoner | $0.55 | $2.19 |
| Grok-4 | $3.00 | $15.00 |
| Kimi K2 | $0.60 | $2.50 |
| GLM-4.5 | $0.60 | $2.20 |

Grok / Kimi / GLM are starting prices — confirm them in the
provider's own docs before relying on them. Local models are
always free and never appear in the price list.

## Where the prices live

- **Server:** the price table lives on the VPS and is set by the
  server owner in the VPS admin panel
  (https://api.localbotz.io/admin). The same table prices every
  premium request.
- **Public price list:** `GET /v1/pricing` on the gateway — no
  auth needed, so users can see what renting costs before they
  register. The app shows it under Settings → Connectors →
  VPS Premium → Show prices.
- **Client:** the app keeps a copy of the price table in
  `data/pricing.json` for cost estimates only — the estimated
  cost shown under each chat reply and in Settings → Wallet.
  Local models are always $0.
