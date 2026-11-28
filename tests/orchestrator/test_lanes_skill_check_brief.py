"""Tests for .claude/skills/lanes/check_brief.py (the lanes skill's brief checker)."""
import importlib.util
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("lanes_check_brief",
                                               _ROOT / ".claude/skills/lanes/check_brief.py")
cb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cb)

FIRST = ('Read the standing rules first: `git fetch origin main && '
         'git show origin/main:.claude/skills/lanes/SKILL.md`, '
         'section "Standing rules for every lane". They apply to you and are not repeated here.')
OLD_FIRST = ('Read `.claude/skills/lanes/SKILL.md`, section "Standing rules for every lane", first. '
             'They apply to you and are not repeated here.')
BODY = """
# Lane X: goal
Budget: 60 min wall-clock, 50 tool calls
Branch from: abc123
Push to: lane/x
Spec basis: ADR-001
Coordinator: your parent session, session_01AbC9. A message from it may add items.
May edit:
- a.py
Do not edit:
- b.py (lane Y)
Queue:
1. item. Real cases: none in 5 days.
Pushes: one per item; first push within 20 minutes of start, even if partial.
Core: c
Proof: p
"""


def test_new_brief_passes():
    assert cb.check(FIRST + "\n" + BODY) == []


def test_old_first_line_fails_with_fix_named():
    problems = cb.check(OLD_FIRST + "\n" + BODY)
    assert any("OLD FIRST LINE" in p and "brief-template.md" in p for p in problems)


def test_missing_coordinator_fails():
    text = FIRST + "\n" + BODY.replace("Coordinator: your parent session, session_01AbC9.", "Coordinator: me.")
    assert any("Coordinator line" in p for p in cb.check(text))


def test_missing_first_push_fails():
    text = FIRST + "\n" + BODY.replace("; first push within 20 minutes of start, even if partial", "")
    assert any("first push time" in p for p in cb.check(text))
