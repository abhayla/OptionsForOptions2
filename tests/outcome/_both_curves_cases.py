"""Shared cases for the GC-UI step 4 server tests (both curves, payoff-table step, SD block).

Strategy 54's shape (BUY 22600 CE / SELL 22800 CE, 1 lot, one expiry) on the recorded 2026-10-08 NIFTY replay (13-Oct
expiry, lot 65), plus a calendar (22600 CE 13-Oct SELL / 22600 CE 19-Oct BUY). Entries are each leg's replay LTP
(ADR-068), so no figure here is typed from memory and none is a Sensibull number."""
from __future__ import annotations

import json
import pathlib

from marketdata._kite_fixture import all_instrument_ids, new_provider_with_futures, replay
from ofo.engine.legs import Action
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, from_entries, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.views import View
from outcome.test_same_engine import RATE, VALUATION

GOLDEN = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "outcome_both_curves" / "flag_off.json"
S54 = (("NSE_FO:44616", Action.BUY), ("NSE_FO:44624", Action.SELL))  # 22600 CE / 22800 CE 13-Oct
CALENDAR = (("NSE_FO:44616", Action.SELL), ("NSE_FO:47139", Action.BUY))  # 22600 CE 13-Oct / 19-Oct


def market():
    provider, clock, items, _futures = new_provider_with_futures("NIFTY")
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def definition(provider, legs):
    return StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, 1, provider.book.get(iid, VALUATION).ltp,
                                                        VALUATION) for iid, action in legs))


def snapshot(provider, d):
    return read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)


def outcome(provider, legs, **kw):
    d = definition(provider, legs)
    return build_outcome(d, snapshot(provider, d), VALUATION, **kw)


def entries_outcome(provider, legs, **kw):
    """REQ-077 AC-9 (the not-live path): At Expiry from the user's prices, contracts read from the snapshot."""
    d = definition(provider, legs)
    return from_entries(d, snapshot(provider, d), None, VALUATION, **kw)


def as_json(body) -> dict:
    return json.loads(json.dumps(body, default=str, ensure_ascii=False))


def replies(provider) -> dict:
    """Today's default replies (no new option), per case: the flag-off byte-identity baseline."""
    out = {}
    for name, legs in (("s54", S54), ("calendar", CALENDAR)):
        for view in View:
            out[f"{name}_{view.value}"] = outcome_to_dict(outcome(provider, legs, view=view))
    out["s54_from_entries"] = outcome_to_dict(entries_outcome(provider, S54))
    return as_json(out)


def golden_text(provider) -> str:
    return json.dumps(replies(provider), indent=1, ensure_ascii=False, sort_keys=True) + "\n"
