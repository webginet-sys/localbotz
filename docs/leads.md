# Leads — find new clients

LocalBotz can hunt for new clients for you. Give it an area and a sector —
"Doha, Qatar" and "Construction" — and it searches public directories and
search results for businesses there, then sorts them into three tiers:

- **🔥 Hot** — they have a website and a way to reach them, and they look
  ready to buy: a new project, a tender, an expansion.
- **🟡 Warm** — they can be reached, but it is not clear yet whether they
  need anything.
- **❄️ Cold** — no usable contact was found.

Every lead shows **why** it got its tier — the evidence lines — and a link
to the source page, so you can check it yourself. A phone number or a
website is only shown when the page actually showed it. LocalBotz never
invents contact details.

## What you can do with a lead

- **→ Deal** — turns the lead into a deal in the General pipeline, at the
  New stage, with the business as the client. The deal's timeline records
  that it came from a lead.
- **Proposal pack** — builds a `.docx` proposal and an `.xlsx` tracker row
  under `data/documents/leads/<lead-id>/`, using your business profile
  (company name, services, tone) when you have set one. The files are
  listed on the Leads page.
- **Dismiss** — removes the lead. Dismissed leads do not come back on the
  next hunt: hunting skips any business whose website or phone is already
  saved.

## How a hunt works

1. The bot searches the web for businesses in the area and sector, and
   opens the public directory and search-result pages it finds.
2. From each page it takes only what the page actually shows: the business
   name, website, phone, email, and a line of evidence.
3. It classifies the tier from that evidence and saves the lead.

In **mock mode** (no model running) the hunt returns a small fixed list of
Doha construction firms, labelled `[MOCK MODE]`, so the whole flow can be
tested without the web.

## Honest limits

- Hunting uses public web sources only. It does **not** scrape Google Maps
  — that breaks Google's terms — and it only reads pages a browser can
  open.
- A hunt is only as good as the pages it finds. A business with no public
  listing will not appear, and a tier is a best guess from the evidence
  shown, not a promise that the business will buy.
- Hunting only runs while the app is open.
