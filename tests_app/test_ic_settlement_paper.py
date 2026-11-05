# ruff: noqa: E501
"""IC e2e paper contract, Stage C2 item 2 (REQ-109 AC-7): legs of a paper iron condor held to expiry are settled by
``paper_settlement.settle_expired`` at the intrinsic value of the official close; the final P&L in the history equals the sum
of the stored fills (entry + settle); a second run writes nothing.

PATH-50 condor: BUY 22950 PE, SELL 23150 PE, SELL 23500 CE, BUY 23700 CE (2 lots of 65). Injected close 23,600: only the
short 23500 CE is in the money (settle price 100; a BUY of 130); the other three settle at 0.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import test_ic_exits_paper as ex
import test_ic_paper_loop_core as core
from ofo.timeutil import IST
from ofo_app import paper_settlement as ps

CLOSE = D("23600")
EXPIRY = datetime.date(2026, 11, 9)
AFTER = datetime.datetime(2026, 11, 9, 15, 50, tzinfo=IST)
BEFORE = datetime.datetime(2026, 11, 9, 14, 0, tzinfo=IST)


def _close_of(calls: list | None = None):
    async def close_of(underlying: str, expiry: datetime.date) -> D | None:
        if calls is not None:
            calls.append((underlying, expiry))
        return CLOSE
    return close_of


async def _settles(sid: int) -> list[tuple]:
    return [tuple(r) for r in await core._rows(
        "SELECT c.strike, c.instrument_type, o.side, o.quantity, o.price FROM public.paper_orders o "
        "JOIN public.catalogue_contracts c ON c.id = o.contract_id WHERE o.strategy_id = :s AND o.kind = 'settle' "
        "ORDER BY c.instrument_type, c.strike", s=sid)]


async def test_held_to_expiry_legs_settle_once_and_history_equals_the_fills(app_engine, monkeypatch):
    sid = await ex.setup(app_engine, monkeypatch)
    try:
        await core._move(ex.F_SETTLE)
        entry_cash = await ex.sum_of_fills(sid)
        legs_before = {c: n for c, n in (await core._net(sid)).items() if n}
        assert len(legs_before) == 4  # attack 1 reversed: all four legs are open before the settlement
        # before the settle time: nothing (a settle is never early)
        async with core._engine().connect() as conn:
            early = await ps.settle_expired(conn, BEFORE, _close_of())
        assert [s for s in early.settled if s.strategy_id == sid] == []
        calls: list = []
        async with core._engine().connect() as conn:
            run = await ps.settle_expired(conn, AFTER, _close_of(calls))
        mine = [s for s in run.settled if s.strategy_id == sid]
        assert len(mine) == 4 and run.failed == ()
        assert calls.count(("NIFTY", EXPIRY)) == 1
        assert await _settles(sid) == [(D("23500"), "CE", "BUY", 130, D("100")),  # short call in the money: bought back at 100
                                        (D("23700"), "CE", "SELL", 130, D("0")),
                                        (D("22950"), "PE", "SELL", 130, D("0")),
                                        (D("23150"), "PE", "BUY", 130, D("0"))]
        assert set((await core._net(sid)).values()) == {0}
        cash = await ex.sum_of_fills(sid)
        assert cash == entry_cash - D(130) * D(100), (cash, entry_cash)  # exact Decimal: settle adds only -13,000
        async with ex.client() as ac:
            assert (await ac.get(f"/api/strategies/{sid}/adjustment-check")).status_code == ex.OK
            assert await ex.booked(ac, sid) == cash
        # attack 3: the second run writes 0 rows
        before = (await core._rows("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid))[0][0]
        async with core._engine().connect() as conn:
            again = await ps.settle_expired(conn, AFTER, _close_of())
        assert [s for s in again.settled if s.strategy_id == sid] == []
        assert (await core._rows("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid))[0][0] == before
    finally:
        await ex.cleanup()
