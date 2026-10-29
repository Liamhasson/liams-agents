# CLAUDE.md — how to work in this repo

This repo is **Liam's agents**: a small team of agents that finds design jobs and
freelance work in Berlin and remote, tells Liam on WhatsApp the moment something fits,
helps him write the application in his own voice, and applies once he approves.

**The full plan lives in [`docs/BUILD_BRIEF.md`](docs/BUILD_BRIEF.md). Read it before writing any code.**
It is the source of truth for the goal, the team of agents, the architecture, the data
model and the build phases. This file is the short operating manual.

Liam is a product designer, not a developer. Explain changes in plain words. Any step he
has to do himself (accounts, secrets, approvals in Meta/Notion/GitHub) gets a numbered,
one-screen-at-a-time walkthrough. Use Plan mode at the start of each build phase, show him
the plan, then build. Ask before guessing.

---

## Ground rules (not up for negotiation)

1. **Nothing is sent without Liam's approval.** No application, email or pitch leaves
   without an explicit yes on WhatsApp.
2. **No logged-in LinkedIn automation, ever.** It risks a ban on his real account.
3. **Never bypass CAPTCHAs, bot checks or logins.** If a site needs one, hand the step to Liam.
4. **Respect sites.** Honest User-Agent, ~1 request/second per host, follow robots.txt and
   terms, give attribution where a feed requires it (Remotive, RemoteOK, Jobicy, Himalayas).
5. **No personal data in the repo.** This repo is public. CVs, `mytone.md`, salary and
   standard answers live in Notion or GitHub secrets — never committed.
6. **No cold marketing emails to German businesses.** German law restricts them. Draft
   pitches; Liam reaches out himself.
7. **Spend carefully.** Cheap model (Haiku) for scoring/parsing; the stronger model (Sonnet)
   only after Liam approves a job.
8. **Never invent facts about Liam.** Everything comes from his CV, `mytone.md` and Notion.

---

## Target repo layout

See `BUILD_BRIEF.md` §5 for the full picture. Where we're heading:

```
liams-agents/
├── CLAUDE.md                 # this file
├── docs/BUILD_BRIEF.md       # the plan
├── agents/                   # scout, hunter (+ sources/), matcher, messenger,
│                             # researcher, writer, applier, freelance_hunter
├── shared/                   # notion client, claude client, models, config, rate-limited http
├── webhook/                  # Vercel function for WhatsApp
├── config/settings.yaml      # search terms, filters, thresholds (nothing personal)
├── tests/
└── .github/workflows/        # hunter.yml (hourly), daily.yml, scout.yml (weekly), dispatch.yml
```

**Current state (mid-transition):** the repo still has the original single-pipeline layout
(`orchestrator.py`, `modules/`, `seen_jobs.json`). It is being rebuilt phase by phase per
the brief. Don't assume the target layout exists yet — check before importing.

---

## How to run (current)

```bash
pip install -r requirements.txt
python -m playwright install chromium        # PDFs are rendered via headless Chromium
python orchestrator.py --dry-run             # safe: generates drafts, sends nothing
python orchestrator.py                        # live run
```

- Local secrets live in `.env` (gitignored, never committed). See `.env.example` for keys.
- The daily GitHub Action (`.github/workflows/job_agent.yml`) runs on `ubuntu-24.04`.
- PDFs are rendered with **Playwright/Chromium**, not WeasyPrint. Don't re-add WeasyPrint
  system deps to the workflow.

---

## Personal data policy

Never commit: CVs, cover letters written in Liam's voice, `mytone.md`/voice notes, salary,
standard answers, real contact details, any `*token*`/`*credential*` file. These load at
runtime from Notion or GitHub secrets. If you find personal data in the repo or its history,
stop and tell Liam — removing it from history needs a force-push and his explicit OK.

---

## Models & cost

- Haiku: scoring, parsing WhatsApp replies, cheap classification.
- Sonnet: research and writing, only after Liam approves a job.
- Claude runs on Liam's Claude subscription through the Claude Code CLI (`shared/claude.py`,
  `CLAUDE_CODE_OAUTH_TOKEN` on GitHub), so the agents cost nothing extra. Don't add
  `ANTHROPIC_API_KEY` to workflows: it would bill the API.
- Every run logs its usage (API-equivalent $) to the Notion "Usage" database. The monthly
  limit lives in `settings.yaml > usage`; Telegram warns at 80%, and at 100% the Matcher
  and Researcher pause.

---

## Working style

- Each agent is its own module with a clear input and output.
- Every build phase ends with tests, a short demo Liam can see, and his OK before moving on.
- When in doubt about whether a job/role fits, ask Liam rather than dropping it.
