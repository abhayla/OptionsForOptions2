"""Lane RA2 item 6 (Lane FD5 "Not done"; ADR-283 (1), FR 3.4): the time of the quote a basket's spot came from is STORED
with the basket's facts (migration 0063, column ``spot_at``), not only carried to the writer.

Real case: the user confirmed a not-live index value at the fill: the order clock is 11:41:00 and the spot 24187.35
was seen at 15:29:58 the day before. Before: the row held the clock and the spot but not that 15:29:58. A basket
stored without a ``spot_at`` keeps NULL, never the order clock. New code on a database not migrated yet still
stores the basket's facts (the rule starting point) through the six-column insert."""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo_app import entry_facts_store as facts
from sqlalchemy import text
from test_paper_routes import db  # noqa: F401 - the rollback fixture
from test_strategy_tracking import _setup

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
CLOCK = datetime.datetime(2026, 10, 8, 11, 41, tzinfo=IST)
SPOT_AT = datetime.datetime(2026, 10, 7, 15, 29, 58, tzinfo=IST)
D = Decimal


async def _stored(db, strategy_id: int, basket_no: int):  # noqa: F811
    return (await db.execute(text("SELECT spot, spot_at, clock FROM public.strategy_basket_facts "
                                  "WHERE strategy_id = :s AND basket_no = :b"),
                             {"s": strategy_id, "b": basket_no})).one()


async def test_core_the_spot_time_is_stored_beside_the_spot(db):  # noqa: F811
    _app, stored, *_ = await _setup(db)
    one = facts.BasketFacts(CLOCK, D("24187.35"), D("14.2"), {("CE", D("24200"), datetime.date(2026, 10, 13), "SELL"):
                                                              D("60.00")}, SPOT_AT)
    await facts.record_basket(db, stored.id, 0, one)
    row = await _stored(db, stored.id, 0)
    assert (row.spot, row.spot_at, row.clock) == (D("24187.35"), SPOT_AT, CLOCK)


async def test_a_basket_without_a_spot_time_keeps_null_never_the_order_clock(db):  # noqa: F811
    _app, stored, *_ = await _setup(db)
    await facts.record_basket(db, stored.id, 1, facts.BasketFacts(CLOCK, D("24187.35"), None, {}))
    row = await _stored(db, stored.id, 1)
    assert row.spot_at is None and row.clock == CLOCK


async def test_the_stored_basket_still_reads_back_for_the_rules(db):  # noqa: F811
    _app, stored, *_ = await _setup(db)
    await facts.record_basket(db, stored.id, 0, facts.BasketFacts(CLOCK, D("24187.35"), D("14.2"), {}, SPOT_AT))
    back = (await facts.read_baskets(db, stored.id))[0]
    assert (back.clock, back.spot, back.atm_iv) == (CLOCK, D("24187.35"), D("14.2"))


async def test_a_database_without_the_column_still_stores_the_basket_facts(db, monkeypatch):  # noqa: F811
    _app, stored, *_ = await _setup(db)
    monkeypatch.setattr(facts, "_INSERT_BASKET_SPOT_AT", text(
        "INSERT INTO public.strategy_basket_facts (strategy_id, basket_no, clock, spot, atm_iv, legs, no_such_column) "
        "VALUES (:strategy_id, :basket_no, :clock, :spot, :atm_iv, CAST(:legs AS JSONB), :spot_at)"))
    await facts.record_basket(db, stored.id, 0, facts.BasketFacts(CLOCK, D("24187.35"), D("14.2"), {}, SPOT_AT))
    row = await _stored(db, stored.id, 0)
    assert (row.spot, row.clock, row.spot_at) == (D("24187.35"), CLOCK, None)
