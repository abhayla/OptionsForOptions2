# ruff: noqa: PLR2004, E501 - strikes, lots and counts of the scenario cases; catalogue texts quoted whole
"""REQ-155 AC-1 and AC-8: the approach builder (backend/ofo/adjustment/approaches.py) against the scenario library's
hand-derived approach legs (tests/adjust_scenarios_gen.py ``hand_approaches``, written without backend/ofo), plus the
AC-1 example, the tested-side flip and every answer state of the chain row a new leg lands on."""
from __future__ import annotations

import datetime
import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import adjust_scenarios_gen as gen
import pytest
from ofo.adjustment.approaches import (
    APPROACH_IDS,
    ChainRow,
    Position,
    PositionLeg,
    applicable_approaches,
    build_approach,
    load_config,
)
from ofo.adjustment.approaches import tested_side as side_under_test  # a bare test_* name would be collected

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"
CFG = load_config()
IC_IDS = sorted(s["id"] for s in gen.scenarios() if s["family"] == "ic")  # the generator's own list, not a file scan


def load(sid: str) -> dict:
    return json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))


def _d(value: object) -> D | None:
    return None if value is None else D(str(value))


def inputs(sc: dict) -> tuple[Position, list[ChainRow], D]:
    """The scenario as the builder's input; a leg whose quote answered 'not found' has no price on its row."""
    unpriced = {q["tradingsymbol"] for q in sc["broker"]["quote"]["legs"] if q["state"] != "stated"}
    expiry = sc["expiry"]
    rows = []
    for c in sc["market"]["chains"]:
        if c["expiry"] != expiry:
            continue
        for r in c["rows"]:
            gone = r["tradingsymbol"] in unpriced
            rows.append(ChainRow(D(r["strike"]), r["type"], datetime.date.fromisoformat(c["expiry"]),
                                 r["tradingsymbol"], None if gone else _d(r["ltp"]), None if gone else _d(r["bid"]),
                                 None if gone else _d(r["ask"]), _d(r["delta"]), r["listed"], r["tradable"],
                                 r["low_oi"]["state"], r["low_oi"]["blocked"]))
    legs = tuple(PositionLeg(x["side"], x["type"], D(x["strike"]), datetime.date.fromisoformat(x["expiry"]), x["lots"],
                             D(x["entry"]), x["tradingsymbol"]) for x in sc["position"]["legs"])
    today = datetime.date.fromisoformat(sc["clock"]["ist"][:10])
    return Position(sc["underlying"], sc["lot"], sc["expiry_kind"], today, legs), rows, D(sc["market"]["spot"])


def plain(built) -> dict:
    """The builder's answer in the fixture's text form."""
    def t(v):
        return format(v, "f") if isinstance(v, D) else v.isoformat() if isinstance(v, datetime.date) else v

    basis = {"step_basis": built.step_basis, "step_value": t(built.step_value)}
    if built.refusal is not None:
        return {"side": built.side, "refused": built.refusal, **basis}

    def leg(x, keys):
        return {k: t(getattr(x, k)) for k in keys}
    trades = [leg(x, ("action", "type", "strike", "expiry", "lots", "quantity", "price", "tradingsymbol"))
              for x in built.trades]
    after_keys = ("side", "type", "strike", "expiry", "lots", "entry", "tradingsymbol")
    closed_keys = ("side", "type", "strike", "expiry", "lots", "quantity", "entry", "exit", "tradingsymbol")
    return {"side": built.side, **basis, "trades": trades,
            "after": [leg(x, after_keys) for x in built.after],
            "closed": [leg(x, closed_keys) for x in built.closed],
            "warnings": list(built.warnings)}


def fixture_form(expected: dict) -> dict:
    out = dict(expected)
    if "after" in out:
        out["after"] = [{k: v for k, v in x.items() if k != "quantity"} for x in out["after"]]
    return out


@pytest.mark.parametrize("sid", IC_IDS)
def test_every_scenario_and_approach_equals_the_hand_derived_legs(sid):
    """AC-1 (core proof): every iron condor scenario x the 7 approaches equals expected.approach_legs exactly."""
    sc = load(sid)
    position, chain, spot = inputs(sc)
    built = {a.id: a for a in applicable_approaches(position, chain, spot, CFG)}
    assert list(built) == list(APPROACH_IDS)
    for aid, expected in sc["expected"]["approach_legs"].items():
        assert plain(built[aid]) == fixture_form(expected), (sid, aid)
        # the After quantities: lots x the scenario's lot size
        for x, e in zip(built[aid].after, expected.get("after", []), strict=True):
            assert x.lots * sc["lot"] == e["quantity"]


def test_library_covers_every_iron_condor_scenario():
    assert len(IC_IDS) >= 29
    assert {"ADJ-02", "ADJ-13", "ADJ-20c", "ADJ-20d", "ADJ-20e", "ADJ-21", "ADJ-22"} <= set(IC_IDS)


def _no_delta(chain):
    return [replace(r, delta=None) for r in chain]


def strikes_of(legs):
    return [(x.side, x.type, x.strike) for x in legs]


def test_ac1_example_put_spread_up_200_calls_unchanged():
    """AC-1: 2-lot -23450 CE / +23650 CE / -22600 PE / +22400 PE of 3 Nov, put spread up 200 -> -22800 PE / +22600 PE,
    calls unchanged. Calls tested (spot 23380), no delta on the chain: the 200-point NIFTY step, labelled."""
    position, chain, spot = inputs(load("ADJ-20a"))
    a01 = build_approach(position, _no_delta(chain), spot, "A-01", CFG)
    assert a01.refusal is None and a01.side == "put"
    assert (a01.step_basis, a01.step_value) == ("points", D("200"))
    assert sorted(strikes_of(a01.after)) == sorted([("BUY", "PE", D("22600")), ("SELL", "PE", D("22800")),
                                                    ("SELL", "CE", D("23450")), ("BUY", "CE", D("23650"))])
    assert all(x.lots == 2 for x in a01.after)
    assert [(t.action, t.type, t.strike, t.quantity) for t in a01.trades] == [
        ("BUY", "PE", D("22600"), 130), ("BUY", "PE", D("22600"), 130), ("SELL", "PE", D("22400"), 130),
        ("SELL", "PE", D("22800"), 130)]
    # buy back the 22600 short, buy the new 22600 wing; sell the old 22400 wing, sell the new 22800 short
    assert {c.strike for c in a01.closed} == {D("22400"), D("22600")}


def test_tested_side_flips_between_a01_and_a05_with_spot():
    """AC-1: the tested side is decided by each short's distance from spot, so which spread a roll moves flips."""
    position, chain, _ = inputs(load("ADJ-20a"))
    flat = _no_delta(chain)
    near_calls = {a: build_approach(position, flat, D("23380"), a, CFG) for a in ("A-01", "A-05")}
    near_puts = {a: build_approach(position, flat, D("22650"), a, CFG) for a in ("A-01", "A-05")}
    assert side_under_test(position, D("23380")) == "call" and side_under_test(position, D("22650")) == "put"
    # spot near the calls: A-01 moves the PUT spread up 200, A-05 the CALL spread up 200
    assert {t.type for t in near_calls["A-01"].trades} == {"PE"}
    assert {t.type for t in near_calls["A-05"].trades} == {"CE"}
    assert D("22800") in {x.strike for x in near_calls["A-01"].after}
    assert D("23650") in {x.strike for x in near_calls["A-05"].after} and D("23850") in {
        x.strike for x in near_calls["A-05"].after}
    # spot near the puts: the roles swap (A-01 moves the CALL spread down, A-05 the PUT spread down)
    assert {t.type for t in near_puts["A-01"].trades} == {"CE"}
    assert {t.type for t in near_puts["A-05"].trades} == {"PE"}
    assert D("23250") in {x.strike for x in near_puts["A-01"].after}
    assert D("22400") in {x.strike for x in near_puts["A-05"].after}


def test_equidistant_spot_tests_the_call_side():
    """Attack 1: spot exactly halfway (23025 between 22600 and 23450): the call side is tested (leg_edit's tie rule)."""
    position, _, _ = inputs(load("ADJ-20a"))
    assert side_under_test(position, D("23025")) == "call"
    assert side_under_test(position, D("23024.95")) == "put"


def test_ac8_adj20d_refuses_only_a05_naming_the_leg():
    """AC-8: a landing strike not listed -> that approach is refused naming the leg; every other one still builds."""
    position, chain, spot = inputs(load("ADJ-20d"))
    built = {a.id: a for a in applicable_approaches(position, chain, spot, CFG)}
    assert built["A-05"].refusal == "No 23,700 CE is listed for 03 Nov 2026, so leg 4 cannot move there."
    assert built["A-05"].trades == ()
    refused = {a for a, b in built.items() if b.refusal}
    assert refused == {"A-05", "A-11"}  # A-11 only for its own rule (1 day left)
    assert built["A-11"].refusal == "This approach needs at least 3 days left; days left now: 1."


def test_ac8_adj20e_low_oi_unknown_is_a_warning_not_a_refusal():
    position, chain, spot = inputs(load("ADJ-20e"))
    # the unknown row is 23650 CE (the call wing); A-11 does not run at 1 day, so land a roll there: A-01 from the
    # call side when puts are tested, by points
    unknown = next(r for r in chain if r.low_oi_state == "unknown")
    assert (unknown.strike, unknown.type) == (D("23650"), "CE")
    row_moved = [replace(r, low_oi_state="unknown", low_oi_blocked=None) if (r.strike, r.type) == (D("23700"), "CE")
                 else r for r in chain]
    a05 = build_approach(position, row_moved, spot, "A-05", CFG)
    assert a05.refusal is None
    assert a05.warnings == ("Zerodha may refuse fresh orders in Leg 4 (BUY NIFTY 23,700 CE, expiry 03 Nov 2026) if its open "
                            "interest is too low; this app could not check that.",)
    # closing a leg in an unknown-low-OI contract is not a fresh order: no warning, no refusal
    a28 = build_approach(position, chain, spot, "A-28", CFG)
    assert a28.refusal is None and a28.warnings == ()


def test_adj20c_unpriced_leg_refuses_the_approaches_that_trade_it():
    """ADJ-20c (one leg unpriced, the 22400 PE wing): a stated state, '... has no price' naming the leg; the
    approaches that do not trade it still build."""
    position, chain, spot = inputs(load("ADJ-20c"))
    built = {a.id: a for a in applicable_approaches(position, chain, spot, CFG)}
    text = "Leg 1 (BUY NIFTY 22,400 PE, expiry 03 Nov 2026) has no price, and this approach trades it."
    assert built["A-01"].refusal == text and built["A-31"].refusal == text
    for aid in ("A-36", "A-05", "A-28", "A-29"):
        assert built[aid].refusal is None, aid


@pytest.mark.parametrize(("change", "reason"), [
    ({"listed": False}, "No 23,700 CE is listed for 03 Nov 2026, so leg 4 cannot move there."),
    ({"tradable": False}, "Leg 4 (BUY NIFTY 23,700 CE, expiry 03 Nov 2026) cannot be traded from Zerodha's current data."),
    ({"low_oi_state": "stated", "low_oi_blocked": True},
     "Zerodha blocks fresh orders in Leg 4 (BUY NIFTY 23,700 CE, expiry 03 Nov 2026) because its open interest is low."),
    ({"ltp": None, "bid": None, "ask": None}, "Leg 4 (BUY NIFTY 23,700 CE, expiry 03 Nov 2026) has no price, and this approach trades it."),
])
def test_ac8_every_answer_state_of_the_landing_row(change, reason):
    """AC-8 answer states of the row a new leg lands on (A-05's wing lands on 23,700 CE in ADJ-20a)."""
    position, chain, spot = inputs(load("ADJ-20a"))
    changed = [replace(r, **change) if (r.strike, r.type) == (D("23700"), "CE") else r for r in chain]
    built = {a.id: a for a in applicable_approaches(position, changed, spot, CFG)}
    assert built["A-05"].refusal == reason
    assert built["A-36"].refusal is None and built["A-28"].refusal is None


def test_landing_price_from_mid_when_no_ltp():
    """The planned price is ADR-068 (1)'s rule: LTP, else the mid of bid and ask (half-up to 0.01)."""
    position, chain, spot = inputs(load("ADJ-20a"))
    changed = [replace(r, ltp=None, bid=D("10.05"), ask=D("10.10")) if (r.strike, r.type) == (D("23700"), "CE")
               else r for r in chain]
    a05 = build_approach(position, changed, spot, "A-05", CFG)
    assert [t.price for t in a05.trades if t.strike == D("23700")] == [D("10.08")]


def _synthetic(strikes, expiry, kind_rows=("CE", "PE")):
    return [ChainRow(D(k), t, expiry, f"NIFTY26N03{k}{t}", D("10.00"), D("9.95"), D("10.05"))
            for k in strikes for t in kind_rows]


def test_a01_that_would_cross_the_other_short_is_refused():
    """Attack 2: a narrow condor (-23000 PE / -23100 CE): A-01 by 200 points would put the put short above the call."""
    expiry = datetime.date(2026, 11, 3)
    legs = (PositionLeg("BUY", "PE", D("22800"), expiry, 2, D("5"), "p1"),
            PositionLeg("SELL", "PE", D("23000"), expiry, 2, D("20"), "p2"),
            PositionLeg("SELL", "CE", D("23100"), expiry, 2, D("20"), "c1"),
            PositionLeg("BUY", "CE", D("23300"), expiry, 2, D("5"), "c2"))
    position = Position("NIFTY", 65, "weekly", datetime.date(2026, 11, 2), legs)
    chain = _synthetic(range(22500, 23700, 50), expiry)
    a01 = build_approach(position, chain, D("23090"), "A-01", CFG)
    assert a01.refusal == ("Moving Leg 2 (SELL NIFTY 23,000 PE, expiry 03 Nov 2026) to 23,200 would cross the other short "
                           "leg at 23,100.")


def test_a29_one_lot_is_refused_and_two_lots_halve():
    """Attack 3: half of one lot is not a whole lot -> refused with the reason; 2 lots -> 1 lot closed, 1 kept."""
    position, chain, spot = inputs(load("ADJ-20a"))
    one = replace(position, legs=tuple(replace(x, lots=1) for x in position.legs))
    assert build_approach(one, chain, spot, "A-29", CFG).refusal == \
        "Leg 3 (SELL NIFTY 23,450 CE, expiry 03 Nov 2026) or its wing holds only one lot, so it cannot be halved into whole lots."
    two = build_approach(position, chain, spot, "A-29", CFG)
    assert [(c.type, c.lots) for c in two.closed] == [("CE", 1), ("CE", 1)]
    assert sorted((x.type, x.lots) for x in two.after) == [("CE", 1), ("CE", 1), ("PE", 2), ("PE", 2)]


def test_sensex_uses_its_500_point_step_and_lot_20():
    """Attack 4 + 5: SENSEX (ADJ-21) with no delta on the chain rolls 500 points, quantities in SENSEX lots of 20."""
    position, chain, spot = inputs(load("ADJ-21"))
    a05 = build_approach(position, _no_delta(chain), spot, "A-05", CFG)
    assert (a05.step_basis, a05.step_value) == ("points", D("500"))
    assert a05.side == "call"
    assert sorted(x.strike for x in a05.after if x.type == "CE") == [D("78000"), D("79000")]
    assert {t.quantity for t in a05.trades} == {40}
    # with delta: the monthly Early delta of the playbook (0.25), labelled
    assert build_approach(position, chain, spot, "A-05", CFG).step_value == D("0.25")


def test_delta_absent_falls_back_to_points_labelled():
    """Attack 5: NIFTY without delta rolls 200 points and says so; with delta it says the target delta."""
    position, chain, spot = inputs(load("ADJ-02"))
    assert build_approach(position, chain, spot, "A-05", CFG).step_value == D("0.30")
    flat = build_approach(position, _no_delta(chain), spot, "A-05", CFG)
    assert (flat.step_basis, flat.step_value) == ("points", D("200"))
    assert sorted(x.strike for x in flat.after if x.type == "CE") == [D("23700"), D("23900")]


def test_non_condor_shape_builds_only_no_change_and_exit():
    position, chain, spot = inputs(load("ADJ-20a"))
    strangle = replace(position, legs=tuple(x for x in position.legs if x.side == "SELL"))
    built = {a.id: a for a in applicable_approaches(strangle, chain, spot, CFG)}
    assert built["A-36"].refusal is None and built["A-31"].refusal is None
    assert built["A-05"].refusal == "This approach needs one call spread and one put spread with a short leg each, on one expiry."


def test_unknown_approach_is_an_error():
    position, chain, spot = inputs(load("ADJ-20a"))
    with pytest.raises(ValueError, match="unknown approach"):
        build_approach(position, chain, spot, "A-99", CFG)
