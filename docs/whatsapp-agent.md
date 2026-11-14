# WhatsApp sales agent

Customers message your WhatsApp Business number, LocalBotz drafts a reply,
and **nothing is sent until you approve it**. This is the same rule as the
Auditor for office jobs: a draft is a draft until a human says send.

## How it works

1. A customer writes to your WhatsApp Business number.
2. Meta calls LocalBotz at `POST /api/whatsapp/webhook`. The call is
   checked: when `WHATSAPP_APP_SECRET` is set, the `X-Hub-Signature-256`
   signature must match, or the message is rejected.
3. Only senders on the **allowlist** get a reply. Anyone else is logged
   as blocked and gets nothing. The allowlist is the WhatsApp channel's
   approved senders (Settings → Messaging channels) plus
   `data/whatsapp_allowlist.json`; a do-not-reply blocklist
   (`data/whatsapp_blocklist.json`) always wins.
4. The WhatsApp bot (pickable in Messaging channels, otherwise your first
   bot) drafts a reply, using your business profile and the rule never to
   invent a price, a date or a delivery. The draft is stored in
   `data/whatsapp_inbox.json` with status `awaiting_approval`.
5. You approve it in **Messaging channels → WhatsApp sales agent**, and
   only then is it sent through the official Graph API
   (`POST https://graph.facebook.com/v21.0/{phone_number_id}/messages`).
   A failed send is reported honestly with the provider's error — the
   message stays awaiting approval.

## Setting it up

In Meta for Developers, create a WhatsApp app and add these in
**Secure store** (they are keys, so they live in `.env`, never in chat):

- `WHATSAPP_ACCESS_TOKEN` — a permanent token for the app
- `WHATSAPP_PHONE_NUMBER_ID` — the phone number ID of your business number
- `WHATSAPP_VERIFY_TOKEN` — any word you choose; Meta sends it back when
  it checks the webhook
- `WHATSAPP_APP_SECRET` — the app secret, used to check the signature
- `WHATSAPP_BOT_NUMBER` — your WhatsApp Business number, shown on the
  gateway's `/whatsapp` page

Then, in the Meta app, set the webhook URL to
`https://your-server/api/whatsapp/webhook` and subscribe to `messages`.
`GET /api/whatsapp/webhook` answers Meta's verification check: it returns
the challenge only when `hub.mode=subscribe` and the verify token matches.

`GET /api/whatsapp/status` tells you honestly what is set and what is not.
Until the token and phone number ID are saved, it says "not set up yet"
and nothing is sent.

## Honest limits

- Without a WhatsApp Business number and a Meta app, nothing works — the
  agent ships ready, but the status says so plainly.
- WhatsApp is **official Business API only**. There is no QR-code pairing:
  logging in by scanning a code breaks WhatsApp's rules and can get the
  number banned, so LocalBotz does not do it.
- In mock mode, approving a draft records it as "sent (mock)" and makes
  no network call.
- The agent answers text messages only. Voice notes, images and status
  updates are ignored.
