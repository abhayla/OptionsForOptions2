"""W-068 step 4: `python -m ofo_app.catalogue_load` (REQ-053 AC-2, ADR-058/059; REQ-035 AC-8 needs contracts to pick).

Spec basis: the command downloads, parses and calls the existing guarded ``apply_update`` unchanged; the ADR-058 admin
setting ``CATALOGUE_MAX_DELIST_PERCENT`` is read from ``Settings`` and passed on (issue #126, the "read the setting"
part only: the Notifier alert and audit record for a refusal are not built here).

The fixture is the real-instrument slice. ``as_of`` is fixed so the slice's expiries are ahead; every test runs in a
transaction that is rolled back, so public.catalogue_contracts stays empty.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ofo_app import catalogue_load
from ofo_app.config import Settings

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 9, 28, 10, 0, tzinfo=IST)
SLICE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "instruments" / "instruments_slice.csv"
TABLE = "public.catalogue_contracts"


def _settings(percent: str) -> Settings:
    return Settings(DATABASE_URL="postgresql+asyncpg://unused", CATALOGUE_MAX_DELIST_PERCENT=Decimal(percent))


def _csv() -> str:
    return SLICE.read_text(encoding="utf-8")


def _lines_where(csv_text: str, **want: str) -> list[str]:
    columns = {"name": 3, "expiry": 5, "type": 9}
    return [line for line in csv_text.splitlines()
            if all(line.split(",")[columns[k]] == v for k, v in want.items())]


def _without_one_nifty_call(csv_text: str) -> str:
    dropped = _lines_where(csv_text, name="NIFTY", expiry="2026-09-29", type="CE")[0]
    kept = csv_text.splitlines(True)
    kept.remove(dropped + "\n") if (dropped + "\n") in kept else kept.remove(dropped)
    return "".join(kept)


async def _count(conn) -> int:
    return (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one()


async def test_load_prints_the_counts_and_writes_the_slice(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            out = io.StringIO()
            assert await catalogue_load.run(conn, _csv(), _settings("10"), out, as_of=AS_OF) == 0
            stored = await _count(conn)
            assert stored > 1000
            assert out.getvalue().startswith(f"catalogue updated: added={stored} seen=0 ")
            assert "delisted=0" in out.getvalue()
        finally:
            await trans.rollback()


async def test_a_setting_of_zero_refuses_a_one_contract_delisting_and_writes_nothing(app_engine: AsyncEngine) -> None:
    shorter = _without_one_nifty_call(_csv())
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await catalogue_load.run(conn, _csv(), _settings("10"), io.StringIO(), as_of=AS_OF)
            before = (await conn.execute(text(
                f"SELECT count(*), count(*) FILTER (WHERE delisted), count(*) FILTER (WHERE currently_listed) "
                f"FROM {TABLE}"))).one()
            out = io.StringIO()
            code = await catalogue_load.run(conn, shorter, _settings("0"), out, as_of=AS_OF)
            assert code == 1 and "REFUSED, nothing written" in out.getvalue(), out.getvalue()
            after = (await conn.execute(text(
                f"SELECT count(*), count(*) FILTER (WHERE delisted), count(*) FILTER (WHERE currently_listed) "
                f"FROM {TABLE}"))).one()
            assert tuple(after) == tuple(before) and before[1] == 0
            # the same list under the default setting (10%) is one delisting of ~290 NIFTY contracts: accepted
            out = io.StringIO()
            assert await catalogue_load.run(conn, shorter, _settings("10"), out, as_of=AS_OF) == 0
            assert "delisted=1" in out.getvalue(), out.getvalue()
        finally:
            await trans.rollback()


async def test_the_setting_reaches_apply_update(app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    real = catalogue_load.apply_update

    async def spy(conn, rows, **kwargs):
        seen.update(kwargs)
        return await real(conn, rows, **kwargs)

    monkeypatch.setattr(catalogue_load, "apply_update", spy)
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await catalogue_load.run(conn, _csv(), _settings("25"), io.StringIO(), as_of=AS_OF)
            assert seen["max_delist_percent"] == Decimal("25") and seen["as_of"] == AS_OF
        finally:
            await trans.rollback()


def test_the_default_setting_is_the_adr_058_ten_percent() -> None:
    assert Settings(DATABASE_URL="postgresql+asyncpg://unused").CATALOGUE_MAX_DELIST_PERCENT == Decimal("10")


async def test_an_unparseable_row_stops_the_load_naming_it_and_writes_nothing(app_engine: AsyncEngine) -> None:
    lines = _csv().splitlines(True)
    victim = _lines_where(_csv(), name="NIFTY", expiry="2026-10-06", type="PE")[0]
    fields = victim.split(",")
    fields[6] = "not-a-number"
    lines[lines.index(victim + "\n")] = ",".join(fields) + "\n"
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            out = io.StringIO()
            assert await catalogue_load.run(conn, "".join(lines), _settings("10"), out, as_of=AS_OF) == 1
            assert "REFUSED, nothing written" in out.getvalue() and fields[2] in out.getvalue()
            assert await _count(conn) == 0
        finally:
            await trans.rollback()


def test_the_command_is_runnable_as_a_module() -> None:
    assert callable(catalogue_load.main) and catalogue_load.__name__ == "ofo_app.catalogue_load"
