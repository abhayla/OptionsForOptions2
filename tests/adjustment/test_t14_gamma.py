
"""Stage B2 (goal contract ic-e2e-paper, design decision 8): T-14 gamma = the worst whole-position P&L change from
repricing at spot x 1.01 and x 0.99 (same IV, same clock) through the one engine (ADR-008), as a % of the margin
blocked; fires at >= the stage value. Margin absent / unreadable / not positive -> not checked, never passed.

Core proof: the real scenario position ADJ-02 (the base of PATH-01), its chain IVs and its clock; the engine figures
equal an independent per-leg Black-Scholes repricing written here within Rs 1.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

import pytest
from ofo.adjustment import gamma
from ofo.adjustment import playbook_eval as pe
from ofo.engine.black_scholes import bs_price, year_fraction
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import model_inputs
from ofo.marketdata.forward import spot_fallback_forward
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST
from test_adjust_scenarios import load
from test_playbook_eval import _row, body_of, evaluate, state_of

SC = load("ADJ-02")
SIGN = {"BUY": 1, "SELL": -1}


def _model(sc: dict = SC, clock: datetime.datetime | None = None, legs: list | None = None, iv_of=None):
    clock = clock or datetime.datetime.fromisoformat(sc["clock"]["ist"])
    spot, rate = D(sc["market"]["spot"]), D(sc["market"]["rate"])
    rows = legs if legs is not None else sc["position"]["legs"]
    ins = tuple(LegInput(underlying="NIFTY", contract=x["tradingsymbol"], action=Action(x["side"]),
                         instrument=Instrument(x["type"]), strike=D(x["strike"]),
                         expiry=datetime.date.fromisoformat(x["expiry"]), quantity=x["quantity"],
                         premium=D(x["entry"]), ltp=D(_row(sc, x)["ltp"]),
                         iv=(iv_of or (lambda r: D(r["iv"])))(_row(sc, x))) for x in rows)
    si = StrategyInput(underlying="NIFTY", valuation_time=clock, rate=rate, legs=ins,
                       spot=SpotReading(level=spot, at=clock, health=DataHealth.AVAILABLE))
    return model_inputs(si, {e: spot_fallback_forward(e, spot, clock, clock, rate, days_in_year=si.days_in_year,
                                                      spot_health=DataHealth.AVAILABLE)
                             for e in {x.expiry for x in ins}})


def _hand(level: D, sc: dict = SC, clock: datetime.datetime | None = None, legs: list | None = None) -> D:
    """Independent: sum over legs of side x qty x (BS value at ``level`` - BS value at spot), same IV, same clock."""
    clock = clock or datetime.datetime.fromisoformat(sc["clock"]["ist"])
    spot, rate = D(sc["market"]["spot"]), D(sc["market"]["rate"])
    total = D(0)
    for x in legs if legs is not None else sc["position"]["legs"]:
        years = year_fraction(clock, datetime.date.fromisoformat(x["expiry"]))
        iv, inst, k = D(_row(sc, x)["iv"]), Instrument(x["type"]), D(x["strike"])
        total += SIGN[x["side"]] * x["quantity"] * (bs_price(inst, level, k, years, rate, iv)
                                                     - bs_price(inst, spot, k, years, rate, iv))
    return total


def _t14(ev) -> list:
    return [r for r in ev.results if r.trigger_id == "T-14"]


def _state(**kw) -> pe.StrategyState:
    return replace(state_of(SC), gamma=gamma.gamma_figures(_model()), **kw)


def _limit() -> D:
    body = body_of(SC)
    ev = evaluate(body, _state(), {}, None)
    return D(body["triggers"]["T-14"][SC["expiry_kind"]][ev.stage_index])


# ---- core -----------------------------------------------------------------------------------------------------------
def test_core_adj02_engine_figures_equal_an_independent_repricing_within_one_rupee():
    figs = gamma.gamma_figures(_model())
    assert figs.reason is None and figs.levels == (D("23654.20"), D("23185.80"))
    assert abs(figs.up - _hand(D("23654.20"))) <= 1 and abs(figs.down - _hand(D("23185.80"))) <= 1, figs
    worst = min(figs.up, figs.down)
    value = -worst * 100 / D(SC["broker"]["margin"]["value"])
    hand_value = -min(_hand(D("23654.20")), _hand(D("23185.80"))) * 100 / D(SC["broker"]["margin"]["value"])
    assert abs(value - hand_value) * D(SC["broker"]["margin"]["value"]) / 100 <= 1
    t = _t14(evaluate(body_of(SC), _state(), {}, None))
    assert len(t) == 1 and not isinstance(t[0], pe.NotChecked), t
    assert isinstance(figs.up, D) and isinstance(figs.down, D)


def test_the_move_is_exactly_one_percent_up_and_down():
    assert D(1) == pe.GAMMA_MOVE_PCT
    assert gamma.gamma_figures(_model()).levels == (D("23654.20"), D("23185.80"))  # 23420 x 1.01 / x 0.99


# ---- crossing / not crossing (the real ADJ-02 figures, margin set either side of the stage value) -----------------
def _margin_at(lim: D) -> D:
    figs = gamma.gamma_figures(_model())
    return -min(figs.up, figs.down) * 100 / lim


def test_crossing_fires_at_exactly_the_stage_value_inclusive():
    lim = _limit()
    t = _t14(evaluate(body_of(SC), _state(margin=_margin_at(lim)), {}, None))
    assert len(t) == 1 and isinstance(t[0], pe.Flag) and t[0].threshold == lim and t[0].cmp == "ge", t
    assert lim <= t[0].value < lim + D("1e-20")


def test_exact_boundary_value_equal_to_the_stage_value_fires():
    lim = _limit()
    state = replace(state_of(SC), gamma=pe.GammaFigures(-lim * 1000, D("50"), None), margin=D("100000"))
    t = _t14(evaluate(body_of(SC), state, {}, None))
    assert len(t) == 1 and isinstance(t[0], pe.Flag) and t[0].value == lim, t
    below = replace(state, gamma=pe.GammaFigures(-lim * 1000 + D("0.01"), D("50"), None))
    assert _t14(evaluate(body_of(SC), below, {}, None)) == []


def test_not_crossing_one_rupee_more_margin_is_not_fired():
    lim = _limit()
    ev = evaluate(body_of(SC), _state(margin=_margin_at(lim) + 1), {}, None)
    t = _t14(ev)
    assert t == [] and ev.memory["T-14"]["seen_clear"] is True  # checked and clear: no entry, memory says clear


@pytest.mark.parametrize(("up", "down"), [(D("-5000"), D("120")), (D("120"), D("-5000"))])
def test_attack2_the_worst_side_is_read_whether_it_is_the_up_or_the_down_move(up, down):
    state = replace(state_of(SC), gamma=pe.GammaFigures(up, down, None), margin=D("100000"))
    t = _t14(evaluate(body_of(SC), state, {}, None))
    assert len(t) == 1 and isinstance(t[0], pe.Flag) and t[0].value == D(5), t  # 5000 / 100000 = 5% >= 3 or 2


# ---- answer states ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("margin", "code"), [
    (None, f"{pe.P}missing_margin"),
    (D("NaN"), pe.MARGIN_UNREADABLE),
    (D("Infinity"), pe.MARGIN_UNREADABLE),
    ("100000", pe.MARGIN_UNREADABLE),
    (D(0), f"{pe.P}margin_not_positive"),
    (D("-100000"), f"{pe.P}margin_not_positive"),
])
def test_margin_absent_unreadable_or_not_positive_is_not_checked_never_passed(margin, code):
    state = replace(state_of(SC), gamma=pe.GammaFigures(D("-99999"), D("-99999"), None), margin=margin)
    t = _t14(evaluate(body_of(SC), state, {}, None))
    assert t == [pe.NotChecked("T-14", "T-14", code)], t
    assert pe.reason_text(code)


def test_no_gamma_figures_live_mode_is_not_checked_yet_exactly_as_before():
    t = _t14(evaluate(body_of(SC), replace(state_of(SC), gamma=None), {}, None))
    assert t == [pe.NotChecked("T-14", "T-14", pe.T14_PENDING)]
    assert "1% move" in pe.reason_text(pe.GAMMA_UNKNOWN)


def test_a_leg_without_iv_or_no_model_gives_no_figures_never_zero():
    figs = gamma.gamma_figures(_model(iv_of=lambda r: None if r["type"] == "CE" else D(r["iv"])))
    assert (figs.up, figs.down, figs.reason) == (None, None, pe.GAMMA_UNKNOWN)
    assert gamma.gamma_figures(None).reason == pe.GAMMA_UNKNOWN
    t = _t14(evaluate(body_of(SC), replace(state_of(SC), gamma=figs), {}, None))
    assert t == [pe.NotChecked("T-14", "T-14", pe.GAMMA_UNKNOWN)]


def test_attack3_stale_prices_withhold_t14_like_every_other_rule():
    ev = evaluate(body_of(SC), _state(prices_fresh=False, margin=D(1)), {}, None)
    t = _t14(ev)
    assert t == [pe.NotChecked("T-14", "T-14", f"{pe.P}withheld_stale")], t
    assert ev.withheld


def test_attack4_one_side_left_after_an_exit_is_still_valued():
    calls = [x for x in SC["position"]["legs"] if x["type"] == "CE"]
    figs = gamma.gamma_figures(_model(legs=calls))
    assert figs.reason is None
    assert abs(figs.up - _hand(D("23654.20"), legs=calls)) <= 1
    assert abs(figs.down - _hand(D("23185.80"), legs=calls)) <= 1
    assert figs.up < 0 < figs.down  # a short call spread loses on the up move


def test_attack5_expiry_day_1529_uses_one_clock_for_base_and_both_moves():
    at = datetime.datetime(2026, 11, 9, 15, 29, tzinfo=IST)
    figs = gamma.gamma_figures(_model(clock=at))
    assert figs.reason is None and figs.at == at
    assert abs(figs.up - _hand(D("23654.20"), clock=at)) <= 1 and abs(figs.down - _hand(D("23185.80"), clock=at)) <= 1
