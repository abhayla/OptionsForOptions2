"""Contract "Your adjustment settings" step 3, round 3: live stop alerts come ONLY from the settings in
force.

Spec basis: ADR-245, ADR-247, ADR-250 (saved plans keep their own stops; no 2x line), ADR-251 (2x the NET credit
so far).
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
from ofo_app import background
from ofo_app import settings_in_force as sif

ROOT = Path(__file__).resolve().parents[1]
MAX_LOSS = D("23897.04")
CREDIT = D("8918")
#: files allowed to name a stop trigger id or a stop_line_* key: the one reader, the domain names, the label catalogue
#: and the migrations
ALLOW = {"backend/ofo_app/settings_in_force.py", "backend/ofo/adjustment/stop_lines.py",
         "backend/ofo/errors/explanations.py"}  # round 4: the plan editor is NOT allowed (its stop edit goes through
#                                           settings_in_force.set_max_loss_stop / sheet_stop, #656 MAJOR 4)


def _ic_body(*, v2: bool = True) -> dict:
    """The iron condor after migration 0040 (ADR-247 shape); ``v2=False`` -> the shipped seed, the body a plan saved
    before ADR-247 holds (ADR-216: % of margin guard 4, T-16 on 4 / 4 / 3)."""
    data = json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text(encoding="utf-8"),
                      parse_float=D)
    row = next(r for r in data["playbooks"] if r["strategy_type"] == "ic")
    body = json.loads(json.dumps(row["body"], default=str))
    if v2:  # migration 0040's change on the ADR-216 seed: margin guard dropped, T-16 off (values kept)
        body["guards"].pop("stop_line_pct_of_margin", None)
        body["triggers"][sl.TRIGGER_MARGIN]["on"] = False
    return body


def _state(stops, pnl: D, days_left: int = 3, **kw) -> pe.StrategyState:
    return pe.StrategyState(expiry_kind="weekly", days_left=days_left, hhmm="11:00", spot=D(23100), pnl=pnl,
                            max_loss=MAX_LOSS, prices_fresh=True, stops=stops, **kw)


def _plan(body, *, before: bool) -> check.Resolved:
    return check.Resolved("plan", body, None, None, False, saved_before_adr247=before)


def _results(ev) -> dict:
    return {r.rule_id: r for r in ev.results if sl.is_stop_rule(r.rule_id)}


# (1) no reader outside the allowlist names a stop trigger or a stop_line_* key ----------------------------------------
def test_no_stop_reader_outside_settings_in_force():
    found = []
    for tree in ("backend/ofo", "backend/ofo_app"):
        for path in (ROOT / tree).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in ALLOW or "/alembic/versions/" in rel:
                continue
            found.extend(f"{rel}:{node.lineno} {node.value!r}"
                         for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(node, ast.Constant) and isinstance(node.value, str)
                         and (node.value in sl.STOP_TRIGGERS or node.value.startswith("stop_line_")))
    assert found == []


# (2) no default on the path: state_of's resolved, StrategyState.stops, Resolved's flag, Watched.resolved --------------
def _no_default(cls, name: str) -> bool:
    f = next(x for x in dataclasses.fields(cls) if x.name == name)
    return f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING


def test_no_default_for_stops_resolved_or_the_saved_plan_flag():
    assert inspect.signature(check.state_of).parameters["resolved"].default is inspect.Parameter.empty
    assert _no_default(pe.StrategyState, "stops")
    assert _no_default(check.Resolved, "saved_before_adr247")
    assert _no_default(background.Watched, "resolved")
    ev = pe.evaluate(_ic_body(), _state(None, D(-20000)), {}, None, gap_until="09:30")
    assert _results(ev)["T-06"] == pe.NotChecked("T-06", "T-06", sl.STOPS_NOT_SUPPLIED)
    assert pe.reason_text(sl.STOPS_NOT_SUPPLIED)


# (3) parity: every active line in force answers once, under its id, with the same figure / amount -------------------
def test_every_active_stop_line_has_a_matching_result():
    body = _ic_body()
    stops = sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, CREDIT), sif.StageAt("weekly", 3))
    active = {x.kind: x for x in stops.lines if x.active}
    assert {k: (x.figure, x.amount) for k, x in active.items()} == {
        sl.STOP_MAX_LOSS: (D(50), D("11948.52")), sl.STOP_CREDIT: (D(2), D("17836.00"))}
    ev = pe.evaluate(body, _state(stops, D("-12000")), {}, None, gap_until="09:30")
    got = _results(ev)
    vals = {v.rule_id: v for v in ev.values if sl.is_stop_rule(v.rule_id)}
    assert set(got) | set(vals) == {"T-06", "T-16", sl.CREDIT_RULE}
    # the margin line is off on the shipped body: T-16 answers "switched off", as it did when the body held T-16 off
    assert got["T-16"] == pe.NotChecked("T-16", "T-16", "adjust_trigger_switched_off")
    t06 = got["T-06"]
    assert isinstance(t06, pe.Flag) and t06.threshold == D(50)  # loss 12,000 >= 11,948.52 = 50 % of max loss
    assert vals[sl.CREDIT_RULE].threshold == D("17836.00") and not vals[sl.CREDIT_RULE].fired
    below = pe.evaluate(body, _state(stops, D("-11948")), {}, None, gap_until="09:30")
    assert "T-06" in below.clear  # one rupee short of the line: not fired


# (4) ADR-250: a plan saved before ADR-247 keeps 40 % in the last stage and has no 2x line
def test_pre_adr247_plan_keeps_its_own_stops_and_new_plan_gets_the_default():
    money = sif.MoneyInputs(MAX_LOSS, CREDIT)
    last = sif.StageAt("weekly", 0)
    old = sif.stops_of(_plan(_ic_body(v2=False), before=True), money, last)
    old_active = {x.kind: x for x in old.lines if x.active}
    assert sl.STOP_CREDIT not in {x.kind for x in old.lines}
    assert old_active[sl.STOP_MAX_LOSS].figure == D(40)
    assert old_active[sl.STOP_MARGIN].figure == D(3) and old_active[sl.STOP_MARGIN].reason == sif.MARGIN_NOT_READ
    early = sif.stops_of(_plan(_ic_body(v2=False), before=True), money, sif.StageAt("weekly", 6))
    assert next(x for x in early.lines if x.kind == sl.STOP_MAX_LOSS).later == (D(50), D(40))
    new = sif.stops_of(_plan(_ic_body(), before=False), money, last)
    new_active = {x.kind: x for x in new.lines if x.active}
    assert new_active[sl.STOP_MAX_LOSS].figure == D(40)  # ADR-252: T-06 50 / 50 / 40, the last stage stricter
    assert new_active[sl.STOP_CREDIT].amount == D("17836.00")
    assert sl.STOP_MARGIN not in new_active
    unknown = sif.stops_of(_plan(_ic_body(v2=False), before=True), money, None)
    assert next(x for x in unknown.lines if x.kind == sl.STOP_MAX_LOSS).reason == sif.STAGE_UNKNOWN


# (4b) the expiry-day tighten rule still tightens the max-loss line, for an old plan and a new one --------------------
def test_tighten_rule_still_applies_to_the_max_loss_line():
    for body, before in ((_ic_body(v2=False), True), (_ic_body(), False)):
        stops = sif.stops_of(_plan(body, before=before), sif.MoneyInputs(MAX_LOSS, CREDIT), sif.StageAt("weekly", 0))
        figure = next(x for x in stops.lines if x.kind == sl.STOP_MAX_LOSS).figure
        ev = pe.evaluate(body, _state(stops, D("-1"), days_left=0, tighten_percent=D(20)), {}, None,
                         gap_until="09:30")
        t06 = next(v for v in ev.values if v.rule_id == "T-06")
        assert t06.threshold == figure * D("0.8")  # 40 -> 32 (old plan), 50 -> 40 (new plan)


# (5) ADR-251: 2x the net credit so far; zero / debit / unread -> not checked, max-loss still checked
def test_two_x_credit_uses_net_credit_so_far():
    assert adjust_money.net_credit_so_far(D(-1500), [("SELL", D(60), 100)]) == D(4500)  # 6,000 entry, roll cost 1,500
    body = _ic_body()
    lines = {x.kind: x for x in sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, D(4500)), sif.StageAt("weekly", 3)).lines}
    assert lines[sl.STOP_CREDIT].amount == D("9000.00")
    for credit, reason in ((D(-100), sif.NO_CREDIT), (D(0), sif.NO_CREDIT), (None, sif.CREDIT_UNKNOWN)):
        stops = sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, credit), sif.StageAt("weekly", 3))
        got = {x.kind: x for x in stops.lines}
        assert got[sl.STOP_CREDIT].amount is None and got[sl.STOP_CREDIT].reason == reason
        res = _results(pe.evaluate(body, _state(stops, D("-12000")), {}, None, gap_until="09:30"))
        assert res[sl.CREDIT_RULE] == pe.NotChecked(sl.CREDIT_RULE, sl.CREDIT_RULE, sl.not_checked_code(reason))
        assert isinstance(res["T-06"], pe.Flag)  # the max-loss stop is still checked and named
        assert pe.reason_text(sl.not_checked_code(reason))


def test_credit_line_has_catalogue_words():
    assert check.trigger_words(_ic_body(), sl.CREDIT_RULE) == ("Loss reached 2x the net credit collected so far", "Rs")


# fail closed: an unreadable stop value is "not checked", never a pass ------------------------------------------------
def test_unreadable_stop_value_is_not_checked():
    body = _ic_body()
    body["guards"]["stop_line_x_credit"] = "two"
    stops = sif.stops_of(_plan(body, before=False), sif.MoneyInputs(MAX_LOSS, CREDIT), sif.StageAt("weekly", 3))
    res = _results(pe.evaluate(body, _state(stops, D("-1")), {}, None, gap_until="09:30"))
    assert res[sl.CREDIT_RULE].code == sl.NOT_CHECKED_OTHER
