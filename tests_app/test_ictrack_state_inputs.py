"""GC-ICTRACK task 14a: the ONE state build (``adjustment_check.state_of``: screen check, worker, playbook test route)
fills ADR-280's position-derived inputs and copies the five market-wide inputs from ``MarketInputs.regime``, so the 12
new IC triggers evaluate on a real position (ADJ-02's legs) instead of answering ``missing_open_legs``. No DB."""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import t19_support as s
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import EntryFacts
from ofo.marketdata.spot_source import SpotAnswer
from ofo.settings import layers
from ofo_app import adjustment_check as check
from ofo_app.regime_inputs import RegimeInputs

SC = s.load("ADJ-02")


def state(market=None, facts=None, sc: dict = SC) -> pe.StrategyState:
    tracked, m, spot = s.inputs(sc)
    m = market or m
    return check.state_of(tracked, m, SpotAnswer(spot, "feed", m.now), None, s.RATES, True, s.body_of(sc),
                          config=s.PREFS.approach, user_values=None, strategy_layer=None, entry_facts=facts,
                          resolved=None)


def switched_on(sc: dict, *ids: str) -> dict:
    """The scenario's playbook with ``ids`` switched on and a rule naming each (the playbook keeps them off)."""
    body = s.body_of(sc)
    for t in ids:
        body["triggers"][t]["on"] = True
        body["triggers"][t].pop("greyed", None)
        body["rules"].append({"id": t, "any_of": [t]})
    return body


def answers(body: dict, st: pe.StrategyState, *ids: str) -> dict:
    ev = pe.evaluate(body, st, gap_until="09:30")
    got = {r.rule_id: r for r in ev.results if r.rule_id in ids}
    got.update({v.rule_id: v for v in ev.values if v.rule_id in ids and v.rule_id not in got})
    assert set(got) == set(ids), (ids, ev.results)
    return got


def test_core_position_fields_reach_the_state_from_adj02_legs():
    st = state(facts=EntryFacts(D("23400"), D("300"), D("300")))
    legs = [x for x in SC["position"]["legs"] if x["type"] != "FUT"]
    assert st.open_legs is not None and len(st.open_legs) == len(legs) > 0
    assert {(o.kind, o.side, o.strike, o.lots, o.entry) for o in st.open_legs} == \
        {(x["type"], x["side"], D(x["strike"]), x["lots"], D(x["entry"])) for x in legs}
    assert all(o.ltp is not None for o in st.open_legs)  # ADJ-02's legs are all priced
    assert (st.lot_size, st.underlying, st.expiry.isoformat(), st.entry_spot) == \
        (SC["lot"], SC["underlying"], SC["expiry"], D("23400"))


def test_core_t08_and_t05_evaluate_on_adj02_never_missing_open_legs():
    got = answers(switched_on(SC, "T-08", "T-05"), state(), "T-08", "T-05")
    for r in got.values():
        assert not isinstance(r, pe.NotChecked), r  # before: missing_open_legs


def test_entry_spot_none_without_entry_facts_or_when_unreadable():
    assert state().entry_spot is None
    assert state(facts=layers.Unreadable("entry_facts_unreadable")).entry_spot is None


def test_no_regime_read_leaves_the_five_inputs_none_and_a_read_is_copied():
    st = state()
    assert (st.available_margin, st.vix, st.vix_prev_close, st.vix_percentile, st.adx) == (None,) * 5
    _, m, _ = s.inputs(SC)
    r = RegimeInputs(D("150000"), D("16.8"), D("15"), D("72.4"), D("27.1"))
    st = state(dataclasses.replace(m, regime=r))
    assert (st.available_margin, st.vix, st.vix_prev_close, st.vix_percentile, st.adx) == \
        (D("150000"), D("16.8"), D("15"), D("72.4"), D("27.1"))


def test_t11_evaluates_on_a_live_mode_state_from_the_stored_entry_iv():
    """GC-ICTRACK task 10 (ADR-270 (1)): no scenario in this process (live mode), entry facts carry the entry ATM IV
    -> T-11 is checked against it; facts without an IV -> T-11 says so (missing_entry_atm_iv), never a pass."""
    from ofo_app import scenario_mode  # noqa: PLC0415
    assert scenario_mode.current() is None
    _t, m, _spot = s.inputs(SC)
    live = dataclasses.replace(m, vol=D("0.1550"))  # the current ATM IV the market reader gives
    with_iv = state(market=live, facts=EntryFacts(D("23400"), D("300"), D("300"), entry_atm_iv=D("0.1432")))
    assert with_iv.entry_atm_iv == D("0.1432")
    got = answers(switched_on(SC, "T-11"), with_iv, "T-11")["T-11"]
    assert not isinstance(got, pe.NotChecked), got
    without = state(market=live, facts=EntryFacts(D("23400"), D("300"), D("300")))
    got = answers(switched_on(SC, "T-11"), without, "T-11")["T-11"]
    assert isinstance(got, pe.NotChecked) and got.code.endswith("missing_entry_atm_iv"), got
