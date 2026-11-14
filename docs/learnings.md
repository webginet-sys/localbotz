# Learnings — the team learns from daily work

The team learns what you want from the work it actually does, keeps
a record, and presents it back when you need it — for example, the
pricing it learned when drafting your next quotation.

## What it is

- **Recorded from daily work.** When a routine runs and finishes,
  the bot records what the routine is for — what you want done
  regularly, and what the last run produced. When you approve an
  office job, the team records the brief and the audit verdict.
  Each record says where it came from (routine name / job title)
  and when. Nothing is recorded from a failed run.
- **Taught by hand.** You can teach the team directly, on the
  Routines page (for a bot) or the Office page (for the whole
  office): e.g. "Always add 12% margin to Cisco quotes." A manual
  learning is a standing instruction the team keeps.
- **Presented when needed.** A bot's learnings are in its prompt
  every time it works — chat, routine, or task — under "What the
  team has learned from this user's daily work". An office job's
  prompt includes the office's learnings too. So when the team
  drafts a quotation, it already has your pricing the way you
  taught it, and the prices it saw in your daily price checks.
- **Yours to see and delete.** Routines page and Office page both
  list the learnings, with where each one came from. Delete any
  that is wrong or out of date — the team forgets it at once.

## What it is not (yet)

- **Not a model that trains itself.** Learnings are a record, not
  fine-tuning. The local model does not change; the bot reads the
  record each time it works. With a real model the bot applies the
  record well; in mock mode the record is kept and shown, never
  invented. A real model-distilled preference (the model writing
  "the user prefers X" from a finished job, instead of the job
  summary) is the natural next step.
- **No automatic pricing yet.** The team records what it saw and
  what you taught it. It does not yet compute a quotation from a
  price list on its own — that is the Office documents step
  (.docx/.xlsx output), which is still to come.

## API

| Endpoint | What it does |
|---|---|
| `GET /api/learnings?bot_id=&office_id=` | List learnings (filter by bot or office) |
| `POST /api/learnings` | Teach — `{text, bot_id?, office_id?}` (one of bot/office required) |
| `DELETE /api/learnings/{id}` | Forget one learning |

Learnings live in `data/learnings.json` (last 200, oldest dropped).
The same text recorded twice for the same bot/office is kept once.
