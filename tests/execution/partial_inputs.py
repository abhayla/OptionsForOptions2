"""Shared inputs for the partial-execution tests (W-023, REQ-058).

The strategy is the golden Iron Condor of scenario-calculations.md §6 (strikes, sides, prices), on the real
instrument-list fixture's NIFTY 2026-10-06 expiry with one real lot (65 units), as in execution_inputs.py. The
broker is a fake that counts every call; the orders and fills go through the real OrderBook.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from typing import Sequence

from execution_inputs import AS_OF, LOT, all_true_context, condor_legs

from ofo.engine import Action, Strategy
from ofo.execution import ExecutionContext
from ofo.execution.partial import OrderRefused, BrokerOrderStatus, BrokerPositionLine, ExecutionPlan, PlannedLeg
from ofo.orders import FillEvent, Order, OrderBook, OrderState
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import StrategyRecord

STRATEGY_ID = "S-1"
CONTRACTS = ("NIFTY26O0622800PE", "NIFTY26O0623000PE", "NIFTY26O0623400CE", "NIFTY26O0623600CE")  # real fixture symbols (W-026)
REFS = ("leg-1", "leg-2", "leg-3", "leg-4")
BROKER_IDS = ("BRK-1", "BRK-2", "BRK-3", "BRK-4")
REJECT_TEXT = "RMS:Margin Exceeds, Required:4400.00, Available:1200.00 for entity account-XX"
FILL_AT = datetime.datetime(2026, 9, 29, 4, 31, tzinfo=datetime.timezone.utc)
READ_AT = datetime.datetime(2026, 9, 29, 4, 32, tzinfo=datetime.timezone.utc)


class Clock:
    """The platform clock injected into every test book: fixed until a test moves it."""

    def __init__(self, t: datetime.datetime = READ_AT + datetime.timedelta(seconds=10)) -> None:
        self.t = t

    def __call__(self) -> datetime.datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += datetime.timedelta(seconds=seconds)


VERSION_ID = "v1"  # the record's own id of the version the plan executes (REQ-036 AC-1)


def record_for_legs(legs: tuple) -> StrategyRecord:
    """A record whose version 1 is exactly ``legs`` (proposed for execution)."""
    record = StrategyRecord(StrategyDefinition.from_engine("NIFTY", Strategy(tuple(legs))),
                            at=FILL_AT - datetime.timedelta(minutes=10), clock=lambda: READ_AT)
    record.propose_execution(at=FILL_AT - datetime.timedelta(minutes=9))
    return record


def condor_record(quantity: int = LOT) -> StrategyRecord:
    """The strategy's record: version 1 is exactly the plan's legs (proposed for execution)."""
    record = StrategyRecord(StrategyDefinition.from_engine("NIFTY", Strategy(condor_legs(quantity))),
                            at=FILL_AT - datetime.timedelta(minutes=10), clock=lambda: READ_AT)
    record.propose_execution(at=FILL_AT - datetime.timedelta(minutes=9))
    return record


def new_book(clock: Clock | None = None, record: StrategyRecord | None | bool = None) -> OrderBook:
    """``record=False`` leaves the strategy unbound (no record: REQ-036 AC-1 negative cases)."""
    book = OrderBook(clock=clock or Clock())
    if record is not False:
        book.bind_strategy(STRATEGY_ID, record or condor_record())
    return book


def plan() -> ExecutionPlan:
    return ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, leg) for r, c, leg in zip(REFS, CONTRACTS, condor_legs())))


def book_with_three_filled(fourth: OrderState = OrderState.REJECTED, clock: Clock | None = None,
                           record: StrategyRecord | None | bool = None) -> OrderBook:
    """Legs 1-3 filled at their planned prices; leg 4 (BUY 23,600 CE) in ``fourth`` with nothing filled."""
    book = new_book(clock, record)
    for i, (ref, contract, leg) in enumerate(zip(REFS, CONTRACTS, condor_legs())):
        book.add(Order(STRATEGY_ID, ref, contract, leg.action, leg.quantity, leg.entry_price,
                       broker_order_id=BROKER_IDS[i], version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        if i < 3:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, leg.action, leg.quantity,
                                      leg.entry_price, FILL_AT))
    if fourth is not OrderState.SUBMITTED:
        book.transition("BRK-4", fourth)
    return book


def three_positions(ltps: Sequence[D | None] = (None, None, None)) -> list[BrokerPositionLine]:
    legs = condor_legs()
    out = []
    for i in range(3):
        sign = 1 if legs[i].action is Action.BUY else -1
        out.append(BrokerPositionLine(CONTRACTS[i], sign * LOT, legs[i].entry_price, ltps[i]))
    return out


def statuses(fourth: OrderState = OrderState.REJECTED, reason: str | None = REJECT_TEXT) -> list[BrokerOrderStatus]:
    out = [BrokerOrderStatus(BROKER_IDS[i], CONTRACTS[i], OrderState.EXECUTED, LOT) for i in range(3)]
    out.append(BrokerOrderStatus("BRK-4", CONTRACTS[3], fourth, 0, reason))
    return out


class FakeBroker:
    """Counts every read; ``fail`` names a read that raises. Returns the lists it is given."""

    def __init__(self, positions: list[BrokerPositionLine], order_statuses: list[BrokerOrderStatus],
                 margin: D = D("150000.00"), fail: str | None = None,
                 read_at: datetime.datetime = READ_AT) -> None:
        self.positions, self.order_statuses, self.margin, self.fail = positions, order_statuses, margin, fail
        self.read_at = read_at
        self.calls: list[str] = []

    def _read(self, name: str) -> None:
        self.calls.append(name)
        if self.fail == name:
            raise ConnectionError(f"{name} timed out")

    def fetch_positions(self, strategy_id: str) -> tuple[list[BrokerPositionLine], datetime.datetime]:
        self._read("positions")
        return self.positions, self.read_at

    def fetch_order_statuses(self, strategy_id: str) -> tuple[list[BrokerOrderStatus], datetime.datetime]:
        self._read("order_statuses")
        return self.order_statuses, self.read_at

    def fetch_available_margin(self) -> D:
        self._read("margin")
        return self.margin


class FakePlanner:
    """Records every strategy it is asked about; answers a fixed figure."""

    def __init__(self, answer: D = D("48210.75")) -> None:
        self.answer = answer
        self.asked: list[Strategy] = []

    def required_margin(self, strategy: Strategy) -> D:
        self.asked.append(strategy)
        return self.answer


class FakeSubmitter:
    """Records every order sent; ``refuse`` = number of the call (1-based) that raises the broker's text."""

    def __init__(self, refuse: int | None = None) -> None:
        self.sent: list[Order] = []
        self.refuse = refuse

    def submit(self, order) -> str:
        return self._send(order)

    def _send(self, order: Order) -> str:
        """The broker's side once the capability was redeemed (subclasses reuse it)."""
        self.sent.append(order)
        if self.refuse == len(self.sent):
            raise OrderRefused("Order rejected: RMS:Margin Exceeds")
        return f"NEW-{len(self.sent)}"


def entry_context(**overrides: object) -> ExecutionContext:
    overrides.setdefault("version_id", VERSION_ID)
    return all_true_context(**overrides)


__all__ = ["AS_OF", "LOT"]
