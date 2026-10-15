"""Stored exchange freeze limits: load an NSE contract file, read the limit in force (W-076, REQ-054 AC-4, ADR-081).

Basis: ADR-081 "the freeze limit is stored per exchange from the exchange's file, with its date". The file is parsed by
``ofo.instruments.freeze_file`` (header allow-list, V1 underlyings only), joined to the live catalogue on (NSE_FO,
exchange token) with lot, expiry, strike and type cross-checked, and only agreeing rows are stored (append-only; the
migration's guard refuses updates, deletes and a file dated after today on the DATABASE clock, ADR-023). The newest
file date is the limit in force; an older file never replaces a newer limit.

Command: ``python scripts/load_freeze_file.py <NSE_FO_contract_ddmmyyyy.csv.gz>`` (never scheduled here; the daily job
is issue #126's).
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import date
from typing import Any, NamedTuple, TextIO

from sqlalchemy import text

from ofo.execution.freeze import StoredFreeze, freeze_limits_for_plan
from ofo.instruments.freeze_file import Disagreement, match_to_catalogue, parse_freeze_file
from ofo.instruments.models import NSE_FO, InstrumentId
from ofo_app.catalogue_store import load_catalogue

_TODAY_IST = text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date")
_INSERT = text(
    "INSERT INTO public.exchange_freeze_limits (exchange_segment, exchange_token, file_date, freeze_limit, file_name) "
    "VALUES (:segment, :token, :file_date, :limit, :file_name) ON CONFLICT DO NOTHING")
_IN_FORCE = text(
    "SELECT DISTINCT ON (exchange_segment, exchange_token) exchange_segment, exchange_token, file_date, freeze_limit "
    "FROM public.exchange_freeze_limits ORDER BY exchange_segment, exchange_token, file_date DESC")


_SAME_DAY = text(
    "SELECT exchange_token, freeze_limit FROM public.exchange_freeze_limits "
    "WHERE exchange_segment = 'NSE_FO' AND file_date = :file_date")


_STORED_ONE = text(
    "SELECT freeze_limit FROM public.exchange_freeze_limits "
    "WHERE exchange_segment = 'NSE_FO' AND exchange_token = :token AND file_date = :file_date")


class StoredLimit(NamedTuple):
    freeze_limit: int
    file_date: date


class FreezeLoadResult(NamedTuple):
    file_date: date
    inserted: int
    already_stored: int
    not_in_catalogue: int
    disagreements: tuple[Disagreement, ...]


async def limits_in_force(conn: Any) -> dict[InstrumentId, StoredLimit]:
    """The limit with the newest file date for every stored contract."""
    rows = (await conn.execute(_IN_FORCE)).all()
    return {InstrumentId(r.exchange_segment, r.exchange_token): StoredLimit(r.freeze_limit, r.file_date) for r in rows}


async def load_freeze_file(conn: Any, path: str | pathlib.Path, *, nse_name: str | None = None) -> FreezeLoadResult:
    """Parse ``path``, join it to the catalogue and store the agreeing rows. Never commits. Raises ``ValueError`` for
    a bad name or header, a bad value, or a file dated after today on the database clock (nothing written)."""
    parsed = parse_freeze_file(path, nse_name=nse_name)
    today = (await conn.execute(_TODAY_IST)).scalar_one()
    if parsed.file_date > today:
        raise ValueError(f"the file is dated {parsed.file_date}, later than today ({today}) on the database clock")
    join = match_to_catalogue(parsed, await load_catalogue(conn))
    file_name = pathlib.PurePath(nse_name or str(path)).name
    same_day = {r.exchange_token: r.freeze_limit
                for r in (await conn.execute(_SAME_DAY, {"file_date": parsed.file_date})).all()}
    for m in join.matched:
        stored = same_day.get(m.instrument_id.exchange_token)
        if stored is not None and stored != m.freeze_limit:
            raise ValueError(f"token {m.instrument_id.exchange_token}: this file (dated {parsed.file_date}) shows "
                             f"{m.freeze_limit} but {stored} is already stored for that date; nothing written")
    inserted = 0
    async with conn.begin_nested():
        for m in join.matched:
            result = await conn.execute(_INSERT, {
                "segment": NSE_FO, "token": m.instrument_id.exchange_token, "file_date": parsed.file_date,
                "limit": m.freeze_limit, "file_name": file_name})
            if result.rowcount:
                inserted += result.rowcount
                continue
            # Conflict: a concurrent load (or an earlier one) stored this row after the pre-check. Compare, never
            # silently keep the wrong value; the raise rolls back this savepoint (nothing of this file is written).
            stored = (await conn.execute(_STORED_ONE, {
                "token": m.instrument_id.exchange_token, "file_date": parsed.file_date})).scalar_one_or_none()
            if stored is not None and stored != m.freeze_limit:
                raise ValueError(f"token {m.instrument_id.exchange_token}: this file (dated {parsed.file_date}) shows "
                                 f"{m.freeze_limit} but {stored} was stored for that date meanwhile; nothing written")
    return FreezeLoadResult(parsed.file_date, inserted, len(join.matched) - inserted, join.not_in_catalogue,
                            join.disagreements)


async def review_freeze_limits(conn: Any, plan: Any) -> dict[str, StoredFreeze]:
    """The ``freeze_limits`` argument of ``execution_review`` for ``plan``: stored limits by InstrumentId joined to the
    catalogue's Zerodha symbols, lot from the catalogue."""
    return freeze_limits_for_plan(plan, await load_catalogue(conn),
                                  {k: (v.freeze_limit, v.file_date) for k, v in (await limits_in_force(conn)).items()})


def format_result(result: FreezeLoadResult) -> str:
    text_ = (f"freeze limits loaded for file date {result.file_date}: inserted={result.inserted} "
             f"already_stored={result.already_stored} not_in_catalogue={result.not_in_catalogue} "
             f"disagreements={len(result.disagreements)}")
    for d in result.disagreements:
        text_ += f"\n  not stored: token {d.exchange_token} differs from the catalogue in {', '.join(d.fields)}"
    return text_


async def main(path: str, out: TextIO | None = None) -> int:
    from ofo_app.db import close_db, get_engine

    out = out if out is not None else sys.stdout
    try:
        async with get_engine().connect() as conn:
            trans = await conn.begin()
            try:
                result = await load_freeze_file(conn, path)
            except ValueError as exc:
                await trans.rollback()
                print(f"freeze file REFUSED, nothing written: {exc}", file=out)
                return 1
            await trans.commit()
            print(format_result(result), file=out)
            return 0
    finally:
        await close_db()


def run(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/load_freeze_file.py <NSE_FO_contract_ddmmyyyy.csv[.gz]>", file=sys.stderr)
        return 2
    return asyncio.run(main(argv[1]))
