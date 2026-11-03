"""REQ-170 AC-5: "Risk exits are not delayed: a stop-loss or conditional exit (REQ-041 / paper triggers) acts on the
live price at once; this requirement applies only to adjustment suggestions."

Two proofs:
1. Structural (the one path every paper exit passes): the paper trigger modules never reach the alert gate
   (``ofo.adjustment.alert_gate``) or the worker that drives it (``ofo_app.background``), walked with the same import
   closure walker as the order doors; a mutation adding the import is red with its chain.
2. Behavioural: a strategy whose adjustment rule is gated (an open record just opened, so a cool-down is running) still
   has its paper conditional exit fire on the FIRST live tick past the level, through the real monitor and database.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.timeutil import IST
from ofo_app import paper_store, playbook_store, strategy_pause_store, tracked_contracts
from test_order_path_switch import ALLOWED_ORDER_PATHS, BACKEND, order_closure_problems
from test_paper_monitor import (  # noqa: F401
    INDEX,
    OPEN_AT,
    Market,
    _alerts,
    _exit_below,
    _monitor,
    _stops,
    _trigger_state,
    db,
)
from test_paper_order_door import PAPER_MODULES, _mutated
from test_strategy_store import _user, _with_draft

D = Decimal
#: the gate, its worker, and the user's pause (A-38, GC-IC1 4a): a pause is for adjustment checks only (AC-5)
GATE_MODULES: frozenset[str] = frozenset({"ofo.adjustment.alert_gate", "ofo_app.background",
                                          "ofo.adjustment.monitor_pause", "ofo_app.strategy_pause_store",
                                          # the user's level watch (A-37, GC-IC1 4c, ADR-242): an adjustment alert
                                          "ofo.adjustment.level_watch", "ofo_app.strategy_level_watch_store"})
#: the paper exit path: the monitor, the trigger store, the stop crossing rule (the order book's own modules too)
EXIT_MODULES: tuple[str, ...] = PAPER_MODULES


def _gate_reached(root=BACKEND, modules=EXIT_MODULES) -> list[str]:
    problems, _ = order_closure_problems(list(modules), root, dict(ALLOWED_ORDER_PATHS), GATE_MODULES)
    return [p for p in problems if any(p.endswith(f"-> {g}") for g in GATE_MODULES)]


def test_no_paper_exit_module_reaches_the_alert_gate_or_the_worker():
    assert "ofo_app.paper_monitor" in EXIT_MODULES and "ofo.tracking.stops" in EXIT_MODULES
    assert _gate_reached() == []


@pytest.mark.parametrize(("module_file", "extra", "gate"), [
    ("ofo_app/paper_monitor.py", "from ofo.adjustment import alert_gate  # noqa: F401", "ofo.adjustment.alert_gate"),
    ("ofo/tracking/stops.py", "def _late():\n    from ofo.adjustment import alert_gate  # noqa: F401",
     "ofo.adjustment.alert_gate"),
    ("ofo_app/paper_trigger_store.py", "from ofo_app import background  # noqa: F401", "ofo_app.background"),
    ("ofo_app/paper_monitor.py", "from ofo_app import strategy_pause_store  # noqa: F401",
     "ofo_app.strategy_pause_store"),
    ("ofo/tracking/stops.py", "from ofo.adjustment import monitor_pause  # noqa: F401", "ofo.adjustment.monitor_pause"),
    ("ofo/tracking/stops.py", "from ofo.adjustment import level_watch  # noqa: F401", "ofo.adjustment.level_watch"),
    ("ofo_app/paper_monitor.py", "from ofo_app import strategy_level_watch_store  # noqa: F401",
     "ofo_app.strategy_level_watch_store"),
])
def test_mutation_a_gate_import_in_a_paper_exit_module_is_red(tmp_path, module_file, extra, gate):
    reached = _gate_reached(_mutated(tmp_path, module_file, extra))
    assert any(p.endswith(f"-> {gate}") for p in reached), reached


async def test_a_gated_adjustment_rule_never_delays_the_conditional_exit(db):  # noqa: F811 - the paper fixture
    market = Market()
    user = _user()
    _, stored = await _with_draft(db, user)
    ids = stored.saved.contract_ids[:2]
    await paper_store.place(db, user, stored.id, [
        paper_store.NewOrder(ids[0], "SELL", 65, D("39.15"), "open", OPEN_AT),
        paper_store.NewOrder(ids[1], "BUY", 65, D("12.95"), "open", OPEN_AT)])
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    # the adjustment side: an open T-01 record just opened, so the gate would hold the rule (cool-down running)
    rec = await playbook_store.open_suggestion(db, user, stored.id, "T-01", trigger_id="T-01", stage="Middle",
                                               value=D("0.3416"), threshold=D("0.5000"), source="system")
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22849.95")  # the first tick past the level
    assert await monitor.step() == 1
    assert [s[1:3] for s in await _stops(db, stored.id)] == [("BUY", 65), ("SELL", 65)]
    assert await _trigger_state(db, tid) == (True, False)
    assert len(await _alerts(db, stored.id)) == 1
    assert [(r.id, r.outcome) for r in await playbook_store.open_suggestions(db, user, stored.id)] == [
        (rec.id, "open")]  # the exit neither waited for nor touched the adjustment record



async def test_a_user_paused_strategy_still_fires_its_conditional_exit(db):  # noqa: F811 - the paper fixture
    """A-38 (GC-IC1 4a): the user paused the strategy's ADJUSTMENT checks 10:10 -> 10:30; its paper exit crossing
    inside the pause (the first tick past the level) still fires at once, through the real monitor and database."""
    market = Market()
    user = _user()
    _, stored = await _with_draft(db, user)
    ids = stored.saved.contract_ids[:2]
    await paper_store.place(db, user, stored.id, [
        paper_store.NewOrder(ids[0], "SELL", 65, D("39.15"), "open", OPEN_AT),
        paper_store.NewOrder(ids[1], "BUY", 65, D("12.95"), "open", OPEN_AT)])
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    day = datetime.date(2026, 11, 3)
    paused_at = datetime.datetime.combine(day, datetime.time(10, 10), IST)
    until = datetime.datetime.combine(day, datetime.time(10, 30), IST)
    assert await strategy_pause_store.set_pause(db, user, stored.id, until, paused_at) == until
    assert await strategy_pause_store.pause_of(db, user, stored.id) == until
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22849.95")  # the first tick past the level, inside the pause
    assert await monitor.step() == 1
    assert [s[1:3] for s in await _stops(db, stored.id)] == [("BUY", 65), ("SELL", 65)]
    assert await _trigger_state(db, tid) == (True, False)
