# Connectors — the most popular ones

LocalBotz has two kinds of connectors, sharing one store
(`data/connectors.json`):

- **Model providers** — where the AI comes from (LM Studio, Ollama,
  Claude, OpenAI, Gemini, OpenRouter, Groq, Mistral, Cerebras,
  DeepSeek, VPS Premium…). See the README providers table.
- **Service connectors** — the apps your bots can talk to. 25 of the
  most popular, grouped by category below.

Status uses the same words everywhere: **Not connected** (no key
saved) / **Saved, not checked** (key saved, never tested) /
**Connected** (the last Test really reached the service) /
**Failed** (the last Test failed — the detail says why). Nothing is
ever faked: a connector only shows Connected after a real check
succeeds.

## How to connect one

1. Open Settings → Connectors (or Library → Connectors).
2. Find the connector, read its Setup column — it names the exact
   token/key env var to save (e.g. `GITHUB_TOKEN`).
3. Save that token in Settings → Secure store (it goes into the
   gitignored `.env`, masked, never logged, never committed).
4. Enable the connector, press **Test**.

## Token-based connectors — Test really checks them

Test calls the service's own "who am I" endpoint with your saved
token and reports Connected with the account name, or Failed with
the honest reason (401 = token rejected, 403 = token lacks the
permission, or the service could not be reached).

| Connector | Category | Token env var | What Test calls |
|---|---|---|---|
| GitHub | Dev | `GITHUB_TOKEN` | `GET api.github.com/user` |
| GitLab | Dev | `GITLAB_TOKEN` | `GET gitlab.com/api/v4/user` |
| Slack | Chat | `SLACK_BOT_TOKEN` | `POST slack.com/api/auth.test` |
| Telegram | Chat | `TELEGRAM_BOT_TOKEN` | `GET api.telegram.org/bot<token>/getMe` |
| Discord | Chat | `DISCORD_BOT_TOKEN` | `GET discord.com/api/users/@me` |
| Notion | Work | `NOTION_TOKEN` | `GET api.notion.com/v1/users/me` |
| Trello | Work | `TRELLO_API_KEY` + `TRELLO_TOKEN` | `GET api.trello.com/1/members/me` |
| Airtable | Work | `AIRTABLE_PAT` | `GET api.airtable.com/v0/meta/bases` |
| Stripe | Payments | `STRIPE_SECRET_KEY` | `GET api.stripe.com/v1/account` |
| Dropbox | Email & productivity | `DROPBOX_TOKEN` | `POST api.dropboxapi.com/2/users/get_current_account` |
| Zoom | Video & meetings | `ZOOM_ACCESS_TOKEN` | `GET api.zoom.us/v2/users/me` |
| HubSpot | CRM & sales | `HUBSPOT_TOKEN` | `GET api.hubapi.com/oauth/v1/access-tokens/<token>` |

Notes:

- **Trello** needs two credentials: an API key (`TRELLO_API_KEY`)
  and a token (`TRELLO_TOKEN`), both from trello.com/app-key.
- **Zoom** needs a Server-to-Server OAuth app access token
  (`ZOOM_ACCESS_TOKEN`); without a token it stays Not connected.
- **HubSpot** Test checks the token with HubSpot's access-token
  endpoint. That endpoint is made for OAuth access tokens; if you
  use a private-app token and Test says Failed, the token may still
  be fine for the HubSpot API itself — check it in HubSpot's
  settings instead.
- **Telegram / Discord / WhatsApp** also appear under Messaging
  channels (Settings → Messaging channels), where you set up
  inbound replies and approved senders. The connector Test only
  checks the token; it does not start a live listener.
- **WhatsApp** is token-based (`WHATSAPP_ACCESS_TOKEN`) but Test
  does not call Meta yet — it stays Not connected with the setup
  text until that check is built.

## OAuth-only connectors — config + setup instructions (v1)

These need an OAuth sign-in flow, which is not built yet. They
stay **Not connected** with honest setup instructions, and Test
returns Not connected with that setup text — never a fake
Connected.

| Connector | Category | Auth |
|---|---|---|
| Gmail | Email & productivity | OAuth (Google account) |
| Google Drive | Email & productivity | OAuth (Google account) |
| Google Calendar | Email & productivity | OAuth (Google account) |
| Google Sheets | Work | OAuth (Google account) |
| Outlook (Microsoft 365) | Email & productivity | OAuth (Microsoft account) |
| Microsoft Teams | Chat | OAuth (Microsoft account) |
| Asana | Work | OAuth |
| Jira | Work | OAuth (Atlassian account) |
| Linear | Work | OAuth |
| Salesforce | CRM & sales | OAuth |
| X (Twitter) | Social & publishing | OAuth 2.0 |
| LinkedIn | Social & publishing | OAuth 2.0 |

## What a bot can do with a connector

In v1, connectors are connections, not tools: a bot can be told
which connectors are enabled (in its instructions), but there is
no live read/write of Gmail, Drive, Slack, etc. from a bot yet —
the token only proves the connection works. Live actions per
connector (read inbox, list files, post a message) are the next
step after the OAuth flows.
