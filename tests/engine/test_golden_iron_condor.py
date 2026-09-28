"""Golden test: the handoffs' Iron Condor, spec/business-rules/scenario-calculations.md §6 (and §1 worked check)."""
import datetime
from decimal import Decimal as D

from ofo.engine import Action, Instrument, Leg, Strategy, expiry_pnl, live_pnl, strategy_metrics

EXPIRY = datetime.date(2026, 10, 27)
QTY = 75

LEG1 = Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D("38.20"))
LEG2 = Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50"))
LEG3 = Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D("78.00"))
LEG4 = Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D("39.50"))
CONDOR = Strategy((LEG1, LEG2, LEG3, LEG4))


def _expected_strategy_expiry_pnl(level: int) -> D:
    """§6 bullet 3, transcribed as ranges."""
    if level <= 22800 or level >= 23600:
        return D("-8175")
    if level in (22900, 23500):
        return D("-675")
    return D("6825")  # 23,000-23,400


def test_golden_iron_condor_reproduced_exactly():
    """AC-7: every §6 number is computed from the four legs with exact Decimal equality."""
    # Live P&L per leg and the strategy total.
    assert [live_pnl(leg) for leg in CONDOR.legs] == [D("-322.50"), D("1012.50"), D("1012.50"), D("-337.50")]
    assert CONDOR.live_pnl() == D("1365.00")

    # Max profit, max loss, breakevens, all derived from the payoff.
    metrics = strategy_metrics(CONDOR)
    assert metrics.max_profit == D("6825")
    assert metrics.max_loss == D("8175")
    assert metrics.min_pnl == D("-8175")
    assert metrics.breakevens == (D("22909"), D("23491"))
    assert all(CONDOR.expiry_pnl_at(be) == 0 for be in metrics.breakevens)

    # 21 strategy expiry levels, 22,000 to 24,000 in 100-point steps.
    levels = list(range(22000, 24001, 100))
    assert len(levels) == 21
    for level in levels:
        assert CONDOR.expiry_pnl_at(D(level)) == _expected_strategy_expiry_pnl(level), level

    # Per-leg samples.
    assert expiry_pnl(LEG1, D("22000")) == D("56812.50")
    assert expiry_pnl(LEG2, D("22000")) == D("-68550")
    assert expiry_pnl(LEG3, D("23500")) == D("-637.50")
    assert expiry_pnl(LEG4, D("24000")) == D("26700")


def test_worked_check_uses_entry_price_not_ltp():
    """AC-7: §1 worked check - BUY 22,800 PE at 22,000 is 56,812.50, not the LTP-based 57,135."""
    assert expiry_pnl(LEG1, D("22000")) == D("56812.50")
    assert expiry_pnl(LEG1, D("22000")) != D("57135")


def test_minus_322_50_stays_exact():
    """AC-7: §5 - leg 1's live P&L is exactly -322.50 where binary float gives -322.4999999999998."""
    assert (38.20 - 42.50) * 75 != -322.50  # the float defect §5 measured
    assert live_pnl(LEG1) == D("-322.50")
    assert str(live_pnl(LEG1)) == "-322.50"
