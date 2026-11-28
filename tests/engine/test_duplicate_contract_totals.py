"""D-60: adding a contract already in the strategy as a second row (Keep separate) or as more lots on the one row
(Increase quantity) gives the same numbers: the engine sums legs, so the choice never changes a figure."""
import datetime
from decimal import Decimal as D

from ofo.engine import Action, Instrument, Leg, PriceBasis, Strategy, net_premium, strategy_metrics

EXPIRY = datetime.date(2026, 11, 25)
LOT = 65


def _condor(extra: list[Leg]) -> Strategy:
    return Strategy((
        Leg(Action.BUY, Instrument.PE, D("25300"), EXPIRY, LOT, D("40.00"), D("38.00")),
        Leg(Action.SELL, Instrument.PE, D("25500"), EXPIRY, LOT, D("60.00"), D("57.00")),
        Leg(Action.SELL, Instrument.CE, D("26500"), EXPIRY, LOT, D("55.00"), D("50.00")),
        Leg(Action.BUY, Instrument.CE, D("26700"), EXPIRY, LOT, D("30.00"), D("27.00")),
        *extra,
    ))


def test_increase_quantity_and_keep_separate_give_equal_numbers():
    separate = _condor([Leg(Action.BUY, Instrument.PE, D("25300"), EXPIRY, LOT, D("40.00"), D("38.00")),
                        Leg(Action.SELL, Instrument.PE, D("25500"), EXPIRY, LOT, D("60.00"), D("57.00"))])
    increased = Strategy((
        Leg(Action.BUY, Instrument.PE, D("25300"), EXPIRY, 2 * LOT, D("40.00"), D("38.00")),
        Leg(Action.SELL, Instrument.PE, D("25500"), EXPIRY, 2 * LOT, D("60.00"), D("57.00")),
        Leg(Action.SELL, Instrument.CE, D("26500"), EXPIRY, LOT, D("55.00"), D("50.00")),
        Leg(Action.BUY, Instrument.CE, D("26700"), EXPIRY, LOT, D("30.00"), D("27.00")),
    ))
    for basis in PriceBasis:
        assert net_premium(separate, basis) == net_premium(increased, basis)
    a, b = strategy_metrics(separate), strategy_metrics(increased)
    assert (a.max_profit, a.max_loss) == (b.max_profit, b.max_loss)
