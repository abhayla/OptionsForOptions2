"""Route profile harness (REQ-049 AC-4; Lane Q1). NOT collected by default (no ``test_`` file prefix), skipped
unless OFO_PERF=1. Run one file, real PostgreSQL, the app's real routes:

    OFO_PERF=1 python -m pytest -c pytest-app.ini tests_app/perf_route_profile.py -q -s

Book: 10 paper strategies from the scenario library (ADJ-01 with its plan, the system iron condor playbook copy; ADJ-02
.. ADJ-10 without). The scenario mode serves instant, fresh quotes through the app's own seams (price reads are free
here). The BROKER MARGIN transport is wrapped: every call counts, and each sleeps ASSUMED_BROKER_ROUND_TRIP seconds (an
ASSUMPTION, not a measurement: the count of calls is the finding). Each route: 1 warm-up then RUNS runs, margin cache
warm (the app's own plan-keyed cache, as production) and again with that cache cleared before every run (cold).
Writes the table to the path in OFO_PERF_OUT (default: stdout only).
"""
from __future__ import annotations

import collections
import logging
import os
import re
import statistics
import time

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import adjustment_check as check
from ofo_app import db as app_db
from ofo_app import scenario_mode
from ofo_app.routes import adjustment_check as route_check
from ofo_app.routes import outcome
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401
from test_plan_watch import _arm

pytestmark = pytest.mark.skipif(os.environ.get("OFO_PERF") != "1", reason="measurement harness: set OFO_PERF=1")

ASSUMED_BROKER_ROUND_TRIP = 0.5  # seconds; an assumption, labelled in the output
RUNS = 5
LINE = re.compile(r"request (\w+) (\S+) (\d+) ([\d.]+)ms(?: db=([\d.]+)ms/(\d+)q)?(?: price=([\d.]+)ms)?"
                  r"(?: margin=([\d.]+)ms)?(?: compute=([\d.]+)ms)?")


class _Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _med(xs):
    return statistics.median(xs) if xs else 0.0


async def test_profile(app_db_url, monkeypatch):  # noqa: F811, PLR0915, C901
    # ---- the book
    for n in range(10, 1, -1):
        await _seeded(app_db_url, monkeypatch, f"ADJ-{n:02d}", plan=False)
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")  # last: the active scenario of the app below
    await _arm(app_db_url, sid)
    async with app_db_url.connect() as conn:
        from sqlalchemy import text  # noqa: PLC0415
        n_strats = (await conn.execute(text("select count(*) from strategies"))).scalar()

    # ---- counters: broker margin calls, run_check / state_of / evaluate_stored calls
    calls = collections.Counter()
    real_transport = scenario_mode.Scenario.margin_transport

    def counting_transport(self, method, url, headers, body):
        calls["broker_funds" if method == "GET" else "broker_basket"] += 1
        time.sleep(ASSUMED_BROKER_ROUND_TRIP)  # runs in a worker thread (asyncio.to_thread)
        return real_transport(self, method, url, headers, body)

    monkeypatch.setattr(scenario_mode.Scenario, "margin_transport", counting_transport)

    def counted(name, fn, async_=False):
        if async_:
            async def w(*a, **k):
                calls[name] += 1
                return await fn(*a, **k)
        else:
            def w(*a, **k):
                calls[name] += 1
                return fn(*a, **k)
        return w
    monkeypatch.setattr(route_check, "run_check", counted("run_check", route_check.run_check, True))
    from ofo_app.routes import plan_watch  # noqa: PLC0415
    monkeypatch.setattr(plan_watch, "run_check", route_check.run_check)
    monkeypatch.setattr(check, "state_of", counted("state_of", check.state_of))
    monkeypatch.setattr(check, "evaluate_stored", counted("evaluate_stored", check.evaluate_stored, True))

    # ---- the app, ONE for all runs; the positions route gets an empty broker book through its own seam
    from ofo_app.kite_reads import KiteReads  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes import execute as exec_route  # noqa: PLC0415
    _reset_engine()
    app = create_app()

    def empty_book(method, url, headers, body):
        import json as _j  # noqa: PLC0415
        return 200, _j.dumps({"status": "success", "data": {"net": [], "day": []} if url.endswith("positions") else []})

    class _S:
        api_key = "k"
        reads = KiteReads(api_key="k", access_token="t", transport=empty_book)  # noqa: S106
        margin = None
    app.dependency_overrides[exec_route.get_kite_session] = _S
    margin_source = app.dependency_overrides[outcome.get_margin_source]()

    statements: list[str] = []
    from sqlalchemy import event  # noqa: PLC0415
    event.listen(app_db.get_engine().sync_engine, "before_cursor_execute",
                 lambda _c, _cur, st, *_rest: statements.append(" ".join(st.split())))
    handler = _Lines()
    logging.getLogger("ofo_app.request").addHandler(handler)

    routes = [
        ("plan-watch", f"/api/strategies/{sid}/plan-watch"),
        ("adjustment-plan", f"/api/strategies/{sid}/adjustment-plan"),
        ("adjustment-plan/levels", f"/api/strategies/{sid}/adjustment-plan/levels"),
        ("adjustment-check", f"/api/strategies/{sid}/adjustment-check"),
        ("positions", "/positions"),
        ("paper/strategies/{id}", f"/paper/strategies/{sid}"),
    ]
    out = [f"book: {n_strats} strategies; ADJ-01 id={sid}; assumed broker round-trip {ASSUMED_BROKER_ROUND_TRIP}s "
           f"(assumption); {RUNS} runs after 1 warm-up", ""]
    out.append("route | cache | total ms med/max | db ms med/max | queries | price ms | margin ms med/max | "
               "broker margin calls (funds+basket) | run_check/state_of/evaluate | compute ms med")
    all_statements: dict[str, list[list[str]]] = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for label, url in routes:
            for cache in ("warm", "cold"):
                rows = []
                for i in range(RUNS + 1):
                    if cache == "cold":
                        margin_source._cache.clear()
                    calls.clear()
                    statements.clear()
                    handler.lines.clear()
                    r = await ac.get(url)
                    assert r.status_code == 200, (url, r.status_code, r.text[:300])  # noqa: PLR2004
                    m = LINE.match(handler.lines[-1])
                    assert m, handler.lines
                    if i:  # the first is the warm-up
                        f = [float(x) if x else 0.0 for x in m.groups()[3:]]
                        rows.append((*f, dict(calls), list(statements)))
                total, db, q, price, margin, compute = ([x[k] for x in rows] for k in range(6))
                c = rows[-1][6]
                out.append(f"{label} | {cache} | {_med(total):.1f}/{max(total):.1f} | {_med(db):.1f}/{max(db):.1f} | "
                           f"{int(_med(q))} | {_med(price):.1f} | {_med(margin):.1f}/{max(margin):.1f} | "
                           f"{c.get('broker_funds', 0)}+{c.get('broker_basket', 0)} | "
                           f"{c.get('run_check', 0)}/{c.get('state_of', 0)}/{c.get('evaluate_stored', 0)} | "
                           f"{_med(compute):.1f}")
                if cache == "warm":
                    all_statements[label] = [rows[-1][7]]
        if os.environ.get("OFO_PERF_PROFILE"):  # one warm request per route under cProfile, top 22 by cumulative time
            import cProfile  # noqa: PLC0415
            import io  # noqa: PLC0415
            import pstats  # noqa: PLC0415
            for label, url in routes[:6]:
                prof = cProfile.Profile()
                prof.enable()
                await ac.get(url)
                prof.disable()
                buf = io.StringIO()
                pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(r"ofo", 22)
                out += ["", f"## cProfile {label} (own code, cumulative)", buf.getvalue()[-3500:]]
    logging.getLogger("ofo_app.request").removeHandler(handler)
    out += ["", "repeated statements per route (last warm run; count x text[:150])"]
    for label, runs in all_statements.items():
        cnt = collections.Counter(runs[0])
        out.append(f"## {label}: {len(runs[0])} statements, {len(cnt)} distinct")
        out += [f"  {n}x {s[:150]}" for s, n in cnt.most_common(8) if n > 1]
    text_out = "\n".join(out)
    print("\n" + text_out)
    if os.environ.get("OFO_PERF_OUT"):
        with open(os.environ["OFO_PERF_OUT"], "w", encoding="utf-8") as fh:  # noqa: ASYNC230
            fh.write(text_out + "\n")
    await app_db.close_db()


async def test_concurrency(app_db_url, monkeypatch):  # noqa: F811, C901
    """Q1 phase 2 step 1: N concurrent plan-watch (one per strategy) + N concurrent adjustment-check through ONE app
    instance (ASGITransport, asyncio.gather); instant price, warm margin. Median / max per request (the request log's
    own total ms). Every strategy has its plan; the app's active scenario is the last one seeded (ADJ-01)."""
    import asyncio  # noqa: PLC0415
    http_ok = 200
    ids = []
    for _ in range(10):  # ten strategies of the ONE active scenario (another scenario's strategy is refused)
        ids.append(await _seeded(app_db_url, monkeypatch, "ADJ-01"))  # noqa: PERF401 - awaits in order
    for sid in ids:
        await _arm(app_db_url, sid)
    from ofo_app.kite_reads import KiteReads  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes import execute as exec_route  # noqa: PLC0415
    _reset_engine()
    app = create_app()

    def empty_book(method, url, headers, body):
        import json as _j  # noqa: PLC0415
        return 200, _j.dumps({"status": "success", "data": {"net": [], "day": []} if url.endswith("positions") else []})

    class _S:
        api_key = "k"
        reads = KiteReads(api_key="k", access_token="t", transport=empty_book)  # noqa: S106
        margin = None
    app.dependency_overrides[exec_route.get_kite_session] = _S
    handler = _Lines()
    logging.getLogger("ofo_app.request").addHandler(handler)
    out = ["concurrency (instant price, warm margin; ms from the request log line, median/max per request)",
           "n | route | sequential med | concurrent med/max | wall ms for the batch"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        async def one(path):
            r = await ac.get(path)
            if r.status_code != http_ok:
                print("NON200", path, r.status_code, r.text[:300])
            return r.status_code

        for kind in ("plan-watch", "adjustment-check"):
            for sid in ids:  # warm: margin cache, imports
                assert await one(f"/api/strategies/{sid}/{kind}") == 200  # noqa: PLR2004
        for n in (10, 20):
            for kind in ("plan-watch", "adjustment-check"):
                paths = [f"/api/strategies/{ids[i % len(ids)]}/{kind}" for i in range(n)]
                handler.lines.clear()
                for p in paths[:5]:
                    await one(p)
                seq = [float(LINE.match(x).group(4)) for x in handler.lines]
                handler.lines.clear()
                t0 = time.perf_counter()
                codes = await asyncio.gather(*[one(p) for p in paths])
                wall = (time.perf_counter() - t0) * 1000.0
                assert set(codes) == {200}, codes
                conc = [float(LINE.match(x).group(4)) for x in handler.lines]
                out.append(f"{n} | {kind} | {_med(seq):.1f} | {_med(conc):.1f}/{max(conc):.1f} | {wall:.0f}")
    logging.getLogger("ofo_app.request").removeHandler(handler)
    text_out = "\n".join(out)
    print("\n" + text_out)
    if os.environ.get("OFO_PERF_CONC_OUT"):
        with open(os.environ["OFO_PERF_CONC_OUT"], "w", encoding="utf-8") as fh:  # noqa: ASYNC230
            fh.write(text_out + "\n")
    await app_db.close_db()
