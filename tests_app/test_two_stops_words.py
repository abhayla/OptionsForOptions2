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
THREE = "50 % of max loss, 2x the credit received or 20 % of margin, whichever comes first"
SERVER = {"either": THREE, "loss": TWO, "margin": THREE}


@pytest.mark.parametrize("case", TABLE["cases"], ids=[c["name"] for c in TABLE["cases"]])
def test_server_stop_words(case):
    _, stop = _words({"guards": case["guards"]}, case["guards"])
    if case["name"].startswith("both values, a DIFFERENT"):  # the rule text no longer narrows the words (ADR-247)
        assert stop == THREE
        return
    assert stop == (None if case["expect"] is None else SERVER[case["expect"]])
