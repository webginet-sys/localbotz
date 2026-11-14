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
server owner can change any of them in the admin panel (Pricing),
and the new price applies to later requests.

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

- **Server:** `server/data/pricing.json` on the VPS, managed
  through the admin panel (`GET /admin` → Pricing) or the API
  (`GET /admin/pricing`, `POST /admin/pricing`, header
  `X-Admin-Token`). The same table is used to price every premium
  request: each completed chat writes its cost into `usage.log`.
- **Public price list:** `GET /v1/pricing` on the gateway — no
  auth needed, so users can see what renting costs before they
  register. The app shows it under Settings → Connectors →
  VPS Premium → Show prices.
- **Client:** the app's own Super Admin pricing
  (`data/pricing.json`, Settings → Super Admin) is the same
  table for the client's own metering and wallets. Keep the two
  in step when you change a price.

## The pricing panel (admin panel → Pricing)

Open `GET /admin` on the VPS, enter the admin token, go to
**Pricing**. You see one row per premium model with its input
and output price per 1M tokens. Change a number, hit **Save
pricing** — done. There is nothing else to configure: no plans,
no tiers, no hidden fees. Pay-as-you-go only.

## Revenue (admin panel → Revenue)

Every premium request is metered: tokens in/out and cost, per
workspace and per model, in `usage.log`. The **Revenue** tab
shows total revenue, requests billed, paying workspaces, cost by
model, and the last 14 days. That is the money the rented server
has earned. The **Overview** tab shows the same total at a glance.

## Wallets (client Super Admin)

On the client side, workspaces have wallets (`data/wallets/`)
and metering (`data/metering.jsonl`): master-paid usage is
charged to the workspace wallet at these prices, with a low
balance warning (default $1). Local and BYOK usage costs the
host $0 and is tracked only. See Super Admin → Wallet in the app.
