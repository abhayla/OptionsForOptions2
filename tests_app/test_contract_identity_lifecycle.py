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

    def __init__(self, rows: list | None = None, delisted: list | None = None) -> None:
        self.rows = rows or []
        self.delisted = delisted or []
        self.writes: list[tuple[str, str, object]] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        rows = self.delisted if sql.startswith("SELECT d.id,") else self.rows

        class _Result:
            def all(self):
                return rows

            def scalar_one(self):
                return 0

        if sql.startswith(("SELECT c.id,", "SELECT d.id,", "SELECT count(*)")):
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


def _kinds(conn: "_FakeConn") -> list[str]:
    """The write plan in order: delist / retire / reinstate / insert / revise / see / listed."""
    out = []
    for kind, sql, _ in conn.writes:
        for marker, name in (("SET delisted = TRUE", "delist"), ("SET retired = TRUE", "retire"),
                             ("SET delisted = FALSE", "reinstate"), ("INSERT INTO public.catalogue_contracts", "insert"),
                             ("INSERT INTO public.broker_instruments", "insert-broker"), ("SET expiry", "revise"),
                             ("UPDATE public.broker_instruments", "see"), ("SET currently_listed = :listed", "listed")):
            if marker in sql:
                out.append(name)
                break
        else:
            out.append(kind)
    return out


@pytest.mark.parametrize("other, kind", [
    (_row(62964, date(2026, 3, 31), "31000", "PE", "NIFTY26MAR31000PE"), "revision"),  # real: +5 days
    (_row(62964, date(2026, 4, 1), "31000", "PE", "NIFTY26MAR31000PE"), "revision"),  # +6 days: the boundary
    (_row(62964, date(2026, 4, 2), "31000", "PE", "NIFTY26APR31000PE"), "new"),  # +7 days (ADR-059: at most 6)
    (_row(62964, date(2026, 3, 19), "31000", "PE", "NIFTY26MAR31000PE"), "new"),  # -7 days
    (_row(62964, date(2026, 3, 26), "30500", "PE", "NIFTY26MAR30500PE"), "revision"),  # strike only (79199 shape)
    (_row(62964, date(2026, 3, 31), "30500", "PE", "NIFTY26MAR30500PE"), "new"),  # strike AND expiry
    (_row(62964, date(2026, 3, 26), "31000", "CE", "NIFTY26MAR31000CE"), "new"),  # PE -> CE
    (_row(62964, date(2026, 3, 26), "0", "FUT", "NIFTY26MARFUT"), "new"),  # option -> future
], ids=["plus-5-days", "plus-6-days", "plus-7-days", "minus-7-days", "strike-only", "strike-and-expiry", "pe-to-ce",
        "pe-to-fut"])
async def test_ac3_fix1_adr059_classifies_a_changed_row_on_a_live_token(other: ListedContract, kind: str) -> None:
    """AC-3 / ADR-059: 62964 is live (NIFTY 31000 PE, expiry 2026-03-26). A row on its token revises it only if
    underlying, type and segment are unchanged AND (strike unchanged and expiry moved <= 7 days, OR expiry unchanged and
    strike changed); anything else delists the stored contract and inserts the row as a new contract, delist first.
    62964 sits among 11 other live NIFTY contracts, 2 of them in its expiry, so the one delisting is counted by both
    guards and stays under them (1 of 12 = 8.3%; 1 of 3 of the expiry)."""
    others = _fillers(9) + _fillers(2, first_token=600001, expiry=date(2026, 3, 26))
    conn = _FakeConn(_stored_all(others) + [_stored(R62964_A, 50)])
    result = await apply_update(conn, others + [other], as_of=_as_of(date(2025, 9, 1)))
    if kind == "revision":
        assert (result.added, result.delisted, result.seen) == (0, 0, 12)
        assert _kinds(conn) == ["revise", "see", "listed"]
    else:
        assert (result.added, result.delisted, result.seen) == (1, 1, 11)
        assert _kinds(conn) == ["delist", "insert", "insert-broker", "see", "listed"]
        assert conn.writes[0][2] == {"ids": [50]}


async def test_ac3_fix2r_a_list_reassigning_most_tokens_of_an_index_is_refused() -> None:
    """ADR-059 "Both guards count every live contract that would stop being live in this update - those the list no
    longer carries AND those delisted because their token now carries another contract": 20 live NIFTY contracts; a
    list keeping all 20 tokens but giving 15 of them other contracts (strike and expiry changed) is refused, nothing
    written; 2 of 20 (10%) is accepted."""
    live = _fillers(20)
    moved = [_row(r.contract.exchange_token, date(2026, 11, 24), "20550", "CE", "MOVED") for r in live]
    conn = _FakeConn(_stored_all(live))
    with pytest.raises(ValueError, match="refused: would drop 15 of 20 live NIFTY contracts"):
        await apply_update(conn, moved[:15] + live[15:], as_of=_as_of(date(2026, 10, 7)))
    assert conn.writes == []
    ok = _FakeConn(_stored_all(live))
    result = await apply_update(ok, moved[:2] + live[2:], as_of=_as_of(date(2026, 10, 7)))
    assert (result.delisted, result.added) == (2, 2)


async def test_ac3_fix2r_reused_tokens_count_in_the_half_expiry_guard() -> None:
    """ADR-059: 1,000 live NIFTY contracts of 2027-12-28 and 10 of 2026-10-13; a list giving 6 of the 10 weekly
    tokens other contracts (0.6% of the index) is refused by the per-expiry guard; 5 of 10 is accepted."""
    big, weekly = _fillers(1000), _fillers(10, first_token=400001, expiry=date(2026, 10, 13))
    moved = [_row(r.contract.exchange_token, date(2027, 1, 26), "30000", "PE", "MOVED") for r in weekly]
    conn = _FakeConn(_stored_all(big + weekly))
    with pytest.raises(ValueError, match="would drop 6 of 10 live NIFTY contracts of expiry 2026-10-13"):
        await apply_update(conn, big + moved[:6] + weekly[6:], as_of=_as_of(date(2026, 10, 7)))
    assert conn.writes == []
    result = await apply_update(_FakeConn(_stored_all(big + weekly)), big + moved[:5] + weekly[5:],
                                as_of=_as_of(date(2026, 10, 7)))
    assert result.delisted == 5


async def test_ac3_fix1_61746_minus_3_days_is_a_revision() -> None:
    """AC-3 / ADR-059 real case: 61746 NIFTY 23000 CE 2029-12-27 -> 2029-12-24 (3 days, same strike) is a revision."""
    conn = _FakeConn([_stored(R61746_A, 61)])
    result = await apply_update(conn, [R61746_B], as_of=_as_of(date(2025, 9, 1)))
    assert (result.added, result.delisted, result.revised) == (0, 0, 1)
    assert _kinds(conn) == ["revise", "see", "listed"]


def _other_zerodha_token(row: ListedContract, broker_token: str) -> ListedContract:
    import dataclasses

    return ListedContract(contract=row.contract,
                          broker_refs=tuple(dataclasses.replace(r, broker_token=broker_token) for r in row.broker_refs))


@pytest.mark.parametrize("second", [R67245_OLD, _row(67245, date(2026, 12, 29), "72200", "PE", "OTHER"),
                                    _other_zerodha_token(R67245_NEW, "99999999")],
                         ids=["same-row-twice", "two-contracts-one-token", "one-exchange-token-two-zerodha-tokens"])
async def test_ac3_two_rows_with_one_token_in_one_list_refuse_the_whole_list(second: ListedContract) -> None:
    """AC-3: two rows with the same exchange token in ONE list refuse the whole list (even an identical repeat, and
    even when Zerodha gives them different instrument tokens); nothing is written, including the unrelated row 61746."""
    conn = _FakeConn()
    with pytest.raises(CatalogueStoreError, match="token NSE_FO:67245 twice"):
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
    with pytest.raises(ValueError, match="timezone-aware as_of \\(the retirement date"):
        await apply_update(conn, [R67245_NEW], as_of=datetime(2026, 9, 30, 10, 0))
    assert conn.writes == []


async def test_ac3_a_stored_live_contract_with_no_expiry_stops_the_load() -> None:
    """AC-3 fail closed: a stored live contract without an expiry can never be judged retired; the load refuses."""
    stored = _stored(R67245_OLD, 7)
    stored.expiry = None
    conn = _FakeConn([stored])
    with pytest.raises(CatalogueStoreError, match="id=7 .* has no expiry"):
        await apply_update(conn, [R61746_B], as_of=_as_of(date(2026, 9, 30)))
    assert conn.writes == []


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt, params=None):
        rows = self.rows

        class _Result:
            def all(self):
                return rows

        return _Result()


async def test_ac3_lookups_fail_closed() -> None:
    """AC-3: two live rows on one token (only possible if the live key was dropped) are never resolved to one of them;
    a link is a positive integer internal id; an unknown id is refused."""
    with pytest.raises(CatalogueStoreError, match="2 live contracts share"):
        await live_contract_id(_Rows([SimpleNamespace(id=1), SimpleNamespace(id=2)]), InstrumentId("NSE_FO", 67245))
    assert await live_contract_id(_Rows([SimpleNamespace(id=9)]), InstrumentId("NSE_FO", 67245)) == 9
    assert await live_contract_id(_Rows([]), InstrumentId("NSE_FO", 67245)) is None
    with pytest.raises(TypeError):
        await live_contract_id(_Rows([]), ("NSE_FO", 67245))
    for bad in (0, -1, True, "7", 7.0):
        with pytest.raises(CatalogueStoreError, match="positive integer internal id"):
            await load_contract(_Rows([]), bad)
    with pytest.raises(CatalogueStoreError, match="no stored contract has internal id 7"):
        await load_contract(_Rows([]), 7)


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


async def test_ac3_fix1_a_token_reused_in_the_same_list_never_repoints_the_old_contract(
    app_engine: AsyncEngine,
) -> None:
    """AC-3 / ADR-059 (the review's CRITICAL): 61746 is live as NIFTY 23000 CE 2029-12-24; ONE list gives the token to
    NIFTY 20550 CE 2026-11-24 (strike and expiry both changed). The old contract is delisted (kept, terms unchanged, no
    revision history) and a new contract takes the token; a link by the old internal id still resolves to 23000 CE.
    The database also refuses a second live row on the token (unique live identity)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            others = _fillers(9) + _fillers(2, first_token=200001, expiry=date(2029, 12, 24))
            await _load_days(conn, [(date(2025, 9, 1), others + [R61746_B])])
            old_id = await live_contract_id(conn, InstrumentId("NSE_FO", 61746))
            reuse = _row(61746, date(2026, 11, 24), "20550", "CE", "NIFTY26NOV20550CE")
            result = await apply_update(conn, others + [reuse], as_of=_as_of(date(2025, 9, 2)))
            assert (result.added, result.delisted, result.revised) == (1, 1, 0)
            new_id = await live_contract_id(conn, InstrumentId("NSE_FO", 61746))
            assert new_id is not None and new_id != old_id
            old = await load_contract(conn, old_id)
            assert (old.delisted, old.listed.contract.strike, old.listed.contract.expiry) == (
                True, Decimal("23000.00"), date(2029, 12, 24))
            assert [h[3] for h in await _history(conn) if h[1] == old_id] == ["delisted_on"]
            new = await load_contract(conn, new_id)
            assert (new.listed.contract.strike, new.listed.contract.expiry) == (Decimal("20550.00"), date(2026, 11, 24))
            await _expect_refused(conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, expiry, strike, "
                                        "instrument_type) VALUES ('NSE_FO', 61746, 'NIFTY', '2026-12-29', 72200, 'CE')",
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


async def test_ac3_retiring_is_held_to_its_last_terms_and_cascades_to_broker_rows(admin_engine: AsyncEngine) -> None:
    """AC-3 database guards: 67245 (expiry 2026-08-25, passed) is still live after a 2026-08-03 load. Retiring it while
    changing its strike or keeping it listed is refused; a plain retire succeeds, stamps retired_at and retires its
    Zerodha row; a broker row cannot then be added to it."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _load_days(conn, [(date(2026, 8, 3), [R67245_OLD])])
            (cid,) = [r[0] for r in await _contracts(conn, 67245)]
            await _expect_refused(conn, f"UPDATE {TABLE} SET retired = TRUE, currently_listed = FALSE, strike = 1 "
                                        f"WHERE id = {cid}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET retired = TRUE WHERE id = {cid}", CATALOGUE_SQLSTATE)
            await conn.execute(text(f"UPDATE {TABLE} SET retired = TRUE, currently_listed = FALSE WHERE id = {cid}"))
            row = (await conn.execute(text(f"SELECT c.retired, c.retired_at IS NOT NULL, b.retired FROM {TABLE} AS c "
                                           f"JOIN {BROKER} AS b ON b.contract_id = c.id WHERE c.id = {cid}"))).one()
            assert tuple(row) == (True, True, True)
            await _expect_refused(conn, f"INSERT INTO {BROKER} (contract_id, broker, broker_token, broker_symbol, "
                                        f"broker_segment, lot_size, tick_size) VALUES ({cid}, 'zerodha', 'X1', 'X1', "
                                        "'NFO-OPT', 75, 0.05)", CATALOGUE_SQLSTATE)
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


# ---------------------------------------------------------------------------------------------------------------
# Migration 0005 (the schema half of AC-3)
# ---------------------------------------------------------------------------------------------------------------


def _migration(name: str):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions" / f"{name}.py"
    loader = importlib.util.spec_from_file_location(f"ofo_migration_{name}_w057_test", path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _without_guards(pins: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in pins.items()
            if k not in ("public.catalogue_contracts_guard()", "public.broker_instruments_guard()")}


def test_ac3_migration_0005_shape() -> None:
    """AC-3 schema: strike joins expiry as a revisable contract term (history broker NULL); retired is app-updatable on
    contracts but never on broker rows; both live keys are checked by the allowlist; only the two guard bodies are
    re-pinned (different from 0004's, every other pin equal)."""
    m5, m4 = _migration("0005_contract_lifecycle"), _migration("0004_broker_instruments")
    assert m5.down_revision == "0004_broker_instruments"
    assert m5.CONTRACT_REVISABLE == ("expiry", "strike")
    assert m5.CONTRACT_IDENTITY == ("id", "exchange_segment", "exchange_token", "name", "instrument_type")
    assert m5.HISTORY_FIELDS == ("expiry", "strike", "delisted_on", "broker_symbol", "lot_size", "tick_size",
                                 "freeze_limit")
    assert m5.ADDED_UPDATE_COLUMNS == ("strike", "retired", "delisted")
    assert m5.LIVE_PREDICATE == "NOT retired AND NOT delisted"
    assert "retired" not in m5.APP_BROKER_UPDATE_COLUMNS + m5.APP_BROKER_INSERT_COLUMNS + m5.APP_INSERT_COLUMNS
    for fn in ("public.catalogue_contracts_guard()", "public.broker_instruments_guard()"):
        assert m5.PINNED_BODIES[fn] != m4.PINNED_BODIES[fn]
    assert _without_guards(m5.PINNED_BODIES) == _without_guards(m4.PINNED_BODIES)
    allowlist = m5.extended_allowlist_sql()
    assert allowlist.count("live key public.catalogue_contracts_live_identity_key") == 1
    assert allowlist.count("live key public.broker_instruments_live_token_key") == 1
    with pytest.raises(RuntimeError, match="changed shape"):
        m5.extend_allowlist(allowlist)


async def test_ac3_downgrade_of_0005_refuses_while_rows_exist(admin_engine: AsyncEngine) -> None:
    """AC-3: the downgrade cannot express a retired contract (0004 keys a token for ever), so it refuses while any
    contract exists; its first statement is run (as the owner) on a loaded catalogue and must raise."""
    recorded: list[str] = []
    m5 = _migration("0005_contract_lifecycle")
    m5.op = SimpleNamespace(execute=lambda sql, *a, **k: recorded.append(str(sql)))
    m5._BASE._app_role = lambda: "ofo_app"
    m5.downgrade()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _load_days(conn, [(date(2026, 8, 3), [R67245_OLD])])
            with pytest.raises(DBAPIError, match="refusing to downgrade 0005_contract_lifecycle"):
                async with conn.begin_nested():
                    await conn.execute(text(recorded[0]))
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Round 2 (ADR-058): delisted before expiry, and the counting truncation guard
# Spec basis: ADR-058 "refuse the whole update, writing nothing, if more than 10% of an index's live contracts would
# disappear at once"; REQ-054 AC-3 "A contract the daily list stops carrying before its expiry is marked delisted and
# kept, and its token is free for reuse (ADR-058)."
# ---------------------------------------------------------------------------------------------------------------


def _fillers(n: int, name: str = "NIFTY", first_token: int = 100001,
             expiry: date = date(2027, 12, 28)) -> list[ListedContract]:
    """n live contracts of one index with future expiries (synthetic: only their COUNT matters to the guard)."""
    import dataclasses

    rows = []
    for i in range(n):
        row = _row(first_token + i, expiry, str(10000 + 50 * i), "CE", f"{name}27DEC{10000 + 50 * i}CE",
                   name=name)
        if name == "SENSEX":
            row = ListedContract(contract=dataclasses.replace(row.contract, exchange_segment="BSE_FO"),
                                 broker_refs=tuple(dataclasses.replace(r, broker_segment="BFO-OPT")
                                                   for r in row.broker_refs))
        rows.append(row)
    return rows


def _stored_all(rows: list[ListedContract]) -> list[SimpleNamespace]:
    return [_stored(r, i + 1) for i, r in enumerate(rows)]


def _delist_writes(conn: _FakeConn) -> list:
    return [p for kind, sql, p in conn.writes if "SET delisted = TRUE" in sql]


async def test_ac3_r2_a_small_cleanup_is_accepted_and_delists_the_missing() -> None:
    """AC-3 / ADR-058 example: 1,832 live NIFTY contracts; the list lacks 14 (0.8%) -> accepted; the 14 are delisted
    (kept, token freed) in the first write; the other 1,818 are seen."""
    live = _fillers(1832)
    conn = _FakeConn(_stored_all(live))
    missing = {r.id for r in live[100:114]}
    result = await apply_update(conn, [r for r in live if r.id not in missing], as_of=_as_of(date(2026, 10, 7)))
    assert (result.added, result.seen, result.delisted, result.retired, result.newly_unlisted) == (0, 1818, 14, 0, 14)
    assert _delist_writes(conn) == [{"ids": list(range(101, 115))}]
    assert conn.writes[0][0] == "UPDATE" and "SET delisted = TRUE" in conn.writes[0][1]


async def test_ac3_r2_a_truncated_list_is_refused_with_nothing_written() -> None:
    """AC-3 / ADR-058: the same 1,832 NIFTY contracts and a list missing 733 of them (40.0%) -> refused, no write."""
    live = _fillers(1832)
    conn = _FakeConn(_stored_all(live))
    with pytest.raises(ValueError, match=r"refused: would drop 733 of 1832 live NIFTY contracts"):
        await apply_update(conn, live[733:], as_of=_as_of(date(2026, 10, 7)))
    assert conn.writes == []


@pytest.mark.parametrize("missing, refused", [(183, False), (184, True)], ids=["exactly-10pct", "just-over-10pct"])
async def test_ac3_r2_the_boundary_is_more_than_ten_percent(missing: int, refused: bool) -> None:
    """ADR-058 "more than 10%": 183 of 1,830 is exactly 10% -> accepted; 184 (10.05%) -> refused."""
    live = _fillers(1830)
    conn = _FakeConn(_stored_all(live))
    if refused:
        with pytest.raises(ValueError, match="refused: would drop 184 of 1830"):
            await apply_update(conn, live[missing:], as_of=_as_of(date(2026, 10, 7)))
        assert conn.writes == []
    else:
        result = await apply_update(conn, live[missing:], as_of=_as_of(date(2026, 10, 7)))
        assert result.delisted == 183


async def test_ac3_r2_the_threshold_is_a_setting_with_default_ten() -> None:
    """ADR-058 "the 10% is an admin setting": Settings defaults to 10; a lower setting refuses what 10 accepts; a value
    that is not a percentage is refused before anything is read."""
    from ofo_app.catalogue_store import DEFAULT_MAX_DELIST_PERCENT
    from ofo_app.config import Settings

    assert DEFAULT_MAX_DELIST_PERCENT == Decimal("10")
    assert Settings(DATABASE_URL="postgresql://x").CATALOGUE_MAX_DELIST_PERCENT == Decimal("10")
    live = _fillers(1830)
    conn = _FakeConn(_stored_all(live))
    with pytest.raises(ValueError, match=r"refused: would drop 92 of 1830 .*more than 5%"):
        await apply_update(conn, live[92:], as_of=_as_of(date(2026, 10, 7)), max_delist_percent=Decimal("5"))
    assert conn.writes == []
    for bad in (-1, Decimal("100.1"), 10.0, True, Decimal("NaN"), "10"):
        empty = _FakeConn()
        with pytest.raises(CatalogueStoreError, match="max_delist_percent"):
            await apply_update(empty, [], as_of=_as_of(date(2026, 10, 7)), max_delist_percent=bad)
        assert empty.writes == []


async def test_ac3_r2_each_index_is_counted_on_its_own() -> None:
    """ADR-058 "an index's live contracts": dropping 3 of 10 SENSEX contracts (30%) is refused even though that is
    0.16% of all 1,842 live contracts; dropping 1 of 10 SENSEX (10%) is accepted."""
    nifty, sensex = _fillers(1832), _fillers(10, name="SENSEX", first_token=900001)
    stored = _stored_all(nifty + sensex)
    conn = _FakeConn(stored)
    with pytest.raises(ValueError, match="refused: would drop 3 of 10 live SENSEX contracts"):
        await apply_update(conn, nifty + sensex[3:], as_of=_as_of(date(2026, 10, 7)))
    assert conn.writes == []
    result = await apply_update(_FakeConn(stored), nifty + sensex[1:], as_of=_as_of(date(2026, 10, 7)))
    assert result.delisted == 1


async def test_ac3_r2_plan_for_61746_delists_then_a_reuse_is_a_new_contract() -> None:
    """AC-3 / F-30, 61746 modelled with NIFTY rows: stored live (expiry 2029-12-24) next to 10 other live NIFTY
    contracts; the 2026-08-26 list lacks it (1 of 11 = 9.1%) -> delisted; once delisted it is not in the live SELECT, so
    a list giving 61746 to a NIFTY Nov-2026 future (models WIPRO Nov-2026 futures) inserts a new contract."""
    others = _fillers(10) + _fillers(2, first_token=200001, expiry=date(2029, 12, 24))
    conn = _FakeConn(_stored_all(others) + [_stored(R61746_B, 61)])
    result = await apply_update(conn, others, as_of=_as_of(date(2026, 8, 26)))
    assert (result.delisted, result.retired, result.added) == (1, 0, 0)
    assert _delist_writes(conn) == [{"ids": [61]}]
    reuse = _row(61746, date(2026, 11, 24), "0", "FUT", "NIFTY26NOVFUT")
    after = _FakeConn(_stored_all(others))
    result = await apply_update(after, others + [reuse], as_of=_as_of(date(2026, 9, 1)))
    inserted = [p for kind, sql, p in after.writes if sql.startswith("INSERT INTO public.catalogue_contracts")]
    assert result.added == 1 and [p["exchange_token"] for p in inserted[0]] == [61746]


async def test_ac3_r2_61746_delisted_before_expiry_then_reused(app_engine: AsyncEngine) -> None:
    """AC-3 core proof of round 2 through PostgreSQL: 61746 (NIFTY 23000 CE) is one contract across its expiry move
    (2029-12-27 -> 2029-12-24, one history row); the 2026-08-26 list lacks it while its expiry is 3 years away ->
    delisted on the database's IST date with a history row, kept, unlisted, its Zerodha row freed; the 2026-09-01 list
    gives 61746 to a different contract -> a new contract; the old one still resolves by its internal id."""
    others = _fillers(10) + _fillers(2, first_token=200001, expiry=date(2029, 12, 24))
    early = _fillers(10) + _fillers(2, first_token=200001, expiry=date(2029, 12, 27))
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            today = (await conn.execute(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date"))
                     ).scalar_one()
            await _load_days(conn, [(date(2025, 1, 1), early + [R61746_A]), (date(2025, 9, 1), others + [R61746_B])])
            old_id = await live_contract_id(conn, InstrumentId("NSE_FO", 61746))
            result = await apply_update(conn, others, as_of=_as_of(date(2026, 8, 26)))
            assert (result.delisted, result.retired) == (1, 0)
            assert await live_contract_id(conn, InstrumentId("NSE_FO", 61746)) is None
            reuse = _row(61746, date(2026, 11, 24), "0", "FUT", "NIFTY26NOVFUT")
            result = await apply_update(conn, others + [reuse], as_of=_as_of(date(2026, 9, 1)))
            assert result.added == 1
            new_id = await live_contract_id(conn, InstrumentId("NSE_FO", 61746))
            assert new_id is not None and new_id != old_id
            old = await load_contract(conn, old_id)
            assert (old.delisted, old.delisted_on, old.retired, old.currently_listed) == (True, today, False, False)
            assert (old.listed.contract.expiry, old.listed.contract.strike, old.listed.contract.instrument_type) == (
                date(2029, 12, 24), Decimal("23000.00"), "CE")
            assert [h for h in await _history(conn) if h[1] == old_id] == [
                (61746, old_id, None, "expiry", "2029-12-27", "2029-12-24"),
                (61746, old_id, None, "delisted_on", None, today.isoformat())]
            rows = (await conn.execute(text(f"SELECT contract_id, retired FROM {BROKER} WHERE broker_token = :t "
                                            "ORDER BY contract_id"), {"t": str(61746 * 256 + 2)})).all()
            assert [tuple(r) for r in rows] == [(old_id, True), (new_id, False)]
            await _expect_refused(conn, f"UPDATE {TABLE} SET delisted = FALSE WHERE id = {old_id}",
                                  CATALOGUE_SQLSTATE)  # a delisted contract never changes (as the app role)
        finally:
            await trans.rollback()


async def test_ac3_r2_delisting_is_held_by_the_database(admin_engine: AsyncEngine) -> None:
    """ADR-058 database guards, as the owner: delisting while listed, while changing a term, or together with retiring
    is refused; a broker row cannot be freed by hand; a plain delist stamps delisted_on and frees the Zerodha row; a
    delisted contract cannot be retired, re-listed, revised or un-delisted."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _load_days(conn, [(date(2025, 9, 1), [R61746_B])])
            (cid,) = [r[0] for r in await _contracts(conn, 61746)]
            await _expect_refused(conn, f"UPDATE {TABLE} SET delisted = TRUE WHERE id = {cid}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET delisted = TRUE, currently_listed = FALSE, strike = 1 "
                                        f"WHERE id = {cid}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET delisted = TRUE, retired = TRUE, currently_listed = FALSE "
                                        f"WHERE id = {cid}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET retired = TRUE WHERE contract_id = {cid}",
                                  CATALOGUE_SQLSTATE)
            await conn.execute(text(f"UPDATE {TABLE} SET delisted = TRUE, currently_listed = FALSE WHERE id = {cid}"))
            row = (await conn.execute(text(f"SELECT c.delisted_on IS NOT NULL, b.retired FROM {TABLE} AS c "
                                           f"JOIN {BROKER} AS b ON b.contract_id = c.id WHERE c.id = {cid}"))).one()
            assert tuple(row) == (True, True)
            for change in ("retired = TRUE", "currently_listed = TRUE", "expiry = '2029-12-27'", "delisted = FALSE"):
                await _expect_refused(conn, f"UPDATE {TABLE} SET {change} WHERE id = {cid}", CATALOGUE_SQLSTATE)
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Fix round 1 (ADR-059): reinstatement, the per-expiry half guard, stale rows, the forced audit event
# ---------------------------------------------------------------------------------------------------------------


def _delisted_row(row: ListedContract, contract_id: int) -> SimpleNamespace:
    stored = _stored(row, contract_id)
    stored.currently_listed = False
    return stored


async def test_ac3_fix2_an_identical_delisted_contract_returning_is_reinstated() -> None:
    """AC-3 / ADR-059: 61746 (NIFTY 23000 CE 2029-12-24, Zerodha token 15807234) was delisted as id 61; a list carrying
    the identical row reinstates id 61 (no insert); a delisted row with another strike is not reinstated."""
    conn = _FakeConn([], delisted=[_delisted_row(R61746_B, 61)])
    result = await apply_update(conn, [R61746_B], as_of=_as_of(date(2026, 8, 27)))
    assert (result.added, result.reinstated, result.seen) == (0, 1, 0)
    assert _kinds(conn) == ["reinstate", "see", "listed"]
    assert conn.writes[0][2] == {"ids": [61]}
    other = _FakeConn([], delisted=[_delisted_row(_row(61746, date(2029, 12, 24), "23050", "CE", "X"), 61)])
    result = await apply_update(other, [R61746_B], as_of=_as_of(date(2026, 8, 27)))
    assert (result.added, result.reinstated) == (1, 0) and _kinds(other) == ["insert", "insert-broker"]


async def test_ac3_fix2_two_identical_delisted_candidates_refuse_the_list() -> None:
    """Fail closed: two delisted contracts identical to one row cannot both be the returning contract."""
    conn = _FakeConn([], delisted=[_delisted_row(R61746_B, 61), _delisted_row(R61746_B, 62)])
    with pytest.raises(CatalogueStoreError, match="2 delisted contracts"):
        await apply_update(conn, [R61746_B], as_of=_as_of(date(2026, 8, 27)))
    assert conn.writes == []


async def test_ac3_fix2_a_partial_list_heals_on_the_next_full_list(app_engine: AsyncEngine) -> None:
    """AC-3 / ADR-059: list A = 20 Dec-2027 + 4 Jun-2027 NIFTY contracts; list B lacks 2 of the weekly
    (2 of 24 = 8.3% of the index, exactly half of the expiry: accepted) -> 2 delisted; list C is full again -> the same
    24 internal ids as after A, all live, each delisting undone with a history row."""
    weekly = _fillers(4, first_token=300001, expiry=date(2027, 6, 29))  # live by the database clock too
    full = _fillers(20) + weekly
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, full, as_of=_as_of(date(2025, 9, 1)))
            ids_a = {r.contract.exchange_token: await live_contract_id(conn, r.id) for r in full}
            result = await apply_update(conn, _fillers(20) + weekly[2:], as_of=_as_of(date(2025, 9, 2)))
            assert result.delisted == 2
            result = await apply_update(conn, full, as_of=_as_of(date(2025, 9, 3)))
            assert (result.reinstated, result.added) == (2, 0)
            ids_c = {r.contract.exchange_token: await live_contract_id(conn, r.id) for r in full}
            assert ids_c == ids_a
            day = (await conn.execute(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date::text"))
                   ).scalar_one()
            assert [(h[0], h[3], h[4], h[5]) for h in await _history(conn)] == [
                (300001, "delisted_on", None, day), (300002, "delisted_on", None, day),
                (300001, "delisted_on", day, None), (300002, "delisted_on", day, None)]
            assert (await conn.execute(text(f"SELECT count(*) FROM {TABLE} WHERE delisted"))).scalar_one() == 0
        finally:
            await trans.rollback()


@pytest.mark.parametrize("missing, refused", [(5, False), (6, True)], ids=["exactly-half", "more-than-half"])
async def test_ac3_fix3_one_expiry_losing_more_than_half_is_refused(missing: int, refused: bool) -> None:
    """ADR-059: 1,000 live NIFTY contracts of 2027-12-28 plus 10 of 2026-10-13. Losing 5 of the 10 (exactly half, 0.5%
    of the index) is accepted; losing 6 (more than half) is refused with nothing written."""
    big, weekly = _fillers(1000), _fillers(10, first_token=400001, expiry=date(2026, 10, 13))
    conn = _FakeConn(_stored_all(big + weekly))
    if refused:
        with pytest.raises(ValueError, match="would drop 6 of 10 live NIFTY contracts of expiry 2026-10-13"):
            await apply_update(conn, big + weekly[missing:], as_of=_as_of(date(2026, 10, 7)))
        assert conn.writes == []
    else:
        result = await apply_update(conn, big + weekly[missing:], as_of=_as_of(date(2026, 10, 7)))
        assert result.delisted == 5


async def test_ac3_fix4_a_stale_row_never_creates_a_live_contract() -> None:
    """ADR-059: a list row whose expiry (2026-10-06) is before the load date (2026-10-07) is skipped, never loaded."""
    stale = _row(500001, date(2026, 10, 6), "25000", "CE", "NIFTY26O0625000CE")
    conn = _FakeConn()
    result = await apply_update(conn, [stale], as_of=_as_of(date(2026, 10, 7)))
    assert (result.added, result.domain.skipped_expired) == (0, 1) and conn.writes == []


def test_ac3_fix5_a_forced_update_audits_every_contract_it_delists() -> None:
    """ADR-059: a forced update's audit event names the contracts not carried AND the ones whose token is reused."""
    from ofo.audit import AuditLog
    from ofo.instruments.catalogue import Catalogue

    cat = Catalogue()
    cat.load([R62964_A, R61746_A])
    log = AuditLog()
    reuse = _row(62964, date(2026, 11, 24), "20550", "CE", "NIFTY26NOV20550CE")
    result = cat.update([reuse], as_of=_as_of(date(2025, 6, 27)), force=True, reason="test", actor="admin-1",
                        audit_log=log, max_delist_percent=100)
    assert result.replaced == (InstrumentId("NSE_FO", 62964),)
    assert result.delisted == (InstrumentId("NSE_FO", 61746),)
    (event,) = log.events
    assert sorted(event.payload["dropped_instrument_tokens"]) == [("NSE_FO", 61746), ("NSE_FO", 62964)]
    assert sorted(event.payload["dropped_tradingsymbols"]) == [("zerodha", "NIFTY26MAR31000PE"),
                                                               ("zerodha", "NIFTY29DEC23000CE")]


async def test_ac3_fix2r_the_stored_forced_audit_payload_names_every_delisted_contract(app_engine: AsyncEngine) -> None:
    """ADR-059 + REQ-063 AC-5: through the real audit store, a forced update's stored payload keeps the declared keys
    and names both the contract the list stopped carrying (61746) and the one whose token was reused (67245, modelled
    live until 2027-12-28 so the database clock can be the as_of the audit clock window accepts)."""
    from ofo_app.audit_store import load_log

    held = _row(67245, date(2027, 12, 28), "410", "PE", "NIFTY27DEC410PE")
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            now = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            await apply_update(conn, [held, R61746_B], as_of=now)
            reuse = _row(67245, date(2028, 1, 25), "20550", "CE", "NIFTY28JAN20550CE")
            now = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            await apply_update(conn, [reuse], as_of=now, force=True, reason="exchange reused the token",
                               actor="admin-1")
            log, _ = await load_log(conn)
            payload = log.events[-1].payload
            assert sorted(map(tuple, payload["dropped_instrument_tokens"])) == [("NSE_FO", 61746), ("NSE_FO", 67245)]
            assert sorted(map(tuple, payload["dropped_tradingsymbols"])) == [("zerodha", "NIFTY27DEC410PE"),
                                                                             ("zerodha", "NIFTY29DEC23000CE")]
            assert (await load_contract(conn, (await _contracts(conn, 67245))[0][0])).delisted
        finally:
            await trans.rollback()


async def test_ac3_fix2r_an_expired_delisted_contract_is_never_reinstated(admin_engine: AsyncEngine) -> None:
    """ADR-059 database guard: a delisted contract whose expiry (2026-03-31) has passed by the database's IST date
    cannot return to live, even with every term unchanged."""
    others = _fillers(9) + _fillers(2, first_token=600001, expiry=date(2026, 3, 31))
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _load_days(conn, [(date(2025, 9, 1), others + [R62964_B]), (date(2025, 9, 2), others)])
            (cid,) = [r[0] for r in await _contracts(conn, 62964)]
            assert (await load_contract(conn, cid)).delisted
            await _expect_refused(conn, f"UPDATE {TABLE} SET delisted = FALSE, currently_listed = TRUE WHERE id = {cid}",
                                  CATALOGUE_SQLSTATE)
        finally:
            await trans.rollback()
