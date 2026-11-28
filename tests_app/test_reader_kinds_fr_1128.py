"""Lane FR (28 Nov 2026), item 2 (issue #864, reader half): ``read_tracked`` takes the worker's record of expiry kinds.
A recorded kind for (underlying, nearest expiry) spares the catalogue read; no record or an empty one reads the
catalogue as before. Spec basis: ADR-330 (44), (58); REQ-115 AC-3.
"""
from __future__ import annotations

import datetime

import pytest
import test_background_worker as bw
from ofo_app import adjustment_readers
from ofo_app.adjustment_readers import read_tracked
from sqlalchemy import text
from test_background_worker import app_db_url  # noqa: F401 - the fixture

NEAR = datetime.date(2026, 11, 9)


@pytest.fixture
def catalogue_reads(monkeypatch):
    asked: list[tuple[str, datetime.date]] = []

    async def stored(db, underlying, expiry, **k):
        asked.append((underlying, expiry))
        return "monthly"
    monkeypatch.setattr(adjustment_readers, "stored_kind", stored)
    return asked


async def test_core_a_recorded_kind_makes_no_catalogue_read(app_db_url, monkeypatch, catalogue_reads):  # noqa: F811
    await bw._seeded(app_db_url, monkeypatch)
    sid = await _sid(app_db_url)
    tracked = await read_tracked(sid, None, kinds={("NIFTY", NEAR): "weekly"})
    print("CATALOGUE READS", catalogue_reads)
    assert tracked.position.expiry_kind == "weekly" and catalogue_reads == []


@pytest.mark.parametrize("kinds", [None, {}, {("NIFTY", NEAR): ""}, {("SENSEX", NEAR): "weekly"},
                                   {("NIFTY", datetime.date(2026, 12, 28)): "weekly"}])
async def test_no_record_or_an_empty_one_reads_the_catalogue(app_db_url, monkeypatch, catalogue_reads,  # noqa: F811
                                                             kinds):
    await bw._seeded(app_db_url, monkeypatch)
    sid = await _sid(app_db_url)
    tracked = await read_tracked(sid, None, kinds=kinds)
    assert tracked.position.expiry_kind == "monthly" and len(catalogue_reads) == 1


async def _sid(url) -> int:
    async with url.begin() as conn:
        return (await conn.execute(text("SELECT id FROM public.strategies ORDER BY id DESC LIMIT 1"))).scalar_one()
