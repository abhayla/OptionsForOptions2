"""Shared reconciliation fixtures: the golden Iron Condor (spec/business-rules/scenario-calculations.md §6, the same
four legs as tests/engine/test_golden_iron_condor.py and tests/strategy/test_versions.py), executed as version 1.

Signed units: BUY positive, SELL negative. Golden legs, 75 units each: BUY 22800 PE, SELL 23000 PE, SELL 23400 CE,
BUY 23600 CE.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

from ofo.audit.log import AuditLog
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus, StrategyRecord

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
NEXT_EXPIRY = datetime.date(2026, 11, 24)
QTY = 75

GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D("39.50")),
))
CONDOR = StrategyDefinition.from_engine("NIFTY", GOLDEN, risk_limits={"max_loss": D("8175")})


def c(instrument: Instrument, strike: str, expiry: datetime.date = EXPIRY) -> tuple:
    return ("NIFTY", instrument, D(strike), expiry)


BP22800 = c(Instrument.PE, "22800")
SP23000 = c(Instrument.PE, "23000")
SC23400 = c(Instrument.CE, "23400")
BC23600 = c(Instrument.CE, "23600")
CONDOR_UNITS = {BP22800: 75, SP23000: -75, SC23400: -75, BC23600: 75}


def at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def clock() -> datetime.datetime:
    return T0 + datetime.timedelta(days=1)


def with_legs(definition: StrategyDefinition, legs) -> StrategyDefinition:
    return dataclasses.replace(definition, legs=tuple(legs))


def scaled(definition: StrategyDefinition, quantity: int) -> StrategyDefinition:
    return with_legs(definition, (dataclasses.replace(leg, quantity=quantity) for leg in definition.legs))


def executed(definition: StrategyDefinition = CONDOR, reference: str = "exec-1") -> StrategyRecord:
    """A record whose version 1 (``definition``) executed completely and is active."""
    rec = StrategyRecord(definition, at=T0, clock=clock)
    v1 = rec.propose_execution(at=at(1))
    rec.confirm(v1.number, at=at(2))
    rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, v1.intended_position, at(3), reference))
    assert rec.active_version == v1 and not rec.reconciliation_required
    return rec


def single_leg(action: Action, instrument: Instrument, strike: str, quantity: int) -> StrategyDefinition:
    from ofo.strategy.definition import DefinitionLeg
    return StrategyDefinition("NIFTY", (DefinitionLeg(action, instrument, D(strike), EXPIRY, quantity),))


def position(units: dict) -> Position:
    return Position.of(units)


def audit_log() -> AuditLog:
    return AuditLog()
