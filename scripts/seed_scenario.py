"""seed_scenario.py <ADJ-id>: puts a scenario's iron condor on the Live Strategies screen of the dev app (GC-ADJ1 1b).

Run: ``python scripts/orchestrator/dev_run.py <worktree> python scripts/seed_scenario.py ADJ-02`` (dev_run sets
DATABASE_URL to ofo_dev). Reads ``tests/fixtures/adjust_scenarios/<id>.json`` ``position`` and, through the app's own
stores (``strategy_store.save_draft``, ``paper_store.place``; no raw write SQL), creates ONE paper strategy named
"Scenario <id>" for the owner: the four current legs opened at the scenario's entry prices, and each history leg
opened and exited as the trade was placed (``placement_batches``: one entry batch, one batch per adjustment), so the
booked P&L equals ``position.booked_pnl``.

Refusals (nothing is read or written): APP_ENV set to anything but ``development`` / ``test`` (unset = the app's own
default, development); a DATABASE_URL whose database is not exactly ``ofo_dev``; an id that is not a file in the
fixture folder. Idempotent: a strategy already named "Scenario <id>" for the owner prints its id, changes nothing.
Every answer state of the position: legs absent / empty, a leg whose contract is not in the catalogue, a booked P&L
that does not equal the history's -> refused, nothing written (one transaction).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import pathlib
import re
import sys
from collections.abc import Mapping
from decimal import Decimal

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "adjust_scenarios"
ALLOWED_ENVS = ("development", "test")
DEV_DATABASE = "ofo_dev"
ID_SHAPE = re.compile(r"ADJ-[0-9]{2}[a-e]?")
NAME_PREFIX = "Scenario "
OWNER_REF = "owner"  # routes.broker.V1_OWNER_REF, the one signed-in user of v1


class SeedRefused(Exception):
    pass


def check_environment(env: Mapping[str, str]) -> None:
    app_env = env.get("APP_ENV", "development")
    if app_env not in ALLOWED_ENVS:
        raise SeedRefused(f"REFUSED: APP_ENV is {app_env!r}, not development or test")
    from sqlalchemy.engine import make_url  # noqa: PLC0415
    url = env.get("DATABASE_URL", "")
    try:
        database = make_url(url).database
    except Exception:  # noqa: BLE001 - any unreadable URL is a refusal
        database = None
    if database != DEV_DATABASE:
        raise SeedRefused(f"REFUSED: DATABASE_URL names database {database!r}, not exactly {DEV_DATABASE!r}")


def scenario_path(scenario_id: str) -> pathlib.Path:
    if not ID_SHAPE.fullmatch(scenario_id or ""):
        raise SeedRefused(f"REFUSED: {scenario_id!r} is not a scenario id")
    path = FIXTURES / f"{scenario_id}.json"
    if not path.is_file():
        raise SeedRefused(f"REFUSED: no scenario file {path.name} in {FIXTURES}")
    return path


def strategy_name(scenario_id: str) -> str:
    return f"{NAME_PREFIX}{scenario_id}"


def booked(history: list[dict]) -> Decimal:
    """The history's booked P&L from its entry / exit prices (BUY earns exit - entry, SELL entry - exit)."""
    total = Decimal(0)
    for h in history:
        move = Decimal(h["exit"]) - Decimal(h["entry"])
        total += (move if h["side"] == "BUY" else -move) * int(h["quantity"])
    return total


def placement_batches(position: dict, clock: datetime.datetime) -> list[tuple[datetime.datetime, list[tuple]]]:
    """The trade as it was placed: ONE entry batch at the entry clock (every leg with no ``opened_by``: history legs
    and current legs never adjusted), then ONE batch per adjustment number at ``position.adjustment_times[n]``: that
    adjustment's exits (history legs with ``adjustment`` n, at their exit price) then the legs it opened (history and
    current legs with ``opened_by`` n, at their entry price). Each item is (side, leg, price, kind). A history whose
    adjustment has no time, or times not after the entry clock and increasing, is refused."""
    legs, history = position.get("legs") or [], position.get("history") or []
    times = position.get("adjustment_times") or {}
    numbers = sorted({int(h["adjustment"]) for h in history} | {int(x["opened_by"]) for x in legs + history
                                                                  if "opened_by" in x})
    at = {}
    for n in numbers:
        if str(n) not in times:
            raise SeedRefused(f"REFUSED: adjustment {n} has no time in position.adjustment_times")
        at[n] = datetime.datetime.fromisoformat(times[str(n)])
    if [clock, *(at[n] for n in numbers)] != sorted({clock, *at.values()}):
        raise SeedRefused("REFUSED: adjustment times must be after the entry clock and increasing")
    opp = {"BUY": "SELL", "SELL": "BUY"}
    batches = [(clock, [(x["side"], x, x["entry"], "open") for x in history + legs if "opened_by" not in x])]
    for n in numbers:
        exits = [(opp[h["side"]], h, h["exit"], "exit") for h in history if int(h["adjustment"]) == n]
        opens = [(x["side"], x, x["entry"], "open") for x in history + legs if x.get("opened_by") == n]
        batches.append((at[n], exits + opens))
    return batches


async def _contract_id(conn, leg: dict, underlying: str) -> int:
    from sqlalchemy import text  # noqa: PLC0415
    rows = (await conn.execute(
        text("SELECT id FROM public.catalogue_contracts WHERE name = :name AND instrument_type = :type "
             "AND strike = :strike AND expiry = :expiry AND NOT retired AND NOT delisted"),
        {"name": underlying, "type": leg["type"], "strike": Decimal(leg["strike"]),
         "expiry": datetime.date.fromisoformat(leg["expiry"])})).all()
    if len(rows) != 1:
        raise SeedRefused(f"REFUSED: {len(rows)} live catalogue contracts for {underlying} {leg['strike']} "
                          f"{leg['type']} {leg['expiry']}")
    return int(rows[0][0])


async def seed(scenario_id: str) -> int:
    doc = json.loads(scenario_path(scenario_id).read_text(encoding="utf-8"))
    position = doc.get("position") or {}
    legs, history = position.get("legs") or [], position.get("history") or []
    if not legs:
        raise SeedRefused(f"REFUSED: {scenario_id} has no position legs")
    if booked(history) != Decimal(position.get("booked_pnl", "0")):
        raise SeedRefused(f"REFUSED: {scenario_id} history books {booked(history)}, "
                          f"position.booked_pnl is {position.get('booked_pnl')}")
    clock = datetime.datetime.fromisoformat(doc["position"]["entry"]["clock"])
    underlying = doc.get("underlying", "NIFTY")

    from ofo.engine.legs import Action  # noqa: PLC0415
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from ofo_app import paper_store, strategy_store  # noqa: PLC0415
    from ofo_app.db import close_db, get_sessionmaker  # noqa: PLC0415

    name = strategy_name(scenario_id)
    try:
        async with get_sessionmaker()() as db:
            for found in await strategy_store.list_strategies(db, OWNER_REF):
                if found.name == name:
                    return found.id  # idempotent: change nothing
            choices = [sf.LegChoice(await _contract_id(db, leg, underlying), Action(leg["side"]), int(leg["quantity"]))
                       for leg in legs]
            stored = await strategy_store.save_draft(
                db, OWNER_REF, await strategy_store.build_definition(db, underlying, choices), name)
            orders = []
            for at, batch in placement_batches(position, clock):  # one batch per real placement (REQ-163)
                for side, leg, price, kind in batch:
                    cid = (choices[legs.index(leg)].contract_id if leg in legs
                           else await _contract_id(db, leg, underlying))
                    orders.append(paper_store.NewOrder(cid, side, int(leg["quantity"]), Decimal(price), kind, at))
            await paper_store.place(db, OWNER_REF, stored.id, orders)
            await db.commit()
            return stored.id
    finally:
        await close_db()


def main(argv: list[str]) -> int:
    try:
        if len(argv) != len(("script", "id")):
            raise SeedRefused("usage: seed_scenario.py <ADJ-id>")
        check_environment(os.environ)
        scenario_path(argv[1])
        print(f"{argv[1]} strategy id {asyncio.run(seed(argv[1]))}")
    except SeedRefused as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
