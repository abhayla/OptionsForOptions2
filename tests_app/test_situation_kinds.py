"""GC-IC1 step 6b (REQ-159 AC-5, ADR-240 (1)): S-03, S-04, S-05 are guidance, from ONE server constant; the playbook
reply carries each situation's kind; no body key is stored or needed. Pure: no DB."""
from __future__ import annotations

import copy
import json
import pathlib

from ofo.adjustment import playbook_eval as pe
from ofo_app.routes.playbooks import situation_kinds

SEED = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo" / "adjustment" / "system_playbooks.json"


def _ic() -> dict:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
    return copy.deepcopy(next(r["body"] for r in rows if r["strategy_type"] == "ic"))


def test_the_constant_names_exactly_s03_s04_s05() -> None:
    assert pe.GUIDANCE_SITUATIONS == ("S-03", "S-04", "S-05")


def test_iron_condor_reply_marks_exactly_the_guidance_situations() -> None:
    kinds = situation_kinds(_ic())
    assert [k["id"] for k in kinds] == [s["id"] for s in _ic()["situations"]]
    assert {k["id"] for k in kinds if k["kind"] == "guidance"} == {"S-03", "S-04", "S-05"}
    assert all(k["kind"] == "rule" and k["label"] is None for k in kinds if k["id"] not in pe.GUIDANCE_SITUATIONS)
    assert all(k["label"] == "Guidance" for k in kinds if k["kind"] == "guidance")


def test_no_kind_key_is_added_to_a_body_and_odd_bodies_read_as_none() -> None:
    body = _ic()
    before = copy.deepcopy(body)
    situation_kinds(body)
    assert body == before
    assert all("kind" not in s for s in body["situations"])
    assert situation_kinds({}) == []
    assert situation_kinds({"situations": "x"}) == []
    assert situation_kinds({"situations": [{"name": "no id"}, 5]}) == []
