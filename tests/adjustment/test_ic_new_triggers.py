"""ADR-280: the 12 new iron condor triggers on the real system iron condor body, each switched on (ADR-276 (3): the
playbook keeps them OFF; the test copies the body and sets ``on: true``). Weekly, 3 days left = the "Middle" stage.
Each trigger: one case that fires and one that clears with the numbers worked by hand in the comment, plus its main
"not checked" case (never a pass, never a zero)."""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.adjustment import level_watch as lw
from ofo.adjustment import playbook_eval as pe
from ofo.engine.black_scholes import Greeks
from ofo.errors import render

SEED = Path(__file__).resolve().parents[2] / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
P = pe.P
MIDDLE = 3  # weekly days left inside the "Middle" stage (2..4)


def _ic_body() -> dict:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    return copy.deepcopy(next(x["body"] for x in seed["playbooks"] if x["strategy_type"] == "ic"))


def _body(tid: str, **override: object) -> dict:
    """The real IC body with ``tid`` switched on and a rule naming it; ``override`` sets trigger keys (task 21 sets the
    T-11c / T-20b limits and drops the greyed key in the playbook itself)."""
    body = _ic_body()
    t = body["triggers"][tid]
    t["on"] = True
    t.update(override)
    t.pop("greyed", None)
    body["rules"].append({"id": tid, "any_of": [tid]})
    return body


def _state(**kw: object) -> pe.StrategyState:
    base = {"expiry_kind": "weekly", "days_left": MIDDLE, "hhmm": "11:00", "spot": D("24000"), "prices_fresh": True}
    base.update(kw)
    return pe.StrategyState(stops=None, **base)  # type: ignore[arg-type]


def _answer(body: dict, state: pe.StrategyState, tid: str):
    """("fired", Flag) / ("clear", RuleValue) / ("not", NotChecked) for rule ``tid``."""
    ev = pe.evaluate(body, state, gap_until="09:30")
    for r in ev.results:
        if r.rule_id == tid:
            kind = "fired" if isinstance(r, pe.Flag) else "not" if isinstance(r, pe.NotChecked) else "other"
            return kind, r
    assert tid in ev.clear, (tid, ev.results)
    return "clear", next(v for v in ev.values if v.rule_id == tid)


def _g(delta: str = "0", theta: str = "0", vega: str = "0") -> Greeks:
    return Greeks(delta=D(delta), gamma=D(0), theta=D(theta), vega=D(vega))


def _held(*legs: tuple[str, str, str, str]) -> tuple[pe.HeldLeg, ...]:
    """(side, delta, theta, vega) per unit, 1 lot each."""
    return tuple(pe.HeldLeg(_g(d, t, v), side, 1) for side, d, t, v in legs)


# ---- T-04 net delta per lot (ADR-280 (1)); Middle limit 0.15 -----------------------------------------------------
def test_t04_fires_and_clears_on_net_delta_per_lot():
    body = _body("T-04")
    # SELL CE 0.45, BUY CE 0.20, SELL PE -0.10, BUY PE -0.05, 1 lot each: -0.45 + 0.20 + 0.10 - 0.05 = -0.20
    # -> 0.20 >= 0.15 fires
    kind, r = _answer(body, _state(held=_held(("SELL", "0.45", "0", "0"), ("BUY", "0.20", "0", "0"),
                                              ("SELL", "-0.10", "0", "0"), ("BUY", "-0.05", "0", "0"))), "T-04")
    assert kind == "fired" and r.value == D("0.20") and r.threshold == D("0.15")
    # SELL CE 0.35 instead: -0.35 + 0.20 + 0.10 - 0.05 = -0.10 -> 0.10 < 0.15 clears
    kind, r = _answer(body, _state(held=_held(("SELL", "0.35", "0", "0"), ("BUY", "0.20", "0", "0"),
                                              ("SELL", "-0.10", "0", "0"), ("BUY", "-0.05", "0", "0"))), "T-04")
    assert kind == "clear" and r.value == D("0.10") and not r.fired


def test_t04_without_leg_greeks_is_not_checked():
    body = _body("T-04")
    for held in (None, (), (pe.HeldLeg(None, "SELL", 1),)):
        kind, r = _answer(body, _state(held=held), "T-04")
        assert (kind, r.code) == ("not", pe.MISSING_LEG_DELTA)


def test_t04_stays_off_in_the_shipped_playbook():
    body = _ic_body()  # ADR-276 (3): OFF and named by no rule, so never answered
    assert body["triggers"]["T-04"]["on"] is False
    ev = pe.evaluate(body, _state(), gap_until="09:30")
    assert all(r.rule_id != "T-04" for r in ev.results) and "T-04" not in ev.clear


def test_unknown_data_kind_and_greyed_still_refuse():
    body = _body("T-04", data="feed")  # a data kind the evaluator does not read: refused as before
    assert _answer(body, _state(), "T-04")[1].code == f"{P}data_unavailable"
    body = _body("T-11c")
    body["triggers"]["T-11c"]["greyed"] = "Needs price history (not in V1)"  # task 21 removes it; until then refused
    assert _answer(body, _state(underlying="NIFTY", vix_percentile=D(90)), "T-11c")[1].code == f"{P}greyed"


# ---- open-leg triggers: lot size 75; IC SELL CE 24500 / BUY CE 24700 / SELL PE 23500 / BUY PE 23300, 1 lot each ----
LOT = 75


def _legs(ce_sell: str | None = "120", ce_buy: str | None = "40", pe_sell: str | None = "30",
          pe_buy: str | None = "10",
          entries: tuple[str | None, str | None, str | None, str | None] = ("100", "40", "90", "30")):
    ltps = (ce_sell, ce_buy, pe_sell, pe_buy)
    shape = (("CE", "SELL", "24500"), ("CE", "BUY", "24700"), ("PE", "SELL", "23500"), ("PE", "BUY", "23300"))
    return tuple(pe.OpenLeg(k, s, D(st), 1, None if e is None else D(e), None if p is None else D(p))
                 for (k, s, st), e, p in zip(shape, entries, ltps, strict=True))


def _code(body: dict, state: pe.StrategyState, tid: str) -> str:
    kind, r = _answer(body, state, tid)
    assert kind == "not", (kind, r)
    return r.code.removeprefix(P)


def test_t05_side_value_ratio():
    body = _body("T-05")  # Middle limit 3
    # CE (120 - 40) x 75 = 6000; PE (30 - 10) x 75 = 1500; 6000 / 1500 = 4 >= 3 fires
    kind, r = _answer(body, _state(open_legs=_legs(), lot_size=LOT), "T-05")
    assert kind == "fired" and r.value == D(4) and r.threshold == D(3)
    # CE SELL at 80: (80 - 40) x 75 = 3000; 3000 / 1500 = 2 < 3 clears
    kind, r = _answer(body, _state(open_legs=_legs(ce_sell="80"), lot_size=LOT), "T-05")
    assert kind == "clear" and r.value == D(2)
    # PE side (10 - 10) x 75 = 0: no ratio; a leg unpriced; no lot size; no legs
    assert _code(body, _state(open_legs=_legs(pe_sell="10"), lot_size=LOT), "T-05") == "side_value_not_positive"
    assert _code(body, _state(open_legs=_legs(ce_buy=None), lot_size=LOT), "T-05") == "missing_leg_price"
    assert _code(body, _state(open_legs=_legs()), "T-05") == "missing_lot_size"
    assert _code(body, _state(lot_size=LOT), "T-05") == "missing_open_legs"


def test_t06b_loss_vs_credit():
    body = _body("T-06b")  # weekly Middle limit 1
    # credit = (100 - 40 + 90 - 30) x 75 = 9000; pnl -9000 -> loss 9000 / 9000 = 1 >= 1 fires (inclusive)
    kind, r = _answer(body, _state(open_legs=_legs(), lot_size=LOT, pnl=D(-9000)), "T-06b")
    assert kind == "fired" and r.value == D(1)
    # pnl -8000 -> 8000 / 9000 = 0.888.. < 1 clears; a profit -> loss 0 -> clears
    for pnl in ("-8000", "500"):
        kind, r = _answer(body, _state(open_legs=_legs(), lot_size=LOT, pnl=D(pnl)), "T-06b")
        assert kind == "clear" and not r.fired
    # a debit: (40 - 100 + 30 - 90) x 75 = -9000 -> no credit, not checked
    debit = _legs(entries=("40", "100", "30", "90"))
    assert _code(body, _state(open_legs=debit, lot_size=LOT, pnl=D(-9000)), "T-06b") == "no_credit"
    no_entry = _legs(entries=("100", None, "90", "30"))
    assert _code(body, _state(open_legs=no_entry, lot_size=LOT, pnl=D(-1)), "T-06b") == "missing_leg_entry"
    assert _code(body, _state(open_legs=_legs(), lot_size=LOT), "T-06b") == "missing_pnl"


def test_t08_short_leg_stop():
    body = _body("T-08")  # Middle limit 2
    # SELL CE entry 100 ltp 210 -> 2.1; SELL PE 90 -> 30 = 0.33; BUY CE 40 -> 400 (10x) is a long: ignored. 2.1 >= 2
    kind, r = _answer(body, _state(open_legs=_legs(ce_sell="210", ce_buy="400")), "T-08")
    assert kind == "fired" and r.value == D("2.1")
    # SELL CE ltp 190 -> 1.9 < 2 clears
    kind, r = _answer(body, _state(open_legs=_legs(ce_sell="190", ce_buy="400")), "T-08")
    assert kind == "clear" and r.value == D("1.9")
    assert _code(body, _state(open_legs=_legs(pe_sell=None)), "T-08") == "missing_short_price"
    assert _code(body, _state(open_legs=_legs(entries=("0", "40", "90", "30"))), "T-08") == "entry_not_positive"


# ---- VIX / history triggers ------------------------------------------------------------------------------------
def test_t11b_vix_up_today():
    body = _body("T-11b")  # data "vix", limit 10 %
    # (13.2 - 12) x 100 / 12 = 10 >= 10 fires
    kind, r = _answer(body, _state(vix=D("13.2"), vix_prev_close=D(12)), "T-11b")
    assert kind == "fired" and r.value == D(10)
    # (13.1 - 12) x 100 / 12 = 9.1666.. < 10 clears; a fall (11 vs 12 = -8.33 %) clears, never an absolute move
    for now in ("13.1", "11"):
        kind, r = _answer(body, _state(vix=D(now), vix_prev_close=D(12)), "T-11b")
        assert kind == "clear" and not r.fired
    assert _code(body, _state(vix=D(13), vix_prev_close=D(0)), "T-11b") == "vix_prev_close_not_positive"
    assert _code(body, _state(vix_prev_close=D(12)), "T-11b") == "missing_vix"
    assert _code(body, _state(vix=D(13)), "T-11b") == "missing_vix_prev_close"


def test_t11c_vix_percentile():
    body = _body("T-11c")  # data "hist", limit 80
    kind, r = _answer(body, _state(underlying="NIFTY", vix_percentile=D(85)), "T-11c")  # 85 >= 80 fires
    assert kind == "fired" and r.value == D(85)
    kind, r = _answer(body, _state(underlying="NIFTY", vix_percentile=D("79.5")), "T-11c")  # 79.5 < 80 clears
    assert kind == "clear"
    assert _code(body, _state(underlying="SENSEX", vix_percentile=D(85)), "T-11c") == "sensex_no_vix"
    assert _code(body, _state(underlying="NIFTY"), "T-11c") == "missing_vix_percentile"
    assert _code(body, _state(underlying="NIFTY", vix_percentile=D(101)), "T-11c") == "vix_percentile_unusable"
    assert _code(body, _state(vix_percentile=D(85)), "T-11c") == "missing_underlying"


def test_t20b_adx_trending():
    limits = ["25", "25", "25"]  # ADR-280 (12); task 21 writes them into the playbook
    body = _body("T-20b", weekly=limits, monthly=limits, cmp="ge")
    assert _answer(body, _state(adx=D(25)), "T-20b")[0] == "fired"  # 25 >= 25 fires (inclusive)
    kind, r = _answer(body, _state(adx=D(24)), "T-20b")  # 24 < 25 clears
    assert kind == "clear" and r.value == D(24)
    assert _code(body, _state(), "T-20b") == "missing_adx"
    assert _code(body, _state(adx=D(-1)), "T-20b") == "adx_unusable"
    # task 21: the shipped IC body now carries the ADR-280 limit (25), so ADX 40 fires with no override
    assert _answer(_body("T-20b"), _state(adx=D(40)), "T-20b")[0] == "fired"


# ---- T-12 move in expected moves -------------------------------------------------------------------------------
def test_t12_move_since_entry_in_sd():
    body = _body("T-12")  # limit 1 SD
    entry = {"entry_spot": D(24000), "entry_atm_iv": D("0.12"), "entry_day": datetime.date(2026, 11, 3),
             "expiry": datetime.date(2026, 11, 10)}
    # SD = 24000 x 0.12 x sqrt(7 / 365) = 2880 x 0.138487 = 398.84; 400 / 398.84 = 1.0029 >= 1 fires
    kind, r = _answer(body, _state(spot=D(24400), **entry), "T-12")
    assert kind == "fired" and D("1.002") < r.value < D("1.003")
    # 398 down / 398.84 = 0.9979 < 1 clears (the move is absolute: down counts as up)
    kind, r = _answer(body, _state(spot=D(23602), **entry), "T-12")
    assert kind == "clear" and D("0.997") < r.value < D("0.998")
    same_day = {**entry, "expiry": entry["entry_day"]}  # 0 calendar days: no expected move
    assert _code(body, _state(**same_day), "T-12") == "expected_move_unusable"
    assert _code(body, _state(**{**entry, "entry_spot": None}), "T-12") == "missing_entry_spot"
    assert _code(body, _state(**{**entry, "expiry": None}), "T-12") == "missing_expiry"
    assert _code(body, _state(**{**entry, "entry_day": None}), "T-12") == pe.MISSING_ENTRY_DAY.removeprefix(P)


# ---- Greeks triggers: per unit (theta per calendar day, vega per 1 vol point), x lots x sign x lot size -----------
IC_GREEKS = _held(("SELL", "0", "-4", "5"), ("BUY", "0", "-2", "3"), ("SELL", "0", "-3", "4"), ("BUY", "0", "-1", "2"))


def test_t14t_theta_vs_premium_left():
    body = _body("T-14t")  # weekly limit 5 %, le
    # theta: +4 - 2 + 3 - 1 = 4 per unit-lot x 75 = Rs 300 a day; 300 x 100 / 9000 = 3.33 % <= 5 fires (decay too slow)
    kind, r = _answer(body, _state(held=IC_GREEKS, lot_size=LOT, premium_left=D(9000)), "T-14t")
    assert kind == "fired" and r.cmp == "le" and D("3.33") < r.value < D("3.34")
    # 300 x 100 / 5000 = 6 % > 5 clears
    kind, r = _answer(body, _state(held=IC_GREEKS, lot_size=LOT, premium_left=D(5000)), "T-14t")
    assert kind == "clear" and r.value == D(6)
    assert _code(body, _state(held=IC_GREEKS, lot_size=LOT, premium_left=D(0)), "T-14t") == "no_premium_left"
    no_greeks = (pe.HeldLeg(None, "SELL", 1),)
    assert _code(body, _state(held=no_greeks, lot_size=LOT, premium_left=D(1)), "T-14t") == "missing_leg_greeks"
    assert _code(body, _state(held=IC_GREEKS, premium_left=D(1)), "T-14t") == "missing_lot_size"


def test_t14v_vega_risk_vs_max_profit():
    body = _body("T-14v")  # weekly limit 10 %
    # vega: -5 + 3 - 4 + 2 = -4 per unit-lot x 75 = Rs -300 per vol point -> loss 300; 300 x 100 / 2000 = 15 % >= 10
    kind, r = _answer(body, _state(held=IC_GREEKS, lot_size=LOT, max_profit=D(2000)), "T-14v")
    assert kind == "fired" and r.value == D(15)
    # 300 x 100 / 4000 = 7.5 % < 10 clears
    kind, r = _answer(body, _state(held=IC_GREEKS, lot_size=LOT, max_profit=D(4000)), "T-14v")
    assert kind == "clear" and r.value == D("7.5")
    # net long vega (a rise helps): loss 0 -> 0 % clears, never negative
    kind, r = _answer(body, _state(held=_held(("BUY", "0", "-1", "5")), lot_size=LOT, max_profit=D(4000)), "T-14v")
    assert kind == "clear" and r.value == D(0)
    assert _code(body, _state(held=IC_GREEKS, lot_size=LOT, max_profit=pe.UNLIMITED), "T-14v") == \
        "max_profit_not_finite"


def test_t15_margin_used():
    body = _body("T-15")  # limit 80 %
    # 80000 x 100 / (80000 + 20000) = 80 >= 80 fires (inclusive)
    kind, r = _answer(body, _state(margin=D(80000), available_margin=D(20000)), "T-15")
    assert kind == "fired" and r.value == D(80)
    # 80000 x 100 / 120000 = 66.67 < 80 clears
    assert _answer(body, _state(margin=D(80000), available_margin=D(40000)), "T-15")[0] == "clear"
    assert _code(body, _state(margin=D(80000)), "T-15") == "missing_available_margin"
    assert _code(body, _state(available_margin=D(1)), "T-15") == "missing_margin"
    assert _code(body, _state(margin=D(80000), available_margin=D(-90000)), "T-15") == "margin_room_not_positive"


# ---- T-20 level watch (ADR-242's watches, no second store) -----------------------------------------------------
def test_t20_level_watch():
    body = _body("T-20")  # data "user", no stage values
    above = (lw.LevelWatch("above", D(24100)),)
    kind, r = _answer(body, _state(spot=D(24100), watches=above), "T-20")  # 24100 >= 24100 fires
    assert kind == "fired" and (r.value, r.threshold, r.cmp) == (D(24100), D(24100), "ge")
    kind, r = _answer(body, _state(spot=D(24000), watches=above), "T-20")  # 24000 < 24100 clears
    assert kind == "clear" and not r.fired
    assert _code(body, _state(), "T-20") == "no_level_watch"


NEW_CODES = ("missing_open_legs", "missing_lot_size", "missing_leg_price", "side_value_not_positive",
             "missing_leg_entry", "no_credit", "entry_not_positive", "missing_vix", "missing_vix_prev_close",
             "vix_prev_close_not_positive", "missing_underlying", "sensex_no_vix", "missing_vix_percentile",
             "vix_percentile_unusable", "missing_entry_spot", "missing_expiry", "expected_move_unusable",
             "missing_leg_greeks", "no_premium_left", "missing_available_margin", "margin_room_not_positive",
             "no_level_watch", "missing_adx", "adx_unusable")


@pytest.mark.parametrize("code", NEW_CODES)
def test_every_new_reason_is_in_the_catalogue(code):
    assert render(f"{P}{code}").what_happened
