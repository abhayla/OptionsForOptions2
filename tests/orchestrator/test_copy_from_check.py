"""copy_from_check.py: a brief must cite every legacy-reuse map row that names one of its requirements."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))

import copy_from_check as cfc

ROWS = [
    "| `ticker/pool.py` (414) | ADAPT | pooled connections | REQ-113 |",
    "| `services/autopilot/adjustment_engine.py` (1388) | REFERENCE | Alert + Prepare only | REQ-045 |",
]


def test_a_row_for_the_briefs_requirement_that_the_brief_does_not_cite_is_missing():
    text = "# C2\nSpec basis: REQ-113 AC-1\n## What to build\n1. a new feed process\n"
    assert cfc.missing(ROWS, text) == [ROWS[0]]


def test_a_cited_row_and_a_row_for_another_requirement_are_not_missing():
    text = "# C2\nSpec basis: REQ-113 AC-1\nCopy from: `ticker/pool.py`\n## What to build\n"
    assert cfc.missing(ROWS, text) == []


def test_requirements_named_only_after_what_to_build_do_not_count():
    text = "# B1\nSpec basis: REQ-081\n## What to build\nsee REQ-045 later\n"
    assert cfc.missing(ROWS, text) == []


def test_append_writes_the_rows_once_and_the_brief_then_passes(tmp_path):
    root = tmp_path
    (root / "spec" / "technical-design").mkdir(parents=True)
    (root / "spec" / "technical-design" / "legacy-reuse.md").write_text("\n".join(ROWS) + "\n", encoding="utf-8")
    brief = root / "D3.md"
    brief.write_text("# D3\nSpec basis: REQ-045 AC-2\n## What to build\n", encoding="utf-8")
    assert cfc.main([str(root), str(brief), "--append"]) == 1
    assert cfc.main([str(root), str(brief)]) == 0
    cfc.main([str(root), str(brief), "--append"])
    assert brief.read_text(encoding="utf-8").count(cfc.HEADING) == 1
