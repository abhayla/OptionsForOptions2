"""GC-IC1 step 10 fix (REQ-159 AC-4): the labels answer lists the acting day-rule pairs (the one table) and the
not-checked reason; the tighten rule acts only on expiry + action 4. No DB used (DB run owed: the tests_app
autouse fixtures were not run here)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.adjustment import playbook_eval as pe
from ofo_app.adjustment_check import _tighten
from ofo_app.routes.playbooks import _labels_body


def test_the_labels_answer_carries_the_acting_list_and_the_reason():
    body = _labels_body()
    assert {(p["when"], p["action"]) for p in body["day_acting"]} == pe.ACTING_DAY_PAIRS
    assert "not checked" in body["day_not_checked"].what_happened.lower()


def test_tighten_acts_only_on_expiry_action_4():
    today = datetime.date(2026, 11, 5)
    base = {"on": True, "when": "expiry", "at": "13:00", "percent": "20"}
    assert _tighten({"day_rules": [{**base, "action": 4}]}, today, today, "13:00") == D("20")
    assert _tighten({"day_rules": [{**base, "action": 3}]}, today, today, "13:00") is None
