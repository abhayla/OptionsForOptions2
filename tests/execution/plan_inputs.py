"""Shared hand-built legs for the execution-plan tests (W-022, REQ-056). NIFTY, one real lot (65 units)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from partial_inputs import LOT

from ofo.engine import Action, Instrument, Leg
from ofo.execution.planned import ExecutionPlan, PlannedLeg

EXP = datetime.date(2026, 10, 6)
NEXT = datetime.date(2026, 10, 13)
BUY, SELL = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def leg(action: Action, kind: Instrument, strike: str | None, qty: int = LOT, expiry: datetime.date = EXP,
        price: str = "50.00", ltp: str | None = None) -> Leg:
    return Leg(action, kind, D(strike) if strike else None, expiry, qty, D(price), D(ltp) if ltp else None)


def mk(*legs: Leg) -> ExecutionPlan:
    return ExecutionPlan("S-9", tuple(PlannedLeg(f"L{i + 1}", f"C{i + 1}", lg) for i, lg in enumerate(legs)))
