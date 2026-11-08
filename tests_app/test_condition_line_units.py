"""Class "condition line refuses a trigger's value" (a clock-time trigger answered 500 on every expiry day from 14:30).

RCA: ``condition_line`` retried a refused render with the same value, so a value the slot refuses ("15:00" from T-10b)
raised again and the check route answered 500. Class: every playbook trigger whose value or threshold is a clock time
(unit "time": T-10b today). Detection: every trigger of the scenario library's trigger table renders a line with a
representative value of its unit, so a new unit the slots refuse fails CI, not production."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from ofo_app.adjustment_check import condition_line
from ofo_app.playbook_store import Suggestion

PLAYBOOKS = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "adjust_scenarios"
                        / "_playbooks.json").read_text(encoding="utf-8"))
#: a representative shown value per unit (the check route shows 4 dp numbers, a clock trigger HH:MM)
SAMPLE = {"time": ("15:00", "14:30")}


def test_t10b_clock_time_renders_its_line():
    t = PLAYBOOKS["triggers"]["T-10b"]
    line = condition_line("T-10b", t["label"], t["unit"], "15:00", "14:30")
    assert str(line) == "Clock time reached (checked in this stage): 15:00 (rule 14:30)"


@pytest.mark.parametrize("tid", sorted(PLAYBOOKS["triggers"]))
def test_every_trigger_of_the_table_renders_a_line_with_its_value(tid):
    t = PLAYBOOKS["triggers"][tid]
    value, threshold = SAMPLE.get(t["unit"], ("0.5000", "1.0000"))
    text = str(condition_line(tid, t["label"], t["unit"], value, threshold))
    assert value in text and threshold in text, (tid, t["unit"], text)


@pytest.mark.parametrize("value", ["@@ not a value", "15:00:00", "", "x" * 200])
def test_an_unrenderable_value_still_returns_the_trigger_id_line(value):
    """Last resort (fail visible): the trigger id alone, never an exception (a 500)."""
    line = condition_line("T-10b", "Clock time reached", "time", value, "14:30")
    assert str(line) == "T-10b"


@pytest.mark.parametrize(("kind", "strike", "points", "text"), [
    ("CE", "23500", "100", "spot is beyond the sold 23,500 CE by 100 points"),
    ("PE", "22000", "12.35", "spot is beyond the sold 22,000 PE by 12.35 points")])
def test_t01_beyond_the_short_names_it_never_zero_percent(kind, strike, points, text):
    """ADR-268 (2): a breached short's T-01 line says how far past the sold strike spot is, never "0 %"."""
    t = PLAYBOOKS["triggers"]["T-01"]
    line = str(condition_line("T-01", t["label"], t["unit"], "0.0000", "0.3000",
                              (kind, Decimal(strike), Decimal(points))))
    assert line == f"{t['label']}: {text}", line


def test_t01_beyond_marker_read_back_from_the_record():
    def rec(first):
        return Suggestion(1, 1, "T-01", "T-01", None, Decimal(0), Decimal("0.3"), None, "open", None, [first])
    assert rec({"beyond": {"kind": "CE", "strike": "23500", "points": "100"}}).beyond == (
        "CE", Decimal("23500"), Decimal("100"))
    assert rec({}).beyond is None  # an older record: the plain line
    assert rec({"beyond": {"kind": "XX", "strike": "1", "points": "1"}}).beyond is None  # fail visible
    assert rec({"beyond": {"kind": "CE", "strike": "bad", "points": "1"}}).beyond is None
