"""Class "condition line refuses a trigger's value" (a clock-time trigger answered 500 on every expiry day from 14:30).

RCA: ``condition_line`` retried a refused render with the same value, so a value the slot refuses ("15:00" from T-10b)
raised again and the check route answered 500. Class: every playbook trigger whose value or threshold is a clock time
(unit "time": T-10b today). Detection: every trigger of the scenario library's trigger table renders a line with a
representative value of its unit, so a new unit the slots refuse fails CI, not production."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ofo_app.adjustment_check import condition_line

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
