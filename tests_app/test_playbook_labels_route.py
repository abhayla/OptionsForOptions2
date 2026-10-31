"""GC-ADJ2 step 3 round 2: GET /api/playbooks/labels (REQ-159 AC-4/AC-5, REQ-160 AC-1). Every word the editor shows
that a playbook body does not carry comes from this answer, i.e. from the catalogue; the browser types none of them.
The coverage checks read the shipped system playbooks (backend/ofo/adjustment/system_playbooks.json): every approach id,
day rule kind and action they use has a label, so no editor row can fall back to a raw id or number.
"""
from __future__ import annotations

import json
import pathlib

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from ofo.errors.explanations import ADJUSTMENT_APPROACH_LABEL_TEXT, PLAYBOOK_APPROACH_LABEL_TEXT
from ofo_app.routes import playbooks

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYSTEM = json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text(encoding="utf-8"))
OK = 200


async def _labels() -> dict:
    app = FastAPI()
    app.include_router(playbooks.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/playbooks/labels")
    assert r.status_code == OK, r.text
    return r.json()


def _bodies() -> list[dict]:
    return SYSTEM["playbooks"]


async def test_labels_answer_names_actions_kinds_and_summary_sentences():
    out = await _labels()
    names = {x["key"]: x["text"] for x in out["approaches"]}
    assert names["A-36"] == "No change"  # the compare's table
    assert names["A-01"] == "Roll the untested spread toward spot"
    assert names["A-09"] == "Add wings (cap the loss)"
    actions = {x["key"]: x["text"] for x in out["day_actions"]}
    assert actions["0"] == "Run the carry check (overnight margin, gap loss)"
    assert actions["4"] == "Tighten every trigger by this %"
    kinds = {x["key"]: x["text"] for x in out["day_kinds"]}
    assert kinds["beforeWeekend"] == "The last session before a weekend"
    summary = {x["key"]: x["text"] for x in out["summary"]}
    assert summary["type_line"] == "{type}, {kind} expiry. Stages: {stages}."
    assert summary["plan"] == ("Plan: target {target}% of max profit, stop at {stop}% of max loss, at most {max} "
                               "adjustments.")


def test_the_two_approach_tables_are_disjoint():
    """One home per approach name: the editor's table never re-names an id the compare already names."""
    assert set(ADJUSTMENT_APPROACH_LABEL_TEXT).isdisjoint(PLAYBOOK_APPROACH_LABEL_TEXT)


async def test_every_id_kind_and_action_in_a_system_playbook_has_a_label():
    out = await _labels()
    names = {x["key"] for x in out["approaches"]}
    kinds = {x["key"] for x in out["day_kinds"]}
    actions = {x["key"] for x in out["day_actions"]}
    seen_ids, seen_kinds, seen_actions = set(), set(), set()
    for entry in _bodies():
        body = entry.get("body", entry)
        a = body["approaches"]
        seen_ids |= set(a["applicable"]) | set(a["off_in_playbook"]) | {g["id"] for g in a["greyed"]}
        seen_kinds |= {r["when"] for r in body["day_rules"]}
        seen_actions |= {str(r["action"]) for r in body["day_rules"]}
    assert seen_ids and seen_ids <= names, sorted(seen_ids - names)
    assert seen_kinds <= kinds, sorted(seen_kinds - kinds)
    assert seen_actions <= actions, sorted(seen_actions - actions)
