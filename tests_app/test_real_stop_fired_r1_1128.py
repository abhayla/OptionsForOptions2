# ruff: noqa: F811 - the imported fixture is used as a test argument
"""Lane R1 CORE PROOF (28 Nov 2026; ADR-330 (73), ADR-281, ADR-016 to ADR-019; design note section 6): a stop reached on
a REAL position raises its alert ONCE and stores ONE ``stop_fired`` record; it places no paper order and makes no broker
call; the tag, the kind and the shown book are unchanged. The worker here is the paper monitor driven tick by tick on a
real database (the monitor and the routes share no state: the stop is read from the database).
Spec basis: ADR-330 (73), (58); ADR-281. Answer states: reached once, reached again (claimed once), a leg the plan does
not have, no live price (stays armed), unreadable kind (stays armed), paper (unchanged)."""
from __future__ import annotations

from decimal import Decimal

from ofo_app import paper_store, strategy_store, tracked_contracts
from ofo_app import paper_trigger_store as triggers
from sqlalchemy import text
from test_exit_door_real_fd3 import _sent_basket
from test_paper_monitor import INDEX, Market, _alerts, _monitor
from test_stop_fired_message import db  # noqa: F401 - fixture

D = Decimal
SENT = "Not sent to Zerodha. Place it in Kite."
_PAPER_ORDERS = text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s")
_RECORDS = text("SELECT action, trigger_id FROM public.real_action_records WHERE strategy_id = :s ORDER BY id")
_TAG = text("SELECT tag FROM public.strategy_position_tags WHERE strategy_id = :s")


class _Broker:
    """The egress gate's seam: every Kite call goes through ``check_call``; this one counts them."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, str]] = []
        for module in ("ofo.broker.kite_http", "ofo_app.kite_http"):
            try:
                monkeypatch.setattr(f"{module}.check_call", self._seen, raising=False)
            except (ImportError, AttributeError):
                continue

    def _seen(self, method: str, url: str) -> None:
        self.calls.append((method, url))
        raise AssertionError(f"a broker call was made: {method} {url}")


async def _real_stop(db, level="140.70", leg=0):
    _app, stored, ids = await _sent_basket(db)
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D(level), contract_id=ids[leg]))
    return stored, ids, keys, tid


async def test_core_a_reached_real_stop_alerts_once_stores_one_record_and_sends_nothing(db, monkeypatch):
    broker = _Broker(monkeypatch)
    stored, _ids, keys, tid = await _real_stop(db)
    kinds_before = await strategy_store.kinds_of(db, [stored.id])
    book_before = await paper_store.load(db, stored.id)
    market = Market()
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(INDEX, "22849.95")
    market.tick(keys[0], "141.00")
    fires = await monitor.step()
    print("FIRES", fires, "ALERTS", await _alerts(db, stored.id))
    assert fires == 1 and monitor.fires == 1
    alerts = await _alerts(db, stored.id)
    assert len(alerts) == 1 and SENT in alerts[0][1] and "A paper exit only" not in alerts[0][1]  # (a)
    assert [tuple(r) for r in (await db.execute(_RECORDS, {"s": stored.id})).all()] == [("stop_fired", tid)]  # (b)
    assert (await db.execute(_PAPER_ORDERS, {"s": stored.id})).scalar_one() == 0  # (c)
    assert (await db.execute(_TAG, {"s": stored.id})).scalar_one() == "real"  # (d)
    assert await strategy_store.kinds_of(db, [stored.id]) == kinds_before  # (e)
    assert await paper_store.load(db, stored.id) == book_before == ()  # (f) the shown book is untouched
    listed = next(r for r in await strategy_store.list_strategies(db, stored.user_ref) if r.id == stored.id)
    assert listed.has_paper_order is False and listed.position_tag == "real"
    assert broker.calls == []  # (g)


async def test_a_stop_reached_again_is_claimed_once_and_stores_no_second_record(db, monkeypatch):
    _Broker(monkeypatch)
    stored, _ids, keys, _tid = await _real_stop(db)
    market = Market()
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(INDEX, "22849.95")
    market.tick(keys[0], "141.00")
    await monitor.step()
    market.tick(keys[0], "150.00")
    assert await monitor.step() == 0
    assert len((await db.execute(_RECORDS, {"s": stored.id})).all()) == 1 and len(await _alerts(db, stored.id)) == 1


async def test_a_stop_below_its_level_stays_armed_and_stores_nothing(db, monkeypatch):
    _Broker(monkeypatch)
    stored, _ids, keys, _tid = await _real_stop(db)
    market = Market()
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(INDEX, "22849.95")
    market.tick(keys[0], "100.00")
    assert await monitor.step() == 0
    assert (await db.execute(_RECORDS, {"s": stored.id})).all() == [] and await _alerts(db, stored.id) == []


async def test_a_kind_that_cannot_be_read_leaves_the_stop_armed_and_stores_nothing(db, monkeypatch):
    _Broker(monkeypatch)
    stored, _ids, keys, tid = await _real_stop(db)
    market = Market()
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(INDEX, "22849.95")
    market.tick(keys[0], "141.00")

    async def unknown(_c, sids):
        return dict.fromkeys(sids, "unknown")
    monkeypatch.setattr(strategy_store, "kinds_of", unknown)
    assert await monitor.step() == 0
    assert (await db.execute(_RECORDS, {"s": stored.id})).all() == []
    assert [r.fired_at for r in await triggers.list_for(db, stored.id) if r.trigger.id == tid] == [None]
