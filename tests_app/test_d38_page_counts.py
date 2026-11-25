"""D-38 (GC-ICLIVE-D): what the plan dialog and the settings page wait on, COUNTED.

The real routes run on a fresh migrated database (ADJ-02 seeded, scenario mode). Only the Kite HTTP transport is a
counting wrapper over the scenario's own transport (as tests_app/test_d36_adjustment_counts.py). Counted per request:
broker calls (GET /user/margins = funds), SQL statements, market reads, tracked reads, registry() builds, and the most
pool connections checked out at a broker call or a market read.

BEFORE the fix (code of 25 Nov, this file's own first run):

    route                          funds  sql  market_reads  tracked_reads  held_at_broker/market
    GET  adjustment-plan (no plan)   1     see BEFORE_PLAN printed line
    GET  settings                    0     see BEFORE_SETTINGS printed line

Run: /root/ofo-db-fresh.sh python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_d38_page_counts.py
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
from dataclasses import dataclass, field

import test_adjustment_check as base
from httpx import ASGITransport, AsyncClient
from ofo_app import adjustment_readers
from ofo_app import db as app_db
from ofo_app import scenario_mode
from sqlalchemy import event

_reset_engine, _seeded = base._reset_engine, base._seeded
app_db_url = base.app_db_url
GOLDEN = pathlib.Path(__file__).resolve().parent / "golden_d38"
OK = 200


@dataclass
class Counts:
    funds: int = 0
    sql: int = 0
    market: int = 0
    tracked: int = 0
    held_in_wait: int = 0
    statements: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _wrap(monkeypatch, counts: Counts) -> None:
    real = scenario_mode.Scenario.margin_transport

    def counting(self, method, url, headers, body):
        with counts.lock:
            counts.funds += 1
            counts.held_in_wait = max(counts.held_in_wait, app_db.get_engine().pool.checkedout())
        return real(self, method, url, headers, body)
    monkeypatch.setattr(scenario_mode.Scenario, "margin_transport", counting)
    real_market, real_tracked = adjustment_readers.read_market, adjustment_readers.read_tracked

    async def market(*a, **k):
        counts.market += 1
        counts.held_in_wait = max(counts.held_in_wait, app_db.get_engine().pool.checkedout())
        return await real_market(*a, **k)

    async def tracked(*a, **k):
        counts.tracked += 1
        return await real_tracked(*a, **k)
    monkeypatch.setattr(adjustment_readers, "read_market", market)
    monkeypatch.setattr(adjustment_readers, "read_tracked", tracked)


async def _get(url: str, counts: Counts):
    from ofo_app.main import create_app  # noqa: PLC0415
    _reset_engine()
    engine = app_db.get_engine()
    event.listen(engine.sync_engine, "before_cursor_execute", lambda c, cur, st, *_a: (setattr(counts, "sql", counts.sql + 1), counts.statements.append(st[:90])))
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(url)
    await app_db.close_db()
    return r.status_code, r.json()


def _golden(name: str, reply: dict) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(reply, indent=1, sort_keys=True) + "\n"
    if os.environ.get("D38_WRITE_GOLDEN") == "1":
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert json.loads(json.dumps(reply, sort_keys=True)) == json.loads(path.read_text(encoding="utf-8")), \
        f"{name}: the reply changed"


async def _plan(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    counts = Counts()
    _wrap(monkeypatch, counts)
    status, body = await _get(f"/api/strategies/{sid}/adjustment-plan", counts)
    return counts, status, body


async def test_plan_counts_and_reply(app_db_url, monkeypatch, capsys):
    counts, status, body = await _plan(app_db_url, monkeypatch)
    assert status == OK, body
    with capsys.disabled():
        print(f"\nD38 PLAN funds={counts.funds} sql={counts.sql} market={counts.market} tracked={counts.tracked} "
              f"held={counts.held_in_wait}", *counts.statements, sep="\n  ")
    _golden("plan", body)


async def test_settings_counts_and_reply(app_db_url, monkeypatch, capsys):
    counts = Counts()
    _wrap(monkeypatch, counts)
    status, body = await _get("/api/settings", counts)
    assert status == OK, body
    with capsys.disabled():
        print(f"\nD38 SETTINGS sql={counts.sql}", *counts.statements, sep="\n  ")
    _golden("settings", body)


# ---- AFTER (Tests first: the targets of the fix, D-38) --------------------------------------------------------
# BEFORE (measured above, 25 Nov code): plan sql=12 funds=1 market=1 held=1; settings sql=5.
# Targets: the plan's broker and market waits hold no database connection; a market read that failed is asked once,
# not again for a figure the route never uses; the settings page asks the database clock once, not twice.
async def test_after_plan_holds_no_connection_in_the_broker_and_market_wait(app_db_url, monkeypatch):
    counts, status, _body = await _plan(app_db_url, monkeypatch)
    assert status == OK
    assert (counts.market, counts.tracked) == (1, 1), "one market read, one strategy read"
    assert counts.held_in_wait == 0, "no database connection is checked out while the broker is waited on"


async def test_after_plan_a_failed_market_read_is_asked_once_and_the_sheet_still_answers(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    counts = Counts()
    _wrap(monkeypatch, counts)

    async def failing(*_a, **_k):
        counts.market += 1
        raise RuntimeError("the market read failed")
    monkeypatch.setattr(adjustment_readers, "read_market", failing)
    status, body = await _get(f"/api/strategies/{sid}/adjustment-plan", counts)
    assert counts.market == 1, "a failed read is not asked a second time (no retry, ADR-016)"
    assert status == OK, body
    assert body["type"] == "ic"


async def test_after_settings_asks_the_database_clock_once(app_db_url, monkeypatch):
    counts = Counts()
    _wrap(monkeypatch, counts)
    status, _body = await _get("/api/settings", counts)
    assert status == OK
    assert counts.sql == 4, counts.statements
    assert sum("clock_timestamp" in s for s in counts.statements) == 1
