"""D-21 (ADR-320 (3), GC-ICLIVE-C): every adjustment approach shows a "What changes" block, before against after.

Real case: strategy 164 (23 Nov), Reduce: max loss 21,037.90 -> 22,736.09, max profit 4,962.10 -> 3,140.27, and the
table never said why. The recorded legs of 164 are not in a fixture, so the nearest fixture is used: ADJ-02, an iron
condor whose Reduce (A-29) closes one lot of the tested call spread, raises max loss and lowers max profit the same
way. Hand values come from the fixture's own ``expected`` block and its rows, never from the code under test.

Eight measures per approach: profit range, distance from the index to each breakeven, POP, max profit, max loss, the
credit or debit of the adjustment, margin, net delta. No verdict word anywhere.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import re
from decimal import Decimal as D

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import APPROACH_IDS
from ofo.engine.black_scholes import Greeks
from ofo.outcome.service import MARGIN_CHECKED, Margin, margin_unreadable
from ofo_app import adjustment_check
from ofo_app.routes import adjustment as route
from test_adjustment_approaches_route import FIX, RATES, client_for, load, market_of, post

MEASURES = ["profit_range", "breakeven_distance", "pop", "max_profit", "max_loss", "credit", "margin", "net_delta"]
VERDICT = re.compile(r"\b(better|worse|best|worst|recommend\w*|should|winner|prefer\w*)\b", re.IGNORECASE)


def _num(text: str) -> D:
    return D(re.sub(r"[^\d.\-]", "", text.replace("₹", "").replace(",", "")))


def _greeks(sc: dict) -> dict[str, Greeks]:
    return {r["tradingsymbol"]: Greeks(D(r["delta"]), D(r["gamma"]), D(0), D(0))
            for c in sc["market"]["chains"] for r in c["rows"] if r["delta"] is not None and r["gamma"] is not None}


IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


async def _margin_per_leg(planned):  # 40,000 per open leg: a different figure for a different basket
    need = D(40000) * len(planned)
    return Margin(MARGIN_CHECKED, margin_unreadable().reason, need, need, D("900000"),
                  datetime.datetime(2026, 11, 9, 10, 0, tzinfo=IST))


def client(sc: dict, **kw):
    kw.setdefault("rates", RATES)
    kw.setdefault("environ", {"APP_ENV": "test"})  # the POP switch is on in test
    kw.setdefault("margin", _margin_per_leg)
    c = client_for(sc, **kw)

    async def market(_t, _ctx):
        return dataclasses.replace(market_of(sc), leg_greeks=_greeks(sc))
    c.app.dependency_overrides[route.get_market_reader] = lambda: market
    return c


def rows_of(block: dict) -> dict[str, dict]:
    assert [r["id"] for r in block["rows"]] == MEASURES
    return {r["id"]: r for r in block["rows"]}


def test_d21_reduce_on_the_condor_shows_the_eight_measures_before_against_after_and_one_reason_line():
    sc = load("ADJ-02")
    body = post(client(sc)).json()
    block = body["what_changes"]["A-29"]
    rows = rows_of(block)
    hand = sc["expected"]["approach_after"]
    spot = D(sc["market"]["spot"])
    charges = {a: sum(D(v) for v in (c["this_adjustment"], c["paid_so_far"], c["open_exit"]))
               for a in ("A-36", "A-29") for c in [next(x for x in body["approaches"] if x["id"] == a)["charges"]]}
    # (5) max loss and (4) max profit: the engine's hand values, after charges, each marked up or down
    assert _num(rows["max_loss"]["before_text"]) == D(hand["A-36"]["max_loss"]) + charges["A-36"]
    assert _num(rows["max_loss"]["after_text"]) == D(hand["A-29"]["max_loss"]) + charges["A-29"]
    assert rows["max_loss"]["direction"] == "up"
    assert _num(rows["max_profit"]["before_text"]) == D(hand["A-36"]["max_profit"]) - charges["A-36"]
    assert _num(rows["max_profit"]["after_text"]) == D(hand["A-29"]["max_profit"]) - charges["A-29"]
    assert rows["max_profit"]["direction"] == "down"
    # (1) profit range: both breakevens and the width in points
    for side, key in (("before", "A-36"), ("after", "A-29")):
        text = rows["profit_range"][f"{side}_text"]
        levels = next(a for a in body["approaches"] if a["id"] == key)["after"]["after_charges"]["breakevens"]
        lo, hi = (D(x).quantize(D("0.01")) for x in sorted(levels))
        assert f"{lo}" in text.replace(",", "") and f"{hi}" in text.replace(",", ""), text
        assert f"{hi - lo}" in text.replace(",", "") or f"{(hi - lo).normalize()}" in text.replace(",", ""), text
    # (2) distance from the index to each breakeven, worked out as level minus the index
    lo, hi = sorted(D(x) for x in body["before"]["after"]["after_charges"]["breakevens"])
    before = rows["breakeven_distance"]["before_text"].replace(",", "")
    assert f"{abs(lo - spot)}" in before and "below the index" in before
    assert f"{abs(hi - spot)}" in before and "above the index" in before
    # (6) the credit or debit of the adjustment: Reduce buys back 84.10 x 65 and sells 29.50 x 65 = a debit
    assert _num(rows["credit"]["after_text"]) == (D("84.10") - D("29.50")) * 65
    assert "Debit" in rows["credit"]["after_text"]
    assert rows["credit"]["direction"] == "down"
    # (7) margin: 40,000 per open leg, four legs before, four after (the lots change, not the legs)
    assert _num(rows["margin"]["before_text"]) == D(160000) and _num(rows["margin"]["after_text"]) == D(160000)
    assert rows["margin"]["direction"] == "same"
    # (8) net delta: the signed lots x quantity x per-unit delta of the fixture's own rows
    deltas = {r["tradingsymbol"]: D(str(r["delta"])) for c in sc["market"]["chains"] for r in c["rows"]}
    sign = {"BUY": 1, "SELL": -1}
    want_before = sum(sign[x["side"]] * x["lots"] * sc["lot"] * deltas[x["tradingsymbol"]]
                      for x in sc["position"]["legs"])
    after_legs = sc["expected"]["approach_legs"]["A-29"]["after"]
    want_after = sum(sign[x["side"]] * x["lots"] * sc["lot"] * deltas[x["tradingsymbol"]] for x in after_legs)
    assert _num(rows["net_delta"]["before_text"]) == want_before.quantize(D("0.0001"))
    assert _num(rows["net_delta"]["after_text"]) == want_after.quantize(D("0.0001"))
    assert rows["net_delta"]["direction"] == "down"
    # POP: a probability with the switch on, each side with its own text
    assert rows["pop"]["before_text"].endswith("%") and rows["pop"]["after_text"].endswith("%")
    # the one plain reason line: max loss rises while the action's name says it cuts exposure
    assert block["reason_line"] == "This removes credit from the call side, so the put spread becomes the largest loss."


def test_d21_no_change_shows_before_equal_to_after_and_no_reason_line():
    body = post(client(load("ADJ-02"))).json()
    block = body["what_changes"]["A-36"]
    for r in rows_of(block).values():
        assert r["before_text"] == r["after_text"] and r["direction"] in ("same", "not_available"), r
    assert block["reason_line"] is None


def _all_blocks():
    sc = load("ADJ-02")
    guards = adjustment_check.guards_of_body(pe.body_from_fixture(json.loads((FIX / "_playbooks.json").read_text(
        encoding="utf-8")), "ic"))
    guards.pop("roll_debit_limit", None)
    out = [("ADJ-02+playbook", post(client(sc, guards=guards)).json())]
    out.extend((sid, post(client(load(sid))).json()) for sid in ("ADJ-02", "ADJ-13"))
    return out


def test_d21_every_approach_id_has_the_eight_measures_or_states_its_refusal():
    seen_built: set[str] = set()
    for label, body in _all_blocks():
        by_id = {a["id"]: a for a in body["approaches"]}
        assert list(by_id) == list(APPROACH_IDS), label
        for a in APPROACH_IDS:
            if by_id[a]["refusal"] is not None:  # a refused approach states its refusal and takes no block
                assert a not in body["what_changes"], (label, a)
                continue
            seen_built.add(a)
            for r in rows_of(body["what_changes"][a]).values():
                assert r["before_text"] and r["after_text"], (label, a, r)
                assert r["direction"] in ("up", "down", "same", "not_available"), (label, a, r)
                if r["direction"] == "not_available":  # never a filled default: the reason is stated
                    assert r["unavailable_reason"], (label, a, r)
    assert seen_built >= {a for a in APPROACH_IDS if a not in ("A-24", "A-25", "A-35")}, seen_built


def test_d21_a_measure_that_cannot_be_worked_out_says_not_available_with_its_reason():
    body = post(client_for(load("ADJ-02"), rates=RATES)).json()  # no Greeks read, and the POP switch is off
    rows = rows_of(body["what_changes"]["A-29"])
    assert rows["pop"]["direction"] == "not_available"
    assert rows["pop"]["unavailable_reason"].startswith("POP not available")
    assert rows["net_delta"]["direction"] == "not_available" and rows["net_delta"]["unavailable_reason"]
    assert rows["net_delta"]["after_text"].lower().startswith("not available")


def test_d21_no_verdict_word_in_any_text_of_any_block():
    for label, body in _all_blocks():
        texts = json.dumps(body["what_changes"])
        assert body["what_changes"] and VERDICT.search(texts) is None, (label, VERDICT.search(texts))


def test_d21_the_exit_rows_say_no_position_is_left_and_never_a_zero():
    body = post(client(load("ADJ-02"))).json()
    rows = rows_of(body["what_changes"]["A-31"])
    assert rows["net_delta"]["direction"] == "not_available"
    assert "No position left" in rows["net_delta"]["unavailable_reason"]
    assert rows["profit_range"]["direction"] in ("down", "same", "not_available")


@pytest.mark.parametrize("sid", ["ADJ-02", "ADJ-13"])
def test_d21_the_block_reads_the_same_engine_figures_as_the_compare_table(sid):
    body = post(client(load(sid))).json()
    cells = {c["id"]: c["values"] for c in body["criteria"]}
    for a, block in body["what_changes"].items():
        rows = rows_of(block)
        assert rows["max_loss"]["after_text"] == cells["max_loss"][a]["text"], a
        assert rows["max_profit"]["after_text"] == cells["max_profit"][a]["text"], a
        assert rows["pop"]["after_text"] == cells["pop"][a]["text"] or rows["pop"]["unavailable_reason"], a
