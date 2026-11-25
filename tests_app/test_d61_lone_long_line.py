"""D-61 (ADR-320 point 5, GC-ICLIVE-E): after "Buy back the untested short" leaves a long option with no short
against it, the approach's What changes block says so in one line, decided from the server's resulting legs.

Real case: C7 161: the buy-back of the 25700 CE leaves the long 25800 CE; the trade becomes a put spread plus a
long call. Nearest fixtures (the recorded legs of 161 are not a fixture): ADJ-14 (call closed, long call stays) and
ADJ-02 (put closed, long put stays). The sentence is the owner's, character for character;
<call or put> is the long option's type.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment import what_changes
from ofo.adjustment.approaches import PositionLeg
from test_adjustment_approaches_route import load, post
from test_d21_what_changes import client

LINE = "This trade now has a long {kind} with no short against it; its result now depends on direction."
DAY = datetime.date(2026, 11, 3)


def leg(side, kind, strike):
    return PositionLeg(side, kind, D(strike), DAY, 1, D("10"), f"NIFTY{strike}{kind}")


def test_call_case_long_call_with_no_short_call():
    after = (leg("BUY", "PE", 22400), leg("SELL", "PE", 22600), leg("BUY", "CE", 23650))
    assert what_changes.lone_long_line(after) == LINE.format(kind="call")


def test_put_case_long_put_with_no_short_put():
    after = (leg("BUY", "PE", 22400), leg("SELL", "CE", 23450), leg("BUY", "CE", 23650))
    assert what_changes.lone_long_line(after) == LINE.format(kind="put")


def test_a_short_that_remains_on_that_side_gives_no_line():
    after = (leg("BUY", "PE", 22400), leg("SELL", "PE", 22600), leg("SELL", "CE", 23450), leg("SELL", "CE", 23500),
             leg("BUY", "CE", 23650))
    assert what_changes.lone_long_line(after) is None
    assert what_changes.lone_long_line((leg("BUY", "PE", 22400), leg("SELL", "PE", 22600))) is None


def test_no_after_state_gives_no_line_and_no_crash():
    assert what_changes.lone_long_line(()) is None  # nothing stays open (a full exit)
    assert what_changes.lone_long_line(None) is None  # no after-state built


def test_route_call_case_the_block_of_a26_carries_the_line():
    block = post(client(load("ADJ-14"))).json()["what_changes"]["A-26"]
    assert LINE.format(kind="call") in block["reason_line"]


def test_route_put_case_the_block_of_a26_carries_the_line():
    block = post(client(load("ADJ-02"))).json()["what_changes"]["A-26"]
    assert LINE.format(kind="put") in block["reason_line"]


def test_route_no_other_approach_carries_the_line():
    blocks = post(client(load("ADJ-14"))).json()["what_changes"]
    others = {a: b["reason_line"] for a, b in blocks.items() if a != "A-26"}
    assert others and not any(r and "no short against it" in r for r in others.values())


@pytest.mark.parametrize("sid", ["ADJ-01"])
def test_route_a_full_exit_after_buy_back_gives_no_line(sid):
    block = post(client(load(sid))).json()["what_changes"].get("A-26")
    assert block is None or not (block["reason_line"] and "no short against it" in block["reason_line"])
