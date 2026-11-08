"""F-94 (ADR-082 (2), ADR-008): the paper book's original Max Profit / Max Loss include the round-trip charges, equal to
the builder's figures for the same legs (one engine, one number), to the paisa."""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.charges.round_trip import round_trip_charges
from ofo.engine.extremes import ContractTerms, book_extremes
from ofo.engine.extremes_charges import open_round_trip_charges, with_charges
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import strategy_metrics
from ofo.engine.orderbook import PaperOrder, net_positions
from ofo.engine.strategy import Strategy

D = Decimal
EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
# an iron condor: (contract id, instrument, strike, BUY or SELL, price)
LEGS = (("1", Instrument.PE, D("22600"), "BUY", D("60.65")), ("2", Instrument.PE, D("22700"), "SELL", D("86.35")),
        ("3", Instrument.CE, D("22950"), "SELL", D("107.50")), ("4", Instrument.CE, D("23000"), "BUY", D("86.95")))


def _book():
    orders = [PaperOrder(cid, side, LOT, price, "open", T0) for cid, _, _, side, price in LEGS]
    terms = {cid: ContractTerms(kind, strike, EXPIRY) for cid, kind, strike, _, _ in LEGS}
    return net_positions(orders, {}), terms


def _builder_figures() -> tuple[Decimal, Decimal, Decimal]:
    strategy = Strategy(tuple(Leg(Action(side), kind, strike, EXPIRY, LOT, price)
                              for _, kind, strike, side, price in LEGS))
    charges = round_trip_charges(strategy.legs, "NIFTY", RATES)
    m = strategy_metrics(strategy)
    return m.max_profit - charges, m.max_loss + charges, charges  # outcome.service._summary, ADR-082 (2)


def test_core_paper_max_profit_and_loss_equal_the_builders_charges_inclusive_figures_to_the_paisa() -> None:
    view, terms = _book()
    gross = book_extremes(view, terms, {})
    charges = open_round_trip_charges(view, terms, "NIFTY", RATES)
    got = with_charges(gross, charges)
    profit, loss, builder_charges = _builder_figures()
    assert charges == builder_charges
    assert (got.max_profit, got.max_loss) == (profit, -loss)  # the builder's loss is a magnitude, the book's is signed
    assert (gross.max_profit, gross.max_loss, charges) == (D("3006.25"), D("-3493.75"), D("241.42"))  # hand check
    assert (got.max_profit, got.max_loss) == (D("2764.83"), D("-3735.17"))


def test_no_rates_or_nothing_open_leaves_the_figures_before_charges() -> None:
    view, terms = _book()
    gross = book_extremes(view, terms, {})
    assert open_round_trip_charges(view, terms, "NIFTY", None) is None
    assert with_charges(gross, None) == gross
