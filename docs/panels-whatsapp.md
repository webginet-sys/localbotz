# WhatsApp + Marketing from your own panels

The WhatsApp approval flow and the two things still needed for real use
— your WhatsApp Business number + Meta tokens, and your platform
credentials for Facebook, LinkedIn, X and Instagram — are all doable
from LocalBotz's own panels: users from the **user panel**, admins from
the **admin panel**.

## Two WhatsApp paths — local and hosted

| | Local (the app on your computer) | Hosted (this VPS gateway) |
|---|---|---|
| Where it runs | `app.py` on your machine | `server/app.py` on the VPS |
| Works when your computer is off | No | **Yes** |
| Config | Settings → Messaging channels | User panel → **WhatsApp** |
| Inbox | Messaging channels → WhatsApp inbox | User panel → **WhatsApp** → Inbox |
| Webhook | `http://localhost:8000/api/whatsapp/webhook` | `https://api.localbotz.io/whatsapp/webhook?workspace=<your workspace id>` |
| Sends via | Meta Graph API v21.0 | Meta Graph API v21.0 |

Both are the same sales agent, with the same rules: official WhatsApp
Business API only — never QR pairing. Every incoming message becomes an
inbox item with a suggested draft reply, and **nothing is sent until you
approve it**. The two agents are separate: each has its own config, its
own inbox and its own webhook. Use one or both.

## Setting it up (user panel)

1. Sign in at `https://api.localbotz.io/account` → **💬 WhatsApp**.
2. Fill in the connect form:
   - **Business name** — shown to the agent when it drafts replies.
   - **WhatsApp Business number** — your number, with country code.
   - **Phone number ID** — from your Meta app (WhatsApp → API Setup).
   - **Access token** — a permanent token from your Meta app.
   - **Verify token** — any string you choose; Meta must send it back.
   - **App secret** — from your Meta app; used to check Meta's
     signature on incoming webhooks. Optional, but recommended.
   Tokens are password fields. A saved token is shown masked
   (`EAA...cdef`) and is never shown in full. Leaving a token field
   blank keeps the saved value.
3. Copy the **webhook URL** shown on the page
   (`https://api.localbotz.io/whatsapp/webhook?workspace=<your workspace id>`)
   and paste it into your Meta app dashboard under
   WhatsApp → Configuration → Webhook, with the same verify token.
   Meta calls it once to verify; after that, every customer message
   arrives in your panel inbox.
4. When a message arrives, the panel shows the message and a suggested
   reply, drafted by the cheapest premium model configured on the VPS
   (cheapest first: GPT-4o mini → DeepSeek → Gemini Flash → GPT-4o →
   Gemini Pro → Claude Sonnet → …). The draft is only a suggestion.
   Press **Approve & send** to send it, or **Dismiss** to drop it.
   If no provider key is set on the server yet, the draft is empty and
   the panel says so honestly — write the reply yourself.

The status line tells you at a glance: **not set up yet**,
**connected** (with how many messages are waiting and sent), or
**disabled**. Untick "WhatsApp agent enabled" and incoming messages are
ignored until you turn it back on.

## Marketing accounts (user panel)

User panel → **📣 Marketing**: one connect form per platform —
Telegram (bot token + chat id), Facebook (page token), LinkedIn, X,
Instagram. Tokens are stored per workspace in
`server/data/marketing.json`, masked on read (`Saved, not checked` /
`Not connected`), same rules as the WhatsApp tokens.

**Posting happens in the LocalBotz app for now** — this page connects
your accounts. The app's Marketing publisher composes a post, waits for
your approval, then posts it (Telegram posts for real when configured;
other platforms report honestly when they are not connected).

## Admin view (admin panel)

Admin panel → **💬 WhatsApp**: one row per workspace — business name
and number, configured?, enabled?, messages waiting, messages sent,
last message time — with **Enable / Disable** per workspace. Disabling
stops that workspace's webhook from storing anything. The gateway's own
WhatsApp number (`WHATSAPP_BOT_NUMBER` from `server/.env`) is shown
read-only at the top. Admin panel → **📣 Marketing**: per-workspace
platform connection status — which platforms are saved per workspace.
Token values are never shown in the admin panel.

## API

User endpoints (session cookie, own workspace only):

- `GET /api/account/whatsapp` — masked config + status + webhook URL.
- `PUT /api/account/whatsapp` — save config; empty token fields keep
  the saved value; invalid phone → 400.
- `GET /api/account/whatsapp/inbox` — own workspace, newest first.
- `POST /api/account/whatsapp/inbox/{id}/approve` — sends the draft
  via the Meta Graph API; already-sent/dismissed → 400; no draft → 400;
  Meta error → 502 with Meta's message.
- `POST /api/account/whatsapp/inbox/{id}/dismiss`.
- `GET /api/account/marketing`, `PUT /api/account/marketing`.

Webhook (called by Meta, no session):

- `GET /whatsapp/webhook?workspace=<ws_id>` — `hub.mode=subscribe` +
  `hub.verify_token` must equal the workspace's verify token; returns
  `hub.challenge`. Wrong/missing workspace → 403.
- `POST /whatsapp/webhook?workspace=<ws_id>` — when the workspace has
  an app secret, `X-Hub-Signature-256` (HMAC-SHA256 over the raw body)
  must match or the call is refused with 403. Text messages only;
  statuses and other types are ignored. A disabled or unconfigured
  workspace answers 200 and stores nothing.

Admin endpoints (X-Admin-Token):

- `GET /admin/whatsapp` — per-workspace rows + gateway bot number.
- `POST /admin/whatsapp/{ws_id}/toggle` — enable/disable a workspace.
- `GET /admin/marketing` — per-workspace platform status, no tokens.

The existing `GET /whatsapp` page and `POST /api/whatsapp/start`
(wa.me link to the gateway's bot number) are unchanged.

## Test mode

`WHATSAPP_MOCK=1` in the gateway's environment makes Approve record
"sent (mock)" and never call the network. It is for testing only —
never set it on the live VPS.

## What is NOT verified here

A real Meta Graph send, a real webhook call from Meta, and real
premium-model draft generation all need real Meta tokens and provider
keys on the server. Until then the panel is honest about it: empty
drafts say no provider key is set, and unconfigured platforms say
"Not connected".
