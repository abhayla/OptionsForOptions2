"""Lane FE2 (28 Nov 2026), item 2 (issue #863): the worker reads the chain, the forward and the ATM IV of the SAME
expiry its expiry kind is read for: the nearest leg. Spec basis: ADR-330 (44), (47), (58); REQ-115 AC-4.

Real case: a calendar trade whose first listed leg is the far one (sold Dec 28 call listed before the bought Nov 9
call). The kind was read for Nov 9; the chain, the forward and the ATM IV for Dec 28.
"""
from __future__ import annotations

import dataclasses
import datetime

from ofo.marketdata.shared_compute import FeedScope
from ofo_app import adjustment_readers, background, scenario_mode
from test_background_cycle import DEFAULTS, Prov, _price_time, _watched, scn  # noqa: F401 - the module fixture

NEAR = datetime.date(2026, 11, 9)  # the scenario's one listed expiry
FAR = datetime.date(2026, 12, 28)


class _EveryExpiry(Prov):
    """The scenario lists one expiry; the far leg's chain is the same rows (the test is about WHICH expiry is asked)."""

    def option_chain_snapshot(self, u, e):
        return super().option_chain_snapshot(u, NEAR)


def _far_first(w):
    legs = (dataclasses.replace(w.tracked.position.legs[0], expiry=FAR), *w.tracked.position.legs[1:])
    return dataclasses.replace(w, tracked=dataclasses.replace(
        w.tracked, position=dataclasses.replace(w.tracked.position, legs=legs)))


FORWARD_ASKED: list[datetime.date] = []
_REAL_FORWARD = background.parity_forward


def recording_forward(chain, spot, expiry, *a, **k):  # module level: the shared cache refuses a closure
    FORWARD_ASKED.append(expiry)
    return _REAL_FORWARD(chain, spot, expiry, *a, **k)


def test_chain_forward_and_rows_use_the_nearest_leg_not_the_first_one_listed(scn, monkeypatch):  # noqa: F811
    FORWARD_ASKED.clear()
    asked: dict[str, list] = {"forward": FORWARD_ASKED, "rows": [], "kind": []}
    real_rows, real_kind = adjustment_readers.chain_rows, adjustment_readers.expiry_kind_of

    def rows(listed, expiry, *a, **k):
        asked["rows"].append(expiry)
        return real_rows(listed, expiry, *a, **k)

    def kind(expiry, *a, **k):
        asked["kind"].append(expiry)
        return real_kind(expiry, *a, **k)
    monkeypatch.setattr(background, "parity_forward", recording_forward)
    monkeypatch.setattr(adjustment_readers, "chain_rows", rows)
    monkeypatch.setattr(adjustment_readers, "expiry_kind_of", kind)
    prov = _EveryExpiry(scn)
    at = _price_time(prov)
    w = _far_first(_watched(scn)[0])
    read = background.read_prices(prov, w, at)
    background.market_inputs(w, read, FeedScope(background.SharedCompute(), "owner"), at, DEFAULTS)
    print("ASKED", asked)
    assert {x.expiry for x in w.tracked.position.legs} == {NEAR, FAR}
    assert set(asked["kind"]) == {NEAR}
    assert set(asked["forward"]) == {NEAR}, "the forward must come from the chain of the expiry the kind is read for"
    assert set(asked["rows"]) == {NEAR}


def test_the_daily_iv_row_is_taken_for_the_nearest_leg_of_a_far_first_trade(scn, monkeypatch):  # noqa: F811
    monkeypatch.setattr(scenario_mode, "current", lambda: None)  # the live day: scenario data never enters history
    prov = _EveryExpiry(scn)
    at = _price_time(prov)
    w = _far_first(_watched(scn)[0])
    read = background.read_prices(prov, w, at)
    market = background.market_inputs(w, read, FeedScope(background.SharedCompute(), "owner"), at, DEFAULTS)
    got = background.daily_iv_of(w, read, market, at)
    print("DAILY", got)
    if market.vol is not None and got is not None:
        assert got[2] == NEAR
    assert got is None or got[2] == NEAR
