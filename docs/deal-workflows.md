# Clients & Deals — deal workflows

A small local CRM for sales work, and workflows that act when a deal
moves. (Twenty's idea, LocalBotz-sized: plain local JSON files, no
new stack, no separate product.)

## Deals

- **A deal** is a title, a client, an optional contact, a value and
  a currency, a **department**, and a stage in that department's
  pipeline. Sidebar → Deals → create one, move it with the stage
  buttons. Every deal has one **timeline**: stage moves, notes,
  drafts and workflow runs, in one place.
- **Drafts** live on the deal. A workflow can write one; you send it
  yourself (email, WhatsApp, in person). There is no automatic
  sending — LocalBotz's mail connectors are still config-only.

## One flow per department

Every department has its own pipeline — the same flow, with each
trade's own stage names:

| Department | Pipeline |
|---|---|
| General | New → Quoted → Negotiation → Won / Lost |
| Construction | New lead → Tender received → BOQ prepared → Submitted → Negotiation → Awarded / Lost |
| MEP | New lead → Site survey → BOQ prepared → Submitted → Negotiation → Awarded / Lost |
| Electrical Engineering | New lead → Site survey → Design & BOQ → Submitted → Negotiation → Awarded / Lost |
| IT Services | New lead → Discovery → Proposal → Negotiation → Signed / Lost |
| E-commerce | New lead → Brief → Proposal → Negotiation → Order won / Lost |
| Real Estate | New lead → Viewing → Offer made → Negotiation → Closed / Lost |
| Clinic & Healthcare | New lead → Consultation → Quotation → Negotiation → Booked / Lost |
| Logistics | New lead → Quotation → Negotiation → Booked → Delivered / Lost |
| Manufacturing | New lead → Quotation → Sample → Negotiation → Order / Lost |
| Hotel & Hospitality | New lead → Enquiry → Quotation → Negotiation → Booked / Lost |

A workflow rule can be limited to one department, or left on "Any
department" — a rule for "Awarded" only ever fires for Construction,
MEP and Electrical deals, because no other pipeline has that stage.
Moving a deal to another department resets its stage to the new
pipeline's first stage. Old deals without a department behave as
General.

Every department ships with two **starter workflows**, ready to
use and to edit: when a deal is won (Awarded, Signed, Closed…), a
handover draft is written on the deal; when a deal is lost, a note
asks for the reason. They are created the first time the app runs
with no workflow rules file, and you can pause, edit or delete any
of them from the Deals page.

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
| `GET /api/deals/pipelines` | All department pipelines (stage names) |
| `GET /api/deals` | List deals (newest first) |
| `POST /api/deals` | Create — `{department?, title, client, contact?, value?, currency?}` (department defaults to `general`, currency to QAR) |
| `GET /api/deals/{id}` | One deal, with timeline and drafts |
| `PATCH /api/deals/{id}` | Change fields, move department, move stage (fires workflows), or add `{note}` |
| `DELETE /api/deals/{id}` | Delete the deal |
| `DELETE /api/deals/{id}/drafts/{draft_id}` | Delete a draft |
| `GET /api/deal-workflows` | List workflow rules |
| `POST /api/deal-workflows` | Create — `{name, department?, stage, action, bot_id?, office_id?, text}` |
| `PATCH /api/deal-workflows/{id}` | Pause/resume (`{enabled}`), rename, change text |
| `DELETE /api/deal-workflows/{id}` | Delete the rule |

Deals live in `data/deals.json`, rules in `data/deal_workflows.json`.
Pipelines live in `app.py` (`DEPARTMENT_PIPELINES`).
