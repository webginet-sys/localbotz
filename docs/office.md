# Office — run a team of agents locally

Modelled on **Munder Difflin** (HarnessMD/munder-difflin, MIT):
"an agent harness to run an office of your clones" — an office of
Claude Code / Codex-like agents on your laptop, each with long-term
memory, a mailbox, and a desk on a shared office floor, coordinated
by your clone (Michael) who routes work between them.

LocalBotz does the same idea, local-first, in its own way — no
Electron, no terminal CLIs, no subscriptions. It runs on the local
model (LM Studio / Qwen3.5 by default) with the bots LocalBotz
already has.

## What it is

- **Create your office locally.** Sidebar → Office → give it a name
  ("Acme Paper Co.") and what it does. The office lives in
  `data/offices/<id>/` on your computer.
- **One boss agent.** Every office gets an Office Manager (the
  "Michael") — the only agent you brief. It plans the work, assigns
  it to the team, checks results, and reports back.
- **Hire an AI team.** 101 roles in total. The core team: Researcher,
  Writer, Developer, Analyst, Assistant, Sales, Finance, Legal,
  Recruiter, Teacher. Plus 90 sector roles — every job title a
  construction, MEP, electrical engineering, IT services or e-commerce
  company hires, from senior management (Construction Manager, MEP
  Manager, Cloud Architect) down to technicians and trades (HVAC
  Technician, Plumber, Ductman, Mason, Steel Fixer). Hiring creates a
  normal LocalBotz bot with role instructions, its own memory and chats
  — so a team member is also a bot you can talk to on its own. The hire
  list comes from `GET /api/office/roles`, grouped by sector.
- **Shared office memory.** `data/offices/<id>/memory.md` — markdown
- **Shared office memory.** `data/offices/<id>/memory.md` — markdown
  memory the whole team shares. It survives sessions, every member
  reads it before working, and every finished job writes a summary
  into it. You can add to it by hand on the Office page.
- **Blackboard (mailbox).** `data/offices/<id>/blackboard.json` —
  messages passed between the team: the boss assigns a part, the
  member reports back done. Visible on the Office page.
- **Run a job with the team.** Give a title and a brief. The boss
  assigns the work in order — core team first, then the sector roles
  you hired, Analyst last — each member runs with the brief + the
  shared office memory + what the previous member did, and hands
  its result to the next member. The final result is the last
  member's output plus every step, shown on the Office page.

## What it is not (yet)

Compared with Munder Difflin: no 2D office floor with avatars
walking to desks, no live terminal per agent, no voice dictation,
and no approvals queue for spend / destructive operations — the
Permissions page (Ask / Auto / Full) is the leash instead. The
team runs one job at a time, in order, not in parallel. Those are
the natural next steps; the structure (`OFFICE_ROLES`,
`run_office_job` in `app.py`) is where they plug in.

## API

| Endpoint | What it does |
|---|---|
| `GET /api/offices` | List offices |
| `POST /api/offices` | Create one — `{name, description, boss_name?, provider?, model?}` — creates the boss bot too |
| `GET /api/offices/{id}` | Office detail: members, memory, blackboard, jobs |
| `DELETE /api/offices/{id}` | Delete the office (team bots stay in Bots) |
| `POST /api/offices/{id}/members` | Hire — `{name, role, template?, provider?, model?}` |
| `DELETE /api/offices/{id}/members/{member_id}` | Remove a member |
| `POST /api/offices/{id}/memory` | Add to shared memory — `{text}` |
| `POST /api/offices/{id}/jobs` | Run a team job — `{title, brief}` |
| `GET /api/offices/{id}/jobs` | Job history |

## Rules that stay in place

- **Local first.** The office, its memory and its team run on your
  computer. Nothing leaves it except a premium model call you
  chose (VPS Premium) or a provider key you set.
- **Availability-driven.** Team members use their bot's provider /
  model; if the local model is not running, jobs run in mock mode
  and say so — they never pretend a real model answered.
- **No fake team.** A member is a real bot with real instructions
  and a real run; the job record shows every step's actual output.
