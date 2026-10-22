"""W-126 (REQ-076, REQ-077, REQ-078): POST /api/strategies/leg-edit on the REAL instrument-list fixture.

The golden NIFTY iron condor of the 2026-10-06 expiry (tests/fixtures/instruments/instruments_slice.csv, lot 65). The
capture is a hand price table keyed by (type, strike) so every expected number is a hand computation (see
tests/strategy/test_leg_edit.py for the arithmetic). No database, no Kite connection.
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from ofo.instruments import Catalogue, parse_instruments_csv
from ofo.outcome.planned_entry import PlannedEntry
from ofo_app.main import create_app
from ofo_app.routes.leg_edit import get_capture, get_edit_catalogue
from ofo_app.routes.outcome import get_market_context, load_charge_rates
from ofo_app.routes.planned_entry import get_live_feed

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPIRY = datetime.date(2026, 10, 6)
HTTP_OK, HTTP_UNPROCESSABLE = 200, 422
SHIFT_STEP, INCLUDED_AFTER_UNTICK = 50, 3
STAMP = datetime.datetime(2026, 10, 6, 9, 20, tzinfo=datetime.UTC)
CAT = Catalogue()
CAT.load(parse_instruments_csv(ROOT / "tests" / "fixtures" / "instruments" / "instruments_slice.csv"))
BY_ID = {f"{e.contract.exchange_segment}:{e.contract.exchange_token}": e.contract for e in CAT.all_entries()}
BY_KEY = {(c.instrument_type, int(c.strike)): i for i, c in BY_ID.items()
          if c.name == "NIFTY" and c.expiry == EXPIRY and c.instrument_type in ("CE", "PE")}
#: hand-typed capture prices per (type, strike): Shift +1 table and Width +1 table of the core proof
HAND = {("PE", 22850): "45.00", ("PE", 23050): "90.00", ("CE", 23450): "88.00", ("CE", 23650): "41.00",
        ("PE", 22750): "40.00", ("PE", 22950): "83.00"}
START = [("BUY", "PE", 22800, "42.50"), ("SELL", "PE", 23000, "86.00"), ("SELL", "CE", 23400, "91.50"),
         ("BUY", "CE", 23600, "44.00")]


async def fake_capture(ctx, feed, underlying, ids):
    got = {}
    for i in ids:
        c = BY_ID[i]
        price = HAND.get((c.instrument_type, int(c.strike)))
        got[i] = None if price is None else PlannedEntry(Decimal(price), "ltp")
    return STAMP, got


def legs(prices=None, **extra):
    return [{"instrument_id": BY_KEY[(t, k)], "action": a, "lots": 1, "base_lots": 1,
             "planned_entry": (prices or {}).get(k, p), "captured_at": STAMP.isoformat()} | extra
            for a, t, k, p in START]


def post(body: dict) -> tuple[int, dict]:
    app = create_app()
    app.dependency_overrides[get_edit_catalogue] = lambda: CAT
    app.dependency_overrides[get_market_context] = lambda: None
    app.dependency_overrides[get_live_feed] = lambda: None
    app.dependency_overrides[get_capture] = lambda: fake_capture
    app.dependency_overrides[load_charge_rates] = lambda: None

    async def go():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post("/api/strategies/leg-edit", json={"underlying": "NIFTY"} | body)
            return r.status_code, r.json()
    return asyncio.run(go())


def strikes(reply):
    return [leg["strike"] for leg in reply["legs"]]


def test_ac_078_6_shift_click_sends_only_control_and_direction_and_server_returns_new_legs():
    """REQ-078 AC-6/AC-8/AC-3: Shift +1 moves every option leg +50, re-captures every entry with the capture time, and
    shows the cumulative move (+50); the reply carries the shape label (iron_condor) and the controls that apply."""
    status, reply = post({"legs": legs(), "edit": {"control": "shift", "direction": 1}})
    assert status == HTTP_OK
    assert strikes(reply) == ["22850.00", "23050.00", "23450.00", "23650.00"] or strikes(reply) == [
        "22850", "23050", "23450", "23650"]
    assert [leg["planned_entry"] for leg in reply["legs"]] == ["45.00", "90.00", "88.00", "41.00"]
    assert {leg["captured_at"][:16] for leg in reply["legs"]} == {"2026-10-06T09:20"}
    assert reply["shift_total"] == SHIFT_STEP and reply["shape"] == "iron_condor"
    assert reply["controls"] == {"shift": True, "width": True, "hedge": True}
    assert [leg["hedge"] for leg in reply["legs"]] == [True, False, False, True]


def test_ac_078_7_move_changes_no_side_lots_expiry_or_type():
    """REQ-078 AC-7: after Width +1 every leg keeps its side, lots, expiry and type."""
    status, reply = post({"legs": legs(), "edit": {"control": "width", "direction": 1}})
    assert status == HTTP_OK
    assert [(leg["action"], leg["instrument"], leg["lots"], leg["expiry"]) for leg in reply["legs"]] == [
        (a, t, 1, "2026-10-06") for a, t, _, _ in START]
    assert [int(float(s)) for s in strikes(reply)] == [22750, 22950, 23450, 23650]


def test_ac_078_6_refused_move_is_422_with_catalogue_text_and_changes_nothing():
    """REQ-078 AC-6: Hedge on a Custom shape is refused with the catalogue text; nothing else is returned."""
    custom = [*legs(), {"instrument_id": BY_KEY[("CE", 23000)], "action": "BUY", "lots": 1, "base_lots": 1,
                        "planned_entry": "100.00", "captured_at": STAMP.isoformat()}]
    status, reply = post({"legs": custom, "edit": {"control": "hedge", "direction": 1}})
    assert status == HTTP_UNPROCESSABLE and "Hedge does not apply to this strategy." in str(reply)


def test_ac_077_2_typed_price_off_tick_is_refused_and_on_tick_is_marked_typed():
    """REQ-077 AC-2/AC-4: 81.32 on tick 0.05 is refused; 81.35 is accepted and marked typed."""
    bad, _ = post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": "81.32"}})
    assert bad == HTTP_UNPROCESSABLE
    status, reply = post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": "81.35"}})
    assert status == HTTP_OK
    assert (reply["legs"][1]["planned_entry"], reply["legs"][1]["price_source"]) == ("81.35", "typed")


def test_ac_077_3_typed_price_flows_into_engine_numbers():
    """REQ-077 AC-3: the typed 81.35 is the entry sent to the outcome (engine numbers: tests/strategy)."""
    _, reply = post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": "81.35"}})
    assert reply["outcome"]["state"] == "NOT_CONNECTED"  # no provider here
    reply_legs = reply["outcome"]["legs"]
    assert [leg["planned_entry"] for leg in reply_legs] == ["42.50", "81.35", "91.50", "44.00"]


def test_ac_076_6_unticked_leg_is_left_out_of_the_outcome_and_never_a_stored_flag():
    """REQ-076 AC-6/AC-7: an unticked leg is not in the outcome's legs; a smuggled tick key is a 422."""
    status, reply = post({"legs": legs(), "edit": {"control": "include", "index": 3, "included": False}})
    assert status == HTTP_OK
    assert [leg["included"] for leg in reply["legs"]] == [True, True, True, False]
    assert len(reply["outcome"]["legs"]) == INCLUDED_AFTER_UNTICK
    forged = legs()
    forged[0]["checked"] = True
    assert post({"legs": forged, "edit": {"control": "shift", "direction": 1}})[0] == HTTP_UNPROCESSABLE


def test_ac_076_4_multiplier_range_and_lots():
    """REQ-076 AC-4/AC-5: multiplier 3 gives lots 3 and quantity 195 (3 x 65); 51 and 0 are refused."""
    status, reply = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 3}})
    assert status == HTTP_OK and [(x["lots"], x["quantity"]) for x in reply["legs"]] == [(3, 195)] * 4
    for bad in (0, 51):
        assert post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": bad}})[0] == HTTP_UNPROCESSABLE


def test_ac_077_5_unpriced_new_contract_has_no_price_and_no_outcome():
    """REQ-077 AC-9 / ADR-020 Q185: a stepped leg with no live price comes back unpriced; no number."""
    status, reply = post({"legs": legs(), "edit": {"control": "step", "index": 2, "direction": -1}})
    assert status == HTTP_OK
    assert reply["legs"][2]["planned_entry"] is None and reply["legs"][2]["price_source"] == "none"
    assert reply["outcome"] is None


def test_forged_unlisted_instrument_is_refused():
    """Threat model: an instrument id the server does not list is refused (422), never guessed."""
    bad = legs()
    bad[0]["instrument_id"] = "NSE_FO:1"
    assert post({"legs": bad, "edit": {"control": "shift", "direction": 1}})[0] == HTTP_UNPROCESSABLE


def test_a_control_without_its_fields_is_a_plain_validation_error():
    """A step with no index, a shift with no direction, a price with no price: 422, never "no further listed strike"."""
    for bad in ({"control": "step", "direction": 1}, {"control": "step", "index": 0}, {"control": "shift"},
                {"control": "price", "index": 1}, {"control": "include", "index": 1}, {"control": "multiplier"},
                {"control": "step", "index": 9, "direction": 1}):
        status, reply = post({"legs": legs(), "edit": bad})
        assert status == HTTP_UNPROCESSABLE and "no further" not in str(reply)
