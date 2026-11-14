# What we took from awesome-llm-apps

Source: https://github.com/shubhamsaboo/awesome-llm-apps — 100+ open-source AI
agents, agent skills and RAG apps, Apache-2.0. We took the **ideas** — the
agents, teams and skills — and rebuilt them as LocalBotz-native templates,
office roles and skills. No code was copied: every instruction below was
written fresh for LocalBotz, and it runs on the local model (LM Studio /
Qwen3.5) by default, with the same tools every LocalBotz bot has.

## Bot templates (15 new — 30 total)

| LocalBotz template | From the repo | What it does here |
|---|---|---|
| VC Due Diligence | AI VC Due Diligence Agent Team | Startup investment memo: market, product, team, risk |
| Journalist | AI Journalist Agent | Researches, writes and edits an article, with sources |
| Earnings Call Analyst | Earnings Call Analyst Agent | Quarter brief from a transcript or public reports |
| HN Briefing | Always-on HN Briefing Agent | Ranked daily Hacker News brief (daily 08:00) |
| Release Radar | Release Radar Agent | Breaking changes in your dependencies (daily 08:00) |
| Legal Researcher | AI Legal Agent Team | Legal questions and contracts, in plain language |
| Travel Planner | AI Travel Agent (+ Memory) | Day-by-day itineraries; remembers how you travel |
| Health & Fitness Coach | AI Health & Fitness Agent | Diet and workout plans from your goals |
| Financial Coach | AI Financial Coach Agent | Budget, debt and savings plans from your numbers |
| Business Consultant | AI Consultant Agent | Market analysis and strategy, with live research |
| Teacher | AI Teaching Agent Team | A full learning path, lesson by lesson |
| Data Analyst | AI Data Analysis Agent | Ask CSV / Excel files questions in plain English |
| System Architect | AI System Architect Agent | Architecture reviews and design proposals |
| Sales Intelligence | AI Sales Intelligence Agent Team | Competitive battle cards, in real time |
| Doc Q&A | Chat with PDF / Autonomous RAG | Answers from your own documents, with citations |

## Office roles (5 new — 11 total)

From the repo's multi-agent teams: **Sales** 💰 (battle cards),
**Finance** 💲 (budgets and forecasts), **Legal** ⚖️ (contracts, plain
language), **Recruiter** 💼 (screening scorecards + interview questions),
**Teacher** 👨‍🏫 (lessons from what the team learned). They join the team
job order after the writer and before the assistant and analyst.

## Skills (6 new — 12 total)

From the repo's Agent Skills: **Project Graveyard** (why your side
projects died, and which one to finish), **First Reader** (where a draft
loses its reader), **Scope Creep Detector** (did a change grow beyond its
intent?), **Commit Archaeologist** (why a file exists, from its history),
**Dependency Doctor** (unpinned, obsolete and yanked dependencies),
**Self-Improving Skill** (rewrite your own approach after each task).

## What we did NOT take — and why

- **Voice agents** (audio tours, voice RAG, live voice teams): LocalBotz
  has no microphone or voice pipeline yet. The templates above are
  text-only.
- **Image / video generation** (home renovation renders, meme images,
  music): LocalBotz does not generate images, video or audio yet.
- **Game-playing agents** (chess, tic-tac-toe, PyGame): fun, but not a
  job a personal assistant is asked to do.
- **Fine-tuning recipes** (Gemma / Llama LoRA): useful if we ever train a
  custom local model, but nothing to ship in the app today.
- **Framework crash courses** (ADK, OpenAI Agents SDK): tutorials for
  developers, not features for users.

These stay on the list for later: voice first, then image generation.
