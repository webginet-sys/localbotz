# Clients & Deals — deal workflows

A small local CRM for sales work, and workflows that act when a deal
moves. (Twenty's idea, LocalBotz-sized: plain local JSON files, no
new stack, no separate product.)

## Deals

- **A deal** is a title, a client, an optional contact, a value and
  a currency, and a pipeline stage: **New → Quoted → Negotiation →
  Won / Lost**. Sidebar → Deals → create one, move it with the stage
  buttons. Every deal has one **timeline**: stage moves, notes,
  drafts and workflow runs, in one place.
- **Drafts** live on the deal. A workflow can write one; you send it
  yourself (email, WhatsApp, in person). There is no automatic
  sending — LocalBotz's mail connectors are still config-only.

## Workflows

A workflow rule is: **when a deal moves to [stage], then [action]**.

| Action | What it does |
|---|---|
| Create a task for a bot | Adds a task to the bot's task list (Hermes tasks). It runs on its own if the bot is persistent, or from the bot's Run button. |
| Run an office job with the team | Starts a team job in the office — with the Auditor and the approval gate, like any office job. The finished job waits for your approval. |
| Write a draft on the deal | Writes a draft on the deal's timeline. You send it yourself. |
| Add a note to the timeline | Writes a note (e.g. "Lost: client chose the cheaper bid"). |

Write the action text with `{deal}`, `{client}`, `{value}`,
`{currency}` and `{stage}` — they are filled in from the deal that
moved. Examples:

- Won → office job: "Prepare the onboarding pack for {client} — {deal} ({value} {currency}). Confirm the delivery dates and the first invoice."
- Quoted → task for the Sales bot: "Follow up with {client} about the {deal} quotation ({value} {currency}) — ask if they have questions and offer a site visit."
- Lost → note: "Lost {deal} ({value} {currency}) — record the reason in the next note."
- Negotiation → draft: "Hi {client}, following up on the {deal} quotation…"

Pause, resume or delete a rule from the Deals page. A paused rule
never fires. One rule failing never stops the others, and never
stops the stage change itself — the failure is written on the deal's
timeline.

## What it is not (yet)

- **Not a full CRM.** No companies list separate from deals, no
  custom fields, no kanban board, no dashboard, no "Ask AI about
  your pipeline" — those are the natural next steps, and the deal
  records (`data/deals.json`) are where they plug in.
- **No automatic sending.** Nothing goes out by a workflow on its
  own. Drafts stay drafts; office jobs wait for approval.
- **No email logging.** When a bot drafts or sends an email about a
  client, it is not yet logged on the deal's timeline — that needs
  real email sending first.

## API

| Endpoint | What it does |
|---|---|
| `GET /api/deals` | List deals (newest first) |
| `POST /api/deals` | Create — `{title, client, contact?, value?, currency?}` (currency defaults to QAR) |
| `GET /api/deals/{id}` | One deal, with timeline and drafts |
| `PATCH /api/deals/{id}` | Change fields, move stage (fires workflows), or add `{note}` |
| `DELETE /api/deals/{id}` | Delete the deal |
| `DELETE /api/deals/{id}/drafts/{draft_id}` | Delete a draft |
| `GET /api/deal-workflows` | List workflow rules |
| `POST /api/deal-workflows` | Create — `{name, stage, action, bot_id?, office_id?, text}` |
| `PATCH /api/deal-workflows/{id}` | Pause/resume (`{enabled}`), rename, change text |
| `DELETE /api/deal-workflows/{id}` | Delete the rule |

Deals live in `data/deals.json`, rules in `data/deal_workflows.json`.
