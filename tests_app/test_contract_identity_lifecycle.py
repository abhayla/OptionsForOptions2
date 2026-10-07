"""W-057 / REQ-054 AC-3: a contract keeps its identity while it is live; its token retires after its expiry.

Spec basis (quoted): REQ-054 AC-3 "The identity is (exchange segment, exchange token) while the contract is live: an
exchange change of a live contract's expiry, strike or lot is a revision with history; after the contract's expiry has
passed its token is retired, and a later row with that token is a new contract (ADR-057, correcting ADR-052)."
ADR-057: "Once the stored contract's expiry has passed, the token is retired for it; a later row with the same token
creates a new contract with its own identity, and any record linked to the old one keeps pointing at the old one."

Real rows (NSE F&O bhavcopies, FinInstrmId = exchange token, segment NSE_FO; spec/findings.md F-21, ADR-057):
- 62964: from 2025-06-27 NIFTY 2026-03-26 31000 PE; from 2025-09-01 NIFTY 2026-03-31 31000 PE (expiry moved, live).
- 61746: from 2025-01-01 NIFTY 2029-12-27 23000 CE; from 2025-09-01 NIFTY 2029-12-24 23000 CE (expiry moved, live).
- 67245: 2026-08-03..2026-08-25 ABCAPITAL 2026-08-25 410 PE; from 2026-09-30 NIFTYNXT50 2026-12-29 72200 PE.
- 79199: HINDPETRO 2026-09-29 strike 410 until 2026-08-13, strike 390.75 from 2026-08-14 (corporate action).

MODELLED, not real: V1 loads only NIFTY (NSE_FO) and SENSEX (BSE_FO) contracts (Catalogue._in_scope), so the
ABCAPITAL, NIFTYNXT50 and HINDPETRO rows would be skipped by the loader. Their token sequences (token, dates, expiry,
strike, option type) are kept exactly and the underlying name is replaced by NIFTY; 79199's option type is not in the
source and is modelled as PE. The Zerodha-only values (instrument_token = exchange token * 256 + 2 as on the real
2026-10-02 file, trading symbol, lot 75, tick 0.05) are not in a bhavcopy and are modelled; no assertion relies on
them changing. The real out-of-scope rows themselves are checked to be skipped (nothing written).
Not covered (out of scope for options-only V1, see the W-057 report): 61746 re-used for a WIPRO futures row on
2026-08-26 while the NIFTY contract is live until 2029.

Database tests need TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL (PostgreSQL 16, CI); they skip locally. Each runs
inside a transaction that is rolled back.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.instruments.models import BrokerRef, Contract, InstrumentId, ListedContract
from ofo_app.catalogue_store import (
    CatalogueStoreError,
    apply_update,
    live_contract_id,
    load_catalogue,
    load_contract,
)

IST = timezone(timedelta(hours=5, minutes=30))
CATALOGUE_SQLSTATE = "OF006"
UNIQUE_VIOLATION = "23505"
TABLE = "public.catalogue_contracts"
BROKER = "public.broker_instruments"
HISTORY = "public.catalogue_term_changes"


def _row(token: int, expiry: date, strike: str, option: str, symbol: str, name: str = "NIFTY") -> ListedContract:
    contract = Contract(exchange_segment="NSE_FO", exchange_token=token, name=name, expiry=expiry,
                        strike=Decimal(strike), tick_size=Decimal("0.05"), lot_size=75, instrument_type=option)
    ref = BrokerRef(broker="zerodha", broker_token=str(token * 256 + 2), broker_symbol=symbol,
                    broker_segment="NFO-OPT", lot_size=75, tick_size=Decimal("0.05"), seen_on=None)
    return ListedContract(contract=contract, broker_refs=(ref,))


# The rows above, one constant per (token, terms) state.
R61746_A = _row(61746, date(2029, 12, 27), "23000", "CE", "NIFTY29DEC23000CE")
R61746_B = _row(61746, date(2029, 12, 24), "23000", "CE", "NIFTY29DEC23000CE")
R62964_A = _row(62964, date(2026, 3, 26), "31000", "PE", "NIFTY26MAR31000PE")
R62964_B = _row(62964, date(2026, 3, 31), "31000", "PE", "NIFTY26MAR31000PE")
R67245_OLD = _row(67245, date(2026, 8, 25), "410", "PE", "NIFTY26AUG410PE")  # models ABCAPITAL 25-Aug-2026 410 PE
R67245_NEW = _row(67245, date(2026, 12, 29), "72200", "PE", "NIFTY26DEC72200PE")  # models NIFTYNXT50 29-Dec-2026
R79199_A = _row(79199, date(2026, 9, 29), "410", "PE", "NIFTY26SEP410PE")  # models HINDPETRO, strike 410
R79199_B = _row(79199, date(2026, 9, 29), "390.75", "PE", "NIFTY26SEP410PE")  # strike 390.75 from 2026-08-14

#: Every load day in date order with that day's full list (a contract leaves the list only once it has expired).
DAYS: list[tuple[date, list[ListedContract]]] = [
    (date(2025, 1, 1), [R61746_A]),
    (date(2025, 6, 27), [R61746_A, R62964_A]),
    (date(2025, 9, 1), [R61746_B, R62964_B]),
    (date(2026, 8, 3), [R61746_B, R67245_OLD]),  # 62964 expired 2026-03-31
    (date(2026, 8, 13), [R61746_B, R67245_OLD, R79199_A]),
    (date(2026, 8, 14), [R61746_B, R67245_OLD, R79199_B]),
    (date(2026, 8, 25), [R61746_B, R67245_OLD, R79199_B]),  # 67245 still live on its expiry day
    (date(2026, 9, 30), [R61746_B, R67245_NEW]),  # 67245 back as a new contract; 79199 expired 2026-09-29
]


def _as_of(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST)


# ---------------------------------------------------------------------------------------------------------------
# Planning without a database (runs locally): the store's plan for each rule
# ---------------------------------------------------------------------------------------------------------------


class _FakeConn:
    """Answers the store's live-contract SELECT with `rows` and records every write (no database)."""

    def __init__(self, rows: list | None = None) -> None:
        self.rows = rows or []
        self.writes: list[tuple[str, str, object]] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        rows = self.rows

        class _Result:
            def all(self):
                return rows

            def scalar_one(self):
                return 0

        if sql.startswith("SELECT c.id,") or sql.startswith("SELECT count(*)"):
            return _Result()
        if not sql.startswith("SELECT pg_advisory_xact_lock"):
            self.writes.append((sql.split()[0], sql, params))
        return None

    def begin_nested(self):
        conn = self

        class _Savepoint:
            async def __aenter__(self):
                self.mark = len(conn.writes)
                return self

            async def __aexit__(self, exc_type, *exc):
                if exc_type is not None:
                    del conn.writes[self.mark:]
                return False

        return _Savepoint()


def _stored(row: ListedContract, contract_id: int) -> SimpleNamespace:
    ref = row.ref("zerodha")
    return SimpleNamespace(id=contract_id, currently_listed=True, exchange_segment=row.contract.exchange_segment,
                           exchange_token=row.contract.exchange_token, name=row.contract.name,
                           expiry=row.contract.expiry, strike=row.contract.strike,
                           instrument_type=row.contract.instrument_type,
                           **{k: getattr(ref, k) for k in ("broker", "broker_token", "broker_symbol", "broker_segment",
                                                          "lot_size", "tick_size", "freeze_limit", "seen_on")})


async def test_ac3_plan_retires_the_expired_holder_before_inserting_the_token_reuse() -> None:
    """AC-3: 67245 stored live (expiry 2026-08-25) and listed again on 2026-09-30 with expiry 2026-12-29: the plan
    retires stored contract 7 FIRST (so the live-token key is free), then inserts the new contract and its Zerodha row;
    nothing is revised."""
    conn = _FakeConn([_stored(R67245_OLD, 7)])
    result = await apply_update(conn, [R67245_NEW], as_of=_as_of(date(2026, 9, 30)))
    assert (result.added, result.seen, result.revised, result.retired, result.newly_unlisted) == (1, 0, 0, 1, 1)
    kinds = [(kind, "SET retired = TRUE" in sql) for kind, sql, _ in conn.writes]
    assert kinds == [("UPDATE", True), ("INSERT", False), ("INSERT", False)]
    assert conn.writes[0][2] == {"ids": [7]}
    assert [(p["exchange_token"], p["expiry"], p["strike"]) for p in conn.writes[1][2]] == [
        (67245, date(2026, 12, 29), Decimal("72200"))]


async def test_ac3_plan_keeps_a_live_contract_whose_expiry_or_strike_moves() -> None:
    """AC-3: 62964 live with expiry 2026-03-26, listed on 2025-09-01 with 2026-03-31; 79199 live with strike 410,
    listed on 2026-08-14 with 390.75: both are revisions of the stored contract (no insert, no retire)."""
    conn = _FakeConn([_stored(R62964_A, 1), _stored(R79199_A, 2)])
    result = await apply_update(conn, [R62964_B, R79199_B], as_of=_as_of(date(2025, 9, 1)))
    assert (result.added, result.seen, result.revised, result.retired) == (0, 2, 2, 0)
    revise = [(kind, p) for kind, sql, p in conn.writes if kind == "UPDATE" and "SET expiry" in sql]
    assert len(revise) == 1
    assert sorted((p["exchange_token"], p["expiry"], p["strike"]) for p in revise[0][1]) == [
        (62964, date(2026, 3, 31), Decimal("31000")), (79199, date(2026, 9, 29), Decimal("390.75"))]
    assert not any(kind == "INSERT" for kind, _, _ in conn.writes)


async def test_ac3_a_live_token_on_its_expiry_day_is_not_retired() -> None:
    """AC-3 boundary: on 2026-08-25 (the expiry day of 67245's contract) the contract is still live."""
    conn = _FakeConn([_stored(R67245_OLD, 7)])
    result = await apply_update(conn, [R67245_OLD], as_of=_as_of(date(2026, 8, 25)))
    assert (result.added, result.seen, result.retired) == (0, 1, 0)
    assert not any("SET retired = TRUE" in sql for _, sql, _ in conn.writes)


async def test_ac3_a_live_token_listed_as_a_different_contract_is_refused_with_nothing_written() -> None:
    """AC-3: two live contracts never share a token. 67245 is live until 2026-08-25; a list on 2026-08-14 that gives
    67245 a CE (or another underlying's identity) is refused, nothing written."""
    conn = _FakeConn([_stored(R67245_OLD, 7)])
    other = _row(67245, date(2026, 12, 29), "72200", "CE", "NIFTY26DEC72200CE")
    with pytest.raises(CatalogueStoreError, match=r"instrument_type 'PE' -> 'CE'.*live"):
        await apply_update(conn, [other], as_of=_as_of(date(2026, 8, 14)))
    assert conn.writes == []


@pytest.mark.parametrize("second", [R67245_OLD, _row(67245, date(2026, 12, 29), "72200", "PE", "OTHER")],
                         ids=["same-row-twice", "two-contracts-one-token"])
async def test_ac3_two_rows_with_one_token_in_one_list_refuse_the_whole_list(second: ListedContract) -> None:
    """AC-3: two rows with the same token in ONE list refuse the whole list (even an identical repeat); nothing is
    written, including the unrelated row 61746."""
    conn = _FakeConn()
    with pytest.raises(CatalogueStoreError, match="67245"):
        await apply_update(conn, [R61746_B, R67245_OLD, second], as_of=_as_of(date(2026, 8, 3)))
    assert conn.writes == []


async def test_ac3_a_row_with_no_expiry_is_refused_fail_closed() -> None:
    """AC-3 fail closed: without an expiry the store cannot tell when the token retires; the list is refused."""
    import dataclasses

    no_expiry = ListedContract(contract=dataclasses.replace(R62964_A.contract, expiry=None),
                               broker_refs=R62964_A.broker_refs)
    conn = _FakeConn()
    with pytest.raises(CatalogueStoreError, match="no expiry"):
        await apply_update(conn, [no_expiry], as_of=_as_of(date(2025, 6, 27)))
    assert conn.writes == []


async def test_ac3_a_naive_as_of_is_refused() -> None:
    """AC-3 fail closed: the retirement date needs a timezone-aware as_of."""
    conn = _FakeConn([_stored(R67245_OLD, 7)])
    with pytest.raises(ValueError, match="timezone-aware"):
        await apply_update(conn, [R67245_NEW], as_of=datetime(2026, 9, 30, 10, 0))
    assert conn.writes == []


async def test_ac3_the_real_out_of_scope_rows_are_skipped() -> None:
    """The real ABCAPITAL, NIFTYNXT50 and ABB rows (outside V1's NIFTY/SENSEX scope) are not stored at all."""
    real = [_row(67245, date(2026, 8, 25), "410", "PE", "ABCAPITAL26AUG410PE", name="ABCAPITAL"),
            _row(67245, date(2026, 12, 29), "72200", "PE", "NIFTYNXT5026DEC72200PE", name="NIFTYNXT50"),
            _row(62964, date(2025, 2, 27), "7300", "CE", "ABB25FEB7300CE", name="ABB")]
    for row in real:
        conn = _FakeConn()
        result = await apply_update(conn, [row], as_of=_as_of(date(2025, 1, 1)))
        assert (result.added, result.seen, result.retired) == (0, 0, 0) and conn.writes == []


# ---------------------------------------------------------------------------------------------------------------
# The core proof through PostgreSQL (CI): the real token histories loaded day by day
# ---------------------------------------------------------------------------------------------------------------


async def _contracts(conn: AsyncConnection, token: int) -> list[tuple]:
    return [tuple(r) for r in (await conn.execute(text(
        f"SELECT id, expiry, strike, instrument_type, retired, currently_listed FROM {TABLE} "
        f"WHERE exchange_segment = 'NSE_FO' AND exchange_token = :t ORDER BY id"), {"t": token})).all()]


async def _history(conn: AsyncConnection) -> list[tuple]:
    return [tuple(r) for r in (await conn.execute(text(
        f"SELECT c.exchange_token, h.contract_id, h.broker, h.field, h.old_value, h.new_value FROM {HISTORY} AS h "
        f"JOIN {TABLE} AS c ON c.id = h.contract_id ORDER BY h.id"))).all()]


async def _load_days(conn: AsyncConnection, days) -> dict[date, object]:
    results = {}
    for day, rows in days:
        results[day] = await apply_update(conn, rows, as_of=_as_of(day))
    return results


async def test_ac3_real_token_histories_load_day_by_day(app_engine: AsyncEngine) -> None:
    """AC-3 core proof: 62964 stays ONE contract when its expiry moves 2026-03-26 -> 2026-03-31 (one history row);
    61746 likewise (2029-12-27 -> 2029-12-24); 79199 keeps its contract when its strike moves 410 -> 390.75; 67245
    becomes TWO contracts (the 2026-08-25 410 PE retired, the 2026-12-29 72200 PE new), and a link to the old
    contract's internal id still resolves to the old contract after the reuse."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one() == 0
            await _load_days(conn, DAYS[:7])
            old_67245 = await live_contract_id(conn, InstrumentId("NSE_FO", 67245))
            assert old_67245 is not None
            leg_link = old_67245  # a strategy leg stores the internal id, never the raw token (ADR-057)
            results = await _load_days(conn, DAYS[7:])
            assert (results[date(2026, 9, 30)].added, results[date(2026, 9, 30)].retired) == (1, 2)  # 67245, 79199

            c62964 = await _contracts(conn, 62964)
            c61746 = await _contracts(conn, 61746)
            c67245 = await _contracts(conn, 67245)
            c79199 = await _contracts(conn, 79199)
            assert [r[1:] for r in c62964] == [(date(2026, 3, 31), Decimal("31000.00"), "PE", True, False)]
            assert [r[1:] for r in c61746] == [(date(2029, 12, 24), Decimal("23000.00"), "CE", False, True)]
            assert [r[1:] for r in c79199] == [(date(2026, 9, 29), Decimal("390.75"), "PE", True, False)]
            assert [r[1:] for r in c67245] == [(date(2026, 8, 25), Decimal("410.00"), "PE", True, False),
                                               (date(2026, 12, 29), Decimal("72200.00"), "PE", False, True)]
            assert c67245[0][0] == old_67245 and c67245[1][0] != old_67245
            assert (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one() == 5

            assert await _history(conn) == [
                (61746, c61746[0][0], None, "expiry", "2029-12-27", "2029-12-24"),
                (62964, c62964[0][0], None, "expiry", "2026-03-26", "2026-03-31"),
                (79199, c79199[0][0], None, "strike", "410.00", "390.75"),
            ]

            old = await load_contract(conn, leg_link)
            assert old.contract_id == old_67245 and old.retired and not old.currently_listed
            assert (old.listed.contract.exchange_token, old.listed.contract.expiry, old.listed.contract.strike) == (
                67245, date(2026, 8, 25), Decimal("410.00"))
            assert old.listed.ref("zerodha").broker_token == str(67245 * 256 + 2)
            assert await live_contract_id(conn, InstrumentId("NSE_FO", 67245)) == c67245[1][0]
            assert await live_contract_id(conn, InstrumentId("NSE_FO", 62964)) is None

            live = {e.id: e.contract for e in (await load_catalogue(conn)).all_entries()}
            assert set(live) == {InstrumentId("NSE_FO", 61746), InstrumentId("NSE_FO", 67245)}
            assert live[InstrumentId("NSE_FO", 67245)].strike == Decimal("72200.00")
            broker_rows = (await conn.execute(text(
                f"SELECT contract_id, retired FROM {BROKER} WHERE broker_token = :t ORDER BY contract_id"),
                {"t": str(67245 * 256 + 2)})).all()
            assert [tuple(r) for r in broker_rows] == [(c67245[0][0], True), (c67245[1][0], False)]
        finally:
            await trans.rollback()


async def test_ac3_a_second_live_contract_on_an_occupied_token_is_refused_with_nothing_written(
    app_engine: AsyncEngine,
) -> None:
    """AC-3: 67245 is live until 2026-08-25; on 2026-08-14 a list giving 67245 to a CE is refused and every row is
    unchanged; the database also refuses a second live row on the token (unique live identity)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _load_days(conn, [(date(2026, 8, 3), [R67245_OLD])])
            before = await _contracts(conn, 67245)
            other = _row(67245, date(2026, 12, 29), "72200", "CE", "NIFTY26DEC72200CE")
            with pytest.raises(CatalogueStoreError, match="live"):
                await apply_update(conn, [other], as_of=_as_of(date(2026, 8, 14)))
            assert await _contracts(conn, 67245) == before and await _history(conn) == []
            await _expect_refused(conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, expiry, strike, "
                                        "instrument_type) VALUES ('NSE_FO', 67245, 'NIFTY', '2026-12-29', 72200, 'CE')",
                                  UNIQUE_VIOLATION)
        finally:
            await trans.rollback()


async def test_ac3_retirement_and_retired_rows_are_held_by_the_database(admin_engine: AsyncEngine) -> None:
    """AC-3 database guards, as the owner (who bypasses grants): a live (unexpired) contract cannot be retired; a
    retired contract cannot be un-retired or revised; its broker row never changes; a broker row cannot be added to it."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _load_days(conn, [(date(2026, 8, 3), [R67245_OLD, R61746_B]),
                                    (date(2026, 9, 30), [R67245_NEW, R61746_B])])
            old_id, new_id = [r[0] for r in await _contracts(conn, 67245)]
            live_id = (await _contracts(conn, 61746))[0][0]
            await _expect_refused(conn, f"UPDATE {TABLE} SET retired = TRUE, currently_listed = FALSE "
                                        f"WHERE id = {live_id}", CATALOGUE_SQLSTATE)  # expiry 2029-12-24 not passed
            await _expect_refused(conn, f"UPDATE {TABLE} SET retired = FALSE WHERE id = {old_id}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET expiry = '2026-08-26' WHERE id = {old_id}",
                                  CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET lot_size = 1 WHERE contract_id = {old_id}",
                                  CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET retired = FALSE WHERE contract_id = {old_id}",
                                  CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET retired = TRUE WHERE contract_id = {live_id}",
                                  CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"DELETE FROM {TABLE} WHERE id = {old_id}", CATALOGUE_SQLSTATE)
            assert [r[1:] for r in await _contracts(conn, 67245)] == [
                (date(2026, 8, 25), Decimal("410.00"), "PE", True, False),
                (date(2026, 12, 29), Decimal("72200.00"), "PE", False, True)]
            assert new_id != old_id
        finally:
            await trans.rollback()


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


async def _expect_refused(conn: AsyncConnection, sql: str, expected: str) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql))
    except DBAPIError as exc:
        got = _sqlstate(exc)
        assert got == expected, f"refused with SQLSTATE {got}, expected {expected}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")
