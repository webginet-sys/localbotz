# Marketing — write, approve, post

Write a post once, pick the platforms it goes to, and it is only posted
after you approve it. Nothing is ever posted without approval.

## The flow

1. **Draft** — write the post, tick the platforms (Telegram, Facebook,
   LinkedIn, X, Instagram), save it as a draft.
2. **Approve** — a draft becomes approved. An unapproved post cannot be
   posted or scheduled.
3. **Post now, or schedule** — an approved post can go out immediately, or
   be scheduled for a time in the future. Scheduled posts are posted by
   the app's worker when their time comes (while the app is open).

A post's status tells the truth: `draft`, `approved`, `scheduled`,
`posted`, `partial` (some platforms went out, some did not) or `failed`.
The Result column shows, per platform, what actually happened.

## What posts for real

- **Telegram** posts for real, through the Bot API, when
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are saved in Secure store.
- **Facebook, LinkedIn, X and Instagram** are honest about their state:
  without a token saved they report "not connected — Saved, not checked";
  with a token saved they report that live posting is not wired up yet
  for that platform. Either way the post is recorded as failed for that
  platform, with the reason — it is **never shown as posted when it was
  not**.

## Honest limits

- Posting only happens while the app is open (the worker checks on the
  same 30-second loop as routines, chains and monitors).
- A scheduled post whose time passes while the app is closed goes out
  once, on the next start — there is no backlog.
- Only Telegram is fully wired up in this version. Facebook, LinkedIn, X
  and Instagram need their posting code before they can go live.
