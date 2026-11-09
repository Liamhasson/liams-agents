# Director and Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Writer with a Director that briefs Liam and an Editor that drafts only what each post asks for, started by Liam's text, and fix the Matcher's grading.

**Architecture:** The Matcher adds a quote-checked list of what the post asks for. Brief me starts a one-shot GitHub workflow (Researcher, form lookup, Director). The Editor is a GitHub session started by the Telegram webhook when Liam texts. Its state lives in Notion, so it can close and resume.

**Tech Stack:** Python 3.12, Notion API, Telegram Bot API, GitHub Actions, Vercel webhook, Claude Code CLI on the subscription, Playwright PDFs, pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-director-editor-design.md`

## Global Constraints

- This repo is public. No personal data, and no real job Liam acted on, in code, tests or commits. Use "Acme" in tests.
- Nothing is sent to a company by any agent. Liam applies himself.
- Haiku for scoring and asks. Sonnet only after Brief me. Never add `ANTHROPIC_API_KEY` to workflows.
- Follow robots.txt through `PoliteClient`. Never call Ashby's `/api/` path.
- Every claim about Liam needs a source in his CV or mytone. A quote that fails the check is dropped, never softened.
- Text shown to Liam by code is plain. Asset drafts follow the existing lint: no dashes, no banned words, at most two commas per sentence.
- Corrections to mytone are silent. Telegram mentions them only when a save fails.
- Do not retune point values. `min_fit` is 50. Idle close is 15 minutes. Boot window is 5 minutes.
- The live Notion page keeps its name "Writer references". Only code names change.
- Work on branch `feat/director-editor`. Do not push or merge to `main` until Task 14 and Liam's OK.

Test command everywhere: `.venv/bin/python -m pytest -q`. Baseline before Task 1: 119 passed.

## Review Focus

1. **Liam texts again during the 80 seconds of start-up.** No second run starts, and both messages are answered in order. Test in Task 11.
2. **A session crashes mid-chat.** The window expires by itself, unread messages survive, and the next text resumes with drafts intact. Tests in Tasks 10 and 11.
3. **The model asks to revise an asset that doesn't exist yet.** Code says so plainly, and the reply never claims it was done. Test in Task 9.
4. **Long text hits Telegram's 4,096 limit** (long form answers, Loom script, brief). Messages split on paragraph breaks and nothing is cut. Test in Task 8.
5. **A correct quote has curly quotes, line breaks or emoji.** The check still accepts it. Test in Task 1.

---

### Task 1: Foundations (test setup, quote check, data model)

**Files:**
- Create: `shared/quotes.py`, `shared/assets.py`, `tests/test_quotes.py`, `tests/test_assets.py`
- Modify: `shared/notion/schema.py`, `shared/notion/client.py:62-64`, `config/settings.yaml`, `.gitignore`, `tests/test_notion_foundation.py`

**Interfaces:**
- Produces: `appears_in(quote: str, source: str, min_chars: int = 8) -> bool`
- Produces in `shared/assets.py`: `DRAFTED_KINDS = ("cv", "cover_letter", "form_answers", "loom_script")`, `CHECKLIST_KINDS = ("portfolio", "linkedin", "case_study", "other")`, `LABELS: dict[str, str]`, `@dataclass Planned(kind, state, label, quote)`, `@dataclass Asset(page_id, job_id, kind, state, label, quote, text, first_draft, lines_changed)`, `create_assets(notion, db, job_id, planned) -> list[Asset]`, `load_assets(notion, db, job_id) -> list[Asset]`, `save_text(notion, asset, text) -> Asset`, `set_state(notion, asset, state) -> Asset`, `is_complete(assets) -> bool`, `find(assets, kind) -> Asset | None`
- Produces: `_long_rt(s, limit=_MAX_DESCRIPTION)` and `_MAX_ASSET = 40000`

- [ ] **Step 1: Create the test environment**

Run: `/opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/pip -q install -r requirements.txt`, add `.venv/` to `.gitignore`, create branch `feat/director-editor`.
Expected: `.venv/bin/python -m pytest -q` reports 119 passed.

- [ ] **Step 2: Write failing tests**

```python
def test_exact_quote(): assert appears_in("Record a Loom", "Please record a loom of your work.")
def test_curly_quotes_and_line_breaks():
    assert appears_in("We don't want your CV first", "We don’t want\nyour   CV first.")
def test_emoji_in_source(): assert appears_in("portfolio link 🎨 please", "Send a portfolio link 🎨 please!")
def test_invented_quote_rejected(): assert not appears_in("five years of Figma", "Send a portfolio.")
def test_too_short_rejected(): assert not appears_in("CV", "Send a CV.")
def test_empty_rejected(): assert not appears_in("", "text")

def test_create_assets_is_idempotent(): ...  # second call with same plan creates no new rows
def test_save_text_sets_first_draft_once():
    a = save_text(n, asset, "one"); a = save_text(n, a, "two")
    assert a.first_draft == "one" and a.text == "two" and a.state == "drafted"
def test_complete_ignores_untouched_optional():
    assert is_complete([_a("cv", "final"), _a("cover_letter", "optional"), _a("loom_script", "skipped")])
def test_needed_or_drafted_blocks_complete():
    assert not is_complete([_a("cv", "final"), _a("loom_script", "drafted")])
def test_asset_text_survives_past_6000(): ...  # 30,000 characters round-trip through save_text
def test_schema_has_new_fields():
    for p in ("Application asks", "Ad work", "Base score", "Director brief", "Form questions",
              "Brief message id", "Skip reason"): assert p in JOBS_SCHEMA
    assert "Briefed" in JOB_STATUSES and "Direction" in INBOX_SCHEMA and "Assets" in DATABASES
```

- [ ] **Step 2b: Run them**

Run: `.venv/bin/python -m pytest -q tests/test_quotes.py tests/test_assets.py tests/test_notion_foundation.py`
Expected: FAIL with import errors.

- [ ] **Step 3: Implement**

`appears_in`: lower-case, straighten curly quotes, collapse whitespace, then substring. Assets schema: `Name` title, `Job`, `Kind` select, `State` select (needed, optional, drafted, final, skipped), `Label`, `Quote`, `Text`, `First draft`, `Lines changed`. Jobs gains the fields in the test, with `Application asks` and `Form questions` holding JSON text. Usage `Agent` gains director and editor. Add `min_fit: 50` under `matcher` in settings.

- [ ] **Step 4: Run all tests**

Expected: all pass.

- [ ] **Step 5: Create the Assets database and commit the ids**

Run: `.venv/bin/python -c "from shared.notion import NotionClient as N; print(sorted(N().ensure_databases()))"`
Expected: list includes `Assets`. Vercel reads `config/notion_ids.json`, so it must include the new id.

- [ ] **Step 6: Commit**

`git commit -m "feat: quote check, asset store and new Notion fields"`

---

### Task 2: Matcher grading and asks

**Files:**
- Create: `agents/matcher/asks.py`
- Modify: `agents/matcher/score.py`, `agents/matcher/run.py`, `tests/test_matcher_logic.py`

**Interfaces:**
- Consumes: `appears_in`
- Produces: `ASK_ITEM_SCHEMA: dict`, `verified_asks(raw: list[dict], description: str) -> list[dict]` (items: kind, state, quote), `extract_asks(claude, title, description) -> list[dict]`
- `route(result, alert, ask, rules)` reads `result["fit"]` when present

- [ ] **Step 1: Write failing tests**

```python
def test_fit_below_50_never_sent():
    r = {**_j(40), "score": 95, "fit": 49}
    assert route(r, ALERT, ASK, {**RULES, "min_fit": 50}) == ("dropped", "fit below 50")
def test_fit_50_still_routes():
    assert route({**_j(50), "score": 95, "fit": 50}, ALERT, ASK, {**RULES, "min_fit": 50})[0] == "alert"
def test_score_no_longer_capped():
    assert score_of(_j(95, remote="berlin")) > 100          # replaces the == 100 assertion
def test_age_alone_is_not_ghost():
    assert assess_ghost("low", "2026-04-01", "2026-04-01", "2026-10-28")[0] == "low"
def test_repost_still_ghost():
    assert assess_ghost("low", "2026-10-01", "2026-10-25", "2026-10-28")[0] == "high"
def test_stated_years_still_penalised():
    assert score_of(_j(80, years=5)) == 80 - 20             # unchanged rule
def test_verified_asks_drop_invented_quote():
    raw = [{"kind": "loom_or_video", "state": "required", "quote": "Record a Loom"},
           {"kind": "cover_letter", "state": "required", "quote": "Attach a cover letter"}]
    assert [a["kind"] for a in verified_asks(raw, "Please record a Loom of your work.")] == ["loom_or_video"]
```

Replace `test_ghost_age_bumps_risk` and `test_ghost_moderate_age_is_medium_not_high` with the age-is-not-ghost test.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_matcher_logic.py`
Expected: FAIL on the new tests.

- [ ] **Step 3: Implement**

- `SCHEMA` gains `application_asks` (array of `ASK_ITEM_SCHEMA`: kind enum cv, cover_letter, portfolio, loom_or_video, case_study, form_questions, linkedin, other; state enum required, optional, not_wanted; quote) and `ad_work_quote` (string, the post's exact words, or '').
- `SYSTEM`: in the 70-100 line remove "AND level". Add: "Never lower the score because of a Senior, Lead or Principal title. Judge fit on the work the post describes. Years are handled afterwards." Tighten `field`: finance, banking, crypto, trading, data platforms and developer tools are 'other', even when they use AI.
- `route`: minimum-fit check runs first after German and location. `adjust`: remove the `min(100, ...)`.
- `assess_ghost`: remove both age bumps and their reasons. Keep the repost check.
- `run.py`: set `res["fit"] = fit` before `route`. Write `Application asks` (JSON of verified asks), `Ad work` (the quote only if `appears_in`), `Base score` (`adjust(res, cfg, 0)[0]`). Add a `--sent` flag that selects only jobs with a Telegram message id, for dry runs.

- [ ] **Step 4: Run tests**

Expected: all pass.

- [ ] **Step 5: Dry run on real jobs**

Run: `.venv/bin/python -m agents.matcher.run --sent --all --dry-run`
Expected: the three jobs with fit below 50 show "dropped". The finance job shows field other. Compare the asks against the posts by hand and report to Liam.

- [ ] **Step 6: Commit**

`git commit -m "feat: Matcher reads what a post asks for, minimum fit, title never costs points"`

---

### Task 3: Card, daily age refresh, skip reasons

**Files:**
- Create: `agents/matcher/refresh.py`, `tests/test_refresh.py`
- Modify: `agents/messenger/compose.py`, `agents/messenger/handle.py` (`_list_jobs`, `_skip`, callback), `.github/workflows/daily.yml`, `tests/test_messenger.py`, `tests/test_handle.py`

**Interfaces:**
- Consumes: `age_points`, `freshness`, `Base score`
- Produces: `refreshed(base: int, fit: int, posted_at: str, now_iso: str, rules: dict) -> tuple[int, str]`, `run(dry_run=False) -> dict`; `asks_line(page) -> str`; callback `why:<jid>:<code>`

- [ ] **Step 1: Write failing tests**

```python
def test_card_shows_fit_not_out_of_100():
    text, _ = job_card(_page(score=118, fit=72)); assert "Fit 72" in text and "/100" not in text
def test_card_lists_asks():
    assert "Loom (required)" in job_card(_page(asks=[{"kind":"loom_or_video","state":"required","quote":"x y z w"}]))[0]
def test_card_without_asks_says_so():
    assert "doesn't say what to send" in job_card(_page(asks=[]))[0]
def test_card_warns_ad_work():
    assert "Includes ad work" in job_card(_page(ad="design ad campaigns"))[0]
def test_card_shows_senior_label():
    assert "Senior title" in job_card(_page(flags=["senior"]))[0]
def test_card_button_says_brief_me():
    assert job_card(_page())[1][0][0][0] == "✅ Brief me"
def test_card_says_posted_days_ago(): ...   # "posted 12 days ago" present
def test_refresh_drops_freshness_over_time():
    assert refreshed(80, 70, "2026-10-01", "2026-10-02T00:00:00+00:00", RULES)[0] > \
           refreshed(80, 70, "2026-10-01", "2026-11-20T00:00:00+00:00", RULES)[0]
def test_refresh_gives_no_bonus_below_bonus_min_fit(): ...
def test_jobs_list_hides_fit_below_50_keeps_unscored_legacy(): ...
def test_skip_offers_optional_reasons_and_records_tap():
    # After Skip, buttons appear. why:<jid>:senior writes Skip reason "too senior".
    ...
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Skip reason codes: senior "too senior", field "wrong field", ad "ad work", location "location", other "other". `refresh.run` handles jobs in awaiting statuses that have a Base score, updates Score, Priority and the age part of Score breakdown, and sends nothing. Add the refresh step to `daily.yml` before reminders. Its existing pip line is enough.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: clearer job card, daily freshness, optional skip reasons"`

---

### Task 4: Researcher reads the company's site

**Files:**
- Modify: `agents/researcher/run.py`, `.github/workflows/hourly.yml`, `tests/test_researcher.py`

**Interfaces:**
- Produces: `website_url(job_page_html: str, careers_url: str) -> str`, `run(limit=None, dry_run=False, job_id: str | None = None) -> dict`

- [ ] **Step 1: Write failing tests**

```python
def test_website_from_ashby_page_data():
    html = '<script>window.__appData = {"organization":{"publicWebsite":"https://acme.com/"}};</script>'
    assert website_url(html, "") == "https://acme.com/"
def test_website_from_careers_url_root():
    assert website_url("", "https://acme.com/careers/open") == "https://acme.com/"
def test_hiring_tool_host_is_not_a_company_site():
    assert website_url("", "https://jobs.ashbyhq.com/acme") == ""
def test_notes_no_longer_have_how_you_fit():
    assert "How you fit" not in _notes_text(_res())
def test_notes_say_when_site_was_not_read(): ...
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Remove `how_liam_fits` from schema and notes. Write notes with `_long_rt`. Keep the raw HTML from the job page for `website_url`, then fetch the site through `PoliteClient` (a robots refusal counts as "not read"). Pass up to 6,000 characters of post and 4,000 of site text. With `job_id`, research only that job. Remove the "Research" step from `hourly.yml`, because the Director workflow now runs it.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Researcher reads the company's own site, facts only"`

---

### Task 5: Director brief and asset plan

**Files:**
- Create: `agents/director/__init__.py`, `agents/director/forms.py`, `agents/director/brief.py`, `tests/test_director.py`

**Interfaces:**
- Consumes: `appears_in`, `Planned`, `load_mytone`, `load_base_cv`
- Produces: `parse_greenhouse(source: str, url: str) -> tuple[str, str] | None`, `greenhouse_questions(client, slug, job_id) -> list[dict] | None` (items: label, required, type), `plan_assets(asks: list[dict], form: list[dict] | None) -> list[Planned]`, `write_brief(claude, *, title, company, post, research, cv, mytone) -> dict`, `verified_brief(raw, cv, mytone) -> dict`, `brief_message(brief, planned, form_checked: bool) -> tuple[str, list]`

- [ ] **Step 1: Write failing tests**

```python
def test_form_skips_identity_fields(): ...   # First Name, Last Name, Email, Phone removed
def test_closed_post_returns_none(): ...     # HTTP 404 -> None, no exception
def test_plan_loom_needed_cv_optional_not_listed_when_not_wanted():
    p = plan_assets([{"kind":"loom_or_video","state":"required","quote":"q"},
                     {"kind":"cv","state":"not_wanted","quote":"q"}], None)
    assert [(a.kind, a.state) for a in p] == [("loom_script", "needed")]
def test_plan_form_overrides_post_for_required_and_optional(): ...
def test_plan_custom_questions_make_form_answers(): ...
def test_plan_nothing_stated_offers_cv_and_letter_as_optional():
    assert {(a.kind, a.state) for a in plan_assets([], None)} == {("cv","optional"), ("cover_letter","optional")}
def test_why_point_with_failed_quote_is_dropped():
    b = verified_brief({**BRIEF, "why_you": [{"point":"a","project":"X","source_quote":"built a tool for bookers"},
                                              {"point":"b","project":"Y","source_quote":"invented"}]},
                       cv="I built a tool for bookers.", mytone="")
    assert [p["point"] for p in b["why_you"]] == ["a"]
def test_message_separates_they_say_and_my_read(): ...
def test_message_has_start_and_skip_for_each_drafted_asset(): ...  # callback start:<jid>:cv, skipasset:<jid>:cv
def test_message_asks_to_paste_when_form_not_checked(): ...
def test_message_fits_one_telegram_message(): ...               # under 4096
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Brief schema: `after_they_say`, `after_my_read`, `candidate_they_say`, `candidate_my_read`, `why_you` (point, project, source_quote), `weak_spots`. "They say" fields quote the post, and Sonnet is told to leave "my read" empty rather than guess. Map asks to kinds: loom_or_video to loom_script, form_questions to form_answers, others by name. Portfolio, LinkedIn and case study are checklist items with no start button. Greenhouse `Resume/CV` and `Cover Letter` fields set those assets' state. Callback data must stay under Telegram's 64 bytes.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Director brief with checked quotes and asset plan"`

---

### Task 6: Brief me, end to end

**Files:**
- Create: `agents/director/run.py`, `.github/workflows/director.yml`, `tests/test_director_run.py`
- Modify: `agents/messenger/handle.py`, `tests/test_handle.py`

**Interfaces:**
- Consumes: Task 4 `run(job_id=...)`, Task 5 functions, `create_assets`, `extract_asks`
- Produces: `run(job_id: str) -> dict`; `handle.dispatch(workflow: str, job_id: str | None) -> str | None`; Handler gains `start_director` and `start_editor` injectables (replacing `start`)

- [ ] **Step 1: Write failing tests**

```python
def test_brief_me_tap_approves_and_starts_director():   # label "director-started", started == [JID]
def test_old_apply_and_yes_buttons_still_work():
def test_director_failure_tells_liam_and_offers_retry():
    # Researcher raises -> Telegram message has callback brief:<jid>; job stays Approved; exception re-raised
def test_director_extracts_asks_for_older_jobs():       # empty "Application asks" -> extract_asks called once
def test_usage_limit_says_so_on_telegram():             # over_limit True -> message, nothing else runs
def test_run_saves_brief_sets_briefed_and_message_id():
def test_rerun_does_not_duplicate_assets():
```

Rename `writer-started` and `writer-failed` labels to `director-started` and `director-failed` in the existing tests.

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

`run` order: usage check, Researcher for this job, asks (stored or `extract_asks`), form lookup, brief with Sonnet, `verified_brief`, save, `create_assets`, send, set Status to Briefed. Wrap the body in try/except: on failure send the retry button, then re-raise so the workflow goes red. `director.yml` copies `writer.yml` setup without Playwright and runs `python -m agents.director.run --job "$JOB"`. `_decide` still moves the job to Approved. `_help` offers Brief me for Approved jobs with no brief.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Brief me starts the Researcher and Director"`

---

### Task 7: Rename the Writer to the Editor

**Files:**
- Rename: `agents/writer/` to `agents/editor/`, `tests/test_writer*.py` to `tests/test_editor*.py`
- Modify: every import, `scripts/setup_never_again.py`, `WriterContext` to `EditorContext`, `.github/workflows/writer.yml` to `editor.yml`

**Interfaces:**
- Produces: `agents.editor.*` with the same functions as before; `EditorContext` gains `brief: str`

- [ ] **Step 1: Move and rename with `git mv` and a project-wide replace**

Keep the Notion names `Writer references` and the historic Usage value `writer`.

- [ ] **Step 2: Run all tests**

Expected: the same count as before Task 7, all pass.

- [ ] **Step 3: Pass the full post and the brief into the prompt**

Test: `test_system_prompt_has_full_post_and_brief`, with a 5,000-character description whose last word is present, and the brief text present. Remove `[:3000]`. Add a `DIRECTOR'S BRIEF` block labelled "sets the angle, is not a source of facts". Remove the "ask whether he wants a cover letter" line. `build_context` reads `Director brief`.

- [ ] **Step 4: Commit** `git commit -m "refactor: the Writer becomes the Editor"`

---

### Task 8: Draft and deliver each asset

**Files:**
- Create: `agents/editor/drafts.py`, `agents/editor/deliver.py`, `tests/test_editor_drafts.py`
- Modify: `agents/editor/converse.py`

**Interfaces:**
- Consumes: `enforce_voice`, `lint`, `CV_FORMAT`, `references`, `generate_cv_pdf`, `generate_cover_letter_pdf`, `Asset`
- Produces: `draft(claude, ctx, asset: Asset, history: list[dict]) -> str`, `revise(claude, ctx, asset: Asset, instruction: str) -> tuple[str, str]` (new text, note), `deliver(tg, chat, ctx, asset: Asset) -> None`, `split_message(text: str, limit: int = 4000) -> list[str]`

- [ ] **Step 1: Write failing tests**

```python
def test_each_kind_goes_through_voice_check(): ...       # enforce_voice called for cv, cover_letter, form_answers, loom_script
def test_form_answers_are_one_message_each(): ...         # 3 questions -> 3 send_message calls, answers in <code>
def test_cv_and_letter_arrive_as_pdf(): ...
def test_loom_script_arrives_as_text(): ...
def test_long_text_splits_on_paragraphs_and_loses_nothing():
    text = "\n\n".join("x" * 1500 for _ in range(6))
    parts = split_message(text)
    assert all(len(p) <= 4000 for p in parts) and "".join(parts).replace("\n", "") == text.replace("\n", "")
def test_revise_touches_only_that_asset(): ...           # prompt contains only the asked asset
def test_revise_keeps_liams_exact_words(): ...           # prompt rule present; no voice loop runs
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Split `finalize` into per-kind prompts. Keep the voice plan for the letter. Form answers are stored as JSON `[{"question","answer"}]` and limited to the guide's 80 to 150 words per box. The Loom script uses the post's own requested sections and `[CAPS]` screen cues. It may only describe real projects from the sources. Remove the old `finalize` and `revise`.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Editor drafts and delivers one asset at a time"`

---

### Task 9: Understanding plain requests

**Files:**
- Create: `agents/editor/turn.py`, `agents/editor/act.py`, `tests/test_editor_turn.py`
- Modify: `agents/editor/converse.py` (`build_system` capabilities text)

**Interfaces:**
- Consumes: Task 8, `set_state`, `save_text`, `learn.diff`, `learn.save_reference`
- Produces: `TURN_SCHEMA`, `turn(claude, ctx, history, assets) -> dict` (`reply`, `actions`), `@dataclass Done(lines: list[str], dropped: bool)`, `apply_actions(env, actions: list[dict], message: str) -> Done`, where `env` is a dataclass holding `notion, tg, chat, claude, ctx, assets, ids, history`

Action types: `draft_asset`, `revise_asset`, `skip_asset`, `mark_final`, `drop_application`, `list_jobs`, `save_correction`. Fields: `type`, `kind`, `instruction`, `correction_form`, `old_line`, `new_line`, `liams_words`, `never_line`.

- [ ] **Step 1: Write failing tests**

```python
def test_mixed_message_runs_every_action_in_order():
    # save_correction, then drop_application -> correction saved first, job Skipped
def test_full_stop_done_style_message_drafts():         # actions from "Done." reach draft_asset
def test_skip_one_asset_keeps_the_application():        # state skipped, Status unchanged
def test_revise_missing_asset_is_reported_plainly():
    d = apply_actions(env, [{"type":"revise_asset","kind":"cover_letter","instruction":"shorter"}], "shorter")
    assert "isn't drafted yet" in d.lines[0]
def test_action_failure_is_reported_not_hidden():       # draft raises -> line says it failed
def test_drop_sets_skipped_and_offers_bring_back():     # callback restore:<jid>
def test_list_jobs_sends_the_real_list():
def test_mark_final_counts_lines_and_saves_reference_for_cv_and_letter_only():
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

The system prompt tells the Editor to phrase actions as requested and to let code report the outcome. `Done.lines` is sent after the model's reply, so what Liam reads is what happened. `build_system` lists the real abilities. Job filters stay in `settings.yaml`, and the Editor says so if asked. `save_correction` is a no-op stub here, filled in by Task 12.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Editor acts on plain requests"`

---

### Task 10: The session that closes and resumes

**Files:**
- Modify: `agents/editor/session.py`, `.github/workflows/editor.yml`, `tests/test_editor_learn.py` (retire tap-flow tests), `agents/editor/learn.py`

**Interfaces:**
- Consumes: Task 9, `Inbox`
- Produces: `run(job_id: str, idle_minutes: float = 15.0, max_minutes: float = 80.0) -> dict`, `restore_history(notion, inbox_db, job_id) -> list[dict]`, `log_out(notion, inbox_db, job_id, text) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_message_that_started_session_is_answered_first():   # unread row exists before run -> answered, not discarded
def test_both_sides_are_logged_and_history_restores():
def test_window_rolls_forward_with_each_message():            # Session until moves later after each message
def test_closes_after_idle_and_clears_window():               # no messages -> Session until None, one "text me to pick up" message
def test_final_check_catches_a_last_second_message():         # message arrives during close -> answered
def test_resume_keeps_drafts():                               # second run sees the first run's Asset text
def test_crash_leaves_unread_messages_for_next_run():         # exception in turn -> row stays unread
def test_all_assets_done_sends_checklist():                   # is_complete -> checklist message
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Remove `inbox.drain()`, the phase machine, `DONE_WORDS` and the `first`/`drafts` variables. Mark a message read only after its actions finish. Status becomes Drafting at start and Ready to send when complete. Remove `candidates`, `parse_pick` and `confirm_message` from `learn.py`. `editor.yml` runs `python -m agents.editor.session --job "$JOB"` with `timeout-minutes: 90` and removes the research step. Log usage as `editor`.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Editor sessions save everything, close when idle and resume"`

---

### Task 11: Starting the Editor by text

**Files:**
- Modify: `agents/messenger/handle.py`, `tests/test_handle.py`

**Interfaces:**
- Consumes: `dispatch`, `Session until`, `Inbox`, `Brief message id`
- Produces: labels `editor-started`, `editor-failed`, `editor-choose`; callbacks `start:<jid>:<kind>`, `skipasset:<jid>:<kind>`, `pick:<jid>`, `restore:<jid>`, `resume:<jid>`

- [ ] **Step 1: Write failing tests**

```python
def test_text_starts_editor_for_the_one_waiting_job():    # label editor-started; text saved unread; window ~5 min set
def test_second_text_during_boot_starts_nothing():        # live window -> label inbox; started count stays 1; order kept
def test_reply_to_a_brief_picks_that_job():
def test_several_waiting_gives_buttons_and_keeps_text():  # label editor-choose; row saved with empty Job; pick: fills Job, starts
def test_no_job_waiting_gives_help():
def test_failed_dispatch_clears_window_keeps_message_and_says_why():
def test_expired_window_starts_a_new_run():               # crashed session: Session until past -> editor-started
def test_start_button_saves_request_and_starts():         # start:<jid>:cv -> inbox row "Start with the CV"
def test_skip_button_needs_no_session():                  # Asset state skipped, no dispatch
def test_restore_returns_a_dropped_job_to_briefed():
def test_jobs_command_still_answered_mid_session():
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Order inside `_message`: `jobs` command, card decisions, live session (save to Inbox), then the new start logic, then help. Waiting jobs are Status Briefed or Drafting. Save the message to the Inbox before dispatching. Starting reply: "Starting the Editor. First reply in about a minute and a half."

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: the Editor starts when Liam texts"`

---

### Task 12: Silent corrections to mytone

**Files:**
- Create: `agents/editor/corrections.py`, `tests/test_corrections.py`
- Modify: `agents/editor/act.py`, `agents/editor/mytone.py`

**Interfaces:**
- Consumes: `appears_in`, `learn.add_never_again`, `load_mytone`
- Produces: `entry(action: dict, message: str, asset_before: str, tag: str) -> str | None`, `save(notion, action, message, asset_before, tag) -> bool`

- [ ] **Step 1: Write failing tests**

```python
def test_wording_entry_stores_old_and_his_new_line():
    e = entry({"correction_form":"wording","old_line":"I invented it.","new_line":"I built it."},
              'Change it to "I built it."', "I invented it. More.", "Acme, CV, 2026-11-09")
    assert '"I invented it."' in e and '"I built it."' in e and "Acme, CV" in e
def test_instruction_stores_his_exact_words(): ...
def test_fact_or_rule_stores_his_exact_words(): ...
def test_model_paraphrase_is_not_saved():
    assert entry({"correction_form":"fact_or_rule","liams_words":"He prefers short lines"},
                 "keep it short", "", "t") is None
def test_old_line_must_exist_in_the_asset(): ...
def test_save_sends_no_telegram_message(): ...
def test_failed_save_is_reported_once(): ...              # the one case that messages Liam
def test_heading_added_only_once(): ...
def test_never_line_goes_to_never_again_only_when_said(): ...
def test_mytone_reloaded_after_save(): ...                # next prompt contains the new fact
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Append under a "Corrections" heading in the mytone page, one bullet per entry. Never write a reason. `act.py` runs corrections after the asset change succeeds and updates `ctx.mytone`.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: corrections go silently into mytone"`

---

### Task 13: Applied, reminders and docs

**Files:**
- Modify: `agents/messenger/handle.py`, `agents/editor/session.py`, `agents/messenger/reminders.py`, `config/settings.yaml`, `docs/BUILD_BRIEF.md`, `CLAUDE.md`, `tests/test_handle.py`, `tests/test_messenger.py`

**Interfaces:**
- Produces: callback `applied:<jid>`, label `applied`

- [ ] **Step 1: Write failing tests**

```python
def test_applied_sets_status_date_and_manual_method():
def test_applied_works_without_a_session():
def test_applied_twice_is_harmless():
def test_reminder_includes_briefed_jobs():
def test_checklist_lists_finals_skips_and_link():
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Add `Briefed` to `awaiting_statuses`. Reminder text says "reply to a job's message or text me" and shows Fit, not "/100". In BUILD_BRIEF §3, §4, §11, §12 and §16 and in CLAUDE.md: Director and Editor replace the Writer, the Applier is removed, and the chat starts when Liam texts.

- [ ] **Step 4: Run tests**, expected all pass.

- [ ] **Step 5: Commit** `git commit -m "feat: Applied button, Briefed reminders, docs updated"`

---

### Task 14: One real run (needs Liam)

No code unless the run finds bugs. GitHub can only start workflows that are on `main`, and Vercel deploys from `main`, so this needs Liam's OK to merge first.

- [ ] **Step 1: Ask Liam to approve merging to `main` and pushing.**
- [ ] **Step 2: Confirm the webhook is alive.** Run: `.venv/bin/python scripts/set_telegram_webhook.py --status`. Expected: the Vercel URL with no errors.
- [ ] **Step 3: Liam taps Brief me on the demo post.** Expected: a brief arrives, every "why" point is true by his read, and the asset list matches the post.
- [ ] **Step 4: Liam texts to start.** Expected: first reply in about a minute and a half.
- [ ] **Step 5: Liam tests plain requests**, including a mixed message, a skip, a change to one asset and a stated fact. Expected: each one happens, and the mytone Corrections section updates with no message.
- [ ] **Step 6: Leave the chat idle for 15 minutes, then text again.** Expected: it resumes with drafts intact.
- [ ] **Step 7: Liam marks assets final and taps Applied.** Expected: Status is Applied in Notion.
- [ ] **Step 8: Record real timings and numbers for the Loom script rewrite**, which is separate work.
