"""Lane RA item 5 (Lane FD5 review F1, ADR-292 (4), ADR-330 (64)): a paper stop armed BEFORE the position was
recorded as "Held at my broker" is never fired by the paper monitor, whether the market is open or closed.

Real case: strategy with two open paper legs and an armed index exit "NIFTY below 22,850.00"; later the trader
records the position as held at the broker (``held_entry_store.record``: its paper orders stay). The index then
trades at 22,800 and 22,790. The held position is REAL: the monitor writes no stop order, leaves the stop armed
(never cancelled, nothing removed without the owner) and reports it once as not applicable.
"""
from __future__ import annotations

import logging

import pytest
from ofo_app import held_entry_store, paper_monitor
from test_paper_monitor import (  # noqa: F401 - fixture
    AFTER_CLOSE,
    INDEX,
    OPEN_AT,
    Market,
    _exit_below,
    _monitor,
    _stops,
    _strategy,
    _trigger_state,
    db,
)

CROSSED = "22800.00"  # below the exit level 22,850.00


@pytest.mark.parametrize("at", [OPEN_AT, AFTER_CLOSE], ids=["market_open", "market_closed"])
async def test_ra_f1_a_stop_armed_before_the_held_row_exists_never_fires(db, caplog, at):  # noqa: F811
    market = Market(at)
    stored, _ids, keys = await _strategy(db)  # paper orders, then the stop, THEN the held row
    tid = await _exit_below(db, stored.id)
    assert await _trigger_state(db, tid) == (False, False)
    await held_entry_store.record(db, stored.id, OPEN_AT, None)  # ADR-292: held at the broker = a real position
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, CROSSED)
    monitor = _monitor(db, market)
    with caplog.at_level(logging.INFO, logger=paper_monitor.log.name):
        fired = await monitor.step() + await monitor.step()
        monitor.notify()  # a reload: the report must not repeat
        market.tick(INDEX, "22790.00")
        fired += await monitor.step()
    print("FIRED", fired, "STOPS", await _stops(db, stored.id), "NOT APPLICABLE", dict(monitor.not_applicable))
    assert fired == 0
    assert await _stops(db, stored.id) == [], "no stop order for a held position"
    assert await _trigger_state(db, tid) == (False, False), "left armed: neither fired nor cancelled"
    told = [r for r in caplog.records if "not applicable" in r.getMessage()]
    assert monitor.not_applicable == {tid: "real"}
    assert len(told) == 1, "reported once"


# ---- Coordinator item 7 (G1): the server kinds ``stop`` and ``settle`` at the store's door ----------------------

from decimal import Decimal  # noqa: E402

from ofo_app import paper_store, strategy_store  # noqa: E402
from ofo_app.strategy_refused import StrategyRefused  # noqa: E402

STOP_REFUSED = "real_position_exit_refused"


def _close_leg(contract_id: int, side: str, kind: str) -> paper_store.NewOrder:
    return paper_store.NewOrder(contract_id, side, 65, Decimal("41.00"), kind, OPEN_AT, "test", None)


async def test_ra_g1_a_stop_is_never_stored_on_a_held_position_nor_an_unreadable_one(db, monkeypatch):  # noqa: F811
    """ADR-330 (64): ``stop`` skipped the kind refusal in ``paper_store.place`` ("never a user order"); the monitor's
    two checks (``_paper_only`` at reload, ``_still_paper`` in the fire) were the only guard. The one door now refuses
    a stop unless the position reads paper; nothing is stored."""
    stored, ids, _keys = await _strategy(db)
    before = len(await paper_store.load(db, stored.id))
    paper_ok = await paper_store.place(db, stored.user_ref, stored.id, [_close_leg(ids[1], "SELL", "stop")])
    assert len(paper_ok) == before + 1  # a paper position: the stop is stored
    await held_entry_store.record(db, stored.id, OPEN_AT, None)
    with pytest.raises(StrategyRefused, match=STOP_REFUSED):
        await paper_store.place(db, stored.user_ref, stored.id, [_close_leg(ids[0], "BUY", "stop")])
    assert len(await paper_store.load(db, stored.id)) == before + 1, "nothing stored for the held position"

    async def unreadable(_conn, wanted):
        return dict.fromkeys(wanted, "unknown")
    monkeypatch.setattr(strategy_store, "kinds_of", unreadable)
    with pytest.raises(StrategyRefused, match=STOP_REFUSED):
        await paper_store.place(db, stored.user_ref, stored.id, [_close_leg(ids[0], "BUY", "stop")])


async def test_ra_g1_a_settle_is_stored_on_a_held_position_because_the_contract_expired(db):  # noqa: F811
    """ADR-292: "a held condor settles at expiry through the paper settlement at intrinsic value". A settle is the
    app's own book-keeping of a fact (the contract expired at the exchange whatever anyone did), not an action by the
    trader on the real position, so it passes on a held position."""
    stored, ids, _keys = await _strategy(db)
    await held_entry_store.record(db, stored.id, OPEN_AT, None)
    book = await paper_store.place(db, stored.user_ref, stored.id, [_close_leg(ids[1], "SELL", "settle")])
    assert [o.order.kind for o in book].count("settle") == 1


# ---- Coordinator item 8 (Lane FD5 review F4): open, add and exit each have their own refusal code --------------------

@pytest.mark.parametrize(("kind", "code"), [("open", "real_position_open_refused"),
                                            ("add", "real_position_add_refused"),
                                            ("exit", "real_position_exit_refused")])
async def test_ra_f4_each_user_order_kind_has_its_own_refusal_code_and_all_read_the_same_sentence(
        db, monkeypatch, kind, code):  # noqa: F811
    from ofo.errors import CATALOGUE  # noqa: PLC0415
    stored, ids, _keys = await _strategy(db)

    async def unreadable(_conn, wanted):
        return dict.fromkeys(wanted, "unknown")  # refuses every user order kind (ADR-330 (64): fail closed)
    monkeypatch.setattr(strategy_store, "kinds_of", unreadable)
    with pytest.raises(StrategyRefused) as refused:
        await paper_store.place(db, stored.user_ref, stored.id, [_close_leg(ids[0], "BUY", kind)])
    assert str(refused.value) == code
    parts = ("what_happened", "impact", "what_is_blocked", "next_action")
    same = tuple(getattr(CATALOGUE["real_position_exit_refused"], p) for p in parts)
    assert tuple(getattr(CATALOGUE[code], p) for p in parts) == same, "the sentence stays the same for all three"


# ---- Coordinator item 7 (Z2 review T1): a crossed stop skipped by the fire's own kind check says why -----------------

async def test_ra_t1_a_stop_the_fire_skips_because_the_kind_is_not_paper_now_is_reported_never_silent(
        db, caplog, monkeypatch):  # noqa: F811
    """The reload read the kind as paper, then the fire's own read (``_still_paper``) says no (a failed or changed
    read). The crossed stop is left armed (never cancelled), and the monitor tells it: logged once, named in
    ``not_applicable`` and in the report for its trade, so the trade never reads watched because of silence."""
    market = Market()
    stored, _ids, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22900.00")  # above the level first: the monitor fires on a crossing, not on a state

    async def not_paper(_session, _sid):
        return False
    monkeypatch.setattr(paper_monitor.PaperMonitor, "_still_paper", staticmethod(not_paper))
    monitor = _monitor(db, market)
    with caplog.at_level(logging.WARNING, logger=paper_monitor.log.name):
        fired = await monitor.step()
        market.tick(INDEX, CROSSED)
        fired += await monitor.step() + await monitor.step()
    assert fired == 0
    assert await _trigger_state(db, tid) == (False, False), "left armed, not cancelled"
    assert await _stops(db, stored.id) == []
    assert monitor.not_applicable == {tid: "unknown"}
    assert monitor._na_strategies.get(stored.id), "the trade is named in the next report"
    told = [r for r in caplog.records if "not fired" in r.getMessage()]
    assert len(told) == 1, "logged once, not on every tick"
