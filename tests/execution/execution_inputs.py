"""Shared inputs for the pre-execution gate tests (W-014, REQ-059).

The catalogue is the REAL Zerodha instrument-list slice (tests/fixtures/instruments/, captured 2026-09-29). The
strategy is the golden Iron Condor of scenario-calculations.md §6 (same strikes, sides and prices), placed on the
fixture's NIFTY 2026-10-06 expiry with one real lot (65 units) so every contract exists in the real list.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Callable

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import (
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    SafetyResult,
    VersionState,
    check_pre_execution,
)
from ofo.instruments import Catalogue, EligibilityRegistry, EligibilityStatus, parse_instruments_csv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 6)
LOT = 65
AS_OF = datetime.datetime(2026, 9, 29, 10, 0, tzinfo=IST)


def condor_legs(quantity: int = LOT, expiry: datetime.date = EXPIRY) -> tuple[Leg, ...]:
    return (
        Leg(Action.BUY, Instrument.PE, D("22800"), expiry, quantity, D("42.50")),
        Leg(Action.SELL, Instrument.PE, D("23000"), expiry, quantity, D("86.00")),
        Leg(Action.SELL, Instrument.CE, D("23400"), expiry, quantity, D("91.50")),
        Leg(Action.BUY, Instrument.CE, D("23600"), expiry, quantity, D("44.00")),
    )


@pytest.fixture()
def condor() -> Strategy:
    return Strategy(condor_legs())


@pytest.fixture()
def catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load(parse_instruments_csv(FIXTURE))
    return cat


@pytest.fixture()
def eligibility(catalogue: Catalogue) -> EligibilityRegistry:
    """Every catalogue contract confirmed tradable (as a Zerodha read would record it)."""
    registry = EligibilityRegistry()
    for entry in catalogue.all_entries():
        registry.record(EligibilityStatus(entry.contract.instrument_token, True, AS_OF))
    return registry


def all_true_context(**overrides: Any) -> ExecutionContext:
    base = ExecutionContext(
        strategy_id="S-1",
        version_id="V-3",
        actor="user:U-42",
        underlying="NIFTY",
        action=ExecutionAction.NEW_ENTRY,
        as_of=AS_OF,
        market_open=True,
        broker_connected=True,
        session_valid=True,
        pro_entitled=True,
        version_state=VersionState.ACTIVE,
        rules_valid=True,
        dependencies_satisfied=True,
        data_health={d: DataHealth.HEALTHY for d in DataInput},
        margin_available=D("150000.00"),
        margin_required=D("48210.75"),
        reconciliation_blocked_strategy_ids=frozenset({"S-OTHER"}),
        charges_estimate=D("236.40"),
    )
    return dataclasses.replace(base, **overrides)


@pytest.fixture()
def make_context() -> Callable[..., ExecutionContext]:
    return all_true_context


STRATEGY_ID = "S-1"


def check(
    strategy: Strategy, ctx: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry,
    strategy_id: str = STRATEGY_ID,
) -> SafetyResult:
    """Run the gate for a strategy whose own id is ``strategy_id`` (every test strategy is S-1 unless stated)."""
    return check_pre_execution(strategy, ctx, catalogue, eligibility, strategy_id=strategy_id)


def closing_orders(legs: tuple[Leg, ...]) -> tuple[Leg, ...]:
    """The orders that close ``legs``: same contract and quantity, opposite side."""
    flip = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
    return tuple(dataclasses.replace(leg, action=flip[leg.action]) for leg in legs)


def find_token(catalogue: Catalogue, instrument_type: str, strike: str, expiry: datetime.date = EXPIRY) -> int:
    (contract,) = [
        c for c in catalogue.contracts_for("NIFTY", expiry, frozenset({instrument_type})) if c.strike == D(strike)
    ]
    return contract.instrument_token
