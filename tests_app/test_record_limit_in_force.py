"""GC-ICSAFE c15 (#685 item 4): a record prints the limit in force, the same one the check screen shows.

Real case: PATH-61 frame 1 (weekly NIFTY iron condor, Early stage): T-03 reads 0.3537 against the Early limit 0.30; the
alert gate's rung it reached is 0.35 (the gate's own memory, stored as the record's threshold). The record's words and
the check screen both draw the limit in force (``RuleValue.threshold``). No database.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import alert_gate
from ofo_app import background, playbook_store
from ofo_app import db as app_db
from ofo_app.routes import adjustment_check as check_route
from ofo_app.routes.adjustment_opportunities import condition_text

AT = datetime.datetime(2026, 11, 12, 11, 0, tzinfo=datetime.UTC)
BOOKED = 2  # adjustments booked in the position
TIMELINE = {"cmp": "ge", "label": "Tested short's delta reaches", "unit": "delta"}


def _record(**extra) -> playbook_store.Suggestion:
    return playbook_store.Suggestion(215, 123, "T-03", "T-03", "Early", D("0.3537"), D("0.3500"), AT, "open", None,
                                     [{**TIMELINE, **extra}])


def test_a_record_prints_the_limit_in_force_not_the_gate_rung():
    assert "0.3000" in str(condition_text(_record(limit="0.3000")))
    assert "0.3500" not in str(condition_text(_record(limit="0.3000")))


def test_an_older_record_without_a_stored_limit_prints_its_threshold_as_before():
    assert _record().limit is None
    assert "0.3500" in str(condition_text(_record()))


class _Db:
    async def commit(self) -> None:
        return None


class _Session:
    async def __aenter__(self) -> _Db:
        return _Db()

    async def __aexit__(self, *exc) -> None:
        return None


@pytest.mark.asyncio
async def test_the_worker_stamps_the_limit_in_force_beside_the_gate_rung(monkeypatch):
    stamped: dict = {}

    async def open_suggestion(db, user, sid, rule, **fields):
        stamped.update(fields)
        return SimpleNamespace(id=1)

    monkeypatch.setattr(playbook_store, "open_suggestion", open_suggestion)
    monkeypatch.setattr(app_db, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(check_route, "cheapest", lambda state: None)
    monkeypatch.setattr(check_route, "t19_record", lambda trigger, cheap: {})
    rv = SimpleNamespace(rule_id="T-03", trigger_id="T-03", value=D("0.3537"), threshold=D("0.30"), cmp="ge",
                         beyond=None, approaches=(), carry=None)
    ctx = background.GateContext(SimpleNamespace(values=[rv], results=[], stage_name="Early"), None)
    watched = SimpleNamespace(user_ref="owner", strategy_id=123, body={}, is_system=True,
                              tracked=SimpleNamespace(adjustments_used=BOOKED))
    event = alert_gate.Opened("T-03", AT, 1, D("0.35"), D("0.3537"), None)
    await background.DbGateStore().apply(watched, [event], ctx)
    assert stamped["threshold"] == D("0.3500")
    assert stamped["limit"] == D("0.3000")
    assert stamped["adjustments"] == BOOKED  # the position the record was raised for (#685 item 3)


def test_a_record_reads_its_stored_adjustment_count_and_an_older_one_has_none():
    assert _record(adjustments=BOOKED).adjustments == BOOKED
    assert _record().adjustments is None
    assert _record(adjustments=None).adjustments is None
