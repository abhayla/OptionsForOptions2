"""B1 (27 Nov 2026): a paused paper book's "as of" is the time of the last quote the feed held for the leg
(REQ-109 AC-5, ADR-330 (36): the label and the figure agree), never an order's time. When the feed stopped, the
snapshot keeps the ended subscription's last quote time (``ended_times``); with no time known at all the answer is
None (the screen then omits the clause).
Class: every PAUSED paper book (list, single, totals strip read ``paused_as_of``)."""
from __future__ import annotations

import datetime
from types import SimpleNamespace

from ofo.timeutil import IST
from ofo.tracking import paper

LAST_QUOTE = datetime.datetime(2026, 11, 27, 11, 2, 10, tzinfo=IST)
ORDER_TIME = datetime.datetime(2026, 11, 27, 9, 20, 0, tzinfo=IST)  # the entry's own time: must never label a price


def _snapshot(ended: dict) -> SimpleNamespace:
    # feed stopped: the leg has no held quote (problem set), only the ended subscription's last quote time remains
    return SimpleNamespace(legs={"NSE_FO:1": SimpleNamespace(problem="not_held", quote=None)}, ended_times=ended,
                           market_closed=False)


def test_the_paused_as_of_is_the_last_quote_time_the_feed_held_not_an_order_time():
    price = paper.leg_price(_snapshot({"NSE_FO:1": LAST_QUOTE}), "NSE_FO:1")
    assert price.state == "missing"
    assert paper.paused_as_of([price]) == LAST_QUOTE
    assert paper.paused_as_of([price]) != ORDER_TIME


def test_no_quote_time_known_gives_no_as_of_never_an_invented_one():
    price = paper.leg_price(_snapshot({}), "NSE_FO:1")
    assert paper.paused_as_of([price]) is None
