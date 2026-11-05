"""GC-MU A4 (ADR-230 (4), ADR-247): the plan words show every active stop, "whichever comes first".
The server's ``_words`` reads the same case table as the browser's ``planLine``
(frontend/tests/two-stops-words.test.js)."""
from __future__ import annotations

import json
import pathlib

import pytest
from ofo_app.routes.adjustment_plan import _words

CASES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "stop_words_cases.json"
TABLE = json.loads(CASES.read_text("utf-8"))


# ADR-247: the server words the ACTIVE stops (max loss and the credit multiple always; margin only when the body
# states it), not only the guards present; the shared table's "expect" keys still drive the browser's editor line.
TWO = "50 % of max loss or 2x the credit received, whichever comes first"
THREE = "50 % of max loss, 2x the credit received or 4 % of margin, whichever comes first"


def _ic(t06: bool, t16: bool, guards: dict) -> dict:
    """An iron condor body whose stops are its triggers (ADR-252): T-06 50 / 50 / 40, T-16 4 / 4 / 3, each on/off."""
    stages = {"weekly": [{"name": "Early", "from": 5, "to": None}, {"name": "Middle", "from": 2, "to": 4},
                          {"name": "Last", "from": 0, "to": 1}]}
    return {"strategy_type": "ic", "stages": stages, "guards": guards, "triggers": {
        "T-06": {"on": t06, "weekly": ["50", "50", "40"]}, "T-16": {"on": t16, "weekly": ["4", "4", "3"]}}}


@pytest.mark.parametrize("case", TABLE["cases"], ids=[c["name"] for c in TABLE["cases"]])
def test_server_stop_words_ignore_the_guard_keys(case):
    """ADR-252: the words come from the triggers; whatever stop guard keys the case table holds, the words of a
    new iron condor plan (T-06 on, T-16 off) are the same two stops."""
    _, stop = _words(_ic(True, False, dict(case["guards"])), case["guards"], False)
    assert stop == TWO


@pytest.mark.parametrize(("t06", "t16", "before", "want"), [
    (True, False, False, TWO),
    (True, True, False, THREE),
    (False, False, False, "2x the credit received"),
    (True, True, True, "50 % of max loss or 4 % of margin, whichever comes first"),  # ADR-250: no 2x line
    (False, False, True, None),
])
def test_server_stop_words_follow_the_trigger_switches(t06, t16, before, want):
    _, stop = _words(_ic(t06, t16, {}), {}, before)
    assert stop == want
