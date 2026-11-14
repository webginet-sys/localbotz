# Document workroom — documents with proof

Sidebar → **Workroom**. Modelled on the TeamOffice idea of a private
AI workroom for document-heavy professional teams — rebuilt as
LocalBotz-native, with LocalBotz's own names and wording.

A workroom is a vault of project documents for one job: BOQs,
tenders, contracts, SOWs, SLAs, drawings notes, invoices,
correspondence. You search them and ask questions about them, and
every answer comes back with its sources.

## What it does

- **Vault** — documents stay on your computer, under
  `data/workrooms/<id>/docs/`. Nothing is uploaded anywhere. Add
  files by upload, or from a file already in the workspace folder.
  Supported for text search: `.txt`, `.md`, `.csv`, `.json`, `.log`,
  `.tsv`, `.pdf` (via `pypdf`) and `.docx` (via `python-docx`), up
  to 20 MB each. A file whose text cannot be extracted is still
  stored, and the workroom says so honestly on the document instead
  of pretending it searched it.
- **Search** — keyword search over the documents, in passages
  (~900 characters). A big document set is searched as the work
  happens instead of being stuffed into one prompt. `GET
  /api/workrooms/{id}/search?q=...` returns the matching passages
  with document name and passage number.
- **Ask with receipts** — `POST /api/workrooms/{id}/ask` sends the
  model only the matching passages. The answer comes back with its
  sources (document name + passage), and the model is instructed to
  answer only from those passages. Prices, measurements and dates
  are never invented; if the answer is not in the documents, it
  says so and says which document would settle it. In mock mode
  (`--mock`, no model running) the answer is the matching passages
  themselves, so the search and receipts can still be tested.
- **Redaction** — before anything is sent to an online (non-local)
  model, emails, IBANs, card-like numbers and the workroom's own
  private terms (client name, project code — set per workroom) are
  replaced with placeholders like `[EMAIL-1]`. The placeholders are
  swapped back into the answer on your computer, so you see the
  real text. The redaction record on each question stores only what
  kind of thing was hidden and how many — never the values
  themselves. Local models (LM Studio / Ollama) never leave the
  computer, so redaction is off for them unless you ask for it
  (`"redact": true` on the ask).
- **Reviewer notes** — anyone checking the work can add a note to
  the workroom (`POST /api/workrooms/{id}/notes`).
- **Handoff** — `GET /api/workrooms/{id}/export` downloads one JSON
  package: the workroom, all documents with their text, every
  question and answer with its sources, the redaction log, and the
  reviewer notes — so another reviewer can pick the work up and
  check it.

## API

| Call | What it does |
|---|---|
| `GET /api/workrooms` | List workrooms (name, documents, questions) |
| `POST /api/workrooms` | Create one: `{name, description?, office_id?, provider?, model?, redact_terms?}` |
| `GET /api/workrooms/{id}` | Workroom + documents + notes + last 10 questions |
| `PATCH /api/workrooms/{id}` | Change name, provider, model, redact terms |
| `DELETE /api/workrooms/{id}` | Delete the workroom and its files |
| `POST /api/workrooms/{id}/docs` | Upload a document (multipart `file`) |
| `POST /api/workrooms/{id}/docs/from-workspace` | Add a workspace file: `{path}` |
| `DELETE /api/workrooms/{id}/docs/{doc}` | Remove a document |
| `GET /api/workrooms/{id}/search?q=` | Search the documents |
| `POST /api/workrooms/{id}/ask` | Ask: `{question, provider?, model?, redact?}` |
| `GET /api/workrooms/{id}/asks` | All questions and answers |
| `POST /api/workrooms/{id}/notes` | Add a reviewer note: `{text, ask_id?}` |
| `GET /api/workrooms/{id}/export` | Download the handoff package (JSON) |

A workroom can be linked to an Office (`office_id`), but it does
not have to be — a workroom is for the documents of one job, an
Office is for the team working on it.

## Templates that work with it

Five new bot templates (45 total) are built for document work:
**Document Reviewer**, **Tender Comparator**, **Contract Checker**,
**BOQ Reviewer** and **Evidence Checker**. Each one works only from
the documents given, cites the document and passage for every
claim, and never invents a price, measurement or date.

## What it does not do (yet)

- No semantic/vector search — search is keyword-based, so a
  question in very different words from the document may miss.
  Use the document's own words (e.g. "retention", "payment
  terms") for the best matches.
- No scanned-image PDFs — a PDF that is only pictures has no text
  to extract, and the workroom says so on the document.
- No Word/Excel/PowerPoint *output* yet — answers are text. (That
  is the next idea from the AionUi check: real `.docx` / `.xlsx` /
  `.pptx` output for BOQs, tenders and proposals.)
