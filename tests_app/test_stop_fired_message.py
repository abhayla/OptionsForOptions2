"""W2-A (ADR-330 (3b), (6), (19)(b); owner Q2; the owner's one-module instruction): a fired Stops-panel exit is raised
through ``actionable_alerts.inform`` (kind stop_fired) in the exit's own transaction, with the max-loss line from the
ONE function the Stops panel's route uses (``routes.paper.leg_stop_answer``), priced at the recorded fill (the
"exited at" price of the same message; Lane J review 26 Nov: a gapped fill priced at the level understated max loss).

The book is the app's iron condor of tests_app/test_leg_stop_risk.py: a stop on the short call at 140.70
turns Max Loss 2,860.00 into 12,005.50 at 140.70 exactly; each 0.05 above it adds Rs 3.25
(65 units). States: yes -> line; no / cannot_tell -> no line; an exception
while computing it -> no line, logged, the exit and the record are still written. Every test rolls back.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.errors.explanations import render_explanation
from ofo_app import actionable_alerts as aa
from ofo_app import alert_title, paper_store, tracked_contracts
from ofo_app import paper_trigger_store as triggers
from ofo_app.routes import paper as paper_routes
from test_paper_monitor import INDEX, Market, _alerts, _monitor, _paper_alert_rows, _stops
from test_strategy_store import _user, _with_draft

D = Decimal
AT = datetime.datetime(2026, 11, 25, 5, 0, tzinfo=datetime.UTC)
SIDES, PRICES = ("SELL", "BUY", "SELL", "BUY"), ("80", "20", "130", "34")
SHORT_CALL, LONG_CALL = 0, 1
LINE = "If this stop fires, max loss becomes Rs 12,025.00 (now Rs 2,860.00)."  # filled at 141.00 (stop 140.70)
GAP_LINE = "If this stop fires, max loss becomes Rs 14,560.00 (now Rs 2,860.00)."  # filled at 180.00


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _condor(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    ids = stored.saved.contract_ids
    await paper_store.place(db, user, stored.id, [
        paper_store.NewOrder(ids[i], SIDES[i], 65, D(PRICES[i]), "open", AT) for i in range(4)])
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    return stored, ids, keys


async def _fire_leg(db, which: int, level: str, tick: str):
    market = Market()
    stored, ids, keys = await _condor(db)
    await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D(level), contract_id=ids[which]))
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(INDEX, "22849.95")
    market.tick(keys[which], tick)
    return monitor, stored, ids, await monitor.step()


async def test_a_fired_leg_stop_is_one_informational_history_row_with_the_max_loss_line(db):
    monitor, stored, _ids, fires = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    assert fires == 1 and monitor.fires == 1
    [(title, text)] = await _alerts(db, stored.id)
    assert LINE in text and text.startswith("Stop-loss: ")
    assert f"(#{stored.id}" in title
    assert await _paper_alert_rows(db, stored.id) == 0  # not written twice, not in the old table
    assert len(await _stops(db, stored.id)) == 1
    user = (await aa.history(db, stored.user_ref))[0].strategy_name and stored.user_ref
    assert [a for a in await aa.unanswered(db, user) if a.strategy_id == stored.id] == []  # not on Active
    assert await aa.unanswered_count(db, user) == 0  # the bell is unchanged
    row = next(a for a in await aa.history(db, user) if a.strategy_id == stored.id)
    assert (row.kind, row.answer, row.outcome) == ("stop_fired", "noted", "dismissed")


async def test_a_gapped_fill_prices_the_line_at_the_fill_the_route_gives_for_that_price(db):
    """Review MAJOR 1: stop 140.70, the tick gaps to 180.00; the line is the position actually held, the same figure
    the Stops panel's route gives for a level of 180.00, never the 140.70 figure."""
    _, stored, _, fires = await _fire_leg(db, SHORT_CALL, "140.70", "180.00")
    [(_, text)] = await _alerts(db, stored.id)
    assert fires == 1 and GAP_LINE in text and "exited at 180.00" in text
    assert "12,005.50" not in text


async def test_a_failing_line_computation_never_stops_the_exit_or_the_record(db, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("engine fell over")

    monkeypatch.setattr(paper_routes, "leg_stop_answer", broken)
    monitor, stored, _, fires = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    assert fires == 1 and monitor.fires == 1 and monitor.failures == 0
    [(_, text)] = await _alerts(db, stored.id)
    assert "max loss" not in text and "exited at 141.00" in text
    assert len(await _stops(db, stored.id)) == 1


@pytest.mark.parametrize("state", ["no", "cannot_tell"])
async def test_an_answer_of_no_or_cannot_tell_writes_no_line_and_no_figure(db, monkeypatch, state):
    monkeypatch.setattr(paper_routes, "leg_stop_answer", lambda *a, **k: paper_routes._exit_risk_answer(state))
    _, stored, _, fires = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    [(_, text)] = await _alerts(db, stored.id)
    assert fires == 1 and "max loss" not in text and "Rs" not in text


async def test_a_long_wing_stop_gets_the_engines_own_answer_no_fixed_maximum(db):
    """The brief expected no line; the engine (like the route, tests_app/test_leg_stop_risk.py) says yes: the sold call
    leaves the short call bare, so the line says there is no fixed maximum loss."""
    _, stored, _, fires = await _fire_leg(db, LONG_CALL, "5.00", "5.50")
    [(_, text)] = await _alerts(db, stored.id)
    assert fires == 1 and "If this stop fires, there is no fixed maximum loss (now Rs 2,860.00)." in text


async def test_an_index_exit_gets_a_line_only_when_the_exit_check_says_yes(db):
    market = Market()
    stored, _ids, keys = await _condor(db)
    await triggers.add(db, stored.id, triggers.NewTrigger("conditional_exit", "below", D("22850.00"),
                                                          underlying="NIFTY"))
    monitor = _monitor(db, market)
    await monitor.step()
    for key, price in zip(keys, ("80", "20", "130", "34"), strict=True):
        market.tick(key, price)
    market.tick(INDEX, "22849.95")
    assert await monitor.step() == 1
    [(_, text)] = await _alerts(db, stored.id)
    assert "exited 4 legs" in text and "If this stop fires" not in text  # the whole book closed: nothing widens


async def test_the_history_title_keeps_its_expiry_after_the_book_is_flat(db):
    _, stored, _, _ = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    label = str((await alert_title.labels(db, [(stored.id, "Condor")]))[stored.id])
    assert label.startswith('"Condor" (#') and f"#{stored.id}" in label
    assert render_explanation("alert_title_unnamed", id=1) == "Strategy 1"
