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
from types import SimpleNamespace

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


def _leg_of(x):
    return PositionLeg(x["side"], x["type"], D(x["strike"]), DAY, 1, D("10"), "X")


def test_a27_style_after_state_with_a_lone_long_shows_the_line_on_any_approach():
    """Round 2: the line follows the resulting legs, not the approach id: A-27 (buy back the cheap shorts)
    can leave a long call with no short call exactly like A-26."""
    after = (leg("BUY", "PE", 22400), leg("SELL", "PE", 22600), leg("BUY", "CE", 23650))
    assert what_changes.lone_long_line(after) == LINE.format(kind="call")
    for approach_id in ("A-27", "A-26", "A-01"):  # any id: only the legs decide
        col = SimpleNamespace(built=SimpleNamespace(id=approach_id, after=after))
        assert what_changes._with_lone_long(col, None) == LINE.format(kind="call"), approach_id
    kept_after = (leg("SELL", "CE", 1), leg("BUY", "CE", 2))
    kept = SimpleNamespace(built=SimpleNamespace(id="A-01", after=kept_after))
    assert what_changes._with_lone_long(kept, None) is None


def test_route_the_line_is_on_exactly_the_approaches_whose_after_legs_leave_a_lone_long():
    body = post(client(load("ADJ-14"))).json()
    blocks, seen = body["what_changes"], {"with": set(), "without": set()}
    for a in body["approaches"]:
        if a.get("refusal") or a["id"] not in blocks:
            continue
        lone = what_changes.lone_long_line([_leg_of(x) for x in a["after_legs"]])
        line = blocks[a["id"]]["reason_line"] or ""
        assert ("no short against it" in line) == (lone is not None), a["id"]
        seen["with" if lone else "without"].add(a["id"])
    assert "A-26" in seen["with"] and {"A-28", "A-29"} <= seen["without"]  # a roll / spread keeps its shorts: no line
