# ruff: noqa: PLR2004, E501 - strikes, lots and prices of the cases; catalogue texts quoted whole
"""ADR-238 (GC-IC1 step 2; REQ-155 AC-1, AC-8): the exit and reduce approaches A-24, A-25, A-26, A-27, A-35 against
the generator's engine-free figures (tests/adjust_scenarios_gen.py ``hand_approaches``), their refusals, the caller's
T-09 reader by stage and S-11 keeping all five."""
from __future__ import annotations

import datetime
import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import adjust_scenarios_gen as gen
import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import ExitInputs, build_approach
from ofo.adjustment.offered import EXIT_REDUCE, offered_now
from ofo.adjustment.preferences import PARTIAL_CLOSE_PERCENT, UNTESTED_DECAY_PERCENT
from ofo.settings import defaults as _registry_defaults
from test_approaches import CFG, fixture_form, inputs, load, plain

NEW = ("A-24", "A-25", "A-26", "A-27", "A-35")
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"


def _exits(sc: dict) -> ExitInputs:
    i = sc["expected"]["playbook_exits"]["inputs"]
    return ExitInputs(None if i["t09"] is None else (D(i["t09"]), i["t09_cmp"]), i["time_exit"], i["hhmm"])


def _ic_body() -> dict:
    return pe.body_from_fixture(json.loads((FIX / "_playbooks.json").read_text(encoding="utf-8")), "ic")


@pytest.mark.parametrize("sid", ["ADJ-02", "ADJ-13"])
def test_core_five_approaches_equal_the_generator_with_no_playbook(sid):
    sc = load(sid)
    position, chain, spot = inputs(sc)
    for a in NEW:
        assert plain(build_approach(position, chain, spot, a, CFG)) == fixture_form(sc["expected"]["approach_legs"][a]), a


@pytest.mark.parametrize("sid", gen.PLAYBOOK_EXIT_CASES)
def test_core_a27_a35_with_the_playbook_inputs_equal_the_generator(sid):
    sc = load(sid)
    position, chain, spot = inputs(sc)
    pb = sc["expected"]["playbook_exits"]
    for a, want in pb["approach_legs"].items():
        assert plain(build_approach(position, chain, spot, a, CFG, exits=_exits(sc))) == fixture_form(want), (sid, a)
    # ADJ-09 is past 14:30 on expiry day: A-35 is built, ADJ-02 / ADJ-08 / ADJ-13 are not
    assert ("refused" not in pb["approach_legs"]["A-35"]) is (sid == "ADJ-09")


def test_a24_and_a35_trade_exactly_as_a31():
    """Attack 1: one close-all builder; A-24 and A-35 equal A-31 on the same position."""
    sc = load("ADJ-09")
    position, chain, spot = inputs(sc)
    a31 = build_approach(position, chain, spot, "A-31", CFG)
    for a in ("A-24", "A-35"):
        got = build_approach(position, chain, spot, a, CFG, exits=_exits(sc))
        assert (got.trades, got.after, got.closed) == (a31.trades, a31.after, a31.closed), a
        assert len(got.closed) == len(position.legs) == 4


@pytest.mark.parametrize(("lots", "closes"), [(1, None), (2, 1), (3, None), (4, 2)])
def test_a25_at_50_percent_whole_lots_only(lots, closes):
    """Attack 2: 1 and 3 lots are refused naming leg 1 (never floored); 2 and 4 close half of every leg. ADJ-10 is in
    profit (ADR-238 (6)), so only the whole-lots rule decides."""
    position, chain, spot = inputs(load("ADJ-10"))
    position = replace(position, legs=tuple(replace(x, lots=lots) for x in position.legs))
    got = build_approach(position, chain, spot, "A-25", CFG)
    if closes is None:
        assert got.refusal is not None and got.refusal.startswith("Leg 1 (")
        assert f"holds {lots} lots, and 50% of them is not a whole number of lots." in got.refusal
        assert got.trades == ()
    else:
        assert got.refusal is None and [t.lots for t in got.trades] == [closes] * 4
        assert [x.lots for x in got.after] == [lots - closes] * 4


def _with_price(chain, leg, price):
    """The row's planned price set to ``price``: LTP and a locked live book (ADR-241 prices from the live mid first)."""
    return [replace(r, ltp=price, bid=price, ask=price) if (r.type, r.strike) == (leg.type, leg.strike) else r
            for r in chain]


def test_a26_reads_the_untested_short_against_its_entry():
    """Attack 3: only the untested short counts, against its ENTRY; 80% exactly is offered (>=), 79.x% is not."""
    position, chain, spot = inputs(load("ADJ-02"))  # spot near the call short: the put side is untested
    put_short = next(x for x in position.legs if (x.side, x.type) == ("SELL", "PE"))
    call_short = next(x for x in position.legs if (x.side, x.type) == ("SELL", "CE"))
    at80 = put_short.entry * D("0.20")
    got = build_approach(position, _with_price(chain, put_short, at80), spot, "A-26", CFG)
    assert got.refusal is None and got.side == "put"
    assert [(t.action, t.type, t.strike) for t in got.trades] == [("BUY", "PE", put_short.strike)]
    assert len(got.after) == 3 and (put_short.side, put_short.type, put_short.strike) not in \
        {(x.side, x.type, x.strike) for x in got.after}
    below = build_approach(position, _with_price(chain, put_short, at80 + D("0.05")), spot, "A-26", CFG)
    assert below.refusal is not None and "this approach waits until it has fallen by 80% or more" in below.refusal
    # the tested (call) short decayed 99% but the untested did not: not offered
    tested_only = _with_price(_with_price(chain, call_short, D("0.05")), put_short, put_short.entry)
    assert build_approach(position, tested_only, spot, "A-26", CFG).refusal is not None


def test_a26_entry_zero_is_refused_without_division():
    position, chain, spot = inputs(load("ADJ-02"))
    legs = tuple(replace(x, entry=D(0)) if (x.side, x.type) == ("SELL", "PE") else x for x in position.legs)
    got = build_approach(replace(position, legs=legs), chain, spot, "A-26", CFG)
    assert got.refusal is not None and "has no entry price above zero" in got.refusal


def test_a27_threshold_is_the_current_stage_of_t09():
    """Attack 4: the caller's reader gives Rs 2 on the last day and Rs 3 earlier; a short at 2.50 is bought back
    only on the earlier stage."""
    body = _ic_body()
    guards = body["guards"]
    last = pe.exit_inputs(body, guards, pe.StrategyState("weekly", days_left=0, hhmm="13:30"))
    early = pe.exit_inputs(body, guards, pe.StrategyState("weekly", days_left=6, hhmm="13:30"))
    assert (last.t09, early.t09) == ((D("2"), "le"), (D("3"), "le"))
    assert (last.time_exit, last.hhmm) == ("14:30", "13:30")
    position, chain, spot = inputs(load("ADJ-02"))
    call_short = next(x for x in position.legs if (x.side, x.type) == ("SELL", "CE"))
    put_short = next(x for x in position.legs if (x.side, x.type) == ("SELL", "PE"))
    priced = _with_price(_with_price(chain, call_short, D("2.50")), put_short, D("40"))
    on_last = build_approach(position, priced, spot, "A-27", CFG, exits=last)
    assert on_last.refusal == "No short leg is priced within the buy-back limit of ₹2 your playbook sets for this stage."
    on_early = build_approach(position, priced, spot, "A-27", CFG, exits=early)
    assert [(t.action, t.type, t.strike, t.price) for t in on_early.trades] == [("BUY", "CE", call_short.strike, D("2.50"))]


def test_a27_with_t09_off_or_absent_is_refused_never_a_default():
    body = _ic_body()
    off = {**body, "triggers": {**body["triggers"], "T-09": {**body["triggers"]["T-09"], "on": False}}}
    gone = {**body, "triggers": {k: v for k, v in body["triggers"].items() if k != "T-09"}}
    state = pe.StrategyState("weekly", days_left=3, hhmm="11:00")
    assert pe.exit_inputs(off, None, state).t09 is None and pe.exit_inputs(gone, None, state).t09 is None
    assert pe.exit_inputs(None, None, state) == ExitInputs(None, None, "11:00")
    position, chain, spot = inputs(load("ADJ-02"))
    got = build_approach(position, chain, spot, "A-27", CFG, exits=pe.exit_inputs(off, None, state))
    assert got.refusal == "Your playbook sets no buy-back price for short legs at this stage, so this approach is not built."


def test_a27_short_without_price_is_refused_naming_the_leg():
    position, chain, spot = inputs(load("ADJ-02"))
    call_short = next(x for x in position.legs if (x.side, x.type) == ("SELL", "CE"))
    holed = [replace(r, ltp=None, bid=None, ask=None) if (r.type, r.strike) == ("CE", call_short.strike) else r
             for r in chain]
    got = build_approach(position, holed, spot, "A-27", CFG, exits=ExitInputs((D("3"), "le"), "14:30", "11:40"))
    assert got.refusal is not None and "has no price, and this approach trades it." in got.refusal
    assert f"{call_short.strike:,} CE" in got.refusal


def test_a35_only_on_expiry_day_from_the_time():
    sc = load("ADJ-09")  # expiry day 14:45
    position, chain, spot = inputs(sc)
    for exits, want in [(ExitInputs(None, "14:30", "14:29"), "The time exit is offered on expiry day from 14:30."),
                        (ExitInputs(None, "14:30", None), "The time exit is offered on expiry day from 14:30."),
                        (ExitInputs(None, None, "15:00"), "Your playbook sets no time exit, so this approach is not built.")]:
        assert build_approach(position, chain, spot, "A-35", CFG, exits=exits).refusal == want
    assert build_approach(position, chain, spot, "A-35", CFG, exits=ExitInputs(None, "14:30", "14:30")).refusal is None
    day_before = replace(position, today=position.today - datetime.timedelta(days=1))
    assert build_approach(day_before, chain, spot, "A-35", CFG, exits=ExitInputs(None, "14:30", "15:00")).refusal == \
        "The time exit is offered on expiry day from 14:30."


def test_s11_keeps_all_five_at_the_adjustment_limit():
    body = _ic_body()
    limit = body["guards"]["max_adjustments"]
    at_limit = offered_now(body, limit)
    assert set(NEW) <= EXIT_REDUCE and set(NEW) <= set(at_limit)


def test_the_two_preferences_default_to_the_adr_values():
    values = _registry_defaults()
    assert (values[PARTIAL_CLOSE_PERCENT], values[UNTESTED_DECAY_PERCENT]) == (D("50"), D("80"))
    assert (CFG.partial_close_percent, CFG.untested_decay_percent) == (50, 80)


NOT_IN_PROFIT = "The whole trade is not in profit with every open leg closed at its planned price, so this approach is not built."


def test_adr238_6_take_profit_refused_at_a_loss_and_built_in_profit():
    """ADR-238 (6): ADJ-02 (whole trade at a loss) -> A-24 and A-25 refused with the reason; ADJ-10 (in profit) -> both
    built as before (equal to the generator's copy)."""
    position, chain, spot = inputs(load("ADJ-02"))
    for a in ("A-24", "A-25"):
        assert build_approach(position, chain, spot, a, CFG).refusal == NOT_IN_PROFIT, a
    assert build_approach(position, chain, spot, "A-31", CFG).refusal is None  # the exit stays offered
    sc = load("ADJ-10")
    position, chain, spot = inputs(sc)
    for a in ("A-24", "A-25"):
        got = build_approach(position, chain, spot, a, CFG)
        assert got.refusal is None and plain(got) == fixture_form(sc["expected"]["approach_legs"][a]), a


def test_adr238_6_zero_is_not_profit_and_unknown_booked_is_refused():
    """Boundary: a whole trade of exactly 0 is not in profit (> 0, not >=); booked P&L unknown fails closed."""
    position, chain, spot = inputs(load("ADJ-10"))
    built = build_approach(position, chain, spot, "A-24", CFG)
    whole = position.booked + sum((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built.closed)
    assert whole > 0
    for booked, want in ((position.booked - whole, NOT_IN_PROFIT), (position.booked - whole + D("0.01"), None)):
        assert build_approach(replace(position, booked=booked), chain, spot, "A-24", CFG).refusal == want, booked
    assert build_approach(replace(position, booked=None), chain, spot, "A-25", CFG).refusal == (
        "The profit or loss booked so far is not known, so whether the whole trade is in profit cannot be worked out "
        "and this approach is not built.")
