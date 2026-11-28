"""Lane Q3 helpers: the plan-stop chain with the worker as a SEPARATE OS process on a real PostgreSQL database.

``python -m ofo_app.background`` with ``OFO_SCENARIO=PATH-nn`` and ``APP_ENV=test`` is the product's own scenario worker
(``background._serve_scenario``): the scenario's recorded prices, the scenario's own clock (a market minute), the real
gate and the real store. The test writes the frame index (``scenario_mode.write_frame``), the worker moves its
clock and prices to that frame at its next cycle, and the test reads the alert rows back from the database. Nothing here
is a product seam: no file under backend/ or frontend/ is touched.
"""
from __future__ import annotations

import asyncio
import copy
import datetime
import importlib.util
import os
import pathlib
import subprocess
import sys
import time

from _scenario_catalogue import load_library
from conftest import _admin_run, _db_name, _with_db, clone_for_file
from ofo_app import db as app_db
from ofo_app import playbook_store, scenario_mode, strategy_alert_style_store
from ofo_app.config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)

SETTLE_SECONDS = 7  # after a frame is written: the worker wakes about once a second and checks at its next cycle
START_TIMEOUT = 90


def reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


def make_database() -> tuple[str, str]:
    """A private copy of the file's database for ONE case (so no other case's strategy or alert is there): returns its
    (app URL, admin URL). The file's own copy is the template (``conftest._fresh_database_per_file``)."""
    admin, app = os.environ["TEST_ADMIN_DATABASE_URL"], os.environ["TEST_DATABASE_URL"]
    name = clone_for_file(admin, app)
    return _with_db(app, name), _with_db(admin, name)


def drop_database(app_url: str, admin_url: str) -> None:
    template_admin = os.environ["TEST_ADMIN_DATABASE_URL"]
    _admin_run(template_admin, [f'DROP DATABASE IF EXISTS "{_db_name(app_url)}" WITH (FORCE)'])


def scenario_time(path_id: str, frame: int) -> datetime.datetime:
    """The clock of a frame (the scenario's own minute), for orders the test places at that minute."""
    return datetime.datetime.fromisoformat(scenario_mode.read(path_id, frame)["clock"]["ist"])


class Chain:
    """One case: a private database, one seeded paper iron condor on a PATH scenario, one worker process."""

    def __init__(self, path_id: str, app_url: str, tmp: pathlib.Path):
        self.path_id, self.app_url, self.tmp = path_id, app_url, tmp
        self.engine = create_async_engine(app_url)
        self.sid = 0
        self.proc: subprocess.Popen | None = None
        self.log_path = tmp / f"worker-{path_id}.log"
        self.frame = -1
        self.orders_at_start = 0

    # ---- set up -------------------------------------------------------------------------------------------------
    async def seed(self, monkeypatch, *, plan: bool = True, pin: str = "intraday") -> int:
        monkeypatch.setenv("DATABASE_URL", self.app_url)
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("OFO_SCENARIO", self.path_id)
        monkeypatch.setenv("DB_POOL_SIZE", "2")
        monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
        reset_engine()
        await load_library(self.engine)
        self.sid = await seed_mod.seed(self.path_id)
        reset_engine()
        async with self.engine.begin() as conn:
            await strategy_alert_style_store.set_pin(conn, "owner", self.sid, pin)
        if plan:
            await self.type_plan()
        self.orders_at_start = await self.orders_count()
        return self.sid

    async def type_plan(self, *, guards: dict | None = None, t06_percent: str | None = None,
                        time_exit: str | None = None, keep: tuple[str, ...] | None = (),
                        t06_stages: list[str] | None = None) -> None:
        """What the plan sheet saves: a copy of the system iron condor playbook with the typed guards (ADR-330 (5)).
        ``keep``: the body rules left ON (default none, so only the typed stop can raise an alert and every row read
        back is the case's own); None = the whole system rule list."""
        async with self.engine.begin() as conn:
            system = await playbook_store.active_for(conn, "owner", "ic")
            body = copy.deepcopy(system.body)
            body.setdefault("guards", {}).update(guards or {})
            if keep is not None:
                body["rules"] = [r for r in body["rules"] if r["id"] in keep]
            if t06_percent is not None:  # "Loss reaches this % of max loss": the same value for every stage
                for key in ("weekly", "monthly"):
                    body["triggers"]["T-06"][key] = [t06_percent] * len(body["triggers"]["T-06"][key])
            if t06_stages is not None:  # the PC's #207 shape: a per-stage row, e.g. [50, 5, 40]
                body["triggers"]["T-06"]["weekly"] = list(t06_stages)
                body["triggers"]["T-06"]["on"] = True
            if time_exit is not None:
                body["guards"]["time_exit"] = {"at": time_exit, "on": "2026-11-06"}
                if not any(r["id"] == "T-10b" for r in body["rules"]):
                    body["rules"].append({"id": "T-10b", "any_of": ["T-10b"]})
            await playbook_store.accept_plan(conn, "owner", self.sid, system.id, body)

    # ---- the worker process ---------------------------------------------------------------------------------------
    def start_worker(self) -> None:
        env = dict(os.environ, DATABASE_URL=self.app_url, APP_ENV="test", OFO_SCENARIO=self.path_id,
                   DB_POOL_SIZE="2", DB_MAX_OVERFLOW="0", PYTHONUNBUFFERED="1")
        for name in ("TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL"):
            env.pop(name, None)
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "backend"), env.get("PYTHONPATH", "")])
        self.proc = subprocess.Popen([sys.executable, "-m", "ofo_app.background"], env=env, cwd=str(ROOT),
                                     stdout=open(self.log_path, "w"),  # noqa: SIM115
                                     stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError("the worker process ended at start-up:\n" + self.log()[-1500:])
            if "strategies monitored" in self.log():
                return
            time.sleep(0.5)
        raise AssertionError("the worker process did not start in time:\n" + self.log()[-1500:])

    def stop_worker(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def log(self) -> str:
        return self.log_path.read_text(errors="replace") if self.log_path.exists() else ""

    # ---- frames and rows ------------------------------------------------------------------------------------------
    async def go_to(self, frame: int, settle: float = SETTLE_SECONDS) -> None:
        """Writes the shared frame index and gives the worker process its next cycles to move there and check."""
        async with self.engine.begin() as conn:
            await scenario_mode.write_frame(conn, self.path_id, frame)
        self.frame = frame
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise AssertionError("the worker process ended:\n" + self.log()[-1500:])
            await asyncio.sleep(0.5)

    async def wait_for_alert(self, kind: str, wait_seconds: float = 30) -> bool:
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if await self.alerts(kind):
                return True
            await asyncio.sleep(1)
        return False

    async def alerts(self, kind: str | None = None) -> list[dict]:
        """Every alert row of the strategy (oldest first), as dicts: rule, kind, threshold, value, outcome, answer."""
        sql = ("SELECT rule_id, kind, trigger_id, threshold, value, outcome, answer, shown_at "
               "FROM public.adjustment_suggestions WHERE strategy_id = :s ORDER BY id")
        async with self.engine.connect() as conn:
            rows = (await conn.execute(text(sql), {"s": self.sid})).mappings().all()
        return [dict(r) for r in rows if kind is None or r["kind"] == kind]

    async def plan_alerts(self) -> list[dict]:
        """The rows of the PLAN's own exits (kinds ``plan_*``); the situation row ``sit.S-02`` (guidance on a net delta)
        shows on most paths and is not what a case is about."""
        return [r for r in await self.alerts() if str(r["kind"]).startswith("plan_")]

    async def legs(self) -> list[tuple[int, str, int, object]]:
        """(contract id, side, quantity, price) of each leg's opening order."""
        async with self.engine.connect() as conn:
            rows = (await conn.execute(text("SELECT contract_id, side, quantity, price FROM public.paper_orders "
                                            "WHERE strategy_id = :s ORDER BY id"), {"s": self.sid})).all()
        return [tuple(r) for r in rows]

    async def orders_count(self) -> int:
        async with self.engine.connect() as conn:
            return int((await conn.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s"),
                                           {"s": self.sid})).scalar_one())

    async def close(self) -> None:
        self.stop_worker()
        await self.engine.dispose()
        await app_db.close_db()
        reset_engine()
        scenario_mode._loaded.clear()

    async def alert_at_once(self, kind: str, *, next_frame: int | None = None, wait_seconds: float = 20) -> list[dict]:
        """The alert row of ``rule_id`` must be there at THIS frame's check (ADR-330 (47): the plan's own exits alert on
        the first check past their level). A row that comes only at the next frame (the candle close) is a failure
        that says so: read back from the database, with the worker's log tail."""
        if await self.wait_for_alert(kind, wait_seconds):
            return await self.alerts(kind)
        late = None
        if next_frame is not None:
            await self.go_to(next_frame)
            await self.wait_for_alert(kind, 20)
            late = await self.alerts(kind)
        raise AssertionError(f"no {kind} row at frame {self.frame if next_frame is None else next_frame - 1}'s check; "
                             f"rows then: {[(r['rule_id'], r['kind']) for r in await self.alerts()]}; "
                             f"{'it came one frame later: ' + str(late) if late else 'not at the next frame either'}"
                             f"\n{self.log()[-1500:]}")
