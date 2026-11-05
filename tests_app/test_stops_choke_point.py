"""Contract "Your adjustment settings" step 3, round 3: live stop alerts come ONLY from the settings in force.

Spec basis: ADR-245, ADR-247, ADR-250 (saved plans keep their own stops; no 2x line), ADR-251 (2x the NET credit so far).
Numbers are strategy 82's (ADR-247): max loss 23,897.04 -> 50 % = 11,948.52; credit 8,918 -> 2x = 17,836.

Blind spots of the scan (test 1): it sees string literals only. A stop trigger id built at runtime (``"T-0" + "6"``),
read through a variable holding the id, or a generic ``body["triggers"][tid]`` read with a computed ``tid`` is not
flagged; the structural guard against those is test 2 (the evaluator cannot run without stops) plus the evaluator
skipping every body rule whose members are stop triggers.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import json
from decimal import Decimal as D
from pathlib import Path

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.engine import adjust_money
from ofo_app import adjustment_check as check
from ofo_app import settings_in_force as sif

ROOT = Path(__file__).resolve().parents[1]
MAX_LOSS = D("23897.04")
CREDIT = D("8918")
#: files allowed to name a stop trigger id or a stop_line_* key: the one reader, the domain names, the plan editor
#: (it WRITES the guards the user edits), the label catalogue and the migrations
ALLOW = {"backend/ofo_app/settings_in_force.py", "backend/ofo/adjustment/stop_lines.py",
         "backend/ofo_app/routes/adjustment_plan.py", "backend/ofo/errors/explanations.py"}


def _ic_body(*, v2: bool = True) -> dict:
    data = json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text(encoding="utf-8"),
                      parse_float=D)
    rows = data["playbooks"]
    row = next((r for r in rows if isinstance(r, dict) and r.get("strategy_type") == "ic"), rows[0])
    body = json.loads(json.dumps(row.get("body", row), default=str))
    if v2:  # migration 0040 (ADR-247): the % of margin guard removed and T-16 off
        body["guards"].pop("stop_line_pct_of_margin", None)
        body["triggers"][sl.TRIGGER_MARGIN]["on"] = False
    return body


def _state(stops, pnl: D, days_left: int = 3) -> pe.StrategyState:
    return pe.StrategyState(expiry_kind="weekly", days_left=days_left, hhmm="11:00", spot=D(23100), pnl=pnl,
                            max_loss=MAX_LOSS, prices_fresh=True, stops=stops)


def _plan(body, *, before: bool) -> check.Resolved:
    return check.Resolved("plan", body, None, None, False, saved_before_adr247=before)


# (1) no reader outside the allowlist names a stop trigger or a stop_line_* key ----------------------------------------
def test_no_stop_reader_outside_settings_in_force():
    found = []
    for tree in ("backend/ofo", "backend/ofo_app"):
        for path in (ROOT / tree).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in ALLOW or "/alembic/versions/" in rel:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                        node.value in sl.STOP_TRIGGERS or node.value.startswith("stop_line_")):
                    found.append(f"{rel}:{node.lineno} {node.value!r}")
    assert found == []


# (2) the stops are required: no default anywhere on the path ----------------------------------------------------------
def test_state_of_and_strategy_state_have_no_default_for_stops():
    assert inspect.signature(check.state_of).parameters["resolved"].default is inspect.Parameter.empty
    field = next(f for f in dataclasses.fields(pe.StrategyState) if f.name == "stops")
    assert field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
    ev = pe.evaluate(_ic_body(), _state(None, D(-20000)), {}, None, gap_until="09:30")
    stop = [r for r in ev.results if sl.is_stop_rule(r.rule_id)]
    assert stop == [pe.NotChecked("stop.max_loss_pct", "stop.max_loss_pct", sl.STOPS_NOT_SUPPLIED)]


# (3) parity: every active line in force has exactly one stop result with the same amount -------------------------------
def test_every_active_stop_line_has_a_matching_result_with_the_same_amount():
    body = _ic_body()
    stops = sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, CREDIT))
    active = {x.kind: x.amount for x in stops.lines if x.active}
    assert active == {sl.STOP_MAX_LOSS: D("11948.52"), sl.STOP_CREDIT: D("17836.00")}
    ev = pe.evaluate(body, _state(stops, D("-12000")), {}, None, gap_until="09:30")
    got = {r.rule_id: r for r in ev.results if sl.is_stop_rule(r.rule_id)}
    vals = {v.rule_id: v for v in ev.values if sl.is_stop_rule(v.rule_id)}
    assert set(got) | set(vals) == {sl.rule_id(k) for k in active}
    assert got["stop.max_loss_pct"].threshold == D("11948.52") and got["stop.max_loss_pct"].value == D("12000")
    assert vals["stop.credit_multiple"].threshold == D("17836.00") and not vals["stop.credit_multiple"].fired
    assert not any(r.trigger_id in sl.STOP_TRIGGERS for r in ev.results)  # the body's T-06 / T-16 never answer


# (4) ADR-250: a plan saved before ADR-247 keeps 40 % in the last stage and has no 2x line ------------------------------
def test_pre_adr247_plan_keeps_its_own_stops_and_new_plan_gets_the_default():
    body = _ic_body(v2=False)  # the body a plan saved before ADR-247 holds (T-16 on, margin guard 4)
    money = sif.MoneyInputs(MAX_LOSS, CREDIT)
    last = sif.StageAt("weekly", 0)
    old = sif.stops_of(_plan(body, before=True), money, last)
    old_active = {x.kind: x for x in old.lines if x.active}
    assert sl.STOP_CREDIT not in {x.kind for x in old.lines}
    assert old_active[sl.STOP_MAX_LOSS].figure == D(40)
    assert old_active[sl.STOP_MAX_LOSS].amount == adjust_money.stop_at_pct(MAX_LOSS, D(40))
    assert old_active[sl.STOP_MARGIN].reason == sif.MARGIN_NOT_READ  # its own T-16, margin not read here
    new = sif.stops_of(_plan(_ic_body(), before=False), money, last)
    new_active = {x.kind: x for x in new.lines if x.active}
    assert new_active[sl.STOP_MAX_LOSS].figure == D(50)
    assert new_active[sl.STOP_CREDIT].amount == D("17836.00")
    # unknown stage on an old plan: not checked with a reason, never a guessed stage
    unknown = sif.stops_of(_plan(body, before=True), money, None)
    assert next(x for x in unknown.lines if x.kind == sl.STOP_MAX_LOSS).reason == sif.STAGE_UNKNOWN


# (5) ADR-251: 2x the net credit so far; zero / debit / unread -> not checked, max-loss still checked -------------------
def test_two_x_credit_uses_net_credit_so_far():
    assert adjust_money.net_credit_so_far(D(-1500), [("SELL", D(60), 100)]) == D(4500)  # 6,000 entry, roll cost 1,500
    body = _ic_body()
    lines = {x.kind: x for x in sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, D(4500))).lines}
    assert lines[sl.STOP_CREDIT].amount == D("9000.00")
    for credit, reason in ((D(-100), sif.NO_CREDIT), (D(0), sif.NO_CREDIT), (None, sif.CREDIT_UNKNOWN)):
        stops = sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, credit))
        got = {x.kind: x for x in stops.lines}
        assert got[sl.STOP_CREDIT].amount is None and got[sl.STOP_CREDIT].reason == reason
        ev = pe.evaluate(body, _state(stops, D("-12000")), {}, None, gap_until="09:30")
        res = {r.rule_id: r for r in ev.results if sl.is_stop_rule(r.rule_id)}
        assert res["stop.credit_multiple"] == pe.NotChecked("stop.credit_multiple", "stop.credit_multiple",
                                                            sl.not_checked_code(reason))
        assert isinstance(res["stop.max_loss_pct"], pe.Flag)  # the max-loss stop is still checked and named
        assert pe.reason_text(sl.not_checked_code(reason))


# fail closed: every unreadable answer state is "not checked", never a pass ---------------------------------------------
def test_unreadable_stop_value_is_not_checked():
    body = _ic_body()
    body["guards"]["stop_line_x_credit"] = "two"
    stops = sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, CREDIT))
    ev = pe.evaluate(body, _state(stops, D("-1")), {}, None, gap_until="09:30")
    res = {r.rule_id: r for r in ev.results if sl.is_stop_rule(r.rule_id)}
    assert res["stop.credit_multiple"].code == sl.NOT_CHECKED_OTHER
