"""Shared hand-built legs for the execution-plan tests (W-022, REQ-056). NIFTY, one real lot (65 units)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from partial_inputs import LOT

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.interfaces import MarginRequirement
from ofo.execution.planned import ExecutionPlan, PlannedLeg

PREV = datetime.date(2026, 9, 29)
EXP = datetime.date(2026, 10, 6)
NEXT = datetime.date(2026, 10, 13)
BUY, SELL = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def leg(action: Action, kind: Instrument, strike: str | None, qty: int = LOT, expiry: datetime.date = EXP,
        price: str = "50.00", ltp: str | None = None) -> Leg:
    return Leg(action, kind, D(strike) if strike else None, expiry, qty, D(price), D(ltp) if ltp else None)


def mk(*legs: Leg) -> ExecutionPlan:
    return ExecutionPlan("S-9", tuple(PlannedLeg(f"L{i + 1}", f"C{i + 1}", lg) for i, lg in enumerate(legs)))


class FakeMargin:
    """Engine MarginPlanner: 100,000 + a fixed amount per leg present (so a leg's impact is its amount); counts calls."""

    def __init__(self, per_leg: dict[Leg, D], fail: bool = False, base: D = D("100000")) -> None:
        self.per_leg, self.fail, self.base = per_leg, fail, base
        self.asked: list[Strategy] = []

    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        self.asked.append(strategy)
        if self.fail:
            raise ConnectionError("margin service timed out")
        return MarginRequirement(self.base + sum((self.per_leg.get(lg, D(0)) for lg in strategy.legs), D(0)), "fake")


class FakeConstraints:
    def __init__(self, freeze: object, per_batch: object) -> None:
        self.freeze, self.per_batch = freeze, per_batch

    def freeze_quantity(self, contract: str) -> object:
        return self.freeze

    def max_orders_per_batch(self) -> object:
        return self.per_batch
