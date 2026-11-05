"""GC-IC1 step 6a (REQ-159 AC-5, ADR-240 (3)): S-02 "Trending day" (net delta per lot at or beyond +/-0.15, engine
Greeks) and S-12 "Big win early" (profit at or above 40% of max profit on the entry session) are rules the evaluator
reports as yes/no gate readings; each opens one record per episode through ``alert_gate.step`` naming its approaches.
Thresholds are named code constants (never a body key). Pure: no DB, no clock read."""
from __future__ import annotations

import copy
import dataclasses
import datetime
import json
import pathlib
import re
from decimal import Decimal as D

import pytest
from ofo.adjustment import alert_gate, gate_readings
from ofo.adjustment import playbook_eval as pe
from ofo.engine import adjust_ratios as ratios
from ofo.engine.black_scholes import Greeks
from ofo.engine.legs import Action
from ofo.settings import calc, defaults as settings_defaults
from ofo.strategy.settings_value import IDENTIFIER_PATTERN
from ofo.timeutil import IST

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
PRE = pathlib.Path(__file__).with_name("pre1a_ic_body.json")  # the 37824fb9 system iron condor, saved before 6a
GAP = "09:30"
S02 = "sit.S-02"
S12 = "sit.S-12"
ROLLS = ("A-01", "A-02", "A-05", "A-04", "A-06")  # the iron condor playbook's roll approaches, playbook order
DAY1 = datetime.date(2026, 10, 28)
Z = D(0)
DEFAULTS_S02 = calc.situation_net_delta_per_lot(settings_defaults())
DEFAULTS_S12 = calc.situation_big_win_percent(settings_defaults())


def _ic() -> dict:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
    return copy.deepcopy(next(r["body"] for r in rows if r["strategy_type"] == "ic"))


def _g(delta: str | None) -> Greeks | None:
    return None if delta is None else Greeks(D(delta), Z, Z, Z)


def _held(call_short: str | None = "0.45", lots: int = 2) -> tuple[pe.HeldLeg, ...]:
    """An iron condor, ``lots`` lots a leg: net per lot = -call_short + 0.20 + 0.10 - 0.05 (0.45 -> -0.20)."""
    return (pe.HeldLeg(_g("-0.05"), "BUY", lots), pe.HeldLeg(_g("-0.10"), "SELL", lots),
            pe.HeldLeg(_g(call_short), "SELL", lots), pe.HeldLeg(_g("0.20"), "BUY", lots))


def _state(**kw) -> pe.StrategyState:
    base = {"expiry_kind": "weekly", "days_left": 5, "hhmm": "11:00", "spot": D(23100), "prices_fresh": True,
            "shorts": (pe.ShortLeg(D(22600), D("0.10"), D(20)), pe.ShortLeg(D(23450), D("0.45"), D(60))),
            "held": _held(), "today": DAY1, "entry_day": DAY1 + datetime.timedelta(days=1),
            "pnl": D(1000), "max_profit": D(10000), "max_loss": D(20000), "adjustments_used": 0,
            "s02_delta_per_lot": DEFAULTS_S02, "s12_percent": DEFAULTS_S12, "stops": None}  # registry defaults
    base.update(kw)
    return pe.StrategyState(**base)


def _ev(body=None, **kw) -> pe.Evaluation:
    return pe.evaluate(_ic() if body is None else body, _state(**kw), gap_until=GAP)


def _value(ev: pe.Evaluation, rid: str):
    return next((v for v in ev.values if v.rule_id == rid), None)


def _reading(ev: pe.Evaluation, rid: str):
    got = gate_readings.readings(ev).get(rid)
    return None if got is None else got[1]


def _results(ev: pe.Evaluation, rid: str) -> list:
    return [r for r in ev.results if r.rule_id == rid]


# ---- S-02 ------------------------------------------------------------------------------------------------------------
def test_core_s02_beyond_015_reads_true_and_names_the_playbook_rolls():
    ev = _ev()
    v = _value(ev, S02)
    assert v.fired is True and v.yes_no is True and v.value == D("0.20") and v.threshold == D("0.15")
    assert v.approaches == ROLLS
    spec, reading = gate_readings.readings(ev)[S02]
    assert spec.cmp == "bool" and spec.ladder == () and reading is True
    assert [type(r).__name__ for r in _results(ev, S02)] == ["Flag"]


def test_s02_at_014_reads_false_and_no_approaches():
    ev = _ev(held=_held("0.39"))  # net -0.28 over 2 lots = 0.14
    v = _value(ev, S02)
    assert v.fired is False and v.value == D("0.14") and v.approaches == () and S02 in ev.clear
    assert _reading(ev, S02) is False


def test_s02_exactly_015_fires_inclusive():
    v = _value(_ev(held=_held("0.40")), S02)  # net -0.30 / 2 = 0.15
    assert v.value == D("0.15") and v.fired is True


def test_s02_beyond_minus_015_fires_too():
    held = (pe.HeldLeg(_g("-0.45"), "SELL", 2), pe.HeldLeg(_g("-0.20"), "BUY", 2),
            pe.HeldLeg(_g("0.10"), "SELL", 2), pe.HeldLeg(_g("0.05"), "BUY", 2))  # net +0.40 / 2 = 0.20
    assert _value(_ev(held=held), S02).fired is True


def test_attack3_per_lot_divides_by_the_largest_legs_lots_not_the_leg_count():
    # 2 lots a leg, 4 legs: per lot 0.20 (dividing by 4 legs would read 0.10, under the threshold)
    assert ratios.net_delta_per_lot([(_g("0.45"), Action.SELL, 2), (_g("0.20"), Action.BUY, 2),
                                     (_g("-0.10"), Action.SELL, 2), (_g("-0.05"), Action.BUY, 2)]) == (D("0.40"), D(2))
    # 1 lot a leg: same per-lot figure
    assert _value(_ev(held=_held(lots=1)), S02).value == D("0.20")
    # unequal lots: the largest leg's lots (3) is the denominator
    held = (pe.HeldLeg(_g("0.30"), "SELL", 3), pe.HeldLeg(_g("0.10"), "BUY", 1))
    v = _value(_ev(held=held), S02)
    assert (v.value.quantize(D("0.0001")), v.fired) == (D("0.2667"), True)


def test_attack4_a_missing_leg_delta_is_no_reading_never_zero():
    ev = _ev(held=_held(None))
    assert _reading(ev, S02) is None and S02 not in ev.clear and _value(ev, S02) is None
    assert [r.code for r in _results(ev, S02)] == [pe.MISSING_LEG_DELTA]
    assert pe.reason_text(pe.MISSING_LEG_DELTA)
    ev = _ev(held=None)  # the legs were not read at all
    assert _reading(ev, S02) is None and [r.code for r in _results(ev, S02)] == [pe.MISSING_LEG_DELTA]


def test_s02_withheld_prices_read_none():
    ev = _ev(prices_fresh=False)
    assert _reading(ev, S02) is None and [r.code for r in _results(ev, S02)] == [f"{pe.P}withheld_stale"]


def test_s02_at_the_adjustment_limit_offers_no_roll_so_no_reading():
    ev = _ev(adjustments_used=2)  # S-11: only exit and reduce are offered
    assert _results(ev, S02) == [] and _reading(ev, S02) is None


def test_attack1_a_body_saved_before_6a_fires_s02_and_s12_without_a_new_key():
    body = json.loads(PRE.read_text(encoding="utf-8"))
    text = json.dumps(body)
    assert "net_delta" not in text and "pct_of_max_profit_day1" not in text and "situation_rules" not in text
    ev = pe.evaluate(body, _state(entry_day=DAY1, pnl=D(4000)), gap_until=GAP)
    assert _value(ev, S02).fired is True and _value(ev, S12).fired is True


def test_a_body_without_the_situation_gives_no_reading():
    body = _ic()
    body["situations"] = [s for s in body["situations"] if s["id"] not in ("S-02", "S-12")]
    ev = pe.evaluate(body, _state(entry_day=DAY1, pnl=D(4000)), gap_until=GAP)
    assert _reading(ev, S02) is None and _reading(ev, S12) is None and _results(ev, S02) == []


# ---- S-12 ------------------------------------------------------------------------------------------------------------
def test_core_s12_on_the_entry_session_at_40_pct_reads_true_and_names_a24_a25():
    ev = _ev(entry_day=DAY1, pnl=D(4000))
    v = _value(ev, S12)
    assert v.fired is True and v.yes_no is True and v.value == D(40) and v.threshold == D(40)
    assert v.approaches == ("A-24", "A-25") and _reading(ev, S12) is True


def test_s12_same_day_at_39_pct_reads_false():
    ev = _ev(entry_day=DAY1, pnl=D(3900))
    assert _value(ev, S12).fired is False and _reading(ev, S12) is False and S12 in ev.clear


def test_attack2_s12_next_session_at_45_pct_gives_no_reading():
    ev = _ev(entry_day=DAY1, today=DAY1 + datetime.timedelta(days=1), pnl=D(4500))
    assert _results(ev, S12) == [] and _reading(ev, S12) is None and S12 not in ev.clear


def test_s12_against_max_profit_not_max_loss():
    # 4000 is 40% of max profit 10000 but only 20% of max loss 20000
    assert _value(_ev(entry_day=DAY1, pnl=D(4000), max_profit=D(10000), max_loss=D(20000)), S12).fired is True
    assert _value(_ev(entry_day=DAY1, pnl=D(4000), max_profit=D(20000), max_loss=D(10000)), S12).fired is False


@pytest.mark.parametrize(("change", "code"), [
    ({"entry_day": None}, pe.MISSING_ENTRY_DAY),
    ({"today": None}, f"{pe.P}missing_clock"),
    ({"max_profit": None}, f"{pe.P}missing_max_profit"),
    ({"max_profit": pe.UNLIMITED}, f"{pe.P}max_profit_not_finite"),
    ({"pnl": None}, f"{pe.P}missing_pnl"),
])
def test_s12_answer_states_read_none_with_a_reason(change, code):
    kw = {"entry_day": DAY1, "pnl": D(4500), **change}
    ev = _ev(**kw)
    assert _reading(ev, S12) is None and [r.code for r in _results(ev, S12)] == [code]
    assert pe.reason_text(code)


# ---- the gate: one record per episode ---------------------------------------------------------------------------
def _run(states) -> list:
    gs = alert_gate.initial_state()
    opened = []
    for minute, st in states:
        ev = pe.evaluate(_ic(), st, gap_until=GAP)
        at = datetime.datetime(2026, 10, 28, 11, minute, 1, tzinfo=IST)
        gs, events = alert_gate.step(gs, now=at, preset=alert_gate.INTRADAY, readings=gate_readings.readings(ev))
        opened += [e for e in events if isinstance(e, alert_gate.Opened)]
    return opened


def test_the_gate_opens_one_s02_record_per_episode():
    held = [_held("0.39")] + [_held("0.45")] * 5 + [_held("0.39")] * 2
    opened = _run([(m, _state(held=h)) for m, h in enumerate(held)])
    assert [e.rule_id for e in opened if e.rule_id == S02] == [S02]


def test_the_gate_opens_one_s12_record_per_episode():
    pnl = [3900, 4000, 4200, 4500, 4600, 4700]  # under, then at or above 40% for five checks
    opened = _run([(m, _state(entry_day=DAY1, pnl=D(p))) for m, p in enumerate(pnl)])
    assert [e.rule_id for e in opened if e.rule_id == S12] == [S12]


# ---- the generator cases (scenario numbers -> the evaluator) -------------------------------------------------------
def _scenario_state(sc: dict) -> pe.StrategyState:
    from test_playbook_eval import _row, state_of  # noqa: PLC0415 - the scenario state the screen tests use
    held = tuple(pe.HeldLeg(_g(str(_row(sc, x)["delta"])), x["side"], x["lots"]) for x in sc["position"]["legs"])
    clock = datetime.datetime.fromisoformat(sc["clock"]["ist"]).date()
    entry = datetime.datetime.fromisoformat(sc["position"]["entry"]["clock"]).date()
    whole = sc["expected"]["at_expiry_whole_trade"]
    return dataclasses.replace(state_of(sc), held=held, today=clock, entry_day=entry,
                               max_profit=D(whole["max_profit"]), adjustments_used=0,
                               s02_delta_per_lot=DEFAULTS_S02, s12_percent=DEFAULTS_S12)


@pytest.mark.parametrize("case", ["ADJ-56", "ADJ-57", "ADJ-58", "ADJ-59"])
def test_generator_case_matches_its_engine_free_expected_block(case):
    from test_adjust_scenarios import load  # noqa: PLC0415 - the scenario library's loader
    from test_playbook_eval import body_of  # noqa: PLC0415
    sc = load(case)
    want = sc["expected"]["situation_rules"]
    ev = pe.evaluate(body_of(sc), _scenario_state(sc), gap_until=GAP)
    for rid, w in want.items():
        got = _reading(ev, rid)
        assert got is w["fires"], (case, rid, got, w)
        if w["fires"] is None:
            continue
        v = _value(ev, rid)
        assert list(v.approaches) == w["approaches"]
        assert format(v.value.quantize(D("0.0001")), "f") == w["value"]


# ---- GC-IC1 fix: every produced rule id fits the API's Identifier pattern (ADR-069) --------------------------------
def _produced_ids(body: dict) -> set[str]:
    ids: set[str] = set()
    for kw in ({}, {"days_left": 0, "hhmm": "14:30"}, {"days_left": 0, "hhmm": "15:00"},
               {"entry_day": DAY1, "pnl": D(6000)}, {"held": _held("0.10")}):
        ev = _ev(body, **kw)
        ids |= {r.rule_id for r in ev.results} | {v.rule_id for v in ev.values}
    return ids


def test_guard_every_rule_id_the_evaluator_produces_matches_the_identifier_pattern():

    pre = json.loads(PRE.read_text(encoding="utf-8"))
    bodies = (_ic(), pre.get("body", pre))
    ids = set().union(*(_produced_ids(b) for b in bodies))
    assert S02 in ids and S12 in ids and "day.expiry.1430.5" in ids, sorted(ids)  # the guard saw both kinds
    assert r"[A-Za-z0-9_.-]{1,64}" == IDENTIFIER_PATTERN  # the shared pattern is not loosened
    bad = sorted(i for i in ids if re.fullmatch(IDENTIFIER_PATTERN, i) is None)
    assert bad == [], bad


def test_old_stored_colon_ids_are_read_without_crash_and_never_match_a_rule():
    body = _ic()
    assert pe.is_day_rule_id("day:expiry:14:30:5") and pe.is_situation_rule_id("sit:S-02")
    assert pe.day_rule_action(body, "day:expiry:14:30:5") is None  # not re-opened as a rule of today's form
    assert pe.day_rule_action(body, "day.expiry.1430.5") == 5  # noqa: PLR2004


# ---- REQ-167 AC-4 (GC-IC1 step 10 round 2): the two numbers are settings, not code ---------------------------------
def test_the_registry_defaults_are_todays_numbers():
    assert (D("0.15"), D(40)) == (DEFAULTS_S02, DEFAULTS_S12)


def test_s02_follows_the_setting_with_no_restart():
    # net per lot of the default held legs is -0.20: opens at the default 0.15, stays shut when the setting is 0.25
    assert _reading(_ev(), S02) is True
    assert _reading(_ev(s02_delta_per_lot=D("0.25")), S02) is False
    assert _reading(_ev(s02_delta_per_lot=D("0.20")), S02) is True  # inclusive at the setting


def test_s12_follows_the_setting_with_no_restart():
    same_day = {"today": DAY1, "entry_day": DAY1}  # profit 1000 of 10000 = 10%
    assert _reading(_ev(**same_day), S12) is False
    assert _reading(_ev(s12_percent=D(10), **same_day), S12) is True
    assert _reading(_ev(s12_percent=D(11), **same_day), S12) is False


@pytest.mark.parametrize("rid, key, extra", [(S02, "s02_delta_per_lot", {}),
                                             (S12, "s12_percent", {"today": DAY1, "entry_day": DAY1})])
def test_a_setting_not_read_fails_closed_with_a_named_reason(rid, key, extra):
    ev = _ev(**{key: None}, **extra)
    assert _reading(ev, rid) is None
    [r] = _results(ev, rid)
    assert isinstance(r, pe.NotChecked) and r.code == pe.SETTING_UNAVAILABLE
    assert r.code == "adjust_trigger_situation_setting_unavailable"


def test_the_situation_numbers_are_not_module_constants_any_more():
    assert not hasattr(pe, "S02_NET_DELTA_PER_LOT") and not hasattr(pe, "S12_PCT_OF_MAX_PROFIT")


# ---- REQ-168 AC-4: the gap-at-open line names the user's own time ---------------------------------------------------
@pytest.mark.parametrize("until", ["09:30", "10:00", "15:30"])
def test_the_gap_after_open_line_names_the_preference(until):
    from ofo.errors import render  # noqa: PLC0415
    ev = pe.evaluate(_ic(), _state(hhmm="15:31" if until == "15:30" else "15:20" if until != "09:30" else "11:00"),
                     gap_until=until)
    hit = [r for r in ev.results if isinstance(r, pe.NotChecked) and r.code == "adjust_trigger_gap_after_open"]
    assert hit, "T-13 must be not checked after the gap time"
    err = render(hit[0].code, **dict(hit[0].slots))
    assert f"checked only until {until}." in err.what_happened
    assert "09:30" not in err.what_happened or until == "09:30"
