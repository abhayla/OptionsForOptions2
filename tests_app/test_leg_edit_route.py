"""W-148 (REQ-076): POST /api/strategies/leg-edit on the REAL instrument-list fixture.

The golden NIFTY iron condor of the 2026-10-06 expiry (tests/fixtures/instruments/instruments_slice.csv, lot 65). The
capture is a hand price table keyed by (type, strike) so every expected number is a hand computation. No database, no
Kite connection (the instrument list, the date, the freeze limits and the capture are the route's overridable
dependencies); the engine's own numbers are proven in tests/strategy and the outcome route's tests.
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.engine.legs import Action, Instrument
from ofo.instruments import Catalogue, parse_instruments_csv
from ofo.instruments.models import ZERODHA, InstrumentId
from ofo.outcome.planned_entry import PlannedEntry
from ofo.strategy import stored_form
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo_app.main import create_app
from ofo_app.routes import execute, leg_edit, strategies
from ofo_app.routes.leg_edit import get_capture, get_contract_ids, get_edit_catalogue, get_edit_today, get_freeze_limits
from ofo_app.routes.outcome import (
    get_answer_clock,
    get_margin_source,
    get_market_context,
    load_charge_rates,
)
from ofo_app.routes.planned_entry import get_live_feed
from pydantic import ValidationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPIRY = datetime.date(2026, 10, 6)
TODAY = datetime.date(2026, 10, 1)
HTTP_OK, HTTP_UNPROCESSABLE = 200, 422
PRICE_REFUSED = "USER_INPUT_013"  # the catalogue code of leg_edit_price_not_tick
LOT, INCLUDED_AFTER_UNTICK = 65, 3
STAMP = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=datetime.UTC)
STEPPED_DOWN_STRIKE = 23350
NEW_STAMP = datetime.datetime(2026, 10, 1, 9, 21, 28, tzinfo=datetime.UTC)
TYPED_STAMP = datetime.datetime(2026, 10, 1, 9, 30, 5, tzinfo=datetime.UTC)  # the answer clock of every route test
CAT = Catalogue()
CAT.load(parse_instruments_csv(ROOT / "tests" / "fixtures" / "instruments" / "instruments_slice.csv"))
BY_ID = {f"{e.contract.exchange_segment}:{e.contract.exchange_token}": e.contract for e in CAT.all_entries()}
BY_KEY = {(c.instrument_type, int(c.strike)): i for i, c in BY_ID.items()
          if c.name == "NIFTY" and c.expiry == EXPIRY and c.instrument_type in ("CE", "PE")}
#: hand-typed capture prices per (type, strike): what the fake capture finds for a stepped contract
HAND = {("CE", 23450): "88.00", ("PE", 22850): "45.00", ("PE", 23050): "90.00"}
#: the stored internal id of each live contract, hand-typed apart from the exchange token (the fake store's rows); the
#: stepped-to CE 23350 has no stored row, so its leg comes back without a contract id
STORED = {i: 7_000_000 + n for n, i in enumerate(sorted(BY_ID))}
STEPPED_ID = BY_KEY[("CE", 23450)]
START = [("BUY", "PE", 22800, "42.50"), ("SELL", "PE", 23000, "86.00"), ("SELL", "CE", 23400, "91.50"),
         ("BUY", "CE", 23600, "44.00")]


async def fake_capture(ctx, feed, underlying, ids):
    got = {}
    for i in ids:
        c = BY_ID[i]
        price = HAND.get((c.instrument_type, int(c.strike)))
        got[i] = None if price is None else PlannedEntry(Decimal(price), "ltp")
    return NEW_STAMP, got


def legs(lots=1, **extra):
    return [{"instrument_id": BY_KEY[(t, k)], "action": a, "lots": lots, "base_lots": 1, "planned_entry": p,
             "captured_at": STAMP.isoformat()} | extra for a, t, k, p in START]


async def fake_contract_ids(instrument_ids):
    return {i: STORED[i] for i in instrument_ids if i in STORED and i != BY_KEY[("CE", 23350)]}


def post(body: dict, cat=CAT, limits=None, today=TODAY, capture=fake_capture) -> tuple[int, dict]:
    app = create_app()
    app.dependency_overrides[get_edit_catalogue] = lambda: cat
    app.dependency_overrides[get_edit_today] = lambda: today
    app.dependency_overrides[get_freeze_limits] = lambda: limits or {}
    app.dependency_overrides[get_market_context] = lambda: None
    app.dependency_overrides[get_margin_source] = lambda: None
    app.dependency_overrides[get_live_feed] = lambda: None
    app.dependency_overrides[get_capture] = lambda: capture
    app.dependency_overrides[get_contract_ids] = lambda: fake_contract_ids
    app.dependency_overrides[load_charge_rates] = lambda: None
    app.dependency_overrides[get_answer_clock] = lambda: lambda: TYPED_STAMP

    async def go():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post("/api/strategies/leg-edit", json={"underlying": "NIFTY"} | body)
            return r.status_code, r.json()
    return asyncio.run(go())


def strikes(reply):
    return [int(float(leg["strike"])) for leg in reply["legs"]]


def test_core_step_recaptures_only_the_stepped_leg_with_a_new_capture_time():
    """REQ-076 AC-1/AC-2 (core): + on SELL 23400 CE gives 23450 CE priced 88.00 captured at the new time; the other
    legs keep their planned entries and capture time; the reply's outcome is built from the new legs."""
    status, reply = post({"legs": legs(), "edit": {"control": "step", "index": 2, "direction": 1}})
    assert status == HTTP_OK
    assert strikes(reply) == [22800, 23000, 23450, 23600]
    assert [leg["planned_entry"] for leg in reply["legs"]] == ["42.50", "86.00", "88.00", "44.00"]
    assert [leg["captured_at"][:19] for leg in reply["legs"]] == [
        "2026-10-01T09:20:00", "2026-10-01T09:20:00", "2026-10-01T09:21:28", "2026-10-01T09:20:00"]
    assert reply["legs"][2]["price_source"] == "captured"
    assert [leg["planned_entry"] for leg in reply["outcome"]["legs"]] == ["42.50", "86.00", "88.00", "44.00"]


def test_ac_1_the_last_listed_strike_a_futures_leg_and_a_forged_index_are_refused():
    """REQ-076 AC-1: no step past the last listed strike (422, reason text, nothing changes); a futures leg has no
    stepper; an index outside the legs is a plain validation error."""
    last = BY_KEY[("CE", 25800)]
    one = [{"instrument_id": last, "action": "BUY", "lots": 1, "base_lots": 1, "planned_entry": "1.00",
            "captured_at": STAMP.isoformat()}]
    status, reply = post({"legs": one, "edit": {"control": "step", "index": 0, "direction": 1}})
    assert status == HTTP_UNPROCESSABLE and "no further listed strike" in str(reply) and "legs" not in reply
    fut = next(i for i, c in BY_ID.items() if c.name == "NIFTY" and c.instrument_type == "FUT" and c.expiry >= TODAY)
    one = [{"instrument_id": fut, "action": "BUY", "lots": 1, "base_lots": 1, "planned_entry": "23100.00",
            "captured_at": STAMP.isoformat()}]
    status, reply = post({"legs": one, "edit": {"control": "step", "index": 0, "direction": 1}})
    assert status == HTTP_UNPROCESSABLE and "futures leg and has no strike to step" in str(reply)
    status, reply = post({"legs": legs(), "edit": {"control": "step", "index": 9, "direction": 1}})
    # refused by the request model through the API's one error boundary (ofo_app/errors.py), not by the route
    assert status == HTTP_UNPROCESSABLE and "missing or not in the expected form" in str(reply)


def test_ac_2_a_stepped_leg_with_no_live_price_is_unpriced_never_the_old_price():
    """REQ-076 AC-2 / ADR-020 Q185: SELL 23400 CE stepped to 23350, which the capture has no price for: that leg comes
    back unpriced, the others keep theirs, and no number is computed."""
    status, reply = post({"legs": legs(), "edit": {"control": "step", "index": 2, "direction": -1}})
    assert status == HTTP_OK and strikes(reply)[2] == STEPPED_DOWN_STRIKE
    stepped = reply["legs"][2]
    assert (stepped["planned_entry"], stepped["captured_at"], stepped["price_source"]) == (None, None, "none")
    assert [leg["planned_entry"] for leg in reply["legs"]] == ["42.50", "86.00", None, "44.00"]
    assert reply["outcome"] is None


def test_ac_1_a_past_expiry_and_a_delisted_contract_are_named_not_stepped():
    """REQ-076 AC-1: a leg whose expiry is already past, or whose contract is no longer listed, is refused naming ITS
    leg number and the stored contract."""
    status, reply = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 2}},
                         today=EXPIRY + datetime.timedelta(days=1))
    assert status == HTTP_UNPROCESSABLE and "Leg 1 (BUY NIFTY 22,800 PE, expiry 06 Oct 2026)" in str(reply)
    gone = Catalogue()
    gone.load(parse_instruments_csv(ROOT / "tests" / "fixtures" / "instruments" / "instruments_slice.csv"))
    segment, _, token = BY_KEY[("CE", 23400)].partition(":")
    gone.get(InstrumentId(segment, int(token))).currently_listed = False
    status, reply = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 2}}, cat=gone)
    assert status == HTTP_UNPROCESSABLE and "Leg 3 (SELL NIFTY 23,400 CE, expiry 06 Oct 2026)" in str(reply)


def test_ac_1_an_unknown_instrument_is_refused_by_its_number_only():
    """Threat model: an instrument id the file does not hold is refused (422) by the leg number, never guessed."""
    bad = legs()
    bad[1]["instrument_id"] = "NSE_FO:1"
    status, reply = post({"legs": bad, "edit": {"control": "multiplier", "multiplier": 2}})
    assert status == HTTP_UNPROCESSABLE and "Leg 2 is not a contract in the instrument file." in str(reply)


def test_ac_4_multiplier_gives_lots_and_quantity_and_one_restores_base_lots():
    """REQ-076 AC-4/AC-5: multiplier 3 gives 3 lots = 195 units per leg (3 x 65); sent back with 1, every leg is at
    its base lots; 0, 51, 2.5 and '3' are refused."""
    status, reply = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 3}})
    assert status == HTTP_OK and [(x["lots"], x["quantity"]) for x in reply["legs"]] == [(3, 3 * LOT)] * 4
    assert [leg["lots"] for leg in reply["outcome"]["legs"]] == [3] * 4
    status, back = post({"legs": legs(lots=3), "edit": {"control": "multiplier", "multiplier": 1}})
    assert status == HTTP_OK and [(x["lots"], x["quantity"]) for x in back["legs"]] == [(1, LOT)] * 4
    for bad in (0, 51, 2.5, "3"):
        assert post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": bad}})[0] == HTTP_UNPROCESSABLE


def _split(instrument_id: str) -> tuple[str, int]:
    segment, _, token = instrument_id.partition(":")
    return segment, int(token)


def freeze_limits(limit: int):
    return {InstrumentId(*_split(BY_KEY[("CE", 23400)])): (limit, TODAY)}


def test_ac_5_a_multiplied_quantity_at_or_above_the_freeze_limit_blocks_that_leg_never_splits():
    """REQ-076 AC-5 / ADR-092: stored limit 130 on 23400 CE (lot 65, largest allowed 129 // 65 x 65 = 65 = 1 lot):
    multiplier 3 = 195 units blocks THAT leg only, with the ADR-081 text; multiplier 1 = 65 units is under it; a
    leg with no stored limit is never blocked. The reply never carries a split."""
    symbol = CAT.get(InstrumentId(*_split(BY_KEY[("CE", 23400)]))).ref(ZERODHA).broker_symbol
    status, reply = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 3}},
                         limits=freeze_limits(130))
    assert status == HTTP_OK
    assert [leg["block"] is not None for leg in reply["legs"]] == [False, False, True, False]
    assert str(symbol) in str(reply["legs"][2]["block"]) and "195 units (3 lots)" in str(reply["legs"][2]["block"])
    assert "130 units" in str(reply["legs"][2]["block"]) and "65 units (1 lots)" in str(reply["legs"][2]["block"])
    assert [leg["quantity"] for leg in reply["legs"]] == [195] * 4  # not split: each leg still one quantity
    _, under = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 1}}, limits=freeze_limits(130))
    assert all(leg["block"] is None for leg in under["legs"])
    _, unknown = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 3}}, limits={})
    assert all(leg["block"] is None for leg in unknown["legs"])


def test_ac_6_an_unticked_leg_stays_in_the_reply_and_leaves_every_number(monkeypatch):
    """REQ-076 AC-6: untick BUY 23600 CE: the leg stays, marked left out; the outcome (the one computation behind the
    summary, payoff, table and Greeks) AND the margin call both receive the other three legs only."""
    seen: dict[str, list] = {}
    real_outcome, real_margin = leg_edit.outcome_response, leg_edit.margin_for_request

    def spy_outcome(req, *args, **kwargs):
        seen["outcome"] = [x.instrument_id for x in req.legs]
        return real_outcome(req, *args, **kwargs)

    async def spy_margin(req, *args, **kwargs):
        seen["margin"] = [x.instrument_id for x in req.legs]
        return await real_margin(req, *args, **kwargs)

    monkeypatch.setattr(leg_edit, "outcome_response", spy_outcome)
    monkeypatch.setattr(leg_edit, "margin_for_request", spy_margin)
    status, reply = post({"legs": legs(), "edit": {"control": "include", "index": 3, "included": False}})
    assert status == HTTP_OK
    assert [leg["included"] for leg in reply["legs"]] == [True, True, True, False]
    assert strikes(reply) == [22800, 23000, 23400, 23600]  # the unticked leg is still listed, unchanged
    left_out = BY_KEY[("CE", 23600)]
    assert seen["outcome"] == seen["margin"] == [
        BY_KEY[("PE", 22800)], BY_KEY[("PE", 23000)], BY_KEY[("CE", 23400)]]
    assert left_out not in seen["outcome"] and len(reply["outcome"]["legs"]) == INCLUDED_AFTER_UNTICK


def test_ac_6_every_leg_unticked_computes_no_number():
    """REQ-076 AC-6/AC-10: with no leg ticked the reply has the legs and no outcome (never zeros)."""
    unticked = legs(included=False)
    status, reply = post({"legs": unticked, "edit": {"control": "include", "index": 0, "included": False}})
    assert status == HTTP_OK and reply["outcome"] is None and len(reply["legs"]) == len(START)


def test_ac_7_the_tick_is_never_part_of_the_saved_definition_or_the_execution_plan():
    """REQ-076 AC-7: Save Draft's leg, the strategy body, the Execute request and the stored form all refuse an
    `included` key (closed key sets), so the tick cannot be saved or reach the plan."""
    leg = {"contract_id": 17, "action": "BUY", "quantity": LOT}
    with pytest.raises(ValidationError):
        strategies.LegIn.model_validate(leg | {"included": False})
    with pytest.raises(ValidationError):
        strategies.StrategyIn.model_validate({"underlying": "NIFTY", "legs": [leg | {"included": False}]})
    with pytest.raises(ValidationError):
        execute.ExecuteIn.model_validate({"action": "ENTRY", "included": False})
    strategies.LegIn.model_validate(leg)  # the same leg without the key is fine
    doc = {"schema_version": 1, "underlying": "NIFTY", "rules_ref": None, "risk_limits": {}, "preferences": {},
           "legs": [{"contract_id": 17, "action": "BUY", "instrument": "CE", "strike": "23000",
                     "expiry": "2026-10-06", "quantity": LOT, "included": False}]}

    def never_resolved(*_args, **_kwargs):
        raise AssertionError("the stored form must refuse the key before it reads the catalogue")

    with pytest.raises(stored_form.StoredFormError):
        stored_form.from_document(doc, never_resolved)
    assert "included" not in stored_form.LEG_KEYS | stored_form.ENTRY_LEG_KEYS | stored_form.DOCUMENT_KEYS


def test_ac_8_9_the_reply_carries_the_matched_name_hedge_marks_and_custom_has_none():
    """REQ-076 AC-8/AC-9: the condor's reply names the catalogue template (iron_condor, 'Short Iron Condor') and marks
    the two bought wings; changing a leg to a type that fits no template gives no name and no marks; no leg changed."""
    status, reply = post({"legs": legs(), "edit": {"control": "multiplier", "multiplier": 1}})
    assert status == HTTP_OK and reply["shape"] == "iron_condor" and "Short Iron Condor" in str(reply["shape_name"])
    assert [leg["hedge"] for leg in reply["legs"]] == [True, False, False, True]
    changed = legs()
    changed[3] = {"instrument_id": BY_KEY[("PE", 23200)], "action": "BUY", "lots": 1, "base_lots": 1,
                  "planned_entry": "44.00", "captured_at": STAMP.isoformat()}
    status, custom = post({"legs": changed, "edit": {"control": "multiplier", "multiplier": 1}})
    assert status == HTTP_OK and custom["shape"] is None and custom["shape_name"] is None
    assert [leg["hedge"] for leg in custom["legs"]] == [False] * 4
    assert strikes(custom) == [22800, 23000, 23400, 23200]  # the name never moved or reordered a leg


def test_typed_price_off_tick_is_refused_and_on_tick_is_marked_typed():
    """REQ-077 AC-2 (the price control of the same route): 81.32 on tick 0.05 is refused; 81.35 is marked typed."""
    assert post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": "81.32"}})[0] == HTTP_UNPROCESSABLE
    status, reply = post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": "81.35"}})
    assert status == HTTP_OK
    assert (reply["legs"][1]["planned_entry"], reply["legs"][1]["price_source"]) == ("81.35", "typed")


def test_a_control_without_its_fields_or_a_smuggled_leg_key_is_a_plain_validation_error():
    """A step with no index, a price with no price, an include with no tick, a leg with an unknown key: 422."""
    for bad in ({"control": "step", "direction": 1}, {"control": "step", "index": 0}, {"control": "price", "index": 1},
                {"control": "include", "index": 1}, {"control": "multiplier"}, {"control": "shift", "direction": 1}):
        status, reply = post({"legs": legs(), "edit": bad})
        assert status == HTTP_UNPROCESSABLE and "no further" not in str(reply)
    edit = {"control": "multiplier", "multiplier": 2}
    assert post({"legs": legs(checked=True), "edit": edit})[0] == HTTP_UNPROCESSABLE


def test_ac_2_a_stepped_leg_carries_the_new_contracts_ids_and_the_others_keep_theirs():
    """REQ-076 AC-2 'A stepped leg is a new contract': the reply's instrument id, stored id and lot size for the stepped
    leg are the catalogue's for CE 23450 (not the old CE 23400's); an unstepped leg keeps its own; a contract with no
    stored row has no contract id (answer state: not savable) and the reply is still 200."""
    status, reply = post({"legs": legs(), "edit": {"control": "step", "index": 2, "direction": 1}})
    assert status == HTTP_OK
    stepped, old = reply["legs"][2], BY_KEY[("CE", 23400)]
    assert stepped["instrument_id"] == STEPPED_ID and stepped["instrument_id"] != old
    assert stepped["contract_id"] == STORED[STEPPED_ID] != STORED[old] and stepped["lot_size"] == LOT
    expected = [STORED[BY_KEY[(t, k)]] if (t, k) != ("CE", 23400) else STORED[STEPPED_ID] for _, t, k, _ in START]
    assert [leg["contract_id"] for leg in reply["legs"]] == expected
    status, down = post({"legs": legs(), "edit": {"control": "step", "index": 2, "direction": -1}})
    assert status == HTTP_OK and down["legs"][2]["contract_id"] is None and down["legs"][2]["lot_size"] == LOT


def test_ac_8_the_read_control_names_the_shape_and_marks_and_changes_no_leg():
    """REQ-076 AC-8 on load: control 'read' on the saved iron condor answers 'Short Iron Condor', two Hedge marks and
    the engine's outcome; every leg (strike, lots, entry, capture time) is exactly as sent; no capture is made."""
    status, reply = post({"legs": legs(), "edit": {"control": "read"}})
    assert status == HTTP_OK and reply["shape"] == "iron_condor" and "Short Iron Condor" in str(reply["shape_name"])
    assert [leg["hedge"] for leg in reply["legs"]] == [True, False, False, True]
    assert strikes(reply) == [22800, 23000, 23400, 23600]
    assert [leg["planned_entry"] for leg in reply["legs"]] == [p for *_, p in START]
    assert [leg["captured_at"][:19] for leg in reply["legs"]] == ["2026-10-01T09:20:00"] * 4
    assert reply["outcome"] is not None


def test_ac_1_a_negative_index_is_a_validation_error_never_a_leg():
    """AC-1: ``EditIn.index`` refuses -1 (it would otherwise read the last leg) for every control that takes one."""
    for edit in ({"control": "step", "index": -1, "direction": 1},
                 {"control": "include", "index": -1, "included": False},
                 {"control": "price", "index": -1, "price": "81.32"}):
        assert post({"legs": legs(), "edit": edit})[0] == HTTP_UNPROCESSABLE, edit


# ---- REQ-077 part 21a: typed price time, Reset Prices, per-leg reset ----------------------------------------------
RESET = {("PE", 22800): "40.00", ("PE", 23000): "88.15", ("CE", 23400): "93.20", ("CE", 23600): "45.05"}


def reset_capture(prices=None, seen=None):
    """A fake capture that prices every leg of the condor from RESET (hand-typed), or None where ``prices`` says so;
    ``seen`` collects the ids it was asked about."""
    table = RESET if prices is None else prices

    async def capture(ctx, feed, underlying, ids):
        if seen is not None:
            seen.append(sorted(ids))
        got = {}
        for i in ids:
            c = BY_ID[i]
            price = table.get((c.instrument_type, int(c.strike)))
            got[i] = None if price is None else PlannedEntry(Decimal(price), "ltp")
        return NEW_STAMP, got
    return capture


def marks(reply):
    return [(leg["planned_entry"], leg["price_source"], leg["captured_at"][:19] if leg["captured_at"] else None)
            for leg in reply["legs"]]


def test_ac_1_ac_4_a_typed_price_comes_back_typed_with_its_own_time_and_the_others_keep_theirs():
    """REQ-077 AC-1/AC-4: typing 81.35 on leg 2 returns that leg 'typed' at the moment it was typed (the answer clock),
    never the old capture time; the other legs keep price, mark and capture time."""
    status, reply = post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": "81.35"}})
    assert status == HTTP_OK
    assert marks(reply) == [("42.50", "captured", "2026-10-01T09:20:00"), ("81.35", "typed", "2026-10-01T09:30:05"),
                            ("91.50", "captured", "2026-10-01T09:20:00"), ("44.00", "captured", "2026-10-01T09:20:00")]
    assert reply["outcome"] is not None


def test_ac_2_a_refused_typed_price_changes_nothing_and_answers_in_catalogue_text():
    """REQ-077 AC-2 (attack 1): 0, -5, abc, 81.32 and 81.305 are refused (422) and no leg comes back."""
    for bad in ("0", "0.00", "-5", "abc", "81.32", "81.305", "1e2", " 5", "NaN", ""):
        status, reply = post({"legs": legs(), "edit": {"control": "price", "index": 1, "price": bad}})
        assert status == HTTP_UNPROCESSABLE and "legs" not in reply, bad
        assert reply["code"] == PRICE_REFUSED and "positive multiple of" in reply["what_happened"], bad
        assert all(reply[k] for k in ("what_happened", "impact", "what_is_blocked", "next_action")), bad


def test_ac_2_a_typed_price_is_echoed_as_the_two_decimal_string():
    """REQ-077 AC-2 / money rule: 81.3 is accepted and comes back as "81.30" (leg and outcome); a leg sent with
    planned_entry "42.5" is echoed "42.50"."""
    sent = legs()
    sent[0]["planned_entry"] = "42.5"
    status, reply = post({"legs": sent, "edit": {"control": "price", "index": 1, "price": "81.3"}})
    assert status == HTTP_OK
    assert [leg["planned_entry"] for leg in reply["legs"]][:2] == ["42.50", "81.30"]
    assert reply["outcome"]["legs"][1]["planned_entry"] == "81.30"


def test_ac_1_a_typed_price_on_an_unpriced_leg_prices_it():
    """REQ-077 AC-1: a leg with no live price (planned_entry null) takes the typed price and is no longer unpriced."""
    sent = legs()
    sent[1].pop("planned_entry")
    sent[1].pop("captured_at")
    status, reply = post({"legs": sent, "edit": {"control": "price", "index": 1, "price": "81.35"}})
    assert status == HTTP_OK and marks(reply)[1] == ("81.35", "typed", "2026-10-01T09:30:05")


def test_ac_5_reset_prices_recaptures_every_leg_with_one_new_time_and_clears_every_typed_mark():
    """REQ-077 AC-5 (attack 4): two typed legs and two captured; Reset Prices gives all four the hand-typed current
    prices, ONE capture time, and no 'typed' mark."""
    sent = legs()
    sent[0] |= {"typed": True, "planned_entry": "99.95"}
    sent[2] |= {"typed": True, "planned_entry": "81.30"}
    seen: list = []
    status, reply = post({"legs": sent, "edit": {"control": "reset_prices"}}, capture=reset_capture(seen=seen))
    assert status == HTTP_OK
    assert marks(reply) == [(p, "captured", "2026-10-01T09:21:28") for p in RESET.values()]
    assert [leg["planned_entry"] for leg in reply["outcome"]["legs"]] == list(RESET.values())
    assert len(seen) == 1 and len(seen[0]) == len(sent)  # one capture call for every leg: one capture time


def test_ac_5_reset_leg_changes_one_leg_only():
    """REQ-077 AC-5 (attack 4): reset of leg 3 re-captures that leg alone (its typed mark ends); the typed leg 1 and
    the captured legs 2 and 4 keep price, mark and time; the capture was asked about that leg only."""
    sent = legs()
    sent[0] |= {"typed": True, "planned_entry": "99.95"}
    sent[2] |= {"typed": True, "planned_entry": "81.30"}
    seen: list = []
    edit_leg_3 = {"control": "reset_leg", "index": 2}
    status, reply = post({"legs": sent, "edit": edit_leg_3}, capture=reset_capture(seen=seen))
    assert status == HTTP_OK
    assert marks(reply) == [("99.95", "typed", "2026-10-01T09:20:00"), ("86.00", "captured", "2026-10-01T09:20:00"),
                            ("93.20", "captured", "2026-10-01T09:21:28"), ("44.00", "captured", "2026-10-01T09:20:00")]
    assert seen == [[BY_KEY[("CE", 23400)]]]


def test_ac_5_a_reset_with_no_live_price_leaves_that_leg_unpriced_never_the_old_price():
    """REQ-077 AC-5 / ADR-020 Q185 (attack 5): the typed leg has no live price on reset: it comes back unpriced, not
    typed and without a time (never 81.30 as current); the others are re-captured; no number is computed."""
    sent = legs()
    sent[2] |= {"typed": True, "planned_entry": "81.30"}
    table = {k: v for k, v in RESET.items() if k != ("CE", 23400)}
    status, reply = post({"legs": sent, "edit": {"control": "reset_prices"}}, capture=reset_capture(table))
    assert status == HTTP_OK
    assert marks(reply)[2] == (None, "none", None) and reply["outcome"] is None
    assert [m[0] for m in marks(reply)] == ["40.00", "88.15", None, "45.05"]
    status, reply = post({"legs": sent, "edit": {"control": "reset_leg", "index": 2}}, capture=reset_capture(table))
    assert status == HTTP_OK and marks(reply)[2] == (None, "none", None)
    assert [m[0] for m in marks(reply)] == ["42.50", "86.00", None, "44.00"] and reply["outcome"] is None
    assert [leg["price_reason"] for leg in reply["legs"]] == [None, None, "no_live_price", None]


def test_ac_5_a_reset_with_no_live_price_carries_the_reason_on_every_unpriced_leg():
    """REQ-077 AC-5: Reset Prices with a capture that prices nothing: every leg unpriced, each with the reason code the
    planned-entry route uses ("no_live_price"); with no valuation time at all (not connected): "not_connected"; a
    priced leg carries none."""
    status, reply = post({"legs": legs(), "edit": {"control": "reset_prices"}}, capture=reset_capture({}))
    assert status == HTTP_OK and [leg["price_reason"] for leg in reply["legs"]] == ["no_live_price"] * 4

    async def offline(ctx, feed, underlying, ids):
        return None, dict.fromkeys(ids)
    status, reply = post({"legs": legs(), "edit": {"control": "reset_prices"}}, capture=offline)
    assert [leg["price_reason"] for leg in reply["legs"]] == ["not_connected"] * 4
    status, reply = post({"legs": legs(), "edit": {"control": "reset_prices"}}, capture=reset_capture())
    assert [leg["price_reason"] for leg in reply["legs"]] == [None] * 4


def test_ac_5_reset_leg_needs_its_index_and_a_forged_one_is_a_validation_error():
    """REQ-077 AC-5: reset_leg with no index, or with an index outside the legs, is a plain 422."""
    assert post({"legs": legs(), "edit": {"control": "reset_leg"}})[0] == HTTP_UNPROCESSABLE
    assert post({"legs": legs(), "edit": {"control": "reset_leg", "index": 9}})[0] == HTTP_UNPROCESSABLE


def test_ac_4_ac_7_reopening_returns_exactly_the_saved_entries_marks_and_times_and_invents_none():
    """REQ-077 AC-4/AC-7 (attack 2, the response half): the answer built from a saved definition holds 81.30 typed at
    its time, a captured leg captured at its own time, and NO price, time or mark for a leg saved without an entry; it
    reads no market and calls no capture (the function takes only the saved definition)."""
    day = datetime.date(2026, 10, 27)
    at = datetime.datetime(2026, 10, 21, 10, 35, 12, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    later = at + datetime.timedelta(minutes=7)
    definition = StrategyDefinition("NIFTY", (
        DefinitionLeg(Action.BUY, Instrument.CE, Decimal("23000"), day, LOT),
        DefinitionLeg(Action.SELL, Instrument.CE, Decimal("23200"), day, LOT),
        DefinitionLeg(Action.BUY, Instrument.PE, Decimal("22800"), day, LOT)))
    saved = stored_form.SavedDefinition(definition, (101, 102, 103), (
        stored_form.LegEntry(Decimal("81.30"), later, stored_form.SOURCE_TYPED),
        stored_form.LegEntry(Decimal("30.00"), at), None))
    legs_out = strategies._definition_out(saved)["legs"]
    assert [(x.get("planned_entry"), x.get("captured_at"), x.get("entry_source")) for x in legs_out] == [
        (Decimal("81.30"), later, "typed"), (Decimal("30.00"), at, "captured"), (None, None, None)]
    assert "planned_entry" not in legs_out[2] and "entry_source" not in legs_out[2]
    assert "entry_source" in strategies.LegOut.model_fields


@pytest.mark.parametrize(("where", "key", "bad"), [
    ("leg", "base_lots", True), ("leg", "base_lots", 1.0), ("leg", "base_lots", "2"),
    ("leg", "lots", True), ("leg", "lots", 1.0), ("leg", "lots", "2"),
    ("edit", "direction", True), ("edit", "direction", 1.0), ("edit", "direction", "1"),
    ("edit", "index", True), ("edit", "multiplier", 2.0)])
def test_every_numeric_request_field_is_strict(where, key, bad):
    """Chunk 2 review area B (attack item 3): a bool, a float or a numeric string is a malformed request (a plain 422
    validation error, no legs), never coerced to the integer it resembles."""
    edit = {"control": "step", "index": 1, "direction": 1}
    if key == "multiplier":
        edit = {"control": "multiplier", "multiplier": bad}
    elif where == "edit":
        edit = edit | {key: bad}
    sent = legs()
    if where == "leg":
        sent[1] = sent[1] | {key: bad}
    status, reply = post({"legs": sent, "edit": edit})
    assert status == HTTP_UNPROCESSABLE and "legs" not in reply, (key, bad)
    assert reply.get("code") != PRICE_REFUSED, (key, bad)


@pytest.mark.parametrize("bad", ["0", "0.00", "00.5", "0012.50"])
def test_a_leg_sent_with_a_price_the_stored_form_refuses_is_the_price_error(bad):
    """Chunk 2 review area B (attack item 4): a leg whose planned entry is zero (or any price the stored form's
    is_entry_price_text refuses) is refused with USER_INPUT_013 and its four parts, as the save would refuse it -
    never priced at zero."""
    sent = legs()
    sent[2] = sent[2] | {"planned_entry": bad}
    status, reply = post({"legs": sent, "edit": {"control": "read"}})
    assert status == HTTP_UNPROCESSABLE and "legs" not in reply, bad
    assert reply["code"] == PRICE_REFUSED and "positive multiple of" in reply["what_happened"], bad
    assert all(reply[k] for k in ("what_happened", "impact", "what_is_blocked", "next_action")), bad
    with pytest.raises(stored_form.StoredFormError):
        stored_form.entry_from_text(bad, STAMP.isoformat(), "legs[2]")


def test_the_leg_edit_and_the_stored_form_share_one_price_rule():
    """One judge, not two: LegEntry refuses exactly what is_entry_price_text refuses."""
    for price in ("0", "0.00", "0.05", "81.35", "1.5"):
        ok = stored_form.is_entry_price_text(price)
        try:
            stored_form.LegEntry(Decimal(price), STAMP)
            built = True
        except stored_form.StoredFormError:
            built = False
        assert ok is built, price


def test_req_135_ac_2_every_leg_carries_days_to_expiry_from_the_routes_ist_date_a_futures_leg_too():
    """REQ-135 AC-2: the condor expires 6 Oct; from 1 Oct that is 5 days, the day before 1, on expiry day 0. A NIFTY
    futures leg (27 Oct) carries its own count (26 days from 1 Oct) in the same reply, next to its expiry."""
    for today, days in ((TODAY, 5), (EXPIRY - datetime.timedelta(days=1), 1), (EXPIRY, 0)):
        status, reply = post({"legs": legs(), "edit": {"control": "read"}}, today=today)
        assert status == HTTP_OK
        assert [leg["days_to_expiry"] for leg in reply["legs"]] == [days] * 4
    fut = next(i for i, c in BY_ID.items() if c.name == "NIFTY" and c.instrument_type == "FUT" and c.expiry >= TODAY)
    one = [{"instrument_id": fut, "action": "BUY", "lots": 1, "base_lots": 1, "planned_entry": "23100.00",
            "captured_at": STAMP.isoformat()}]
    status, reply = post({"legs": one, "edit": {"control": "read"}})
    assert status == HTTP_OK
    leg = reply["legs"][0]
    assert (leg["expiry"], leg["days_to_expiry"]) == (BY_ID[fut].expiry.isoformat(), (BY_ID[fut].expiry - TODAY).days)
