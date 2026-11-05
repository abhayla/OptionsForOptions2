"""Contract "Your adjustment settings" step 3, round 4 (#656): every stop line = its trigger in the settings in force.

Spec basis: ADR-252 ("The '% of max loss' stop has ONE source: the playbook's per-stage T-06 value at the strategy's
current stage"; the same for T-16); ADR-247 ("Default stop for the iron condor playbook": iron condor only); ADR-250
(a plan saved before ADR-247 gains no 2x-credit line); ADR-251 (2x the net credit so far); REQ-169 AC-4 / ADR-222 (9).

Inputs are the Tier A reviewers' attack inputs (#656 MAJOR 1-4, MINORs), run on the real functions
(``settings_in_force.stops_of``, ``playbook_eval.evaluate``, ``adjustment_plan.with_overrides``,
``playbook_store.check_body`` / ``adr247_saved_at``). Numbers: strategy 82 (max loss 23,897.04, credit 8,918) and the
reviewers' strangle (Rs 45,000 margin, loss Rs 2,250 = 5 %).

Answer states of the stop read, one row each (outcome in the test name):
value set -> that value at the current stage; trigger absent -> no line; trigger off -> line inactive, never flags;
family not ic -> no 2x-credit line; no playbook -> NO_PLAYBOOK; plan before the cutoff -> no 2x-credit line; plan after
-> the 2x-credit line; invalid value -> "not checked" (never raises), and refused on save.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo_app import adjustment_check as check
from ofo_app import playbook_store as store
from ofo_app import settings_in_force as sif
from ofo_app.routes import adjustment_plan as ap

ROOT = Path(__file__).resolve().parents[1]
MAX_LOSS = D("23897.04")
CREDIT = D("8918")
MARGIN = D("45000")
_BODIES = {r["strategy_type"]: r["body"] for r in json.loads(
    (ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text(encoding="utf-8"))["playbooks"]}


def _m0040():
    path = ROOT / "backend/ofo_app/alembic/versions/0040_ic_default_stop_adr247.py"
    found = importlib.util.spec_from_file_location("m0040_for_test", path)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


def body(family: str = "ic", *, v2: bool = True) -> dict:
    """A shipped body; for the iron condor ``v2`` applies migration 0040's change (margin guard dropped, T-16 off)."""
    out = copy.deepcopy(_BODIES[family])
    if family == "ic" and v2:
        out["guards"].pop("stop_line_pct_of_margin", None)
        out["triggers"][sl.TRIGGER_MARGIN]["on"] = False
    return out


def resolved(b, source="plan", *, before=False) -> check.Resolved:
    return check.Resolved(source, b, None, None, source == "system", saved_before_adr247=before)


def stops(b, source="plan", *, before=False, days=3, credit=CREDIT, margin=MARGIN):
    return sif.stops_of(resolved(b, source, before=before), sif.MoneyInputs(MAX_LOSS, credit, margin),
                        sif.StageAt("weekly", days))


def lines(found) -> dict:
    return {x.kind: x for x in found.lines}


def results(b, found, pnl, days=3) -> dict:
    state = pe.StrategyState(stops=found, expiry_kind="weekly", days_left=days, hhmm="11:00", spot=D(23100), pnl=pnl,
                             max_loss=MAX_LOSS, margin=MARGIN, prices_fresh=True)
    ev = pe.evaluate(b, state, {}, None, gap_until="09:30")
    return {r.rule_id: r for r in ev.results}


def stage_value(b, tid, days) -> D:
    return D(b["triggers"][tid]["weekly"][pe.stage_of(b, "weekly", days)])


# ---- MAJOR 2: ADR-247 is the iron condor's; other families keep their own body ---------------------------------------
def test_strangle_system_t16_on_flags_at_5_pct_of_margin_and_has_no_credit_line():
    b = body("strangle")
    assert b["triggers"][sl.TRIGGER_MARGIN]["on"] is True
    found = stops(b, "system")
    got = lines(found)
    assert sl.STOP_CREDIT not in got  # ADR-247 is "Default stop for the iron condor playbook"
    assert got[sl.STOP_MARGIN].active and got[sl.STOP_MARGIN].figure == stage_value(b, sl.TRIGGER_MARGIN, 3)
    assert isinstance(results(b, found, D(-2250))[sl.TRIGGER_MARGIN], pe.Flag)


def test_strangle_last_stage_max_loss_is_the_bodys_own_value():
    b = body("strangle")
    last = stage_value(b, sl.TRIGGER_MAX_LOSS, 0)
    assert lines(stops(b, "system", days=0))[sl.STOP_MAX_LOSS].figure == last


@pytest.mark.parametrize("family", sorted(set(_BODIES) - {"ic"}))
def test_no_family_but_the_iron_condor_gets_a_credit_line(family):
    assert sl.STOP_CREDIT not in lines(stops(body(family), "system"))


# ---- MAJOR 3: on/off from the trigger switch only ---------------------------------------------------------------------
def test_t16_turned_on_in_a_new_ic_plan_is_active_and_flags():
    b = body()
    b["triggers"][sl.TRIGGER_MARGIN]["on"] = True
    found = stops(b)
    assert lines(found)[sl.STOP_MARGIN].active
    assert isinstance(results(b, found, D(-2250))[sl.TRIGGER_MARGIN], pe.Flag)


def test_t06_switched_off_never_flags_even_at_60_pct():
    b = body()
    b["triggers"][sl.TRIGGER_MAX_LOSS]["on"] = False
    found = stops(b)
    assert not lines(found)[sl.STOP_MAX_LOSS].active
    assert not isinstance(results(b, found, D(-14400)).get(sl.TRIGGER_MAX_LOSS), pe.Flag)


def test_guard_key_is_not_a_source_t06_is():
    b = body()
    b["guards"]["stop_line_pct_of_max_loss"] = "30"
    b["guards"]["stop_line_pct_of_margin"] = "1"  # a margin guard with T-16 off: still off
    got = lines(stops(b))
    assert got[sl.STOP_MAX_LOSS].figure == stage_value(b, sl.TRIGGER_MAX_LOSS, 3)
    assert not got[sl.STOP_MARGIN].active


def test_admin_tightened_t06_to_45_flags_at_47_pct():
    """ADR-252's own case: T-06 45 % on a new plan, loss 47 % of max loss -> flagged."""
    b = body()
    b["triggers"][sl.TRIGGER_MAX_LOSS]["weekly"] = ["45", "45", "40"]
    found = stops(b, days=6)
    assert lines(found)[sl.STOP_MAX_LOSS].figure == D(45)
    assert isinstance(results(b, found, -(MAX_LOSS * D("0.47")).quantize(D("0.01")), days=6)["T-06"], pe.Flag)


# ---- MAJOR 4: the plan sheet's stop edit is the T-06 value the alert reads -------------------------------------------
@pytest.mark.parametrize("before", [True, False])
def test_sheet_stop_edit_to_30_is_the_alert_line(before):
    b = body(v2=not before)
    edited = ap.with_overrides(b, ap.PlanIn(playbook_id=1, stop="30"))
    for days in (6, 3, 0):  # every stage
        assert lines(stops(edited, before=before, days=days))[sl.STOP_MAX_LOSS].figure == D(30)
    assert ap._values(edited, before)["stop"] == D(30)


def test_sheet_stop_edit_turns_a_switched_off_t06_on():
    b = body()
    b["triggers"][sl.TRIGGER_MAX_LOSS]["on"] = False
    edited = ap.with_overrides(b, ap.PlanIn(playbook_id=1, stop="30"))
    assert lines(stops(edited))[sl.STOP_MAX_LOSS].active


# ---- MAJOR 1: the cutoff is 0040's row by its reason, never a version number ------------------------------------------
class _Conn:
    def __init__(self):
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((str(query), dict(params or {})))

        class _R:
            def scalar_one_or_none(self):
                return None
        return _R()


def test_cutoff_reads_0040s_row_by_reason():
    import asyncio
    conn = _Conn()
    assert asyncio.run(store.adr247_saved_at(conn)) is None
    (query, params), = conn.calls
    assert not re.search(r"version\s*=", query, re.IGNORECASE)
    assert _m0040().REASON in params.values()


# ---- MINOR: the max-loss stop does not depend on a body rule made only of stop triggers -------------------------------
def test_max_loss_stop_evaluated_with_its_body_rule_removed():
    b = body()
    b["rules"] = [r for r in b["rules"] if sl.TRIGGER_MAX_LOSS not in (r.get("any_of") or r.get("all_of"))]
    assert isinstance(results(b, stops(b), D(-14400))[sl.TRIGGER_MAX_LOSS], pe.Flag)


def test_max_loss_stop_in_a_mixed_rule_is_evaluated_from_the_line():
    b = body()
    b["rules"] = [({"id": r["id"], "any_of": [sl.TRIGGER_MAX_LOSS, "T-07"]} if r["id"] == sl.TRIGGER_MAX_LOSS else r)
                  for r in b["rules"]]
    assert isinstance(results(b, stops(b), D(-14400))[sl.TRIGGER_MAX_LOSS], pe.Flag)


# ---- MINOR: range checks; invalid -> "not checked" in the check, refused on save --------------------------------------
@pytest.mark.parametrize("raw", ["0", "-2", "1e400", "NaN", "two"])
def test_invalid_credit_multiple_is_not_checked_never_raises(raw):
    b = body()
    b["guards"]["stop_line_x_credit"] = raw
    found = stops(b)
    assert lines(found)[sl.STOP_CREDIT].reason == sif.STOP_VALUE_UNREADABLE
    res = results(b, found, D(-100))
    assert res[sl.CREDIT_RULE].code == sl.NOT_CHECKED_OTHER
    with pytest.raises(store.PlaybookStoreError):
        store.check_body(b, "ic")


@pytest.mark.parametrize("raw", ["0", "-50", "101"])
def test_invalid_max_loss_pct_is_not_checked_and_refused_on_save(raw):
    b = body()
    b["triggers"][sl.TRIGGER_MAX_LOSS]["weekly"] = [raw, raw, raw]
    found = stops(b)
    assert lines(found)[sl.STOP_MAX_LOSS].reason == sif.STOP_VALUE_UNREADABLE
    assert not isinstance(results(b, found, D(500))[sl.TRIGGER_MAX_LOSS], pe.Flag)  # never flags in profit
    with pytest.raises(store.PlaybookStoreError):
        store.check_body(b, "ic")


# ---- the other answer states -----------------------------------------------------------------------------------------
def test_plan_before_cutoff_has_no_credit_line_and_after_has_it():
    assert sl.STOP_CREDIT not in lines(stops(body(v2=False), before=True))
    assert lines(stops(body(), before=False))[sl.STOP_CREDIT].amount == D("17836.00")


def test_system_ic_without_a_plan_takes_the_new_version():
    got = lines(stops(body(), "system"))
    assert got[sl.STOP_CREDIT].active and not got[sl.STOP_MARGIN].active
    assert got[sl.STOP_MAX_LOSS].figure == D(50)


def test_absent_trigger_gives_no_line_and_no_playbook_gives_no_stops():
    b = body()
    del b["triggers"][sl.TRIGGER_MARGIN]
    b["rules"] = [r for r in b["rules"] if sl.TRIGGER_MARGIN not in (r.get("any_of") or r.get("all_of"))]
    assert not lines(stops(b)).get(sl.STOP_MARGIN, sl.StopInForce("x", False, None, None, None, None)).active
    none = sif.stops_of(check.Resolved("none", None, None, None, False, saved_before_adr247=False), None)
    assert none == sif.StopsInForce((), None, sif.NO_PLAYBOOK)


def test_pre_adr247_plan_keeps_40_in_the_last_stage():
    assert lines(stops(body(v2=False), before=True, days=0))[sl.STOP_MAX_LOSS].figure == D(40)


@pytest.mark.parametrize(("family", "v2", "before"), [("ic", False, True), ("ic", True, False), ("strangle", True, False),
                                                      ("debit", True, False)])
def test_plan_stop_words_present_for_every_plan(family, v2, before):
    b = body(family, v2=v2)
    for key in ("stop_line_pct_of_max_loss", "stop_line_pct_of_margin", "stop_line_x_credit"):
        b["guards"].pop(key, None)  # no guard key: the words still come from the triggers
    assert ap._values(b, before)["stop_words"] is not None
