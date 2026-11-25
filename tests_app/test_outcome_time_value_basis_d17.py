"""D-17 (owner decided 25 Nov 2026, ADR-322 point 2): the builder summary's time value is at LIVE prices (REQ-081 AC-3) and
says so: "at live prices, as of HH:MM:SS", the time being the oldest leg quote time the reply already serves
(`oldest_quote_at`, IST). The credit beside it keeps its own basis label (`price_basis_text`, ADR-321 (8)).

Core: the replay condor on the real route. Hand check: the sentence's clock equals oldest_quote_at read in IST; with a leg
quote that has no time the sentence says the time is not given instead of borrowing another time.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata import quote as quote_module  # noqa: E402
from test_outcome_margin import _body  # noqa: E402
from test_outcome_price_basis_d15 import _post, replayed  # noqa: E402, F401

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


async def test_time_value_says_live_prices_as_of_the_oldest_quote_time(replayed):
    out = json.loads((await _post(replayed, _body(replayed), None)).text)
    oldest = datetime.datetime.fromisoformat(out["oldest_quote_at"]).astimezone(IST).strftime("%H:%M:%S")
    assert out["summary"]["time_value"] is not None
    assert out["summary"]["time_value_basis_text"] == f"at live prices, as of {oldest}"


async def test_the_credit_keeps_its_own_basis_label_beside_it(replayed):
    s = json.loads((await _post(replayed, _body(replayed), None)).text)["summary"]
    assert s["price_basis_text"] == "At plan prices"
    assert s["time_value_basis_text"].startswith("at live prices")


async def test_a_leg_quote_without_a_time_says_the_time_is_not_given(replayed, monkeypatch):
    monkeypatch.setattr(quote_module, "price_time", lambda _ts: None)
    s = json.loads((await _post(replayed, _body(replayed), None)).text)["summary"]
    assert s["time_value_basis_text"] == "at live prices, time not given"
