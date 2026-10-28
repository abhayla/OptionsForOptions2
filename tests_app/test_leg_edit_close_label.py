"""ADR-197 round 2: "each captured entry is labelled as the close with its time" also after a leg edit.

A Shift / Width / Hedge / strike step / Reset Prices edit that re-captures a price outside market hours answers that
leg's ``close_at`` (the quote's own last-price time, from the capture); a leg the edit did not re-capture keeps the
``close_at`` the browser sent; a leg re-captured in market hours has none. Driven through the real route with the
leg-edit test seams (tests_app/test_leg_edit_route.py), no database, no Kite connection.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo.outcome.planned_entry import PlannedEntry
from test_leg_edit_route import BY_ID, NEW_STAMP, START, post, rows

CLOSE_AT = datetime.datetime(2026, 9, 30, 15, 29, 58, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
SENT_CLOSE = "2026-09-30T15:29:40+05:30"
HTTP_OK = 200


def _capture(close_at):
    async def capture(ctx, feed, underlying, ids):
        return NEW_STAMP, {i: dataclasses.replace(PlannedEntry(Decimal("10.00"), "ltp"), close_at=close_at)
                           for i in ids if i in BY_ID}
    return capture


def test_a_step_recaptured_after_hours_carries_the_close_time_and_the_others_keep_theirs():
    body = {"legs": rows(START, close_at=SENT_CLOSE), "edit": {"control": "step", "index": 2, "direction": 1}}
    status, reply = post(body, capture=_capture(CLOSE_AT))
    assert status == HTTP_OK, reply
    got = [leg["close_at"] for leg in reply["legs"]]
    assert datetime.datetime.fromisoformat(got[2]) == CLOSE_AT  # the re-captured leg: the close's own time
    assert [datetime.datetime.fromisoformat(got[i]) for i in (0, 1, 3)] == [
        datetime.datetime.fromisoformat(SENT_CLOSE)] * 3  # untouched legs keep what was sent


def test_reset_prices_after_hours_labels_every_recaptured_leg():
    body = {"legs": rows(START), "edit": {"control": "reset_prices"}}
    body["legs"][0]["planned_entry"] = None
    body["legs"][0]["captured_at"] = None
    status, reply = post(body, capture=_capture(CLOSE_AT))
    assert status == HTTP_OK, reply
    assert datetime.datetime.fromisoformat(reply["legs"][0]["close_at"]) == CLOSE_AT


def test_in_market_hours_a_recaptured_leg_has_no_close_time():
    body = {"legs": rows(START), "edit": {"control": "step", "index": 2, "direction": 1}}
    status, reply = post(body, capture=_capture(None))
    assert status == HTTP_OK, reply
    assert [leg["close_at"] for leg in reply["legs"]] == [None] * 4
