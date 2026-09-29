"""Books for the order tests: every strategy an order names is bound to a record with a version v1 (REQ-036 AC-1,
W-026: ``OrderBook.add`` refuses an unbound strategy or a version its record does not have)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.engine import Action, Instrument
from ofo.orders import OrderBook
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import StrategyRecord

TEST_STRATEGIES = ("STRAT-1", "STRAT-2", "STRAT-5", "STRAT-9")
_AT = datetime.datetime(2026, 1, 5, 4, 0, tzinfo=datetime.timezone.utc)


def record_with_v1() -> StrategyRecord:
    leg = DefinitionLeg(Action.BUY, Instrument.CE, D("23000"), datetime.date(2026, 10, 27), 75)
    record = StrategyRecord(StrategyDefinition("NIFTY", (leg,)), at=_AT)
    record.propose_execution(at=_AT)
    return record


def bound_book(**kwargs: object) -> OrderBook:
    book = OrderBook(**kwargs)  # type: ignore[arg-type]
    for sid in TEST_STRATEGIES:
        book.bind_strategy(sid, record_with_v1())
    return book
