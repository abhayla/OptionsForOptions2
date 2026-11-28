"""I-02 (test plan 28 Nov 2026): a plan stop alert, once raised, is KEPT when the loss worsens and when it recovers.
Driven through the REAL gate (``alert_gate.step``, intraday, readings every 5 minutes) and applied by the worker's own
store (``DbGateStore.apply``), so only events the worker can really produce are tested.
What the gate does (Tier A review of 28 Nov, probe): the plan's rupee stop has ONE rung, so a worse loss (400 -> 650 ->
900) emits NO event: the alert stays one open row at the value it fired at (ADR-330 (3): "worse" means one stage worse);
a stop with stages (T-06, two rungs) emits ``Escalated`` and the SAME row is updated and marked escalated.
Recovery under the line (a close that clears it) emits ``Lapsed``: the row stays open with "no longer true
since"; past the line again emits ``TrueAgain``: the note clears, still one row. Nothing answers or exits by itself.
Real case: the S-21 base with a stop typed as Rs 400, loss 400, 650, 900, 250, 420.
Spec basis: ADR-330 (3) (lapse note, one open row per rule), (5)(b), (47).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.adjustment import alert_gate as ag
from ofo.adjustment import stop_lines as sl
from ofo.timeutil import IST
from ofo_app import actionable_alerts, background
from sqlalchemy import text
from test_background_worker import (  # noqa: F401 - the fixture is used by name
    _watched_and_fresh_t03,
    app_db_url,
)

_ROW = ("SELECT id, outcome, kind, value, no_longer_true_since, escalated_at, answer "
        "FROM public.adjustment_suggestions WHERE strategy_id = :s AND rule_id = :r AND id >= :first ORDER BY id")
#: (time, loss) of each check; the rupee loss 400 is the line
READINGS = (("11:00", "400"), ("11:05", "650"), ("11:10", "900"), ("11:15", "250"), ("11:20", "250"),
            ("11:40", "250"), ("11:45", "420"), ("11:50", "420"))


def _at(hhmm: str) -> datetime.datetime:
    hour, minute = hhmm.split(":")
    return datetime.datetime(2026, 11, 25, int(hour), int(minute), 1, tzinfo=IST)


def _run(rule_id: str, ladder: tuple[D, ...], readings=READINGS) -> list[tuple[str, object]]:
    """The gate's events (time, event) for the readings, in order."""
    spec = ag.RuleSpec(rule_id, "ge", ladder)
    state, out = ag.initial_state(), []
    for hhmm, value in readings:
        state, events = ag.step(state, now=_at(hhmm), preset=ag.INTRADAY, readings={rule_id: (spec, D(value))})
        out += [(hhmm, e) for e in events]
    return out


async def _rows(engine, sid: int, rule_id: str, first: int) -> list:
    async with engine.connect() as conn:
        return (await conn.execute(text(_ROW), {"s": sid, "r": rule_id, "first": first})).all()


async def test_gate_events_of_a_worsening_then_recovering_rupee_loss_keep_one_open_row(app_db_url, monkeypatch):  # noqa: F811
    events = _run(sl.RUPEE_LOSS_RULE, (D("400"),))
    kinds = [(t, type(e).__name__) for t, e in events]
    assert kinds == [("11:00", "Opened"), ("11:20", "Lapsed"), ("11:45", "TrueAgain")], kinds  # none at 650 or 900
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    store = background.DbGateStore()
    seen: dict[str, list] = {}
    first = 0
    for hhmm, event in events:
        raised = await store.apply(w, [event])
        rows = await _rows(app_db_url, w.strategy_id, sl.RUPEE_LOSS_RULE, first)
        if isinstance(event, ag.Opened):
            first = raised[sl.RUPEE_LOSS_RULE]
            rows = await _rows(app_db_url, w.strategy_id, sl.RUPEE_LOSS_RULE, first)
        seen[hhmm] = rows
        assert len(rows) == 1 and rows[0].outcome == "open" and rows[0].answer is None, (hhmm, rows)
        assert rows[0].kind == "plan_rupee_loss" and rows[0].value == D("400.0000"), (hhmm, rows)  # fired value stays
    assert seen["11:00"][0].no_longer_true_since is None and seen["11:00"][0].escalated_at is None
    assert seen["11:20"][0].no_longer_true_since is not None  # recovered: kept, with the note
    assert seen["11:45"][0].no_longer_true_since is None  # past the line again: the note clears, no second row
    async with app_db_url.connect() as conn:
        assert [a.id for a in await actionable_alerts.unanswered(conn, "owner") if a.rule_id == sl.RUPEE_LOSS_RULE] \
            == [first]  # still in Active, still counted by the bell


async def test_a_stop_with_stages_updates_the_same_row_when_the_loss_worsens_and_keeps_it_on_recovery(
        app_db_url, monkeypatch):  # noqa: F811
    rule = "T-06"
    events = _run(rule, (D("400"), D("800")), (("11:00", "400"), ("11:05", "900"), ("11:15", "250"), ("11:20", "250")))
    kinds = [(t, type(e).__name__) for t, e in events]
    assert kinds[:2] == [("11:00", "Opened"), ("11:05", "Escalated")] and kinds[-1][1] == "Lapsed", kinds
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    store = background.DbGateStore()
    first = (await store.apply(w, [events[0][1]]))[rule]
    for _, event in events[1:]:
        assert (await store.apply(w, [event])).get(rule, first) == first  # the same alert, never a second one
    rows = await _rows(app_db_url, w.strategy_id, rule, first)
    assert len(rows) == 1 and rows[0].outcome == "open", rows
    assert rows[0].value == D("900.0000") and rows[0].escalated_at is not None, rows  # updated, marked escalated
    assert rows[0].no_longer_true_since is not None, rows  # recovered under the line: kept, with the note
