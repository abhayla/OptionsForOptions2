"""REQ-056 AC-12 / ADR-119: the Execute route's own ``market_open`` (the value it puts in the gate's context) follows the
calendar. No database: the function is pure."""
from __future__ import annotations

import datetime

from ofo.timeutil import IST
from ofo_app.routes.execute import market_open


def _at(month: int, day: int, h: int, m: int = 0, s: int = 0, year: int = 2026) -> datetime.datetime:
    return datetime.datetime(year, month, day, h, m, s, tzinfo=IST)


def test_ac12_route_market_open_proof_cases() -> None:
    """AC-12: Dussehra Tue 20 Oct 10:00 closed; Wed 21 Oct 10:00 open; 15:30:00 closed; 09:15:00 open; a Sunday
    closed; a year with no holiday data is None (unconfirmed), never True."""
    assert market_open(_at(10, 20, 10)) is False
    assert market_open(_at(10, 21, 10)) is True
    assert market_open(_at(10, 21, 15, 30)) is False
    assert market_open(_at(10, 21, 9, 15)) is True
    assert market_open(_at(10, 25, 11)) is False
    assert market_open(_at(1, 5, 10, year=2027)) is None
