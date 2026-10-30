"""GC-ADJ1 step 1b (W-196): ONE reader of OFO_SCENARIO (finding setting-read-from-two-sources): only
ofo_app.scenario_mode reads it; config.Settings declares it only to refuse it."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_one_reader_of_the_variable():
    """Only scenario_mode reads OFO_SCENARIO (config declares it only to refuse it)."""
    readers = []
    for path in (ROOT / "backend").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"""environ(\.get)?\s*[\[(]\s*["']OFO_SCENARIO|getenv\(\s*["']OFO_SCENARIO""", text):
            readers.append(path.name)
        if "OFO_SCENARIO" in text and path.name not in ("scenario_mode.py", "config.py"):
            readers.append(path.name)
        if path.name != "scenario_mode.py" and re.search(
                r"scenario_mode\.ENV_NAME|from ofo_app\.scenario_mode import[^\n]*\bENV_NAME\b", text):
            readers.append(path.name)
    assert readers == []
    assert 'os.environ.get(ENV_NAME' in (ROOT / "backend/ofo_app/scenario_mode.py").read_text(encoding="utf-8")
