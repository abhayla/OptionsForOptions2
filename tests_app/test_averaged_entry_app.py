"""GC-ICFIX issues 3 and 4 (ADR-008, ADR-263, ADR-298): the app-layer half of the averaged-entry tests (they need
``ofo_app``, so they live here; the engine half is ``tests/adjustment/test_averaged_entry.py``). A leg filled in two
orders at different prices has an AVERAGE entry with more than two decimals (38.85 and 38.90 -> 38.875); the app
builds the engine's ``Leg`` from it and must price it exactly. Base position = scenario ADJ-01 (iron condor, 2 lots x 65).
Hand sum: closing SELL 130 @ 38.875 by BUY at 30.00 books (38.875 - 30.00) x 130 = 1,153.75; short-PE two-fill
credit 40.175 x 130 = 5,222.75. No database."""
from __future__ import annotations

import datetime
import sys
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))  # the scenario generator
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "adjustment"))
import test_approach_compare as t
from ofo.charges import ChargeRates
from ofo.engine.adjust_money import closed_booked
from ofo_app import adjustment_check as check
from ofo_app.routes import adjustment as route

ADJ = "ADJ-01"
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")


def _position(entries: dict[int, D]):
    position, _chain, _spot = t.inputs(t.load(ADJ))
    legs = tuple(replace(x, entry=entries.get(i, x.entry)) for i, x in enumerate(position.legs))
    return replace(position, legs=legs)


def _market() -> route.MarketInputs:
    now = datetime.datetime(2026, 11, 2, 5, 0, tzinfo=datetime.UTC)
    return route.MarketInputs((), {}, None, None, None, None, None, now)


def test_offer_money_lines_from_the_exact_average() -> None:
    position = _position({1: D("38.875")})
    leg = position.legs[1]
    assert closed_booked([(leg.side, leg.entry, D("30.00"), 130)]) == D("1153.75")  # the docstring's hand sum
    priced = route.price_after(position.legs, position, D("0"), D("0"), [], RATES, _market())
    assert priced.after is not None and priced.charges_known is True
    assert priced.after.gross.max_profit == D("5222.75")


def test_a_leg_the_charge_engine_cannot_price_gives_the_existing_answer_not_an_exception() -> None:
    # entry 0 on a long leg: the calculator refuses a zero price; price_after keeps the figures and says charges unknown
    position = _position({0: D("0")})
    priced = route.price_after(position.legs, position, D("0"), D("0"), [], RATES, _market())
    assert priced.charges_known is False and priced.after is not None


def test_the_check_reads_an_averaged_entry_exactly() -> None:
    # adjustment_check._engine_legs builds the engine Leg with exact_entry=True: without it, 38.875 is refused
    position = _position({1: D("38.875")})
    assert check._engine_legs(position)[1].entry_price == D("38.875")
