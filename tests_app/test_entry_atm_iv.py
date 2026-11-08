"""ADR-270 (1) / ADR-277 (4): the entry ATM IV at a strategy's first fill, and the app's own daily ATM IV, both from
the check's ONE ATM-IV figure (``read_market``'s ``vol``: the IV of the call nearest the forward the model prices)."""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo_app import adjustment_readers as readers
from ofo_app import background, scenario_mode
from ofo_app.background import PriceState
from ofo_app.routes import outcome
from test_adjustment_approaches_route import load, tracked_of


def _scn(monkeypatch, sid: str):
    scn = scenario_mode.load(sid)
    monkeypatch.setattr(readers, "_scenario", lambda: scn)
    return scn, outcome.MarketContext(scn.provider, scn.clock, scn.rate)


def test_entry_iv_is_the_checks_own_atm_iv(monkeypatch):
    """Core proof: on ADJ-02's chain the entry helper answers a Decimal IV, the very figure the check reads."""
    sc = load("ADJ-02")
    ctx = _scn(monkeypatch, "ADJ-02")[1]
    position = tracked_of(sc).position
    check_vol = asyncio.run(readers.read_market(tracked_of(sc), ctx)).vol
    iv = asyncio.run(readers.atm_iv_now(ctx, position.underlying, position.legs[0].expiry, D(sc["market"]["spot"])))
    assert isinstance(iv, D) and iv > 0 and iv == check_vol


def test_entry_iv_none_when_the_chain_is_unpriced(monkeypatch):
    sc = load("ADJ-02")
    scn, ctx = _scn(monkeypatch, "ADJ-02")
    monkeypatch.setattr(scn.provider, "option_chain_snapshot", lambda *_a: [])
    position = tracked_of(sc).position
    assert asyncio.run(readers.atm_iv_now(ctx, position.underlying, position.legs[0].expiry,
                                          D(sc["market"]["spot"]))) is None


def test_entry_iv_none_when_not_connected():
    assert asyncio.run(readers.atm_iv_now(None, "NIFTY", datetime.date(2026, 11, 10), D("24000"))) is None


# ---- ADR-277 (4): the worker writes the app's own ATM IV once per underlying per IST trading day ---------------------

AT = datetime.datetime(2026, 11, 9, 4, 0, tzinfo=datetime.UTC)  # 09:30 IST, Monday
DAY, NEAR, LATER = datetime.date(2026, 11, 9), datetime.date(2026, 11, 10), datetime.date(2026, 11, 17)
IV = D("0.1432")


def _listed(*expiries):
    return tuple(SimpleNamespace(contract=SimpleNamespace(expiry=e)) for e in expiries)


def _w(expiry=NEAR, underlying="NIFTY"):
    leg = SimpleNamespace(expiry=expiry)
    return SimpleNamespace(tracked=SimpleNamespace(position=SimpleNamespace(underlying=underlying, legs=(leg,))))


LISTED = _listed(datetime.date(2026, 11, 3), NEAR, LATER)  # an expired expiry, the nearest, a later one


def _read(state=PriceState.FRESH, listed=LISTED):
    return SimpleNamespace(state=state, listed=listed)


@pytest.mark.parametrize(("w", "read", "vol", "scn", "row"), [
    (_w(), _read(), IV, None, ("NIFTY", DAY, NEAR, IV)),  # live, fresh, stated, nearest unexpired expiry
    (_w(), _read(), None, None, None),  # no ATM IV (unpriced chain / no forward): nothing, never a guess
    (_w(), _read(), IV, "a scenario", None),  # scenario mode: test data never enters the real history
    (_w(LATER), _read(), IV, None, None),  # not the nearest expiry: one tenor per day
    (_w(), _read(PriceState.MARKET_CLOSED), IV, None, None),  # not a fresh read (market closed)
    (_w(), _read(listed=()), IV, None, None),  # nothing listed: the nearest expiry is not known
])
def test_daily_iv_row_per_answer_state(monkeypatch, w, read, vol, scn, row):  # noqa: PLR0913 - the parameters
    monkeypatch.setattr(scenario_mode, "current", lambda: scn)
    assert background.daily_iv_of(w, read, SimpleNamespace(vol=vol), AT) == row


def _worker(recorder):
    async def lister():
        return []
    return background.Worker(provider_for=lambda _o: None, lister=lister, clock=lambda: AT, settings=None,
                             preferences=None, daily_iv=recorder)


def test_worker_writes_the_day_once_then_no_more_calls():
    calls = []

    async def recorder(*row):
        calls.append(row)
        return True
    w = _worker(recorder)
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV))
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV + 1))  # same day queued again before the write: kept the first
    asyncio.run(w.drain_writes())
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV + 1))  # same day after the write: no DB call
    w._queue_daily_iv(None)  # no row from the check: nothing
    asyncio.run(w.drain_writes())
    assert calls == [("NIFTY", DAY, NEAR, IV)]
    w._queue_daily_iv(("SENSEX", DAY, NEAR, IV))  # another underlying, and the next day: each written once
    w._queue_daily_iv(("NIFTY", DAY + datetime.timedelta(days=1), NEAR, IV))
    asyncio.run(w.drain_writes())
    assert len(calls) == 3  # noqa: PLR2004 - NIFTY today, SENSEX today, NIFTY tomorrow


def test_worker_daily_iv_write_that_fails_is_queued_again_by_the_next_check():
    calls = []

    async def recorder(*row):
        calls.append(row)
        if len(calls) == 1:
            raise RuntimeError("db down")
        return False  # the day already stored (ON CONFLICT): done for the day all the same
    w = _worker(recorder)
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV))
    asyncio.run(w.drain_writes())  # failed: logged, not done
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV))
    asyncio.run(w.drain_writes())
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV))
    asyncio.run(w.drain_writes())
    assert len(calls) == 2  # noqa: PLR2004 - the failed call, then the one that found the day stored


def test_worker_with_no_daily_recorder_queues_nothing():
    """Only the live role wires ``record_daily_iv``; the scenario role and every other worker write no daily row."""
    w = _worker(None)
    w._queue_daily_iv(("NIFTY", DAY, NEAR, IV))
    asyncio.run(w.drain_writes())
    assert w._daily_iv_pending == {} and w._daily_iv_done == set()
