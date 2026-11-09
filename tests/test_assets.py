"""The asset store: one Notion row per job and asset (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import assets as store
from shared.assets import Asset, Planned, create_assets, find, is_complete, load_assets, save_text, set_state
from shared.notion.schema import DATABASES, INBOX_SCHEMA, JOB_STATUSES, JOBS_SCHEMA


class FakeNotion:
    """Stores rows the way Notion hands them back."""

    def __init__(self):
        self.rows = {}
        self.created = 0

    @staticmethod
    def _read(props):
        out = {}
        for name, val in props.items():
            if "title" in val:
                out[name] = {"type": "title", "title": [{"plain_text": t["text"]["content"]} for t in val["title"]]}
            elif "rich_text" in val:
                out[name] = {"type": "rich_text",
                             "rich_text": [{"plain_text": t["text"]["content"]} for t in val["rich_text"]]}
            elif "select" in val:
                out[name] = {"type": "select", "select": val["select"]}
            elif "number" in val:
                out[name] = {"type": "number", "number": val["number"]}
        return out

    def create_page(self, db, props):
        self.created += 1
        pid = f"row{self.created}"
        self.rows[pid] = {"id": pid, "properties": self._read(props)}
        return self.rows[pid]

    def update_page(self, page_id, props):
        self.rows[page_id]["properties"].update(self._read(props))

    def query_database(self, db, filter=None):
        want = filter["rich_text"]["equals"]
        return [r for r in self.rows.values()
                if "".join(t["plain_text"] for t in r["properties"]["Job"]["rich_text"]) == want]


PLAN = [Planned("cv", "needed", "CV", "Attach your CV"), Planned("loom_script", "optional", "Loom script", "")]


def _a(kind, state):
    return Asset("p", "j", kind, state, kind, "", "", "", None)


def test_create_assets_makes_one_row_each():
    n = FakeNotion()
    made = create_assets(n, "db", "job1", PLAN)
    assert [(a.kind, a.state, a.quote) for a in made] == [("cv", "needed", "Attach your CV"),
                                                         ("loom_script", "optional", "")]


def test_create_assets_is_idempotent():
    n = FakeNotion()
    create_assets(n, "db", "job1", PLAN)
    again = create_assets(n, "db", "job1", PLAN)
    assert n.created == 2 and len(again) == 2


def test_rows_belong_to_their_job():
    n = FakeNotion()
    create_assets(n, "db", "job1", PLAN)
    assert load_assets(n, "db", "job2") == []


def test_save_text_sets_first_draft_once():
    n = FakeNotion()
    asset = create_assets(n, "db", "job1", PLAN)[0]
    a = save_text(n, asset, "one")
    a = save_text(n, a, "two")
    assert a.first_draft == "one" and a.text == "two" and a.state == "drafted"
    reloaded = find(load_assets(n, "db", "job1"), "cv")
    assert reloaded.first_draft == "one" and reloaded.text == "two"


def test_asset_text_survives_past_6000():
    n = FakeNotion()
    asset = create_assets(n, "db", "job1", PLAN)[0]
    save_text(n, asset, "x" * 30000)
    assert len(find(load_assets(n, "db", "job1"), "cv").text) == 30000


def test_set_state_persists():
    n = FakeNotion()
    asset = create_assets(n, "db", "job1", PLAN)[0]
    assert set_state(n, asset, "skipped").state == "skipped"
    assert find(load_assets(n, "db", "job1"), "cv").state == "skipped"


def test_complete_ignores_untouched_optional():
    assert is_complete([_a("cv", "final"), _a("cover_letter", "optional"), _a("loom_script", "skipped")])


def test_needed_or_drafted_blocks_complete():
    assert not is_complete([_a("cv", "final"), _a("loom_script", "drafted")])
    assert not is_complete([_a("cv", "needed")])


def test_nothing_chosen_is_not_complete():
    assert not is_complete([])
    assert not is_complete([_a("cv", "optional")])


def test_checklist_items_never_block_complete():
    assert is_complete([_a("cv", "final"), _a("portfolio", "needed")])


def test_every_kind_has_a_label():
    for kind in store.DRAFTED_KINDS + store.CHECKLIST_KINDS:
        assert store.LABELS[kind]


def test_schema_has_new_fields():
    for p in ("Application asks", "Ad work", "Base score", "Director brief", "Form questions",
              "Brief message id", "Skip reason"):
        assert p in JOBS_SCHEMA
    assert "Briefed" in JOB_STATUSES and "Direction" in INBOX_SCHEMA and "Assets" in DATABASES
