"""GC-MU A4 (ADR-230 (4)): two stop values and no combining rule mean "whichever comes first"; the plan words show both.
The server's ``_words`` reads the same expectation table as the browser's ``planLine``
(frontend/tests/two-stops-words.test.js)."""
from __future__ import annotations

import json
import pathlib

import pytest
from ofo_app.routes.adjustment_plan import _words

CASES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "stop_words_cases.json"
TABLE = json.loads(CASES.read_text("utf-8"))


@pytest.mark.parametrize("case", TABLE["cases"], ids=[c["name"] for c in TABLE["cases"]])
def test_server_stop_words(case):
    _, stop = _words(case["guards"])
    expected = None if case["expect"] is None else TABLE[case["expect"]]
    assert stop == expected
