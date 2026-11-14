# Business profile — your company, once

The business profile is a single knowledge base for your company. Write it
once, in **Settings → General → Business profile**, and every bot, office
job, deal draft and proposal uses it:

- **Company name, contact, phone, email, website, area**
- **Services** — one per line, e.g. MEP installation, electrical fit-out
- **Sectors** — one per line, e.g. Construction, MEP
- **Brand tone** — how you speak to clients, e.g. "plain, professional,
  short"
- **FAQs** — one per line, written as `question || answer`
- **Quotation notes** — e.g. "Prices exclude VAT. Valid 30 days."

## Where it is used

- **Chat with a bot** — the bot's instructions gain an "About this
  business:" block with your company, services, tone, FAQs and quotation
  notes, so it answers as your company and quotes in your words.
- **Office jobs** — every team member's prompt carries the same block.
- **Deal drafts** — draft text can use `{company}`, filled in from the
  profile (alongside `{deal}`, `{client}`, `{value}`, `{currency}`,
  `{stage}`).
- **Proposal packs** — a lead's proposal uses your company name and
  services on its cover and in the quotation notes.

## What it is not

If the profile is empty, nothing is added — LocalBotz **never invents**
company facts. It does not learn the profile on its own; what you type is
what the bots use. It is a record, not a training set: it does not change
the model, it just tells the model who it is working for.
