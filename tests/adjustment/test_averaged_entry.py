# ruff: noqa: PLR2004 - exact hand amounts are the assertions
"""GC-ICFIX issues 3 and 4 (ADR-008, ADR-263, ADR-298): a leg filled in two orders at different prices has an AVERAGE
entry with more than two decimals (38.85 and 38.90 -> 38.875). The adjustment offer / compare / prepare readers build
the engine's ``Leg`` from that average; the engine's price guard refused it, so every approach answered with an error.
The average must be priced as it is, never rounded to a price nobody traded at.

Base position = scenario ADJ-01, an iron condor of 2 lots x 65: BUY 22400 PE @ 20.10, SELL 22600 PE @ 38.85,
SELL 23450 CE @ 36.90, BUY 23650 CE @ 15.50.
Hand sums (units = 130):
  all one-fill:            net credit 38.85 + 36.90 - 20.10 - 15.50 = 40.15 -> max profit 40.15 x 130 = 5,219.50
  short PE two-fill 38.875: credit 40.175 x 130 = 5,222.75
  long CE two-fill 15.525:  credit 40.125 x 130 = 5,216.25
The offer's money lines for the short-PE case with the exact average as the exit price: closing SELL 130 @ 38.875 by
BUY at the planned exit 30.00 books (38.875 - 30.00) x 130 = 1,153.75.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

import pytest
import test_approach_compare as t
from ofo.charges import ChargeRates
from ofo.adjustment.approaches import APPROACH_IDS, build_approach
from ofo.adjustment.compare import _strategy
from ofo.engine.adjust_money import closed_booked
from ofo.engine.metrics import strategy_metrics
from ofo_app.routes import adjustment as route

ADJ = "ADJ-01"
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")


def _position(entries: dict[int, D]):
    sc = t.load(ADJ)
    position, chain, spot = t.inputs(sc)
    legs = tuple(replace(x, entry=entries.get(i, x.entry)) for i, x in enumerate(position.legs))
    return replace(position, legs=legs), chain, spot


def _max_profit(position) -> D:
    return strategy_metrics(_strategy(position.legs, position.lot)).max_profit


def _market() -> route.MarketInputs:
    return route.MarketInputs((), {}, None, None, None, None, None, datetime.datetime(2026, 11, 2, 5, 0, tzinfo=datetime.UTC))


def _all_approaches(position, chain, spot) -> list[str]:
    """Every approach builds (a refusal is an answer; an exception is the defect) and its After reads as a strategy."""
    out = []
    for a in APPROACH_IDS:
        built = build_approach(position, chain, spot, a, t.CFG)
        if built.after:
            _strategy(built.after, position.lot)
        out.append(a)
    return out


def test_one_fill_legs_unchanged() -> None:
    position, chain, spot = _position({})
    assert _all_approaches(position, chain, spot) == list(APPROACH_IDS)
    assert _max_profit(position) == D("5219.50")


def test_two_fill_short_leg_builds_every_approach_and_prices_exactly() -> None:
    position, chain, spot = _position({1: D("38.875")})
    assert _all_approaches(position, chain, spot) == list(APPROACH_IDS)
    assert _max_profit(position) == D("5222.75")  # hand sum in the module docstring


def test_two_fill_long_leg_prices_exactly() -> None:
    position, chain, spot = _position({3: D("15.525")})
    assert _all_approaches(position, chain, spot) == list(APPROACH_IDS)
    assert _max_profit(position) == D("5216.25")


def test_offer_money_lines_from_the_exact_average() -> None:
    position, chain, spot = _position({1: D("38.875")})
    leg = position.legs[1]
    assert closed_booked([(leg.side, leg.entry, D("30.00"), 130)]) == D("1153.75")  # the docstring's hand sum
    priced = route.price_after(position.legs, position, D("0"), D("0"), [], RATES, _market())
    assert priced.after is not None and priced.charges_known is True
    assert priced.after.gross.max_profit == D("5222.75")


def test_partly_closed_two_fill_leg() -> None:
    # a partial close leaves the average unchanged: 1 lot of the short PE left at 38.875
    position, chain, spot = _position({1: D("38.875")})
    legs = tuple(replace(x, lots=1) if i == 1 else x for i, x in enumerate(position.legs))
    position = replace(position, legs=legs)
    assert _all_approaches(position, chain, spot) == list(APPROACH_IDS)
    assert _strategy(position.legs, position.lot).legs[1].entry_price == D("38.875")  # 65 units, exact


def test_exactly_two_decimals_is_unchanged() -> None:
    position, chain, spot = _position({1: D("38.90")})
    assert _max_profit(position) == D("40.20") * 130 == D("5226.00")


def test_a_leg_the_charge_engine_cannot_price_gives_the_existing_answer_not_an_exception() -> None:
    # entry 0 on a long leg: the calculator refuses a zero price; price_after keeps the figures and says charges unknown
    position, chain, spot = _position({0: D("0")})
    priced = route.price_after(position.legs, position, D("0"), D("0"), [], RATES, _market())
    assert priced.charges_known is False and priced.after is not None


def test_the_average_is_never_rounded() -> None:
    position, _, _ = _position({1: D("38.875")})
    strategy = _strategy(position.legs, position.lot)
    assert strategy.legs[1].entry_price == D("38.875")
    with pytest.raises(ValueError):  # the float guard stays: a float-built price is still refused
        _strategy((replace(position.legs[1], entry=D(38.875 + 0.1)),), position.lot)
