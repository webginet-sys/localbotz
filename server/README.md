# LocalBotz VPS Premium gateway

A small FastAPI server that runs on **your VPS** and serves premium models
(Claude Sonnet, GPT, Gemini) to LocalBotz clients over an OpenAI-compatible
API — without any provider API key ever leaving the VPS.

```
LocalBotz app (your computer)                Your VPS
  provider = "VPS Premium"      Bearer token   ┌─────────────────────┐
  model = claude-sonnet-4-5 ───────────────►   │ Premium gateway      │
  (no provider keys here)                      │  GET /v1/models      │
                                               │  POST /v1/chat/...   │
                                               │  ANTHROPIC_API_KEY   │
                                               │  OPENAI_API_KEY      │
                                               │  GEMINI_API_KEY      │
                                               └─────────────────────┘
```

## Premium models

Configured in `server/.env` as `PREMIUM_MODELS` (comma-separated).
Default:

| Model | Provider on the VPS |
|---|---|
| `claude-sonnet-4-5` | Anthropic (Claude Sonnet) |
| `gpt-4o`, `gpt-4o-mini` | OpenAI (GPT) |
| `gemini-2.5-flash`, `gemini-2.5-pro` | Google (Gemini) |
| `deepseek-chat`, `deepseek-reasoner` | DeepSeek | Add to `PREMIUM_MODELS` + set `DEEPSEEK_API_KEY` |

To add newer models, add their ids to `PREMIUM_MODELS` and restart:

```bash
PREMIUM_MODELS=claude-sonnet-4-5,gpt-4o,gpt-4o-mini,gpt-5,gemini-2.5-flash,gemini-2.5-pro
```

Routing is by model id prefix: `claude-*` → Anthropic, `gpt-*` → OpenAI,
`gemini-*` → Google, `deepseek-*` → DeepSeek, anything else → OpenRouter
(if `OPENROUTER_API_KEY` is set). A model is only offered if its provider key is configured on
the VPS — otherwise the gateway returns a clear error naming the
provider, not the key.

## How users connect (client side)

In the LocalBotz app: **Settings → Connectors → VPS Premium** — paste
the gateway base URL and the token you issued them, then **List premium
models**. Or in `.env`:

```bash
VPS_BASE_URL=https://YOUR-VPS/v1
VPS_API_TOKEN=<the token you issued them>
```

Then pick provider **VPS Premium** per bot. The app fetches the model
list live from the gateway, so users only see models the VPS actually
offers. If the VPS is unreachable or the token is wrong, the app shows
a clear error and falls back to the local model (LM Studio).

## Setup on the VPS

### 1. Get the files onto the VPS — two ways

**A. SSH** (public VPS):

```bash
# From your computer (replace user@host with your VPS login):
ssh user@host
# On the VPS:
git clone https://github.com/webginet-sys/localbotz.git
cd localbotz/server
cp .env.example .env
nano .env   # set PREMIUM_API_TOKEN + your provider keys (see below)
```

**B. Tailscale** (private, no public ports needed):

```bash
# Join the tailnet on both machines (install Tailscale, log in).
# From your computer, reach the VPS by its tailnet name or 100.x IP:
ssh user@<vps-tailnet-name>
# Then the same steps as above: clone, cd localbotz/server, edit .env.
```

The deploy steps after this are identical for both paths. The only
difference is how the gateway is reached afterwards:

- **Public premium access:** bind to `127.0.0.1` and put nginx + HTTPS
  in front (section 3). Users connect to `https://YOUR-VPS/v1`.
- **Private (tailnet-only) access:** bind to the VPS's Tailscale IP
  (`HOST=<100.x IP>` in `.env`) and skip nginx entirely. Only devices
  on your tailnet can reach it — no public exposure at all.

### 2. Configure `.env`

```bash
cp .env.example .env
nano .env
```

- `PREMIUM_API_TOKEN` — a long random token **you** issue to users.
  Generate one: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
  This is not a provider key and cannot be used anywhere else.
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
  `OPENROUTER_API_KEY` — your provider keys, only in this file, only
  on this VPS. Fill in the ones for the models in `PREMIUM_MODELS`.
- `PREMIUM_MODELS` — the list above; add newer model ids here.

### 3. Run it

**systemd (recommended for always-on):**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create `/etc/systemd/system/localbotz-gateway.service`:

```ini
[Unit]
Description=LocalBotz VPS Premium gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=localbotz
WorkingDirectory=/home/localbotz/localbotz/server
EnvironmentFile=/home/localbotz/localbotz/server/.env
ExecStart=/home/localbotz/localbotz/server/.venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now localbotz-gateway
sudo systemctl status localbotz-gateway
curl http://127.0.0.1:8001/health
```

**Docker:**

```bash
docker build -t localbotz-gateway .
docker run -d --name localbotz-gateway --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8001:8001 localbotz-gateway
```

The image does **not** contain `.env` — pass it with `--env-file`
(or `-e PREMIUM_API_TOKEN=... -e ANTHROPIC_API_KEY=...`).

### 4. Public HTTPS with nginx + Let's Encrypt (only for public access)

If you want users outside your tailnet to use the premium models,
put nginx in front. The gateway itself stays on `127.0.0.1:8001`.

`/etc/nginx/sites-available/localbotz`:

```nginx
server {
    listen 80;
    server_name YOUR-VPS;  # e.g. premium.example.com

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Keep long model replies alive:
        proxy_read_timeout 300s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/localbotz /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d YOUR-VPS   # Let's Encrypt HTTPS
```

Users then set `VPS_BASE_URL=https://YOUR-VPS/v1` in the app.
For tailnet-only access, skip this section and use the Tailscale IP.

## API

| Endpoint | Auth | What it does |
|---|---|---|
| `GET /health` | none | `{"status":"ok", ...}` — uptime check, no keys |
| `GET /v1/models` | Bearer token | The configured premium models |
| `POST /v1/chat/completions` | Bearer token | OpenAI-compatible chat, routed to the right provider |

Requests without a token get `401`; a wrong token gets `401`; a
model that isn't configured gets `400` listing what is available;
a missing provider key on the VPS gets `502` naming the provider
(never the key). Streaming (`stream: true`) is not supported yet.

## Usage logging

Every completed chat is appended to `usage.log` (JSON lines):
timestamp, a SHA-256 hash prefix of the token (never the token
itself), workspace id, client IP, model, provider, input/output
tokens. No message content and no provider keys are ever logged.
Rotate it if it grows: `logrotate` or just `> usage.log` when the
gateway is stopped.

## Where users register

When someone installs LocalBotz and has no premium token, they
register **on this server** — there is no separate website to sign
up on. Two ways in:

1. **In the app:** Settings → Connectors → VPS Premium → "No token
   yet? Register on the VPS" — name + email. The app calls
   `POST /register` here and saves the token it gets back.
2. **In a browser:** open the sign-up page `GET /register` on the
   gateway (same host as the gateway, e.g. `https://YOUR-VPS/register`)
   — name + email, and the page shows the token once, to paste into
   the app under Settings → Connectors → VPS Premium.

`POST /register` (no auth) takes `{"name", "email"}` and returns
`{"workspace_id", "email", "token"}`. The token is shown **once** —
only its SHA-256 hash is stored, in `data/users.json`, next to the
name, email, workspace id and status. One account per email (`409`
if it already exists), invalid email gets `400`, and
`REGISTRATION_DAILY_LIMIT` (default 100/day) caps sign-ups.

## User sign-in portal (like the Abacus flow)

After registering, a user signs in and sees their plan — the same flow
as Abacus: sign-in page, plan page, then WhatsApp.

1. **Sign in:** `GET /login` — email + the token from registration.
   `POST /login` verifies the token hash, sets an `lb_session` cookie
   (HttpOnly, 30 days, stored hashed in `data/sessions.json`) and
   redirects to `/account`. 5 wrong sign-ins locks that email for
   5 minutes.
2. **Plan page:** `GET /account` — "Your free plan works in
   LocalBotz" + "Upgrade to use premium models", buttons **Upgrade to
   Premium** (price list, pay-as-you-go) and **Open LocalBotz** (goes
   to `/whatsapp`), and **Sign out** (`GET /logout`). `GET /api/account`
   (session cookie) returns the workspace, plan, premium usage so far
   (requests, tokens, spend) and the linked WhatsApp number.
3. **WhatsApp:** `GET /whatsapp` — "Chat with LocalBotz on WhatsApp",
   enter your WhatsApp number with country code, **Start WhatsApp
   chat**. `POST /api/whatsapp/start` saves the number on the account
   and, if `WHATSAPP_BOT_NUMBER` is set in `.env`, returns a `wa.me`
   link to the bot's number with a prefilled "Hi LocalBotz, I'm
   <workspace>" message. Until a real WhatsApp Business number is set,
   the page honestly says chat isn't set up yet and offers **Skip,
   download the app instead** (→ the GitHub repo). A webhook that
   answers WhatsApp messages is not built yet — that is the next step
   once the number exists.

## User panel (like the Munder Difflin account page)

`GET /account` (after sign-in) is a dark sidebar panel — `server/account.html`
— with Home, Licence, Plan, Payments, Sign in code and Settings:

- **Home:** "Let your agents work all month", Monthly/Yearly toggle, and
  three plan cards — **Free** ($0, local model unlimited), **Premium**
  (pay as you go, live per-token prices from `/v1/pricing`, no monthly
  fee), **Cloud Office** (always-on computer; monthly price from
  `plans.cloud_office_monthly_usd` in `data/pricing.json`, set in the
  admin panel — yearly is 10× monthly, i.e. 2 months free; until a price
  is set the panel says so). Then "What you get in Premium / Cloud
  Office", a Roadmap (real LocalBotz milestones, all 14 Nov 2026, with
  "We are here" at the user panel), Download (version 0.3.0, Windows /
  Mac / Linux ZIP) and Support (GitHub Issues).
- **Licence:** workspace id, plan, status, member since, premium usage
  and spend so far.
- **Plan:** the same three cards, a Cloud Office configurator (machine
  + disk stepper — larger machines are priced by the server owner),
  Free vs Premium vs Cloud Office table, "Included in every plan",
  Teams (1 workspace) and Receipts.
- **Payments:** premium spend so far and per-day receipts from
  `usage.log`. "Nothing paid yet" until the first premium request.
- **Sign in code:** `POST /api/signin-code` (session) makes a 6-digit
  code, valid 10 minutes, one use. The app exchanges it at
  `POST /v1/exchange-code` — the gateway only stores the token's hash,
  so exchanging mints a **fresh** token for that workspace and the old
  one stops working. The app saves the new token automatically
  (Settings → Connectors → VPS Premium → Sign in with a code).
- **Settings:** signed-in-as card, light/dark theme (this browser
  only), sign out, and **Delete account** (`POST /api/delete-account`
  — removes the user, sessions and codes; cannot be undone).
Set `REGISTRATION_OPEN=false` in `.env` to close sign-ups — then
only tokens you issue by hand (`PREMIUM_API_TOKEN` /
`PREMIUM_API_TOKENS`) work. Registered users' tokens work exactly
like the master token for `/v1/models` and `/v1/chat/completions`.

## Admin panel — where the software is used, and what it logs

Open `GET /admin` in a browser and enter the `ADMIN_TOKEN` from
`.env` (header `X-Admin-Token` for the API). The panel shows:

- **Overview** — registered users (active / disabled), installs
  seen (and in the last 24h), premium requests (total / last 24h),
  total tokens in+out, whether registration is open, premium models.
- **Registered users / workspaces** — name, email, status, when
  they registered. Disable a workspace to cut off its premium
  access at once; enable it again just as fast.
- **Installs** — where the software is used. Every LocalBotz install
  with VPS Premium configured sends a heartbeat when it starts
  (`POST /v1/heartbeat`): install id, app version, platform/OS,
  first/last seen, IP. No personal data, no chat content.
- **Usage log** — one line per premium chat request: time, workspace,
  model, provider, tokens in/out, client IP. Message content is
  never logged.

API (all need `X-Admin-Token`): `GET /admin/stats`,
`GET /admin/users`, `POST /admin/users/<workspace>/disable|enable`,
`GET /admin/installs`, `GET /admin/usage?limit=100`,
`GET /admin/pricing`, `POST /admin/pricing`, `GET /admin/revenue`.

## Pricing — the pricing panel

Renting premium models is pay-as-you-go, per 1M tokens (USD).
Defaults are the providers' public list prices — Claude Sonnet
$3 in / $15 out, GPT-4o $2.50 / $10, GPT-4o mini $0.15 / $0.60,
Gemini 2.5 Flash $0.30 / $2.50, Gemini 2.5 Pro $1.25 / $10,
DeepSeek $0.27 / $1.10 — full table in `docs/pricing.md` and in
`server/data/pricing.json`.

- **Users see the prices before they register:** `GET /v1/pricing`
  (no auth) lists the premium models and their prices. The app
  shows it under Settings → Connectors → VPS Premium → Show prices.
- **You change them in the admin panel:** `GET /admin` → Pricing —
  one row per model, change a number, Save pricing. The new price
  applies to later requests; every completed chat writes its cost
  into `usage.log` (`cost_usd` next to the token counts).
- **Revenue:** `GET /admin` → Revenue — total revenue, requests
  billed, cost by workspace, by model, and by day (last 14 days).
  See `docs/pricing.md` for the full pricing story.

## Security notes

- Keep `.env` readable only by the service user: `chmod 600 .env`.
- Never commit `.env`, never paste provider keys into the client app,
  a chat, or a screenshot.
- Rotate `PREMIUM_API_TOKEN` if it leaks: change it in `.env`,
  restart the gateway, and issue the new token to your users.
- Tool use through the gateway is best-effort for Claude: tool calls
  are translated to/from Anthropic's format in `app.py`, but a model
  that does not support tools returns plain text.
