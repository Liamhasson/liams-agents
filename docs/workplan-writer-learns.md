# Work plan: The Writer learns

## Goal
Every first draft sounds like Liam, so each application needs fewer fixes than the one before.
Measured by counting the lines Liam changes in each first draft before he approves it. That
number should fall with every application, heading for zero.

## Who it is for
Liam, who approves every letter and CV. The Writer agent is what changes.

## Verdict
The idea holds up and fixes the root cause. Drafts sounded off because the Writer imitated
descriptions of Liam (mytone) instead of his real writing. Approved letters give it real writing
to copy.

What changed during the review:
- Learning works both ways. Approved versions become references to reuse, and Liam's edits
  grow a "never again" list.
- Nothing goes on the never-again list until Liam says yes, asked once at the end of each session.
- Facts go out of date. The newest version wins, and this is tracked fact by fact, not letter by letter.
- Approved story paragraphs are reused word for word when the facts still fit. Openings and
  closings are always written fresh, because a reused opening reads as a generic cover letter.
- It covers everything Liam sends. Letters and CVs each get their own references and
  never-again list, plus one shared list for both.
- Chats with Claude prove how Liam works and directs. They are never used as voice samples.

Still risky: two references is a thin start, so the first few drafts will still need edits.

## Scope
**In:**
- Reference library: approved letters and CVs, starting with the fixed UMG letter and the
  approved Replika letter and CV.
- Never-again list with a reason for each line, split into letter, CV and shared.
- Edit capture: compare the first draft with the approved version and count the changed lines.
- One batched confirmation on Telegram at the end of each session.
- Reuse of approved story paragraphs word for word, with fresh openings and closings.
- Dated facts where the newest wins, and a fact check that also runs on reused paragraphs.
- Later outward text (form answers, pitches) uses the same system once the Applier exists.

**Out:**
- Storing any letter, CV or list in the repo. Everything lives in Notion because the repo is public.
- Adding to the never-again list without Liam's yes.
- Using chat transcripts as voice samples.
- Matcher learning from Apply/Skip taps. That's a separate idea.

## Plan
1. **Save the references to Notion.** Create a "Writer references" page under Private holding
   the fixed UMG letter and the approved Replika letter and CV. Tag each with role type, company
   and approval date. *Outcome:* two references the Writer can load. Small.
2. **Never-again list in Notion.** A database with these fields: line, reason, type
   (letter / CV / shared), date, application. Seed it with the lines already rejected in code,
   then move that list out of the code. The Writer loads the list into its prompt, and the lint
   blocks exact matches. *Outcome:* one list Liam can read and edit.
3. **Edit capture and confirmation.** When Liam approves a draft, compare it sentence by
   sentence with the first draft and log the number of changed lines. At the end of the session,
   send one Telegram message: "You changed these N lines. Add them to the never-again list?"
   Liam can answer yes to all, pick some, or say none. The approved version is saved as a new
   reference. *Outcome:* the success metric starts being logged.
4. **Pick the closest references when drafting.** Choose the 2 or 3 references closest by role
   type and company. Pass their story paragraphs as reusable blocks: reuse them word for word if
   the facts fit, and write the opening and closing fresh. *Outcome:* drafts built from real
   writing.
5. **Keep facts fresh.** Date every fact edit. When a reused paragraph clashes with a newer fact
   (in the CV, mytone or a later approved version), the newest version replaces it. The fact
   check covers reused paragraphs too. *Outcome:* old letters never bring old facts back.
6. **Test and demo.** Unit tests for the edit comparison, list loading and reference picking.
   Then draft two real jobs, show Liam the drafts and the changed-line count, and get his OK.

## Risks and how to handle them
- **Letters start to sound the same.** Openings and closings are always fresh. Liam sees which
  paragraphs were reused.
- **Old facts come back through old letters.** Facts are dated, the newest wins, and the fact
  check runs on reused text.
- **One-off edits become global bans.** The confirmation step lets Liam keep company-specific
  changes off the list. Each entry is marked letter, CV or shared.
- **The list grows too long and costs tokens.** Merge similar entries from time to time, and
  show Liam the merged version.
- **Thin start.** Only two references. Expect edits on the first few letters. The metric will
  show whether it's working.

## Open assumptions
- The success metric (changed lines per first draft) was proposed by Claude and not explicitly
  confirmed by Liam.
- There is no set cost ceiling. Liam has said he'd rather spend tokens on checks than re-prompt.
  References add roughly 2 to 4 thousand input tokens per draft, about 1 cent on Sonnet, and
  reused paragraphs save writing tokens.
- How many references to load (2 or 3) and how often to merge the list are still to tune.
- Form answers and pitches join once the Applier is built.

## First step
Save the fixed UMG letter and the approved Replika letter and CV to a "Writer references"
page in Notion under Private.
