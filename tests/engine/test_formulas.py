"""Leg formulas, strategy sum and scenario grid (scenario-calculations.md §1, §2; ADR-035, ADR-041)."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy, expiry_pnl, live_pnl, scenario_grid

EXP = datetime.date(2026, 10, 27)
BUY, SELL = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def leg(action, instrument, strike, entry, qty=75, ltp=None, expiry=EXP):
    strike = None if strike is None else D(strike)
    return Leg(action, instrument, strike, expiry, qty, D(entry), None if ltp is None else D(ltp))


def test_expiry_formulas_for_every_leg_type():
    """AC-1: BUY/SELL CALL and PUT expiry P&L follow the locked formulas, in and out of the money; futures per ADR-041."""
    # BUY CALL [MAX(M-K,0) - Entry] x Qty
    assert expiry_pnl(leg(BUY, CE, "23000", "100"), D("23250")) == D("11250")  # (250-100)*75
    assert expiry_pnl(leg(BUY, CE, "23000", "100"), D("22900")) == D("-7500")  # OTM: -100*75
    # SELL CALL [Entry - MAX(M-K,0)] x Qty
    assert expiry_pnl(leg(SELL, CE, "23000", "100"), D("23250")) == D("-11250")
    assert expiry_pnl(leg(SELL, CE, "23000", "100"), D("22900")) == D("7500")
    # BUY PUT [MAX(K-M,0) - Entry] x Qty
    assert expiry_pnl(leg(BUY, PE, "23000", "80.25"), D("22800")) == D("8981.25")  # (200-80.25)*75
    assert expiry_pnl(leg(BUY, PE, "23000", "80.25"), D("23100")) == D("-6018.75")
    # SELL PUT [Entry - MAX(K-M,0)] x Qty
    assert expiry_pnl(leg(SELL, PE, "23000", "80.25"), D("22800")) == D("-8981.25")
    assert expiry_pnl(leg(SELL, PE, "23000", "80.25"), D("23100")) == D("6018.75")
    # Exactly at the strike the option is worth zero.
    assert expiry_pnl(leg(BUY, CE, "23000", "100"), D("23000")) == D("-7500")
    # Futures (ADR-041 worked check): BUY at 24,000, Qty 75.
    assert expiry_pnl(leg(BUY, FUT, None, "24000"), D("24300")) == D("22500")
    assert expiry_pnl(leg(BUY, FUT, None, "24000"), D("23800")) == D("-15000")
    assert expiry_pnl(leg(SELL, FUT, None, "24000"), D("24300")) == D("-22500")
    assert expiry_pnl(leg(SELL, FUT, None, "24000"), D("23800")) == D("15000")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(strike=None), "strike"),  # option without a strike
        (dict(strike=D("0")), "strike"),
        (dict(instrument=FUT), "futures leg has no strike"),
        (dict(quantity=0), "quantity"),
        (dict(quantity=1.5), "quantity"),
        (dict(quantity=True), "quantity"),
        (dict(entry_price=D("-1")), "entry_price"),
        (dict(entry_price=42.5), "entry_price"),  # float money is refused
        (dict(entry_price=D("NaN")), "entry_price"),
        (dict(ltp=38.2), "ltp"),
        (dict(expiry="2026-10-27"), "expiry"),
        (dict(action="BUY"), "action"),
    ],
)
def test_invalid_leg_is_rejected(kwargs, message):
    """AC-1: a leg the formulas cannot be applied to is refused (fail closed), never defaulted."""
    base = dict(action=BUY, instrument=PE, strike=D("22800"), expiry=EXP, quantity=75, entry_price=D("42.50"))
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        Leg(**base)


def test_float_market_level_is_rejected():
    """AC-1: a float scenario level is refused; levels are exact Decimals."""
    with pytest.raises(ValueError, match="market"):
        expiry_pnl(leg(BUY, CE, "23000", "100"), 23000.0)


def test_strategy_pnl_is_sum_of_legs():
    """AC-2: strategy scenario P&L at a level is the sum of its legs' P&L at that level."""
    long_call = leg(BUY, CE, "23000", "150")
    short_call = leg(SELL, CE, "23200", "60")
    short_fut = leg(SELL, FUT, None, "23100", qty=25)
    strategy = Strategy((long_call, short_call, short_fut))
    for level in (D("22500"), D("23000"), D("23150.5"), D("23200"), D("24000")):
        expected = expiry_pnl(long_call, level) + expiry_pnl(short_call, level) + expiry_pnl(short_fut, level)
        assert strategy.expiry_pnl_at(level) == expected
    # One concrete value: at 23,150.50 -> (150.5-150)*75 + 60*75 + (23100-23150.5)*25 = 37.5 + 4500 - 1262.5
    assert strategy.expiry_pnl_at(D("23150.5")) == D("3275.00")
    with pytest.raises(ValueError, match="at least one leg"):
        Strategy(())


def test_expiry_uses_entry_price_never_ltp():
    """AC-3: the expiry scenario is the same whatever the LTP; §1 worked check gives 56,812.50 not 57,135."""
    at_entry = leg(BUY, PE, "22800", "42.50", ltp="38.20")
    other_ltp = leg(BUY, PE, "22800", "42.50", ltp="500.00")
    no_ltp = leg(BUY, PE, "22800", "42.50")
    results = {expiry_pnl(x, D("22000")) for x in (at_entry, other_ltp, no_ltp)}
    assert results == {D("56812.50")}
    # Red branch: what the LTP would have given, which the engine must not produce.
    assert (D("800") - D("38.20")) * 75 == D("57135.00")


def test_live_pnl_uses_ltp():
    """AC-4: live P&L is BUY (LTP-Entry) x Qty, SELL (Entry-LTP) x Qty, for options and futures; no LTP raises."""
    assert live_pnl(leg(BUY, PE, "22800", "42.50", ltp="38.20")) == D("-322.50")
    assert live_pnl(leg(SELL, PE, "23000", "86.00", ltp="72.50")) == D("1012.50")
    assert live_pnl(leg(BUY, FUT, None, "24000", ltp="24300")) == D("22500")
    assert live_pnl(leg(SELL, FUT, None, "24000", ltp="24300")) == D("-22500")
    with pytest.raises(ValueError, match="needs an LTP"):
        live_pnl(leg(BUY, CE, "23000", "100"))
    with pytest.raises(ValueError, match="needs an LTP"):
        Strategy((leg(BUY, CE, "23000", "100", ltp="90"), leg(SELL, CE, "23200", "40"))).live_pnl()


def test_every_scenario_cell_is_filled():
    """AC-5: every leg has a value at every level, out-of-the-money legs included; no blanks."""
    legs = (
        leg(BUY, PE, "22800", "42.50"),
        leg(SELL, PE, "23000", "86.00"),
        leg(SELL, CE, "23400", "91.50"),
        leg(BUY, CE, "23600", "44.00"),
        leg(BUY, FUT, None, "23100", qty=25),
    )
    levels = [D(x) for x in ("22000", "22909", "23047", "23200", "24000")]
    grid = scenario_grid(Strategy(legs), levels)
    assert grid.levels == tuple(levels)
    assert len(grid.leg_rows) == len(legs)
    for row in grid.leg_rows:
        assert len(row) == len(levels)
        assert all(isinstance(cell, D) for cell in row)
    # Out-of-the-money cells hold the premium result, not a blank: BUY 23,600 CE at 22,000 = -44 x 75.
    assert grid.leg_rows[3][0] == D("-3300.00")
    # BUY 22,800 PE at 24,000 is OTM: -42.50 x 75.
    assert grid.leg_rows[0][4] == D("-3187.50")
    # Totals are the column sums.
    for i in range(len(levels)):
        assert grid.totals[i] == sum(row[i] for row in grid.leg_rows)
    with pytest.raises(ValueError, match="at least one level"):
        scenario_grid(Strategy(legs), [])
    with pytest.raises(ValueError, match="level"):
        scenario_grid(Strategy(legs), [D("22000"), None])
