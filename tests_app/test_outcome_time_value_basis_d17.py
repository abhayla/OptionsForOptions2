"""D-17 (owner decided 25 Nov 2026, ADR-322 point 2): the time value of the builder summary is at LIVE prices
(REQ-081 AC-3) and says so: "at live prices, as of HH:MM:SS", the time being the oldest leg quote time the reply
already serves (`oldest_quote_at`, IST). The credit beside it keeps its own basis label (`price_basis_text`).

Core: the replay condor on the real route. Hand check: the sentence clock equals oldest_quote_at read in IST; with a leg
quote that has no time the sentence says the time is not given instead of borrowing another time.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata import quote as quote_module  # noqa: E402
from ofo_app.routes import outcome as outcome_route  # noqa: E402
from test_outcome_margin import _body  # noqa: E402
from test_outcome_price_basis_d15 import _post  # noqa: E402


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


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


# round 2: the time value is leg prices minus intrinsic at the SPOT, so the label's time is the oldest of both
class _Spot:
    def __init__(self, at):
        self.price_at = at


def _rows(*times):
    return [{"quote_at": t} for t in times]


def _t(clock):
    return datetime.datetime(2026, 11, 25, *map(int, clock.split(":")), tzinfo=IST)


def test_the_spot_older_than_every_leg_quote_sets_the_time():
    legs = _rows(_t("14:12:05"), _t("14:12:09"))
    assert outcome_route._time_value_as_of(legs, _Spot(_t("14:11:00"))) == _t("14:11:00")
    assert outcome_route._time_value_as_of(_rows(_t("14:12:05")), _Spot(_t("14:12:30"))) == _t("14:12:05")


def test_a_missing_spot_or_leg_time_gives_no_time():
    assert outcome_route._time_value_as_of(_rows(_t("14:12:05")), _Spot(None)) is None
    assert outcome_route._time_value_as_of(_rows(_t("14:12:05")), None) is None
    assert outcome_route._time_value_as_of(_rows(_t("14:12:05"), None), _Spot(_t("14:12:30"))) is None


def test_a_closed_market_says_last_close_prices_not_live():
    s = {"time_value": "-10.00"}
    def text(at, closed):
        return outcome_route._with_time_value_basis(s, at, closed)["time_value_basis_text"]

    assert text(_t("15:30:00"), True) == "at the last close prices, as of 15:30:00"
    assert text(None, True) == "at the last close prices"
    assert text(_t("14:12:05"), False) == "at live prices, as of 14:12:05"
