# Office documents — real Word, Excel and PowerPoint files

A team job is text on a page until it leaves the computer. These
exports turn a finished job into a real file you can send to a
client, open in Word/Excel/PowerPoint, or keep in the project
folder. Built with python-docx, openpyxl and python-pptx.

## What each file contains

All three are built from the job's own text only — the title, the
brief, the Auditor's verdict and summary, and each team member's
step, in order. **Nothing is invented**: no price, measurement or
date is added, and a step with no output says "No output from this
step." instead of being padded out.

### Word (.docx)

- Job title as the document title, then office, date, status and
  the brief.
- An Auditor section (verdict, summary, issues) when the job was
  audited.
- One headed section per team member (name + role), with their
  work as paragraphs and bullet lines.
- Tables the team wrote with `| pipes |` become real Word tables
  (first row bold, as the header).

### Excel (.xlsx)

- A **Summary** sheet: job, office, date, status, brief, audit
  verdict, team members.
- One sheet per team member, named after them: their work as text,
  then each `| pipe |` table as a real table.
- Money stays a number, not text: a cell with a currency mark
  (QAR, AED, $, €…) or a thousands separator/decimal is written
  as a number with the `#,##0.00` format, so you can sum a column.
  Bare integers stay text unless the column is a quantity/amount
  column — so codes and years (2024, 001) are never mangled.

### PowerPoint (.pptx)

- A title slide (job title, office, date, status).
- One slide per step (member + role as the title, work as bullets),
  up to 12 slides in total. A step with more than 8 lines is cut
  with a note pointing at the Word/Excel file for the full text,
  and if there are more than 11 steps, the rest are listed on a
  final "More steps" slide.

## Where the files live

`data/documents/<office_id>/<job_id>/<job-title>.docx` (and
`.xlsx` / `.pptx`). Exporting again overwrites the same file, so
there is one file per job per format.

## API

| Endpoint | What it does |
|---|---|
| `POST /api/offices/{office_id}/jobs/{job_id}/export` | Export — `{"format": "docx" \| "xlsx" \| "pptx"}`. Returns `{format, filename, url, size_bytes, created_at}`. Works for any job with steps — approved jobs especially, but a draft awaiting approval can be exported too, to read or check before you approve it. |
| `GET /api/documents` | List all generated documents, newest first. `?office_id=` filters to one office. |
| `GET /api/documents/{office_id}/{job_id}/{filename}` | Download one file. Paths are resolved inside `data/documents/` — anything trying to climb out gets a 404. |

## What it is not (yet)

- **No mail merge, no PDF, no tracked changes.** The export is a
  clean file from the job text. PDF export and a client-ready
  cover page are the natural next steps.
- **No live formulas.** Excel cells hold the numbers the team
  wrote; totals are not recomputed. If a step's table has a total
  row, it is copied as written.
- **No editing in LocalBotz.** To change the file, edit it in
  Word/Excel/PowerPoint — the export is a snapshot of the job at
  the moment you exported it. Export again after the team re-runs
  the job.
