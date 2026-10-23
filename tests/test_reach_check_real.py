"""Reach check on THIS repo (finding verified-on-a-module-the-product-does-not-call): every passing evidence file of a
Verified or finished requirement must test code an app entry reaches, or be a named baseline entry; the baseline only
shrinks (a hit that went away must be deleted from reach_check_baseline.json)."""
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan  # reads every module under backend/ and every evidence file
ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("reach_check", ROOT / "scripts" / "orchestrator" / "reach_check.py")
rc = importlib.util.module_from_spec(_spec)
sys.modules["reach_check"] = rc
_spec.loader.exec_module(rc)


def test_every_hit_is_baselined_and_no_baseline_entry_is_stale(capsys):
    code = rc.main(["--root", str(ROOT)])
    out = capsys.readouterr().out
    assert code == 0, out


def test_baseline_entries_carry_a_reason_and_an_issue():
    entries = rc.load_baseline(ROOT / "scripts" / "orchestrator" / rc.BASELINE_NAME)
    assert entries, "an empty baseline would mean the tree has no hit; delete this assert only then"
    assert all(e["reason"].strip() and e["issue"].strip() for e in entries.values())
