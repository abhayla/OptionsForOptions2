"""D-48 (REQ-078 AC-11, AC-12; ADR-330 (42)): POST /api/strategies/leg-edit with control "expiry" on the real fixture.

Same seams as test_leg_edit_route (no database, no Kite): the golden condor of 2026-10-06 moved to the fixture's other
expiry 2026-09-29 (today 2026-09-28, both listed). A missing strike refuses the whole change and names the strike.
"""
from __future__ import annotations

import datetime

from test_leg_edit_route import BY_ID, HTTP_OK, HTTP_UNPROCESSABLE, STAMP, START, legs, post, strikes

EARLY = datetime.date(2026, 9, 29)
TODAY = datetime.date(2026, 9, 28)
BY_EARLY = {(c.instrument_type, int(c.strike)): i for i, c in BY_ID.items()
            if c.name == "NIFTY" and c.expiry == EARLY and c.instrument_type in ("CE", "PE")}


def expiries(reply):
    return [leg["expiry"] for leg in reply["legs"]]


def test_all_legs_move_keeping_strike_side_and_lots_and_the_reply_has_no_shift_total():
    status, reply = post({"legs": legs(), "shift_total": 100,
                          "edit": {"control": "expiry", "expiry": "2026-09-29"}}, today=TODAY)
    assert status == HTTP_OK
    assert expiries(reply) == ["2026-09-29"] * 4
    assert strikes(reply) == [22800, 23000, 23400, 23600]
    assert [(x["action"], x["instrument"], x["lots"]) for x in reply["legs"]] == [
        (a, t, 1) for a, t, _, _ in START]
    assert reply["shift_total"] is None
    assert [x["instrument_id"] for x in reply["legs"]] == [BY_EARLY[(t, k)] for _, t, k, _ in START]
    assert all(x["price_source"] == "none" for x in reply["legs"])  # re-captured: the fake feed has no price here


def test_one_leg_moves_and_the_others_keep_expiry_and_entry():
    status, reply = post({"legs": legs(), "edit": {"control": "expiry", "index": 1, "expiry": "2026-09-29"}},
                         today=TODAY)
    assert status == HTTP_OK
    assert expiries(reply) == ["2026-10-06", "2026-09-29", "2026-10-06", "2026-10-06"]
    assert reply["legs"][0]["planned_entry"] == "42.50" and reply["legs"][1]["planned_entry"] is None


def test_one_missing_strike_refuses_everything_and_names_the_strike():
    early = [{"instrument_id": BY_EARLY[("CE", 23000)], "action": "BUY", "lots": 1, "base_lots": 1,
              "planned_entry": "1.00", "captured_at": STAMP.isoformat()},
             {"instrument_id": next(i for i, c in BY_ID.items() if c.name == "NIFTY" and c.expiry == EARLY
                                    and c.instrument_type == "PE" and int(c.strike) == 15000),
              "action": "SELL", "lots": 1, "base_lots": 1, "planned_entry": "1.00", "captured_at": STAMP.isoformat()}]
    status, reply = post({"legs": early, "edit": {"control": "expiry", "expiry": "2026-10-06"}}, today=TODAY)
    assert status == HTTP_UNPROCESSABLE and "legs" not in reply
    assert "No 15,000 PE is listed for 06 Oct 2026, so leg 2 cannot move there." in str(reply)
    assert "no leg changed" in str(reply)


def test_an_expired_leg_and_an_unknown_expiry_are_refused_with_reasons():
    status, reply = post({"legs": legs(), "edit": {"control": "expiry", "expiry": "2026-09-29"}},
                         today=datetime.date(2026, 10, 7))
    assert status == HTTP_UNPROCESSABLE and "Leg 1 (BUY NIFTY 22,800 PE, expiry 06 Oct 2026)" in str(reply)
    status, reply = post({"legs": legs(), "edit": {"control": "expiry", "expiry": "2030-01-03"}}, today=TODAY)
    assert status == HTTP_UNPROCESSABLE and "is listed for 03 Jan 2030" in str(reply)


def test_a_missing_expiry_and_a_list_not_loaded_today_are_refused():
    status, _ = post({"legs": legs(), "edit": {"control": "expiry"}}, today=TODAY)
    assert status == HTTP_UNPROCESSABLE
    status, reply = post({"legs": legs(), "edit": {"control": "expiry", "expiry": "2026-09-29"}}, today=TODAY,
                         current=False)
    assert status == HTTP_UNPROCESSABLE and "legs" not in reply
