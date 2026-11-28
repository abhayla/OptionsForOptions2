"""Lane FR (28 Nov 2026), item 1 (issue #863, screen half): the screen's ``read_market`` reads the chain, the forward
and the ATM IV of the NEAREST leg's expiry, the one the worker reads (``background.primary_expiry``).
Spec basis: ADR-330 (44), (47), (58); REQ-115 AC-4.

Real case: a calendar trade listed far-leg-first (sold 28 Dec call before the bought 9 Nov call): the worker read
9 Nov, the screen read 28 Dec.
"""
from __future__ import annotations

import datetime

from ofo.marketdata.shared_compute import FeedScope
from ofo_app import adjustment_readers, background
from ofo_app.routes.outcome import MarketContext, ctx_in_force
from test_background_cycle import DEFAULTS, RATE, Prov, _price_time, _watched, scn  # noqa: F401 - the module fixture
from test_worker_expiry_fe2_1128 import FAR, NEAR, _EveryExpiry, _far_first


async def test_core_screen_and_worker_read_one_expiry_for_a_far_first_calendar(scn, monkeypatch):  # noqa: F811
    asked: list[datetime.date] = []
    real_rows = adjustment_readers.chain_rows

    def rows(listed, expiry, *a, **k):
        asked.append(expiry)
        return real_rows(listed, expiry, *a, **k)
    monkeypatch.setattr(adjustment_readers, "chain_rows", rows)
    prov = _EveryExpiry(scn)
    at = _price_time(prov)
    w = _far_first(_watched(scn)[0])
    assert {x.expiry for x in w.tracked.position.legs} == {NEAR, FAR} and w.tracked.position.legs[0].expiry == FAR
    read = background.read_prices(prov, w, at)
    worker = background.market_inputs(w, read, FeedScope(background.SharedCompute(), "owner"), at, DEFAULTS)
    worker_expiry = set(asked)
    asked.clear()
    ctx = ctx_in_force(MarketContext(prov, lambda: at, RATE), DEFAULTS)
    screen = await adjustment_readers.read_market(w.tracked, ctx)
    print("WORKER expiry", sorted(worker_expiry), "SCREEN expiry", sorted(set(asked)))
    assert worker_expiry == {NEAR}
    # the later rows (A-04: the next listed expiry after the nearest) are read too; the far leg's 28 Dec never is
    assert asked[0] == NEAR and FAR not in asked, "the screen must read the nearest leg's expiry, as the worker does"
    assert screen.vol == worker.vol and screen.expiry_kind == worker.expiry_kind
