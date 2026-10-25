# ruff: noqa: PLR2004, E501
"""REQ-085 (W-159, ADR-185): the outcome reply carries strategy and per-leg warning codes with catalogue text.

CORE PROOF (step 1): the low_liquidity inputs - the 5-level depth and the last trade time of each leg - are on the real
Kite full-mode frames recorded 2026-10-08 as the outcome snapshot reads them (provider ``latest_depth`` and
``latest_day_stats``). Measured on those frames for NIFTY 2026-10-19 options at the last frame (09:20:09 IST):
25,000 CE bid 1.00 ask 1.05 (spread 4.88% of mid, last trade 62.9 s before); 25,000 PE bid 2,410.70 ask 2,468.65
(2.38%, last trade 72,860.9 s before = 20 hours old); of 424 NIFTY options, 26 hold no depth and 93 no last trade
time. Depth and last trade are therefore on the feed, and a leg without them is a stated state (liquidity_unknown /
no trade), not a guess.
No database is needed."""
from __future__ import annotations

import datetime
import inspect
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo_app import live_push  # noqa: E402
from ofo_app.routes import leg_edit  # noqa: E402
from ofo_app.routes.outcome import MarketContext, OutcomeRequest, outcome_response  # noqa: E402

EXPIRY = datetime.date(2026, 10, 19)
ANSWER = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    last = replay(provider, clock)
    return provider, items, last


def _id(items, kind, strike):
    for lc in items:
        c = lc.contract
        if c.name == "NIFTY" and c.instrument_type == kind and c.expiry == EXPIRY and c.strike == Decimal(strike):
            return f"{c.exchange_segment}:{c.exchange_token}"
    raise AssertionError(f"no NIFTY {strike} {kind}")


def test_core_proof_depth_and_last_trade_are_on_the_recorded_full_frames(replayed):
    provider, items, last = replayed
    seen = []
    for kind in ("CE", "PE"):
        key = _id(items, kind, 25000)
        depth, stats = provider.latest_depth(key, last), provider.latest_day_stats(key, last).stats
        assert depth is not None and depth.bids and depth.asks, f"{kind}: no depth on a full-mode leg"
        assert stats is not None and stats.last_trade_ts, f"{kind}: no last trade time"
        bid, ask = depth.bids[0].price, depth.asks[0].price
        seconds = (last - datetime.datetime.fromtimestamp(stats.last_trade_ts, IST)).total_seconds()
        seen.append((kind, bid, ask, (ask - bid) / ((ask + bid) / 2) * 100, seconds))
    assert seen[0][1:3] == (Decimal("1"), Decimal("1.05"))  # the values quoted in the module docstring
    assert 2 < seen[1][3] < 3 and seen[0][4] < 120


def _body(items, legs):
    return {"underlying": "NIFTY", "legs": [
        {"instrument_id": _id(items, kind, strike), "action": action, "lots": 1, "planned_entry": "10.00",
         "captured_at": ANSWER.isoformat()} for action, kind, strike in legs]}


def _answer(replayed, legs):
    provider, items, last = replayed
    req = OutcomeRequest.model_validate(_body(items, legs))
    return outcome_response(req, MarketContext(provider, lambda: last, Decimal("0.065"))).model_dump(mode="json")


def test_a_strangle_on_the_replay_feed_carries_both_unhedged_directions_and_per_leg_lists(replayed):
    body = _answer(replayed, [("SELL", "PE", 25000), ("SELL", "CE", 25200)])
    assert body["state"] == "COMPUTED"
    strategy = [w for w in body["warnings"] if w["code"] == "unhedged_short"]
    assert len(strategy) == 2 and any("rises" in w["text"] for w in strategy) and any("falls" in w["text"] for w in strategy)
    assert all(isinstance(leg["warnings"], list) for leg in body["legs"])
    assert "warnings_label" not in body or body["warnings_label"] is None  # warnings exist: no empty-state label
    shown = {w["code"] for leg in body["legs"] for w in leg["warnings"]}
    assert shown <= {"low_liquidity", "liquidity_unknown", "expiry_day"}  # never a strategy code on a leg


def test_a_second_computation_of_the_same_snapshot_carries_identical_warning_codes(replayed):
    legs = [("SELL", "PE", 25000), ("SELL", "CE", 25200)]
    first, second = _answer(replayed, legs), _answer(replayed, legs)
    assert first["warnings"] == second["warnings"]
    assert [leg["warnings"] for leg in first["legs"]] == [leg["warnings"] for leg in second["legs"]]


def test_rest_leg_edit_and_live_push_all_go_through_the_one_door_and_compute_no_warning_themselves():
    for module in (live_push, leg_edit):
        source = inspect.getsource(module)
        assert "outcome_response(" in source
        assert "strategy_warnings" not in source and "unhedged" not in source  # no second computation (C8)


def test_not_connected_and_refused_answers_carry_no_warning_list_at_all(replayed):
    _, items, _ = replayed
    req = OutcomeRequest.model_validate(_body(items, [("SELL", "CE", 25200)]))
    not_connected = outcome_response(req, None).model_dump(mode="json", exclude_unset=True)
    assert not_connected["state"] in {"NOT_CONNECTED", "FROM_ENTRIES"}
    assert "warnings" not in not_connected and "warnings_label" not in not_connected
    assert all("warnings" not in leg for leg in not_connected["legs"])
    provider, _, last = replayed
    bad = OutcomeRequest.model_validate({**_body(items, [("SELL", "CE", 25200)]), "underlying": "SENSEX"})
    refused = outcome_response(bad, MarketContext(provider, lambda: last, Decimal("0.065")))
    refused = refused.model_dump(mode="json", exclude_unset=True)
    assert refused["state"] != "COMPUTED" and "warnings" not in refused
