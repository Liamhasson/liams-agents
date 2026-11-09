# Director and Editor: design

Date: 2026-11-09. Status: waiting for Liam's approval. Nothing here is built yet.
This repo is public, so this file holds no personal data and names no job Liam acted on.

## 1. Why

The Writer assumes every job wants a CV and a cover letter, and it can only chat.

- Of the 25 jobs that reached Liam's phone, none mention a cover letter and 13 mention a portfolio.
  Real applications have needed form answers, Loom scripts and interview answers, all made by hand.
- Since the webhook went live, the Writer has run three times on GitHub and finished none:
  one cancelled, one dropped, one timed out waiting.
- In the chat, a message that mixed "save this", "drop it" and "remember that" was not acted on.
  Facts Liam gave in chat were lost when the session ended.
- Nothing tells Liam that an exact word like "done" is what makes a draft.
- Sessions start when the agent is ready, so Liam can miss them.

## 2. The new flow

1. **Hunter** finds jobs (unchanged).
2. **Matcher** scores them and sends a card that also shows what the post asks for.
3. Liam taps **Brief me** (replaces Apply, because Liam now applies himself).
4. **Researcher** gathers company facts.
5. **Director** sends a short brief and asks where to start.
6. Liam texts whenever he is ready. **Editor** opens and drafts each asset with him.
7. Corrections go silently into mytone.
8. Liam checks each asset, applies himself and taps **Applied**.

The Applier is removed from the plan.

## 3. Decisions Liam made

- The Director does not write assets. The Editor writes them, working from the Director's brief.
- The Editor drafts everything the post asks for, unless Liam skips one asset. Skipping never drops the application.
- The Director asks where to start.
- Liam talks to the Editor normally and can change anything in any asset.
- Liam applies himself and reviews every asset first.
- Corrections go straight to mytone, automatically and silently. No tap, no confirmation message.
- The chat starts when Liam texts, not when the agent does.
- Fit below 50 is never sent to Liam.
- A "Senior" title is shown but costs no points. Fit is judged on the job description.
- Stated years ("5+ years") keep losing points exactly as they do today.
- Ad work arrives with a warning on the card. It does not disqualify the job.
- The Director runs only after Liam taps Brief me.
- The bot stays buttons and fixed commands outside a write-up. No general assistant.

## 4. Goals, non-goals, anti-goals

**Goals:** every job gets only the assets it asks for. Liam can ask for anything in plain words and it happens. A session can never be missed or lost.

**Non-goals:** automatic submitting, a general Telegram assistant, web search in the Researcher, reading forms the site does not publish, retuning the point values (25 jobs is too few to support it).

**Anti-goals (failure even if it runs):**
- Any claim about Liam with no source in his CV or mytone.
- An asset the post did not ask for, unless Liam asked for it.
- A model-guessed rule written into mytone as if Liam said it.
- Anything submitted or sent to a company by the agents.

## 5. The parts

### A. Matcher and card

**Asks list.** Add to the existing Matcher call, with no extra model call: a list of what the post asks for. Each item has a kind (CV, cover letter, portfolio, Loom or video, case study, form questions, LinkedIn, other), a state (required, optional, not wanted) and the post's exact words. Code checks that the quote appears in the post and drops any item where it does not. If nothing is left, the card says the post doesn't say what to send.

**Grading changes.**

| Change | Rule |
|---|---|
| Minimum fit | Fit below 50 is marked Skipped and never sent, as an alert or a borderline question. The `jobs` command hides these too. |
| Senior title | The prompt says never to lower fit for a title. The "senior" flag still shows on the card. |
| Stated years | No change to the penalties or the drop rule. |
| Ad work | The Matcher returns whether ad work is part of the role, with the post's exact words. The card shows a warning. Score is unaffected. |
| The 100 cap | The stored score is no longer capped, so jobs keep their order. The card shows Fit and the breakdown instead of "/100". |
| Freshness | Age points are recalculated daily with no model call. This changes order in `jobs` and never re-sends a card. |
| Ghost warning | Age alone no longer triggers it. The card shows "posted N days ago" as a plain fact. Vague text and reposting still trigger it. |
| Field bonus | Tighten the prompt so finance and software tools are "other". Test on stored jobs before shipping. |
| Skip reason | After Skip, offer optional one-tap reasons, to collect data for tuning later. |

### B. Brief me

Tapping Brief me starts a new one-shot GitHub workflow: Researcher, then form lookup, then Director. Buttons on old cards keep working. If any step fails, Liam is told on Telegram and can retry.

**Form lookup.** Only Greenhouse publishes form questions (`questions=true` on the single-job endpoint). Skip name, email and phone. Everywhere else the Director says the form wasn't checked and asks Liam to paste the questions. Do not call Ashby's `/api/` path, because its robots.txt disallows it.

### C. Researcher

- Facts about the company only. "How Liam fits" moves to the Director.
- Remove the 1,900-character cut on notes.
- Also read the company's own website, following robots.txt. Use the public website link where the hiring page gives one, or the Careers URL's site from the Companies database. If there is none, say the site wasn't read. Today, on Ashby pages it reads only the job title.

### D. Director

Runs once per job on Sonnet, needs no live session, and sends one short Telegram message:

- What they're after, separated into what they say and what the Director reads into it.
- The candidate they want, split the same way.
- Why Liam: each point names a real project and carries a quote from his CV or mytone. Code checks every quote and drops points that fail.
- Weak spots, for Liam only. These never go in an asset.
- The asset list, then "Where do you want to start?" Each asset gets a start button and a skip button. Liam can also just text.

Assets the Editor drafts: CV, cover letter, form answers, Loom script. Checklist items Liam handles: portfolio link, LinkedIn, case study.

The brief is saved to Notion and sets the Editor's angle. It is never a source of facts.

### E. Editor

Replaces the Writer. Reuses the CV format, PDFs, references, lint, fact check and voice check.

**Starting by text.**
- Any text with no live chat starts the Editor for the job waiting on Liam. A reply to that job's message picks that job. If several are waiting, Liam gets buttons.
- The webhook marks the session live straight away, so texts sent during start-up don't start a second run.
- The message that started it is kept and answered first. Today's start-up step discards waiting messages, so that step must change.
- Liam is told it's starting. Setup measured 73 to 82 seconds in real runs.
- One chat at a time, as today.

**Staying open.** The live window rolls forward with each message and closes after 15 minutes of silence. Before closing it checks once more for new messages. The next text restarts it with everything in place.

**Understanding requests.** Each reply is one Sonnet call that returns the message to Liam plus a list of actions that code carries out in order: draft asset, revise asset, skip asset, mark asset final, drop application, list jobs, save correction. A mixed message runs each action. The Editor never claims something it cannot do.

**Assets.**
- Revising changes only the asset asked about. Liam's own words are used exactly.
- New drafts go through the fact check and voice check, with the full stored post and full research.
- CV and letter arrive as PDFs. Form answers arrive as one copy-ready message per question. The Loom script arrives as text.
- Dropping acts at once, and the message has a "Bring it back" button.

### F. Silent corrections to mytone

Saved to a "Corrections" section in mytone with no message to Liam. A message appears only if a save fails. Each entry is tagged with job, asset and date. Only Liam's words are stored:

1. He gave the wording: the old line and his new line.
2. He gave an instruction ("shorter"): his exact words and the line they applied to.
3. He stated a fact or a rule: his exact words.

Code checks that the saved text appears in his message. The model never writes why he changed something. The Editor reloads mytone after each save, so a new fact is usable straight away.

### G. Applied

When every asset is final or skipped, the Editor sends a checklist with the posting link and an **Applied** button. It also works later without a live session. It sets Status to Applied and records the date.

## 6. Data changes

- **Jobs:** add "Briefed" status, the asks list, ad-work note, Director brief, form questions and base score.
- **New Assets database:** one row per job and asset, with kind, state and full text. The current draft fields cut text at 1,900 characters.
- **Inbox:** add direction, so both sides of the chat are saved and a session can be restored.
- **Usage:** log "director" and "editor".

## 7. Order of work

Each step ends with tests and something Liam can see.

| Step | Done when |
|---|---|
| 1. Asks list and grading | Stored jobs re-run as a dry run: the three weak alerts disappear, and asks match the posts by hand check. |
| 2. Brief me, Researcher, Director | A real brief arrives on Telegram, and every "why Liam" point has a checked quote. |
| 3. Editor, starting by text | Texting starts a session. These real messages work: the mixed save, drop and remember message, and "Done." with a full stop. A closed chat resumes with drafts intact. |
| 4. Silent corrections | A correction shows up in mytone with no message to Liam, and the next draft follows it. |
| 5. Applied and docs | Update BUILD_BRIEF, CLAUDE.md and workflows. Remove the Writer's name and the Applier. |
| 6. One real run | One post goes from card to Applied. |

Steps 1 (asks list), 2, 3 and 4 are what the Loom needs. The script is rewritten after step 6, as separate work.

## 8. Calls made by Claude, for Liam to check

- Age points stay in the score, recalculated daily, because Liam tuned those numbers himself.
- 15 minutes of silence closes a chat.
- A drop acts at once with "Bring it back" rather than asking first.
- The old "Never again" tap goes away. The list is still checked, and it only gains a line when Liam says never to use something. A line replaced for one job is not banned forever.
- If the monthly limit is reached, Brief me says so on Telegram rather than failing quietly.
- Corrections are saved as they happen, not when an asset is marked final.
- Briefed jobs with no chat started join the existing daily reminder, so a brief can't be forgotten.

## 9. Left to the builder

Exact prompts, field names, button layout, file moves, and how the rolling window is written.
Website reads go through `PoliteClient`, which already follows robots.txt and the one-request-a-second limit.

## 10. Known risks

- The Corrections section grows, and mytone (about 3,800 words) is loaded on every call. A tidy-up will be needed later, and it must keep Liam's words.
- The first reply takes about a minute and a half. Making it faster would mean paying per message.
- Only Greenhouse forms can be read automatically.
- Reading company websites is untested against real sites.
