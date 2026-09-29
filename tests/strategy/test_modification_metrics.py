"""REQ-037 AC-2: the modification proposal recalculates max profit/loss, breakevens, current P&L, margin and
charges through the engine and the margin/charges interfaces (AC-2), never a silent 0 when a provider fails.

Core proof (W-027): the golden Iron Condor's sold 23,000 PE rolled to 22,900 PE returns engine-recalculated
Before/After metrics. Before values are the published golden numbers (scenario-calculations.md §6); After values
are hand-computed below from the same §1 formulas, never copied from a code run.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal as D

from ofo.engine.interfaces import ChargesBreakdown, MarginRequirement
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.modification import ChangeKind, LegChange, propose_modification
from ofo.strategy.versions import ExecutionResult, OutcomeKind, Position, ResultStatus, StrategyRecord

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
QTY = 75

GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D("39.50")),
))
CONDOR = StrategyDefinition.from_engine("NIFTY", GOLDEN)

# The rolled put's price: an entry of 70.00 and an LTP of 65.00, chosen for this test (not published anywhere).
ROLLED_ENTRY = D("70.00")
ROLLED_LTP = D("65.00")

ENTRY_PRICES = {
    (Instrument.PE, D("22800"), EXPIRY): D("42.50"),
    (Instrument.PE, D("23000"), EXPIRY): D("86.00"),
    (Instrument.CE, D("23400"), EXPIRY): D("91.50"),
    (Instrument.CE, D("23600"), EXPIRY): D("44.00"),
    (Instrument.PE, D("22900"), EXPIRY): ROLLED_ENTRY,
}
LTPS = {
    (Instrument.PE, D("22800"), EXPIRY): D("38.20"),
    (Instrument.PE, D("23000"), EXPIRY): D("72.50"),
    (Instrument.CE, D("23400"), EXPIRY): D("78.00"),
    (Instrument.CE, D("23600"), EXPIRY): D("39.50"),
    (Instrument.PE, D("22900"), EXPIRY): ROLLED_LTP,
}

# The proposal: roll the sold 23,000 PE to the sold 22,900 PE (REQ-037's worked example).
ROLL = (
    LegChange(ChangeKind.REMOVE, Instrument.PE, D("23000"), EXPIRY),
    LegChange(ChangeKind.ADD, Instrument.PE, D("22900"), EXPIRY, action=Action.SELL, quantity=QTY),
)


def at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def clock() -> datetime.datetime:
    return T0 + datetime.timedelta(days=10)


def contract(instrument: Instrument, strike: str) -> tuple:
    return ("NIFTY", instrument, D(strike), EXPIRY)


FILLED = Position((
    (contract(Instrument.PE, "22800"), QTY),
    (contract(Instrument.PE, "23000"), -QTY),
    (contract(Instrument.CE, "23400"), -QTY),
    (contract(Instrument.CE, "23600"), QTY),
))


def executed_record() -> StrategyRecord:
    """A StrategyRecord whose v1 (the golden condor) is active, as W-012's own core proof builds one."""
    rec = StrategyRecord(CONDOR, at=T0, clock=clock)
    v1 = rec.propose_execution(at=at(1))
    rec.confirm(v1.number, at=at(2))
    outcome = rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, FILLED, at(3), "exec-1"))
    assert outcome.kind is OutcomeKind.ACTIVATED
    return rec


@dataclass(frozen=True)
class _FakeMarginPlanner:
    total: D

    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        return MarginRequirement(total=self.total, source="fake-margin-planner")


@dataclass(frozen=True)
class _FakeChargesModel:
    total: D

    def charges_for(self, strategy: Strategy) -> ChargesBreakdown:
        return ChargesBreakdown(items=(("brokerage", self.total),))


class _FailingMarginPlanner:
    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        raise RuntimeError("margin service unavailable")


class _FailingChargesModel:
    def charges_for(self, strategy: Strategy) -> ChargesBreakdown:
        raise RuntimeError("charges service unavailable")


def test_core_ac2_roll_recalculates_before_and_after():
    """AC-2 (core proof): propose_modification's Before equals the golden condor's published numbers
    (scenario-calculations.md §6: max profit 6,825; max loss 8,175; breakevens 22,909 / 23,491; live P&L 1,365.00),
    and After is hand-computed for BUY 22,800 PE / SELL 22,900 PE (rolled, entry 70.00, LTP 65.00) / SELL 23,400 CE
    / BUY 23,600 CE:

    Net credit = (70.00 + 91.50 - 42.50 - 44.00) x 75 = 75.00 x 75 = 5,625 = max profit.
    Expiry payoff at 0/22,800/22,900/23,400/23,600 = -1,875 / -1,875 / 5,625 / 5,625 / -9,375 (upper tail flat) ->
    min P&L -9,375 = max loss 9,375. Breakevens: 22,800 + 1,875x100/7,500 = 22,825; 23,400 + 5,625x200/15,000 = 23,475.
    Live P&L = -322.50 (unchanged leg 1) + (70.00-65.00)x75=375.00 (rolled leg) + 1,012.50 (unchanged leg 3)
    - 337.50 (unchanged leg 4) = 727.50.
    """
    rec = executed_record()
    comparison = propose_modification(
        rec, ROLL, strategy_id="S-1", entry_prices=ENTRY_PRICES, ltps=LTPS,
        margin_planner=_FakeMarginPlanner(D("50000.00")), charges_model=_FakeChargesModel(D("236.40")),
    )
    assert comparison.active_version_number == 1

    before = comparison.before
    assert before.max_profit == D("6825")
    assert before.max_loss == D("8175")
    assert before.breakevens == (D("22909"), D("23491"))
    assert before.current_pnl == D("1365.00")
    assert before.margin == D("50000.00") and before.margin_unknown_reason is None
    assert before.charges == D("236.40") and before.charges_unknown_reason is None

    after = comparison.after
    assert after.max_profit == D("5625")
    assert after.max_loss == D("9375")
    assert after.breakevens == (D("22825"), D("23475"))
    assert after.current_pnl == D("727.50")
    assert after.margin == D("50000.00")
    assert after.charges == D("236.40")

    # Consistency: after's max loss equals -min_pnl (the same relationship the engine itself locks, §3).
    assert after.max_loss == -after.min_pnl

    # AC-3 side-effect check: computing the comparison creates no version and touches nothing (read-only).
    assert len(rec.versions) == 1 and rec.proposed_version is None and rec.active_version.number == 1


def test_ac2_a_failing_margin_or_charges_provider_gives_unknown_never_zero():
    """AC-2: margin and charges come from the interfaces; a failing provider reports unknown, never a silent 0."""
    rec = executed_record()
    comparison = propose_modification(
        rec, ROLL, strategy_id="S-1", entry_prices=ENTRY_PRICES, ltps=None,
        margin_planner=_FailingMarginPlanner(), charges_model=_FailingChargesModel(),
    )
    for side in (comparison.before, comparison.after):
        assert side.margin is None and side.margin_unknown_reason
        assert side.charges is None and side.charges_unknown_reason
        assert side.current_pnl is None and side.current_pnl_unknown_reason  # no LTPs supplied either
