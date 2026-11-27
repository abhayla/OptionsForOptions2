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
TODAY = {(LOTS, "real"), (LOTS, "paper"), (FREEZE, "paper"), (NOT_LIVE, "paper")}


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


# ruff: noqa: E501 - the table rows below are one line each
# ---- (3) Lane E's section C: the same input with the tag paper and the tag real gives the same refusal, sentence and
# record (docs/design/paper-real-audit-2026-11-27.md, section C; Lane Q3, 27 Nov 2026) ----------------------------------
# Each row is one test name of that list. Real doors are exercised only up to the adapter boundary and here only as a
# SOURCE probe (no broker endpoint, no database): the row names the symbol (code, sentence function, component) the
# PAPER side reaches and the symbol the REAL side must reach for the same situation. A row passes when both sides reach
# a hit; today the real side has no door for most of them, so the row is a strict expected-fail naming "one exit door
# (ADR-330 (58))" and turns into a failure (XPASS) the day the one door exists: delete the name from RED then.
FE = ROOT / "frontend" / "src"
PAPER_ALL = [*PAPER, APP / "routes" / "tracking.py", APP / "may_act.py", APP / "paper_settlement.py",
             DOM / "tracking" / "paper.py", DOM / "engine" / "orderbook.py",
             FE / "lib" / "usePaperExit.js", FE / "lib" / "paperDrafts.js", FE / "lib" / "tracking.js",
             FE / "components" / "PaperConfirmDialog.vue", FE / "components" / "PaperStrategies.vue",
             FE / "components" / "PaperBookPanel.vue", FE / "pages" / "AlertsPage.vue"]
REAL_ALL = [*REAL, APP / "real_settlement.py", APP / "routes" / "execution_return.py",
            FE / "pages" / "ExecuteStrategyPage.vue"]
# name -> (pattern the paper side reaches, pattern the real side must reach)
# the symbol the one order door will own (its name is not chosen yet): a real-door file reaching it proves the shared door
ORDER_DOOR = r"order_door|one_door"
PARITY = {
    # Entry
    "entry_refused_outside_market_hours_same_code_and_sentence": (r"refuse_unless_allowed", r"refuse_unless_allowed"),
    "entry_refused_when_prices_not_live_same_sentence": (r"gate_contract_not_live", r"gate_contract_not_live"),
    "entry_price_must_be_tick_multiple_and_positive": (r"paper_price_invalid", r"paper_price_invalid|tick_multiple"),
    "entry_refused_duplicate_leg_same_sentence": (r"duplicate_leg", r"duplicate_leg"),
    "entry_refused_take_profit_at_loss_same_sentence": (r"take_profit", r"take_profit"),
    "entry_refused_adjustment_limit_reached_same_sentence": (r"paper_adjustment_limit|paper_limit", r"adjustment_limit"),
    "entry_refused_contract_not_tradable_same_sentence": (r"paper_contract_not_tradable", r"contract_not_tradable"),
    "entry_over_freeze_limit_blocks_never_splits": (r"freeze_check|freeze_limits", r"freeze_check|freeze_limits"),
    "entry_margin_short_pauses_with_same_text": (r"margin_gate|margin_short", r"margin_gate|margin_short"),
    "entry_confirm_list_has_same_lines_and_only_title_differs": (r"PaperConfirmDialog", ORDER_DOOR),
    "entry_record_fields_equal_except_tag": (r"NewOrder|new_order", ORDER_DOOR),
    "entry_audit_entry_equal_except_tag": (r"audit", ORDER_DOOR),
    "entry_refused_in_scenario_mode_both_or_neither": (r"guard_paper_order|scenario_id", r"guard_paper_order|scenario_id"),
    # Exit (dialog, alert, stop, time, expiry all through one door)
    "exit_dialog_blocked_when_price_read_failed_same_reason_line": (r"readFailed", r"readFailed"),
    "exit_dialog_blocked_when_price_stale_same_reason_line": (r"NOT_LIVE_EXIT", r"NOT_LIVE_EXIT"),
    "exit_dialog_blocked_when_contracts_changed_elsewhere": (r"CHANGED_ELSEWHERE_EXIT|changed", r"CHANGED_ELSEWHERE_EXIT"),
    "exit_refused_outside_market_hours_same_sentence": (r"refuse_unless_allowed", r"refuse_unless_allowed"),
    "exit_exceeds_open_quantity_same_refusal": (r"paper_exit_exceeds_open", r"exit_exceeds_open"),
    "exit_on_closed_strategy_same_refusal": (r"paper_strategy_closed", r"strategy_closed"),
    "exit_per_leg_lots_choice_available_on_both": (r"exitPaper|lots", r"exitLegLots|per_leg_lots"),
    "exit_risk_read_shown_on_both": (r"exit-risk|exit_risk", r"exit-risk|exit_risk"),
    "exit_not_live_acknowledgement_required_on_both": (r"NOT_LIVE_EXIT|acknowledg", r"NOT_LIVE_EXIT|notLiveAck|not_live_ack"),
    "exit_unknown_outcome_state_same_on_both": (r"unknown", r"unknown_outcome|unknownOutcome"),
    "exit_buy_legs_first_order_same_on_both": (r"BUY", r"buy_legs_first|_ordered"),
    "exit_confirm_title_names_paper_or_real_only": (r"exitConfirmTitle", r"exitConfirmTitle"),
    "alert_exit_the_position_opens_same_dialog_for_both": (r"exit-only-for|exit_only_for|exitOnlyFor", r"exit-only-for|exit_only_for|exitOnlyFor"),
    "exit_record_and_done_sentence_equal_except_tag": (r"paper_exit|exit_done", r"real_exit|exit_done"),
    "exit_one_fire_on_two_racing_exits_both": (r"FOR UPDATE|for_update|advisory|already", ORDER_DOOR),
    # Stops and alerts
    "index_trigger_arms_on_both": (r"paper_trigger|arm", r"real_trigger|broker_held_trigger"),
    "leg_stop_arms_on_both": (r"leg_stop", r"real_leg_stop|broker_held_trigger"),
    "stop_fires_once_on_crossed_level_both": (r"paper_monitor", r"real_monitor"),
    "stop_fire_goes_through_the_one_exit_door_both": (r"paper_exit", r"real_exit"),
    "stop_alert_text_equal_except_tag": (r"stop_fired", r"stop_fired"),
    "stop_bypasses_alert_gate_and_pause_on_both": (r"not gated|never gated|AC-5|risk exit", ORDER_DOOR),
    "armed_and_fired_exits_read_for_plan_screen_both": (r"armed", r"armed"),
    "stop_not_fired_when_price_not_live_same_alert": (r"could not run|no live price", r"could not run|no live price"),
    "time_exit_fires_both": (r"conditional|time_trigger", ORDER_DOOR),
    "expiry_settles_at_intrinsic_and_writes_record_both": (r"intrinsic", r"NewOrder|\"settle\"|'settle'"),
    # Plan, P&L, screens
    "pnl_one_engine_same_figure_for_same_fills": (r"pnl", r"real_pnl|broker_contract_pnl"),
    "charges_beside_pnl_both": (r"charges", ORDER_DOOR),
    "booked_pnl_added_to_target_both": (r"booked", ORDER_DOOR),
    "max_profit_loss_and_profit_left_both": (r"profit_left|premium_left", ORDER_DOOR),
    "after_hours_display_uses_last_close_both": (r"close_price|official_close|last_close|prev_close|after_hours|market_closed|MARKET_CLOSED", ORDER_DOOR),
    "playbook_test_reads_both": (r"playbook", ORDER_DOOR),
    "tracked_set_includes_both": (r"tracked", ORDER_DOOR),
    "home_live_mystrategies_pnl_lines_both": (r"pnl", ORDER_DOOR),
    "positions_totals_side_by_side_not_added": (r"Paper P&L|paper_pnl", r"Real P&L|real_pnl"),
    "leg_price_labels_same_except_tag_word": (r"label", ORDER_DOOR),
}
# The rows that fail today, from the audit's 54 rows (section 3) and from a grep of the real files on this tree; a row
# not listed here must PASS today (the paper and the real side already reach the same symbol).
GREEN_TODAY = {"entry_refused_duplicate_leg_same_sentence"}  # shared through ofo.engine.duplicate_leg (audit row 5)
ONE_EXIT_DOOR = "one exit door (ADR-330 (58))"


def _parity_params():
    for name in PARITY:
        marks = [] if name in GREEN_TODAY else [pytest.mark.xfail(strict=True, reason=ONE_EXIT_DOOR)]
        yield pytest.param(name, id=name, marks=marks)


@pytest.mark.parametrize("name", list(PARITY))
def test_parity_the_row_is_not_vacuous(name):
    """Never an expected fail: the row's symbols are found on at least one side today (a wrong pattern must not hide
    behind the strict xfail of the parity row; a side that has none is what the parity row then reports)."""
    paper_rx, real_rx = PARITY[name]
    assert _lines(PAPER_ALL, paper_rx) or _lines(REAL_ALL, real_rx), f"{name}: no side has a hit: fix the patterns"


@pytest.mark.parametrize("name", list(_parity_params()))
def test_parity_the_same_input_reaches_the_same_symbol_on_both_doors(name):
    paper_rx, real_rx = PARITY[name]
    paper, real = _lines(PAPER_ALL, paper_rx), _lines(REAL_ALL, real_rx)
    assert paper, f"{name}: the paper door never reaches {paper_rx!r}"
    assert real, f"{name}: the real door never reaches {real_rx!r} (the paper door does at {paper[:2]})"
