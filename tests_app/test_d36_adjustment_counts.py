"""D-36 (GC-ICLIVE-D): the adjustment check and the Review adjustment drawer, COUNTED.

Both routes run for real (real readers, real OutcomeMargin, real KiteMargin) on the seeded ADJ-02 iron condor (four
legs, NIFTY) in scenario mode on a fresh migrated database. Only the broker's HTTP transport is replaced by a counting
wrapper over the scenario's own recorded-shape transport (``Scenario.margin_transport``): it records every Kite call
(GET /user/margins = available funds, POST /margins/basket = basket), the most in flight at once, and how many pool
connections are checked out at the moment of a broker call. A SQLAlchemy ``before_cursor_execute`` listener counts
statements. Nothing reaches Kite.

BEFORE the fix (code of 23 Nov, measured by this file; cold margin cache, one request each, ADJ-02 = 15 approaches
asked, 7 with an After leg and a figure, 6 distinct baskets because A-26 and A-27 share one):

    route                         funds basket kite-total SQL  conns held in broker wait  max in flight
    POST adjustment-approaches      7      6      13      12            1                      1
    GET  adjustment-check           2      1       3      20            1                      1

One of the funds calls per request is the regime read (``regime_inputs.in_scenario`` -> ``available_margin``), a
separate reader; the margin reads own 6 (approaches) and 1 (check). Live (23 Nov) had ~15 distinct baskets, so ~30
sequential Kite calls, and the pool (DB_POOL_SIZE=2, no overflow) was held across every one of them.

The replies of both routes for these inputs are the goldens in tests_app/golden_d36/ (recorded BEFORE the fix); the
reply-unchanged tests compare the full JSON, every number and the order, after any change.
Run: /root/ofo-db-fresh.sh python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_d36_adjustment_counts.py
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from dataclasses import dataclass, field

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import db as app_db
from ofo_app import scenario_mode
from sqlalchemy import event
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401 - fixtures and helpers

GOLDEN = pathlib.Path(__file__).resolve().parent / "golden_d36"
SCENARIO = "ADJ-02"
SLEEP = 0.03  # each fake Kite call takes this long, so an overlap shows as in-flight > 1


@dataclass
class Counts:
    funds: int = 0
    basket: int = 0
    sql: int = 0
    held_in_wait: int = 0  # most pool connections checked out at the moment of a broker call
    in_flight: int = 0
    max_in_flight: int = 0
    baskets: list = field(default_factory=list)  # the basket request bodies, in order
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def kite(self) -> int:
        return self.funds + self.basket


def _wrap_transport(monkeypatch, counts: Counts, fail_basket_number: int | None = None) -> None:
    """The counting wrapper over the scenario's transport; ``fail_basket_number`` makes that one basket call a
    Kite network failure (HTTP 503) to prove a failed read stays its own."""
    real = scenario_mode.Scenario.margin_transport

    def counting(self, method, url, headers, body):
        engine = app_db.get_engine()
        with counts.lock:
            counts.in_flight += 1
            counts.max_in_flight = max(counts.max_in_flight, counts.in_flight)
            counts.held_in_wait = max(counts.held_in_wait, engine.pool.checkedout())
            if method == "GET":
                counts.funds += 1
                number = None
            else:
                counts.basket += 1
                counts.baskets.append(body)
                number = counts.basket
        try:
            time.sleep(SLEEP)
            if number is not None and number == fail_basket_number:
                return 503, '{"status": "error", "error_type": "NetworkException"}'
            return real(self, method, url, headers, body)
        finally:
            with counts.lock:
                counts.in_flight -= 1

    monkeypatch.setattr(scenario_mode.Scenario, "margin_transport", counting)


async def _run(method: str, strategy_id: int, counts: Counts, body: dict | None = None):
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    _reset_engine()
    engine = app_db.get_engine()

    def count_sql(*_a):
        counts.sql += 1
    event.listen(engine.sync_engine, "before_cursor_execute", count_sql)
    app = create_app()
    url = f"/api/strategies/{strategy_id}/" + ("adjustment-approaches" if method == "POST" else "adjustment-check")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await (ac.post(url, json=body or {}) if method == "POST" else ac.get(url))
    await app_db.close_db()
    return r.status_code, r.json()


def _clean(reply: dict) -> dict:
    reply = dict(reply)
    reply.pop("timing", None)  # a wall-clock field of the dev reply; the only one
    return json.loads(json.dumps(reply, sort_keys=True))


def _golden(name: str, reply: dict) -> None:
    path = GOLDEN / f"{name}.json"
    if os.environ.get("D36_WRITE_GOLDEN") == "1":
        path.write_text(json.dumps(_clean(reply), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert _clean(reply) == json.loads(path.read_text(encoding="utf-8")), f"{name}: the reply changed"


async def _counted(app_db_url, monkeypatch, method, fail=None):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, SCENARIO)
    counts = Counts()
    _wrap_transport(monkeypatch, counts, fail)
    status, body = await _run(method, sid, counts)
    return counts, status, body


async def test_approaches_counts_and_reply(app_db_url, monkeypatch, capsys):
    counts, status, body = await _counted(app_db_url, monkeypatch, "POST")
    assert status == 200, body
    with capsys.disabled():
        print(f"\nD36 APPROACHES funds={counts.funds} basket={counts.basket} kite={counts.kite} sql={counts.sql} "
              f"held={counts.held_in_wait} max_in_flight={counts.max_in_flight} "
              f"approaches={len(body['approaches'])}")
    _golden("approaches", body)


async def test_check_counts_and_reply(app_db_url, monkeypatch, capsys):
    counts, status, body = await _counted(app_db_url, monkeypatch, "GET")
    assert status == 200, body
    with capsys.disabled():
        print(f"\nD36 CHECK funds={counts.funds} basket={counts.basket} kite={counts.kite} sql={counts.sql} "
              f"held={counts.held_in_wait} max_in_flight={counts.max_in_flight}")
    _golden("check", body)


# ---- AFTER (Tests first: the targets of the fix, D-36) ----------------------------------------------------------
# The margin reads' available-funds figure is read once per request (the regime read is one more, its own reader),
# every basket is still asked once, no connection is held while the broker is waited on, and the independent basket
# reads run together but bounded (the limiter's 10/s and 5 s rules; MAX_TOGETHER below).
MAX_TOGETHER = 4
DISTINCT_BASKETS = 6


async def test_after_approaches_one_funds_read_for_margins_no_connection_held_reads_together(
        app_db_url, monkeypatch):  # noqa: F811
    counts, status, _body = await _counted(app_db_url, monkeypatch, "POST")
    assert status == 200
    assert counts.funds <= 2, "funds: one for the margins (this request) + the regime read"  # noqa: PLR2004
    assert counts.basket == DISTINCT_BASKETS, "a basket asked N times is asked once, none is skipped"
    assert counts.held_in_wait == 0, "no database connection is checked out while the broker is waited on"
    assert 2 <= counts.max_in_flight <= MAX_TOGETHER, "independent reads together, bounded"  # noqa: PLR2004


async def test_after_check_no_connection_held_in_the_broker_wait(app_db_url, monkeypatch):  # noqa: F811
    counts, status, _body = await _counted(app_db_url, monkeypatch, "GET")
    assert status == 200
    assert counts.held_in_wait == 0
    assert (counts.basket, counts.funds) == (1, 2)  # one margin read + the regime read, unchanged


async def test_after_a_failed_basket_read_is_its_own_figure_not_available_no_retry(app_db_url, monkeypatch):  # noqa: F811
    """One basket call fails (HTTP 503 from Kite): that approach says plainly it could not be read, no figure, the
    others keep their golden figures, and the failed basket is not asked again (ADR-016 to ADR-019)."""
    counts, status, body = await _counted(app_db_url, monkeypatch, "POST", fail=3)
    assert status == 200, body
    assert counts.basket == DISTINCT_BASKETS, "no automatic retry"
    golden = {a["id"]: a for a in json.loads((GOLDEN / "approaches.json").read_text(encoding="utf-8"))["approaches"]}
    failed = [a for a in body["approaches"] if (a.get("margin") or {}).get("state") not in
              (None, "stated", "not_needed")]
    assert len(failed) >= 1
    for a in failed:
        assert a["margin"]["value"] is None
        assert "could not be read" in a["margin"]["reason"]
    stated_gold = {i for i, a in golden.items() if (a.get("margin") or {}).get("state") == "stated"}
    for a in body["approaches"]:
        if a not in failed and a["id"] in stated_gold:
            assert a["margin"] == golden[a["id"]]["margin"]
            assert a["after_legs"] == golden[a["id"]]["after_legs"]  # the other figures stay
