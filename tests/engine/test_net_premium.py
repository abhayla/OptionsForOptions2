"""Net premium is strategy-level and owned by the engine (scenario-calculations.md §3; ADR-008).

Signed rupee total, credit positive: SELL legs +price x qty, BUY legs -price x qty; futures legs carry no premium.
"""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, PriceBasis, Strategy, net_premium, strategy_metrics

EXPIRY = datetime.date(2026, 10, 27)

RATIO = Strategy((
    Leg(Action.BUY, Instrument.CE, D("23000"), EXPIRY, 75, D("100"), D("100")),
    Leg(Action.SELL, Instrument.CE, D("23200"), EXPIRY, 150, D("60"), D("60")),
))
CONDOR = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, 75, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, 75, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 75, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 75, D("44.00"), D("39.50")),
))


def test_ratio_spread_net_premium_weights_each_leg_by_its_quantity():
    """AC-4: BUY 75x23000CE@100 / SELL 150x23200CE@60 is +1,500 (9,000 - 7,500), not the per-unit -40."""
    assert net_premium(RATIO, PriceBasis.LTP) == D("1500")
    assert net_premium(RATIO, PriceBasis.ENTRY) == D("1500")


def test_golden_condor_net_premium_entry_and_ltp():
    """AC-4: golden condor entry credit 91 x 75 = +6,825 (equals max profit); at LTPs 72.80 x 75 = +5,460."""
    assert net_premium(CONDOR, PriceBasis.ENTRY) == D("6825.00")
    assert net_premium(CONDOR, PriceBasis.ENTRY) == strategy_metrics(CONDOR).max_profit
    assert net_premium(CONDOR, PriceBasis.LTP) == D("5460.00")


def test_debit_is_negative_and_futures_carry_no_premium():
    """AC-4: a long call is a debit (negative); a futures leg adds 0 even without an LTP."""
    long_call = Leg(Action.BUY, Instrument.CE, D("23000"), EXPIRY, 75, D("100"), D("110"))
    fut = Leg(Action.SELL, Instrument.FUT, None, EXPIRY, 75, D("23100"), None)
    assert net_premium(Strategy((long_call,)), PriceBasis.LTP) == D("-8250")
    assert net_premium(Strategy((long_call, fut)), PriceBasis.ENTRY) == D("-7500")
    assert net_premium(Strategy((fut,)), PriceBasis.LTP) == D("0")


def test_missing_option_ltp_or_bad_basis_raises():
    """AC-4: an option leg without an LTP cannot give an LTP net premium; the basis must be a PriceBasis."""
    no_ltp = Leg(Action.BUY, Instrument.CE, D("23000"), EXPIRY, 75, D("100"), None)
    with pytest.raises(ValueError, match="LTP"):
        net_premium(Strategy((no_ltp,)), PriceBasis.LTP)
    assert net_premium(Strategy((no_ltp,)), PriceBasis.ENTRY) == D("-7500")
    with pytest.raises(ValueError, match="PriceBasis"):
        net_premium(RATIO, "LTP")
