"""W-101: the TEST-ONLY Execute/return replay switch (REQ-073 AC-4; no database, no network).

The switch (``EXECUTE_REPLAY``) is refused at start-up outside ``APP_ENV=test``; off, no override leaks; on, the
Execute and return routes read the recorded 2026-10-16 replies only (nothing here can reach Kite). Expected prices come
from the real recorded depth (asks 3.35 x 56,810: BUY 65 lifts the best ask, ADR-080 (3), by hand) and the real book.
"""
from __future__ import annotations

import ast
import asyncio
import datetime
import os
import subprocess
import sys
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.broker import egress
from ofo.engine import Action
from ofo.instruments import Catalogue
from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execute_plan as ep
from ofo_app import execute_replay as er
from ofo_app import execute_replay_switch as er_switch
from ofo_app import main
from ofo_app import seed_execute_replay as seed
from ofo_app.routes import execute
from starlette.requests import Request

SEAMS = (execute.get_kite_session, execute.get_quote_reader, execute.get_execute_clock, elig.get_eligibility_today)


def _refused_envs() -> list[str]:
    """Every APP_ENV but exactly "test": the named environments plus case, space and suffix variants of "test"."""
    named = ["", "production", "development", "staging"]
    variants = [f("test") for f in (str.upper, str.title, " {}".format, "{} ".format, "{}s".format, "{}ing".format)]
    return named + variants


def _request(path: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "query_string": b""})


def test_ac4_switch_off_installs_no_override(monkeypatch):
    """AC-4: APP_ENV=test without the switch -> the real Kite session, quote reader and clock (no override leaks)."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv(er.ENV_NAME, raising=False)
    app = main.create_app()
    assert not set(SEAMS) & set(app.dependency_overrides)
    for off in ("", "0", "no", "false", "off", "2"):
        monkeypatch.setenv(er.ENV_NAME, off)
        assert er.replay_requested() is False, off
    for on in ("1", "true", "YES", " on "):
        monkeypatch.setenv(er.ENV_NAME, on)
        assert er.replay_requested() is True, on


@pytest.mark.parametrize("env", _refused_envs())
def test_ac4_switch_outside_test_is_refused_at_start_up(monkeypatch, env):
    """AC-4: EXECUTE_REPLAY=1 under any APP_ENV but exactly "test" -> create_app raises; nothing is installed."""
    monkeypatch.setenv(er.ENV_NAME, "1")
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setattr(er, "overrides", lambda: pytest.fail("installed outside APP_ENV=test"))
    with pytest.raises(er.ExecuteReplayRefused):
        main.create_app()


def test_ac4_switch_on_in_test_installs_the_recorded_session_after_the_egress_gate(monkeypatch):
    """AC-4: on + test -> the three seams are overridden; the egress gate is installed first and stays installed."""
    order: list[str] = []
    real_overrides = er.overrides
    monkeypatch.setattr(main._egress, "install", lambda: order.append("egress"))
    monkeypatch.setattr(er, "overrides", lambda: (order.append("replay"), real_overrides())[1])
    monkeypatch.setenv(er.ENV_NAME, "1")
    monkeypatch.setenv("APP_ENV", "test")
    app = main.create_app()
    assert order == ["egress", "replay"]
    assert set(SEAMS) <= set(app.dependency_overrides)
    assert app.dependency_overrides[execute.get_execute_clock]()() == er.AT
    egress.install()
    assert egress.installed()


def test_ac4_execute_reads_the_book_before_the_entry_and_prices_buy_65_at_3_35(monkeypatch):
    """AC-4: Execute's session reads no order today; the frame depth prices BUY 65 NIFTY26O1923650CE at 3.35 (the
    recorded best ask, 56,810 >= 65); the basket api_key is the fixed test value."""
    monkeypatch.setenv(er.ENV_NAME, "1")
    monkeypatch.setenv("APP_ENV", "test")
    app = main.create_app()
    session = app.dependency_overrides[execute.get_kite_session](_request("/strategies/1/execute"))
    assert session.api_key == "kitekey" and session.reads.fetch_orders() == []
    quotes = app.dependency_overrides[execute.get_quote_reader]()
    cat = Catalogue()
    cat.load([er.listed_contract()])
    priced = ep.price_legs("1", "NIFTY", [ep.LegToPrice(er.CORE_ID, Action.BUY, 65, None)], cat, quotes.leg_quote)
    (leg,) = priced.plan.legs
    assert (leg.contract, leg.leg.action, leg.leg.quantity, leg.leg.entry_price) == (
        "NIFTY26O1923650CE", Action.BUY, 65, D("3.35"))
    assert priced.quote_times == (datetime.datetime(2026, 10, 16, 15, 7, 20, tzinfo=er.AT.tzinfo),)
    assert quotes.leg_quote(er.CORE_ID, "1") is None  # any other contract has no quote: refused, never invented


def test_ac4_return_reads_the_122104_book_and_refuses_every_write():
    """AC-4: the return's session reads OFS1V1L0 COMPLETE 65 and its trade; any non-GET (an order) raises."""
    session = er._replay_session(_request("/strategies/1/execution/return"))
    (order,) = session.reads.fetch_orders()
    assert (order["tag"], order["status"], order["filled_quantity"]) == ("OFS1V1L0", "COMPLETE", 65)
    assert len(session.reads.fetch_trades()) == 1
    for url in ("https://api.kite.trade/orders/regular", "https://api.kite.trade/orders"):
        with pytest.raises(AssertionError):
            er.return_replay()("POST", url, {}, "x")  # /orders would otherwise answer
    assert er.entry_replay()("POST", "https://api.kite.trade/margins/basket", {}, "x")[0] == 200


ALLOWED_IMPORT_ROOTS = {"__future__", "datetime", "json", "os", "pathlib", "decimal", "typing", "fastapi", "ofo",
                        "ofo_app", "sqlalchemy", "asyncio", "sys", "collections", "dataclasses", "functools"}


@pytest.mark.parametrize("module", [er, seed, er_switch])
def test_ac4_replay_modules_import_no_network_client(module):
    """AC-4: an allow-list of import roots: anything else (an HTTP client, a socket) fails this test."""
    with open(module.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= ALLOWED_IMPORT_ROOTS, roots - ALLOWED_IMPORT_ROOTS


@pytest.mark.parametrize("env", _refused_envs())
def test_ac4_seed_refuses_outside_test(monkeypatch, env):
    """AC-4: the seed command refuses outside APP_ENV=test before any connection is opened."""
    monkeypatch.setenv("APP_ENV", env)
    from ofo_app import db  # noqa: PLC0415

    monkeypatch.setattr(db, "get_engine", lambda: pytest.fail("connected outside APP_ENV=test"))
    with pytest.raises(er.ExecuteReplayRefused):
        asyncio.run(seed.main())
    with pytest.raises(er.ExecuteReplayRefused):
        asyncio.run(seed.seed(None, env))


class _Conn:
    def __init__(self, held):
        self.held, self.sql = held, []

    async def execute(self, sql, params=None):
        self.sql.append(str(sql))
        return SimpleNamespace(first=lambda: self.held)


def test_ac4_seed_is_idempotent_and_never_takes_another_users_strategy_one(monkeypatch):
    """AC-4: strategy 1 already the owner's -> nothing written; someone else's -> refused; only ofo_test is seeded."""
    monkeypatch.setattr(er, "store_strategy_one", lambda *a, **k: pytest.fail("wrote on a re-run"))
    mine = _Conn(("owner",))
    assert asyncio.run(seed.seed(mine, "test")) is False and len(mine.sql) == 1
    with pytest.raises(seed.SeedRefused):
        asyncio.run(seed.seed(_Conn(("someone",)), "test"))
    for other in ("ofo_dev", "ofo_test2", "postgres", "OFO_TEST", ""):
        with pytest.raises(seed.SeedRefused):
            seed.check_database(f"postgresql+asyncpg://localhost:5432/{other}")
    seed.check_database("postgresql+asyncpg://localhost:5432/ofo_test")


def test_ac4_a_frame_without_the_contracts_depth_is_refused_never_invented(monkeypatch, tmp_path):
    """AC-4: no depth for the replay contract in the recorded frame -> the replay refuses (no made-up quote)."""
    empty = tmp_path / "no-frame.bin"
    empty.write_bytes(b"\x00\x00")  # a Kite binary message holding 0 packets
    monkeypatch.setattr(er, "DEPTH_FRAME", empty)
    with pytest.raises(er.ExecuteReplayRefused):
        er.frame_quote()


def test_ac4_the_return_judges_today_on_the_database_clock_and_execute_keeps_the_pin(monkeypatch):
    """AC-4 (W-101 review MAJOR 1): with the pin at 2026-10-16, the return's "today" is the database clock's India date
    (2026-11-03 18:45 UTC = 2026-11-04 00:15 IST, by hand), the date that stamped plan 1; Execute keeps the pin."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")

    async def _db_now(conn):
        return datetime.datetime(2026, 11, 3, 18, 45, tzinfo=datetime.UTC)

    monkeypatch.setattr(elig, "database_now", _db_now)
    back = er._today_reader(_request("/strategies/1/execution/return"))
    assert asyncio.run(back(None)) == datetime.date(2026, 11, 4)
    entry = er._today_reader(_request("/strategies/1/execute"))
    assert asyncio.run(entry(None)) == datetime.date(2026, 10, 16)


_NO_FIXTURES = """
import os, pathlib, sys
real_text, real_bytes = pathlib.Path.read_text, pathlib.Path.read_bytes
def _guard(real):
    def read(self, *a, **k):
        if "fixtures" in pathlib.Path(self).parts:
            raise OSError(f"test fixture read at import: {self}")
        return real(self, *a, **k)
    return read
pathlib.Path.read_text, pathlib.Path.read_bytes = _guard(real_text), _guard(real_bytes)
from ofo_app import main
assert "ofo_app.execute_replay" not in sys.modules, "create_app's module imported the replay"
main.create_app()
os.environ["EXECUTE_REPLAY"] = "1"
os.environ["APP_ENV"] = "production"
try:
    main.create_app()
except Exception as exc:
    assert type(exc).__name__ == "ExecuteReplayRefused", exc
else:
    raise AssertionError("not refused")
assert "ofo_app.execute_replay" not in sys.modules, "the replay was imported before the refusal"
import ofo_app.execute_replay
print("OK")
"""


def test_ac4_production_start_up_reads_no_test_fixture_and_refuses_before_importing_the_replay():
    """AC-4 (W-101 review MAJOR 2): with every tests/fixtures read failing, importing ofo_app.main, building the app
    and even importing ofo_app.execute_replay succeed; the refusal comes before the replay module is imported."""
    env = {k: v for k, v in os.environ.items() if k not in {"EXECUTE_REPLAY", "OUTCOME_REPLAY", "APP_ENV"}}
    env["PYTHONPATH"] = os.pathsep.join([str(pathlib_backend()), env.get("PYTHONPATH", "")])
    run = subprocess.run([sys.executable, "-c", _NO_FIXTURES], env=env,  # noqa: S603 - our own interpreter
                         capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0 and run.stdout.strip().endswith("OK"), run.stderr[-2000:]


def pathlib_backend():
    import pathlib  # noqa: PLC0415

    return pathlib.Path(er.__file__).resolve().parent.parent
