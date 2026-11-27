"""Gap 9 (Lane Q2, from the coordinator's 17:00 IST message; owner rule ADR-330 (58)): a paper order differs from
a real order
ONLY by its tag. Every rule, limit, check, refusal, message and code path is the same for both; nothing exempts paper.

No database, no broker: this is a SOURCE parity test of the two order doors that exist today (the real door
``routes/execute.py`` + ``ofo/execution``, the paper door ``routes/paper.py`` + ``paper_limit`` / ``paper_exit`` /
``paper_store`` / ``paper_monitor``), until the one door exists. It reads the files with ``ast`` and fails with
FILE:LINE.
 (1) CHECK INVENTORY: each check the owner named (lots limit, freeze quantity, prices not live, duplicate leg) must be
     reached from BOTH doors, through the SAME shared function or refusal code (one message). A check present on
one door
     only, or worded by two codes, fails and names the door that lacks it.
 (2) BRANCH SCAN: an ``if`` / conditional expression / boolean in the order, exit, stop or alert path that tests
for paper
     only (in a real-door file) or for the broker / real only (in a paper-door file) is a paper-only or real-only
branch.
The decision-level cases (entry, add, exit, over the lots limit, over the freeze quantity, prices not live: same
decision and
same message up to the broker adapter) need the one door; their HTTP halves for the paper door are in
tests_app/test_paper_order_lots_limit.py. Spec basis: ADR-330 (58) (coordinator-recorded; not yet in this tree),
(50), (51), (52);
ADR-016..019; ADR-212. Every cell that fails today is a strict xfail naming the lane that fixes it ("the one order
door").
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parent.parent
APP, DOM = ROOT / "backend" / "ofo_app", ROOT / "backend" / "ofo"
REAL = [APP / "routes" / "execute.py", APP / "execute_plan.py", *sorted((DOM / "execution").glob("*.py"))]
PAPER = [APP / "routes" / "paper.py", APP / "paper_limit.py", APP / "paper_exit.py", APP / "paper_store.py",
         APP / "paper_monitor.py", APP / "paper_trigger_store.py"]
ALERT = [APP / "actionable_alerts.py"]  # the one shared alert module (ADR-330 (4)): not a door of either side
ONE_DOOR_LANE = "the one order door (ADR-330 (58)); no branch has it yet"


def _lines(files, pattern: str) -> list[str]:
    rx = re.compile(pattern)
    return [f"{p.relative_to(ROOT)}:{n}" for p in files if p.exists()
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if rx.search(line) and not line.lstrip().startswith("#")]


LOTS = "lots limit per leg (limits.max_lots, ADR-330 (52))"
FREEZE = "freeze quantity (ofo.execution.freeze)"
NOT_LIVE = "prices not live: ONE refusal code"
DUPLICATE = "duplicate leg: the one engine sentence"
#: check -> (the shared symbol or code both doors must reach, one pattern each side that proves it is reached)
CHECKS = {
    LOTS: (r"\bcheck_lots\(|leg_lots_above_limit", r"\bcheck_lots\(|leg_lots_above_limit"),
    FREEZE: (r"freeze_check\(|review_freeze_limits", r"freeze_check\(|freeze_limits|StoredFreeze"),
    NOT_LIVE: (r"gate_contract_not_live", r"gate_contract_not_live"),
    DUPLICATE: (r"duplicate_leg_failure|duplicate_leg import", r"paper_duplicate_leg|duplicate_leg import"),
}
# which cells fail today (so they are strict xfails); the duplicate-leg check is shared through ofo.engine.duplicate_leg
# (FREEZE, "paper") left this set when fix/order-limits-1127 (Lane K) put the freeze check on the paper door:
# its strict xfail then passed (XPASS), the signal to delete the mark (Lane M3, 27 Nov)
TODAY = {(LOTS, "real"), (LOTS, "paper"), (NOT_LIVE, "paper")}


def _cells():
    for name in CHECKS:
        for door in ("real", "paper"):
            reason = f"{door} door lacks it; fixed by {ONE_DOOR_LANE}"
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if (name, door) in TODAY else []
            label = name.split(" (")[0].split(":")[0].replace(" ", "_")
            yield pytest.param(name, door, id=f"{door}-{label}", marks=marks)


@pytest.mark.parametrize(("name", "door"), list(_cells()))
def test_the_check_is_reached_from_this_door(name, door):
    real_rx, paper_rx = CHECKS[name]
    files, pattern = (REAL, real_rx) if door == "real" else (PAPER, paper_rx)
    found = _lines(files, pattern)
    other = _lines(PAPER if door == "real" else REAL, paper_rx if door == "real" else real_rx)
    assert found, f"{name}: the {door} door never reaches it; the other door does at {other[:3]}"


# ---- (2) the branch scan ----------------------------------------------------------------------------------
PAPER_WORD = re.compile(r"(?i)\bpaper\b|is_paper|paper_mode")
REAL_WORD = re.compile(r"(?i)\b(real|kite|zerodha|broker|is_real)\b")


def _tests(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            yield node.test
        elif isinstance(node, ast.comprehension):
            yield from node.ifs


def _words(expr) -> str:
    out = []
    for n in ast.walk(expr):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return " ".join(out)


def branches(files, rx) -> list[str]:
    found = []
    for p in files:
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        found += [f"{p.relative_to(ROOT)}:{t.lineno}: {_words(t)[:70]}" for t in _tests(tree) if rx.search(_words(t))]
    return sorted(set(found))


def test_no_paper_only_branch_in_the_real_order_path():
    found = branches(REAL, PAPER_WORD)  # measured on 206a9f0: none (a guard, not a defect)
    assert found == [], "\n".join(found)


def test_no_real_only_branch_in_the_paper_order_path():
    found = branches(PAPER, REAL_WORD)
    assert found == [], "\n".join(found)


def test_the_shared_alert_module_has_no_paper_or_real_branch():
    found = branches(ALERT, PAPER_WORD) + branches(ALERT, REAL_WORD)
    assert found == [], "\n".join(found)
