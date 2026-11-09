# Liam's agents: build brief

This is the plan for rebuilding Job_Agent into **Liam's agents**, a small team of agents that finds design jobs and freelance work in Berlin and remote, tells Liam on Telegram the moment something fits, briefs him on what the company wants, and drafts everything the post asks for in his voice. Liam reviews every asset and applies himself.

Read this whole file before writing any code. Build in the phases at the bottom, one at a time, and check in with Liam at the end of each phase.

---

## 0. How to work with Liam

- Liam is a product designer, not a developer. He uses Claude Code daily but doesn't write HTML, CSS or Python by hand. Explain what you're doing in plain words.
- Ask before guessing. If a requirement is unclear, ask him one clear question.
- Any step he has to do himself (creating accounts, adding secrets, approving apps in Meta or Notion) gets a numbered walkthrough, one screen at a time.
- Use Plan mode at the start of each phase. Show him the plan, then build.
- Every phase ends with a working demo he can see, plus tests.

---

## 1. The goal

**Apply first, and apply well.** Most applicants find jobs on LinkedIn days after they're posted. Liam's agents find them at the source within an hour, and every application is tailored to the company and written in Liam's own voice.

What success looks like:
1. A new design job appears on a Berlin startup's career page.
2. Within about an hour Liam gets a WhatsApp message explaining the job, the problem the company is hiring to solve, why he's a fit and any gaps.
3. He taps Brief me or Skip. The Director tells him what the company is after, who they want and why he fits, and lists what the post asks applicants to send.
4. He texts when he's ready. The Editor drafts each asset with him, he reviews them and applies himself.
5. Everything is tracked in Notion, including which sources lead to callbacks.

---

## 2. Ground rules

These are not up for negotiation in code.

1. **Nothing is sent without Liam's approval.** No application, email or pitch leaves without an explicit yes on WhatsApp.
2. **No logged-in LinkedIn automation, ever.** It risks a ban on Liam's real account.
3. **Never bypass CAPTCHAs, bot checks or logins.** If a site needs one, hand the step to Liam.
4. **Respect sites.** Honest User-Agent, about 1 request per second per host, follow robots.txt and terms, give attribution where a feed requires it (Remotive, RemoteOK, Jobicy, Himalayas).
5. **No personal data in the repo.** The repo is public. CVs, mytone.md, salary and standard answers live in Notion or GitHub secrets.
6. **No cold marketing emails to German businesses.** German law restricts them. The Freelance Hunter drafts pitches and Liam reaches out himself.
7. **Spend carefully.** Use the cheap Claude model for scoring and the stronger model only after Liam approves a job.
8. **Never invent facts** about Liam. Everything comes from his CV, mytone.md and Notion.

---

## 3. The team

| Agent | Job | Runs | Model |
|---|---|---|---|
| **Scout** | Finds new job sources and new companies, detects which hiring tool each company uses, and adds them to Notion. | Weekly | Haiku |
| **Hunter** | Checks every active source and company career page, collects new jobs and dedupes them. | Hourly | none (plain code) |
| **Matcher** | Scores each job, applies filters, writes the fit summary and flags gaps. Sends borderline ones to Liam as a question. | After each Hunter run | Haiku |
| **Messenger** | Owns WhatsApp: job alerts, Liam's replies, daily reminders for unanswered jobs, weekly stats. | On events + daily | Haiku for parsing replies |
| **Researcher** | Researches the company after Liam approves a job: product, mission, team, recent news, the problem behind the hire. | On approval | Sonnet |
| **Director** | Runs once after Brief me. Short brief: what they're after, who they want, why Liam fits (each point quotes his CV or mytone), weak spots, and which assets the post needs. Never writes assets. | On Brief me | Sonnet |
| **Editor** | Drafts every asset the post asks for (CV, cover letter, form answers, Loom script) and changes them with Liam in plain language on Telegram. Starts when he texts. Saves his corrections to mytone silently. | When Liam texts | Sonnet |
| **Freelance Hunter** | Finds freelance leads and small Berlin businesses that need a website, and drafts pitches for Liam to send himself. | Daily | Haiku, Sonnet for pitches |

Each agent is its own module with a clear input and output, so new agents can join later without touching the others.

---

## 4. Architecture

```
            ┌──────────────── GitHub Actions (public repo, free minutes) ───────────────┐
 hourly ──▶ │ Hunter ──▶ Matcher ──▶ Messenger.send_alert                                  │
 weekly ──▶ │ Scout                                                                         │
 daily  ──▶ │ Messenger.reminders  ·  Freelance Hunter  ·  weekly stats                     │
 dispatch ▶ │ Researcher ▶ Director  ·  Editor (when Liam texts)                                 │
            └───────────────────────────────────────────────────────────────────────────────┘
                     │ reads/writes                                ▲ repository_dispatch
                     ▼                                             │
              ┌──────────────┐        ┌─────────────────────────────────────┐
              │    Notion    │◀──────▶│  Vercel function: /api/whatsapp      │◀── WhatsApp
              │ Jobs, Leads, │        │  receives Liam's replies, updates    │    Cloud API
              │ Sources,     │        │  Notion, starts the Editor             │    (Meta)
              │ Companies    │        │  turns, triggers GitHub for slow work│──▶ messages
              └──────────────┘        └─────────────────────────────────────┘     to Liam
```

- **GitHub Actions** runs the scheduled and heavy work. Keep the repo public so minutes are unlimited.
- **A Vercel serverless function** is the always-on endpoint WhatsApp calls when Liam replies. It must answer Meta fast. Quick work (updating Notion, a short Writer chat reply) happens there. Slow work (research, PDFs, applying) is handed to GitHub with `repository_dispatch`.
- **Notion** is the single source of truth for jobs, leads, sources, companies and drafts. It replaces `seen_jobs.json`.
- **WhatsApp Cloud API by Meta** sends and receives messages.
- **Gmail API** (Liam's main Gmail) sends email applications and can later watch for replies from companies.
- **Claude API** for scoring, research and writing.

Language: Python 3.12 for the agents. The Vercel function can be Python or TypeScript, whichever is simpler to deploy. Check Vercel's current limits for function duration on the free plan before choosing.

---

## 5. Repo

Rename `Job_Agent` to `liams-agents` (GitHub redirects the old URL, and secrets and history carry over).

Suggested layout:

```
liams-agents/
├── CLAUDE.md                 # how to work in this repo (create in phase 0)
├── docs/BUILD_BRIEF.md       # this file
├── agents/
│   ├── scout/
│   ├── hunter/
│   │   └── sources/          # one module per source type: greenhouse.py, lever.py, ashby.py, rss.py ...
│   ├── matcher/
│   ├── messenger/
│   ├── researcher/
│   ├── director/
│   ├── editor/
│   └── freelance_hunter/
├── shared/                   # notion client, claude client, models, config, logging, http with rate limits
├── webhook/                  # Vercel function for WhatsApp
├── config/settings.yaml      # search terms, filters, thresholds (nothing personal)
├── tests/
└── .github/workflows/        # hunter.yml (hourly), daily.yml, scout.yml (weekly), dispatch.yml
```

Personal files are never committed. Load them at runtime from Notion or GitHub secrets.

---

## 6. Notion

Liam creates an empty page called **Liam's agents** and connects a Notion integration to it. The code creates these databases under it on first run.

**Jobs**
- Title, Company, URL, Apply URL
- Source, Company ATS, Location, Remote (yes/no/hybrid), Posted at, First seen at
- Role type: product design, UX/UI, web design, brand or visual, growth design, design engineer, internship, working student, founder associate, other
- Score (0 to 100), Fit summary, Why Liam (2 to 3 lines), Gaps (text), Flags (multi-select: senior, experience gap, borderline, contract, unpaid)
- Status: New, Asked Liam, Waiting for Liam, Approved, Drafting, Ready to send, Applied, Needs Liam to submit, Interview, Offer, Rejected, Skipped, Expired
- Apply method: email, ATS form, manual
- Last reminder at, Reminder count
- Research notes, CV draft, Cover letter draft, Final PDFs
- Applied at, Outcome, Callback (yes/no), Callback at

**Freelance Leads**
- Name, Type (platform post, Reddit, HN, local business), URL, Contact route, What they need, Budget if known, Fit summary, Pitch draft, Status (New, Waiting for Liam, Liam contacting, Won, Lost, Skipped)

**Sources**
- Name, Type (ATS, board, aggregator, RSS, VC board, freelance), Endpoint, Access (API, RSS, HTML), Status (proposed, active, paused, broken), Last checked, Jobs found, Jobs approved, Callbacks, Notes on terms

**Companies**
- Name, Careers URL, ATS, ATS slug, Found via, Last checked, Last new job at, Active (yes/no)

**Private** (a page, not a database)
- mytone.md, base CV content, standard answers (salary, start date, portfolio), the job profile for the Matcher. The agents read these at runtime. Liam edits them in Notion.

Dedupe on `(ATS, company slug, job id)` and also on a hash of normalised title + company, since one job often appears in several places. Keep the earliest First seen.

---

## 7. The Hunter's sources

Priority is speed and reliability. Company career pages are the source, so they come first.

### 7a. Company hiring tools (highest priority, hourly)

All public, no auth. Confirm each pattern still works when you build it.

| ATS | Endpoint |
|---|---|
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Lever | `GET https://api.lever.co/v0/postings/{site}?mode=json` (EU: `api.eu.lever.co`) |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` |
| Personio | `GET https://{sub}.jobs.personio.de/xml?language=en` |
| Workable | `GET https://apply.workable.com/api/v1/widget/accounts/{shortcode}?details=true` |
| Recruitee | `GET https://{co}.recruitee.com/api/offers/` |
| Teamtailor | `https://{careersite}/jobs.rss` or `https://{co}.teamtailor.com/jobs.json` |
| JOIN | `https://join.com/companies/{slug}`, parse `__NEXT_DATA__` (no official API, check terms) |
| SmartRecruiters | `GET https://api.smartrecruiters.com/v1/companies/{id}/postings` (check terms first) |
| Workday | `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`, limit 20 max |

### 7b. Boards and feeds

| Source | Access | Notes |
|---|---|---|
| Berlin Startup Jobs | `https://berlinstartupjobs.com/design-ux/feed/` and main feed | RSS |
| Dribbble Jobs | `https://dribbble.com/jobs.rss` | RSS |
| Arbeitnow | `https://www.arbeitnow.com/api/job-board-api` | free API, DE startups, founder associate roles show up here |
| Bundesagentur für Arbeit | `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs` with header `X-API-Key: jobboerse-jobsuche` | internships (`angebotsart=34`), working student, home office |
| We Work Remotely | `https://weworkremotely.com/categories/remote-design-jobs.rss` | RSS |
| Remotive, RemoteOK, Jobicy, Himalayas | public APIs | attribution and rate limits required |
| HN "Who is hiring" | Algolia API | monthly thread, filter for Berlin and remote design |
| Google Jobs via SerpApi | `engine=google_jobs`, filter to posted today | covers LinkedIn, Indeed, XING and StepStone listings safely. Stay inside the free 250 searches a month: a few targeted searches a day. |
| VC portfolio boards (Getro): Earlybird, Point Nine, HV Capital | HTML `__NEXT_DATA__` | mostly used to find companies, then poll their ATS directly |

Skip Wellfound (blocks bots), logged-in LinkedIn and Indeed scraping.

Track every source's results in Notion so Liam can see after a month which sources lead to callbacks. Only then decide whether to pay for more SerpApi searches.

---

## 8. The Scout

Runs weekly and keeps the source list growing on its own.

1. Collect company names from Arbeitnow, Berlin Startup Jobs, HN threads, Getro boards, the Berlin Startup Map, YC company list and any company the Hunter has seen.
2. For each new company, find its careers page and detect the ATS by URL pattern (`boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, `.jobs.personio.de`, `apply.workable.com`, `.recruitee.com`, `join.com/companies`, `teamtailor`, `myworkdayjobs`, `smartrecruiters`). If nothing matches, try likely slugs against the endpoints above.
3. Add it to Companies as active.
4. Search the web for new job boards and feeds relevant to design jobs in Berlin and remote. Add them to Sources as proposed. Ones with an API or RSS can go active automatically. HTML-only ones wait for Liam's OK on WhatsApp.
5. Mark companies with no new jobs for 60 days as inactive, and recheck them monthly.

---

## 9. The Matcher

**Include:** product design, UX/UI, web design, brand and visual design, growth design, light design engineering, internships, working student roles, founder associate roles, and anything adjacent that fits Liam's profile. When in doubt, ask Liam instead of dropping it.

**Location:** Berlin, or remote roles that can hire someone living in Germany. No relocation.

**Drop:** jobs that require German. Liam's German is A2, so drop anything asking for fluent or business German.

**Keep but flag:** roles asking for more experience than Liam has. Include the gap in the alert.

**Scoring** (configurable in settings.yaml):
- 70 and up: send an alert.
- 40 to 69: ask Liam on WhatsApp with a one-line question ("Founder associate at X, relevant?"). His answer teaches the Matcher.
- Below 40: drop, but log it in Notion so the threshold can be tuned.

The Matcher reads Liam's profile from the Notion Private page. Use Haiku with a strict JSON output: score, role type, why Liam, gaps, flags, German required (yes/no), remote eligibility.

---

## 10. The Messenger and WhatsApp

### Setup (walk Liam through it)
- Meta developer account, a Business app, the WhatsApp product, the free test number, Liam's phone added as a recipient, a permanent token through a system user, and a webhook pointing at the Vercel function.
- Check Meta's current rules and prices before building. Two things to confirm: how many recipients and templates the test number allows, and what utility templates cost per message in Germany.
- **The 24 hour rule:** the bot can message freely only within 24 hours of Liam's last message. Outside that window it can only send pre-approved templates. So the alert and the daily reminder must each have an approved template version.
- If Meta setup becomes a blocker, tell Liam. A Telegram bot is a much simpler fallback, but WhatsApp is what he wants, so only switch if he says so.

### Job alert (one message per job, sent as soon as it's found)

```
🆕 Product Designer at Acme (Berlin, hybrid)
Posted 40 min ago · via Ashby

What it is: <one or two lines>
The problem they're hiring for: <one line>
Why you: <two lines tied to his real work>
Relevant work: Eventread, Cyvore
Gaps: asks for 5+ years

[Apply]  [Skip]  [Tell me more]
```

- Use buttons where WhatsApp allows them, and also accept typed replies like "apply", "skip", "more".
- Map Liam's reply to the right job using the WhatsApp context id of the message he's replying to. Store message id → job id in Notion.

### Reminders
- Every morning, one message listing every job still waiting for Liam, oldest first. Repeat daily until each one is approved or skipped.
- Mark jobs whose posting disappears as Expired and stop reminding.

### Weekly stats
- Jobs found, approved, applied, callbacks, and the top sources by callbacks.

---

## 11. Researcher, Director and Editor

Only run after Liam taps Brief me. The full design is in `docs/superpowers/specs/2026-11-09-director-editor-design.md`.

**Researcher:** reads the job post, the careers page and the company's own website, following robots.txt. Writes facts about the company to Notion.

**Director:** runs once and needs no live chat. Sends a short brief that keeps what the post says apart from its own read. Every "why you" point quotes Liam's CV or mytone, and code drops any point whose quote isn't there. It lists the assets the post asks for and asks where to start. The brief sets the angle and is never a source of facts.

**Editor:** starts when Liam texts, and closes after 15 quiet minutes with everything saved in Notion. Drafts only what the post asks for, unless he asks for more. He can skip one asset without dropping the application. Each draft goes through the fact check and voice check. His corrections go to mytone silently, in his own words only. One page is a hard limit for the CV.

---

## 12. Applying

Liam applies himself and reviews every asset first. When every asset is final or skipped, the Editor sends a checklist with the posting link and an Applied button, which sets the status and date in Notion. There is no Applier agent.

---

## 13. Freelance Hunter

- **Feeds:** Reddit r/forhire and r/DesignJobs through the official API with OAuth, filtered to `[Hiring]`. HN freelancer threads. Dribbble freelance roles.
- **Platforms like Malt, Contra and Upwork can't be automated** within their terms. Leave them out. Upwork has an official API that needs approval, which can be added later.
- **Local businesses:** find Berlin businesses with no website or a weak one (Google Places, which is about 1,000 free calls a month, or OpenStreetMap). Draft a short pitch in Liam's voice and send the lead to WhatsApp. Liam reaches out himself by phone or a contact form.
- Same flow as jobs: alert, Liam decides, drafts on approval. Nothing is ever sent automatically.

---

## 14. Secrets

GitHub secrets (and the same in Vercel where needed):
- `ANTHROPIC_API_KEY`
- `NOTION_TOKEN`, `NOTION_ROOT_PAGE_ID`
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` (verify webhook signatures), `LIAM_WHATSAPP_NUMBER`
- `GMAIL_CREDENTIALS_JSON`, `GMAIL_TOKEN_JSON`
- `SERPAPI_KEY`
- `GITHUB_DISPATCH_TOKEN` (for Vercel to trigger GitHub)
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- `MYTONE_MD` is only a fallback. The main copy lives in Notion.

---

## 15. Costs

- GitHub Actions: free for public repos.
- Vercel: free plan for personal use.
- Notion: free.
- SerpApi: free tier, 250 searches a month.
- WhatsApp: free inside the 24 hour window. Templates may cost a few cents each, so confirm Meta's current price.
- Claude API is the real cost. Haiku for scoring and parsing, Sonnet only after approval. Log token use per agent in Notion so Liam can see it. Set a monthly budget in settings.yaml and warn Liam on WhatsApp at 80%.

---

## 16. Build phases

Each phase ends with tests, a short demo for Liam and his OK before moving on.

### Phase 0: clean up and set up
- Rename the repo to `liams-agents`.
- Fix the broken daily run: delete the "Install WeasyPrint system dependencies" step (WeasyPrint isn't used and that apt package no longer exists on Ubuntu 26) and pin `runs-on: ubuntu-24.04`. If these commits already exist on main, skip.
- Remove `base_documents/cover_letter_avaloq.md`, `cover_letter_gameduel.md` and `voice_rules.md` if still there. They don't sound like Liam.
- Move the CVs and every personal file out of the repo and into Notion. Then remove them from git history with `git filter-repo`. Explain the force push to Liam and get his OK first.
- Create `CLAUDE.md` with the ground rules, repo layout and how to run things.
- Walk Liam through the Notion integration and the GitHub secrets.
- **Done when:** the old daily run passes again, nothing personal is in the repo or its history, and CLAUDE.md exists.

### Phase 1: Notion foundation
- Shared Notion client and models. Script that creates the four databases and the Private page structure.
- Migrate `seen_jobs.json` into dedupe records, then delete the file and its commit-back step.
- **Done when:** the databases exist and a test job can be written, read and deduped.

### Phase 2: Hunter
- One module per ATS type and per feed type, sharing rate-limited HTTP.
- Seed the Companies database with Berlin startups (start with the ones Liam already applied to or knows, plus the seeding sources in section 8).
- Hourly workflow.
- **Done when:** an hourly run collects new jobs from at least the ATS sources and five feeds into Notion with no duplicates.

### Phase 3: Matcher
- Filters, scoring, fit summary, gaps and flags. Tune with Liam on a sample of 20 real jobs.
- **Done when:** Liam agrees with the Matcher on most of the sample.

### Phase 4: Messenger
- Meta setup with Liam. Vercel webhook with signature checks. Alerts, buttons, reply handling, borderline questions, daily reminders and expiry.
- **Done when:** a real job reaches Liam's WhatsApp, and Apply or Skip updates Notion.

### Phase 5: Researcher, Director and Editor
- Research notes. The WhatsApp brainstorm loop. Drafts saved to Notion. One-page PDFs. mytone.md updates from Liam's edits.
- **Done when:** Liam co-writes one real application end to end on WhatsApp and says it sounds like him.

### Phase 6: removed

There is no Applier. Liam applies himself.

### Phase 7: Scout
- Weekly discovery of companies and sources, with Liam's OK for HTML-only sources.
- **Done when:** a weekly run adds new companies and proposes at least one new source.

### Phase 8: Freelance Hunter
- Reddit, HN and Dribbble feeds, plus local business leads with pitch drafts.
- **Done when:** Liam gets a real freelance lead and a pitch draft he'd use.

### Phase 9: Learning loop
- Weekly stats, callbacks by source, cost per agent, the budget warning, and a README that tells the story of the build.

---

## 17. Things still to verify while building

- Meta: test number limits, template rules and current utility template price in Germany.
- Vercel free plan function duration, for webhook replies.
- Personio, SmartRecruiters and JOIN terms for automated reading.
- The Bundesagentur header and response format.
- Getro's internal search request for pages past the first.
- Which hiring forms can be submitted without a CAPTCHA in practice.
