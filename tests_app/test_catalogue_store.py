"""W-053: the contract catalogue stored in PostgreSQL (REQ-053 AC-2, owner decision Q244).

Spec basis: REQ-053 AC-2 "The contract catalogue (what exists) is stored separately from current eligibility (what
Zerodha permits); contracts are never permanently deleted because they are unavailable today."; REQ-053 Q244 (a daily
update "is refused if it would remove any contract whose expiry has not yet passed"); ADR-008 (exact Decimal, never
float); ADR-048 (non-superuser application role, real PostgreSQL).

Every database test runs inside a transaction that is rolled back, so the shared catalogue table stays empty between
tests (the real-file proof needs an empty table to compare counts). Application-role tests use TEST_DATABASE_URL;
owner-level checks and mutations use TEST_ADMIN_DATABASE_URL.
Legacy cases adapted from abhayla/algochanakya@bf9faf7:backend/tests/backend/instruments/test_instrument_master.py
(ADR-047): BFO/SENSEX rows, lot sizes (NIFTY 65, SENSEX 20 on the 2026-10-02 list), futures kept; legacy dropped
expired contracts on refresh, this store keeps them (never deleted).
"""

from __future__ import annotations

import importlib.util
import io
import re
from collections import Counter
import dataclasses
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import Contract, ListedContract
from ofo_app.catalogue_store import (
    CatalogueStoreError,
    apply_update,
    check_storable,
    load_catalogue,
    parse_rows_naming_the_row,
    with_terms,
)

INSUFFICIENT_PRIVILEGE = "42501"
CATALOGUE_SQLSTATE = "OF006"
ALLOWLIST_SQLSTATE = "OF002"
IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 2, 10, 0, tzinfo=IST)  # the fixture's download day; fixed, never the wall clock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests_app" / "fixtures" / "zerodha_instruments_nifty_sensex_2026-10-02.csv"
TABLE = "public.catalogue_contracts"
BROKER = "public.broker_instruments"
#: Every contract column plus its Zerodha row (W-056): a refused write must leave both tables unchanged.
SNAPSHOT = text(
    f"SELECT c.id, c.exchange_segment, c.exchange_token, c.name, c.expiry, c.strike, c.instrument_type, "
    f"c.currently_listed, c.first_seen_at, c.last_seen_at, b.broker, b.broker_token, b.broker_symbol, "
    f"b.broker_segment, b.lot_size, b.tick_size, b.freeze_limit, b.seen_on, b.first_seen_at AS broker_first_seen_at, "
    f"b.last_seen_at AS broker_last_seen_at FROM {TABLE} AS c LEFT JOIN {BROKER} AS b ON b.contract_id = c.id "
    f"ORDER BY c.id, b.broker")


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0006_index_segments.py"  # the head (W-060)
    spec = importlib.util.spec_from_file_location("ofo_migration_0006_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _fixture_text() -> str:
    return "".join(line for line in FIXTURE.read_text(encoding="utf-8").splitlines(True) if not line.startswith("#"))


def _fixture() -> list[ListedContract]:
    return parse_rows_naming_the_row(io.StringIO(_fixture_text()))


def _in_scope(contracts: list[ListedContract]) -> list[ListedContract]:
    return [c for c in contracts if Catalogue._in_scope(c.contract)]


def _sym(c: ListedContract) -> str:
    return c.ref("zerodha").broker_symbol


def _token(c: ListedContract) -> str:
    return c.ref("zerodha").broker_token


def _by_symbol(contracts: list[ListedContract], symbol: str) -> ListedContract:
    return next(c for c in contracts if _sym(c) == symbol)


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


async def _expect_refused(conn: AsyncConnection, sql: str, expected: str, params: dict | None = None) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql), params or {})
    except DBAPIError as exc:
        got = _sqlstate(exc)
        assert got == expected, f"refused with SQLSTATE {got}, expected {expected}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")


async def _count(conn: AsyncConnection) -> int:
    return (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one()


async def _snapshot(conn: AsyncConnection) -> list[tuple]:
    return [tuple(r) for r in (await conn.execute(SNAPSHOT)).all()]


def _role(app_engine: AsyncEngine) -> str:
    role = app_engine.url.username
    assert role and re.fullmatch(r"[a-z_][a-z0-9_]*", role), role
    return role


# ---------------------------------------------------------------------------------------------------------------
# Pure checks (no database)
# ---------------------------------------------------------------------------------------------------------------


def test_database_scope_equals_the_domain_scope() -> None:
    from ofo.instruments.models import BROKER_CODES, EXCHANGE_SEGMENTS
    from ofo.instruments.parser import ZERODHA_EXCHANGE_TO_SEGMENT

    migration = _migration()
    assert dict(migration.SUPPORTED) == SUPPORTED_UNDERLYINGS == {"NIFTY": "NSE_FO", "SENSEX": "BSE_FO"}
    assert set(migration.EXCHANGE_SEGMENTS) == EXCHANGE_SEGMENTS
    assert dict(migration.ZERODHA_EXCHANGE_TO_SEGMENT) == ZERODHA_EXCHANGE_TO_SEGMENT
    assert set(migration.BROKER_CODES) == BROKER_CODES


def test_fixture_holds_real_nifty_and_sensex_rows() -> None:
    contracts = _fixture()
    scoped = _in_scope(contracts)
    # 24 rows: the NIFTY 50 index row (NSE) is outside V1 and skipped by the parser; BANKNIFTY (NFO) is outside scope
    assert len(contracts) == 23 and contracts.skipped_outside_v1 == 1 and len(scoped) == 22
    assert Counter((c.contract.name, c.contract.exchange_segment, c.contract.instrument_type) for c in scoped) == {
        ("NIFTY", "NSE_FO", "FUT"): 3, ("NIFTY", "NSE_FO", "CE"): 4, ("NIFTY", "NSE_FO", "PE"): 4,
        ("SENSEX", "BSE_FO", "FUT"): 3, ("SENSEX", "BSE_FO", "CE"): 4, ("SENSEX", "BSE_FO", "PE"): 4,
    }
    assert {c.ref("zerodha").lot_size for c in scoped if c.contract.name == "NIFTY"} == {65}
    assert {c.ref("zerodha").lot_size for c in scoped if c.contract.name == "SENSEX"} == {20}


@pytest.mark.parametrize(
    "column, bad, match",
    [("strike", "25O50", r"line 8: NIFTY26O0625050CE \(instrument_token 10461954\): unparseable strike"),
     ("tick_size", "", r"line 8: NIFTY26O0625050CE \(instrument_token 10461954\): empty tick_size")],
)
def test_a_row_whose_strike_or_tick_is_not_a_decimal_stops_the_load_naming_it(column: str, bad: str, match: str) -> None:
    good = "10461954,40867,NIFTY26O0625050CE,NIFTY,0,2026-10-06,25050,0.05,65,CE,NFO-OPT,NFO"
    parts = good.split(",")
    parts[{"strike": 6, "tick_size": 7}[column]] = bad
    broken = _fixture_text().replace(good, ",".join(parts))
    assert broken != _fixture_text()
    with pytest.raises(CatalogueStoreError, match=match):
        parse_rows_naming_the_row(io.StringIO(broken))


@pytest.mark.parametrize(
    "field, value, match",
    [("strike", Decimal("25000.125"), "does not fit its column exactly"),
     ("strike", Decimal("NaN"), "not a finite Decimal"),
     ("strike", 25000.0, "not Decimal"),
     ("strike", Decimal("1E10"), "does not fit its column exactly"),
     ("tick_size", Decimal("0.00005"), "does not fit its column exactly"),
     ("tick_size", 0.05, "not Decimal")],
)
def test_a_value_the_table_would_round_is_refused(field: str, value, match: str) -> None:
    contract = with_terms(_by_symbol(_fixture(), "NIFTY26O0625050CE"), **{field: value})
    with pytest.raises(CatalogueStoreError, match=match):
        check_storable(contract)
    check_storable(with_terms(contract, strike=Decimal("25050.50"), tick_size=Decimal("0.0500")))  # fits: accepted


@pytest.mark.parametrize("field", ["lot_size", "tick_size"])
def test_a_zero_lot_or_tick_on_a_non_index_contract_is_refused_by_the_store(field: str) -> None:
    option = _by_symbol(_fixture(), "NIFTY26O0625050CE")
    assert not option.contract.is_index()
    check_storable(option)  # a valid option passes
    with pytest.raises(CatalogueStoreError, match="zero lot or tick size is allowed only on an index contract"):
        check_storable(with_terms(option, **{field: Decimal("0") if field == "tick_size" else 0}))


def test_allowlist_block_shape_guard_fails_closed() -> None:
    migration = _migration()
    previous = migration.previous_allowlist_sql()
    extended = migration.extend_allowlist(previous)
    assert migration.ALLOWLIST_BLOCK_MARKER in extended and extended.count("CREATE OR REPLACE FUNCTION") == 1
    assert "-- 7. audit store" in extended and "-- 6. exactly SELECT" in extended
    with pytest.raises(RuntimeError, match="changed shape"):
        migration.extend_allowlist(previous.replace("    IF cardinality(problems) > 0 THEN\n", "", 1))
    with pytest.raises(RuntimeError, match="changed shape"):
        migration.extend_allowlist(extended)


def test_every_guarded_function_body_is_pinned_from_the_migrations_sql() -> None:
    migration = _migration()
    assert set(migration.PINNED_BODIES) == {
        "public.ledger_entries_trusted_clock()",
        "public.ofo_assert_within_clock_window(timestamptz, timestamptz)",
        "public.ofo_audit_payload_allowlist()",
        "public.ofo_audit_value_is_scalar(jsonb)",
        "public.ofo_audit_payload_conforms(jsonb, jsonb)",
        "public.audit_events_link_and_clock()",
        "public.audit_events_advance_anchor()",
        "public.catalogue_contracts_guard()",
        "public.catalogue_term_changes_guard()",
        "public.broker_instruments_guard()",
    }
    assert all(re.fullmatch(r"[0-9a-f]{32}", d) for d in migration.PINNED_BODIES.values())
    assert [(t, g) for _, t, _, g, _ in migration.GUARDED_TRIGGERS] == [
        ("ledger_entries_trusted_clock", 7), ("audit_events_link_and_clock", 7),
        ("audit_events_advance_anchor", 5), ("catalogue_contracts_guard", 31), ("catalogue_term_changes_guard", 31),
        ("broker_instruments_guard", 31),
    ]
    assert dict(migration.GUARDED_TABLES)["public.audit_anchor"] == ()
    assert migration.APP_UPDATE_COLUMNS == ("currently_listed", "expiry", "strike", "retired", "delisted")  # W-057
    assert migration.APP_INSERT_COLUMNS == ("exchange_segment", "exchange_token", "name", "expiry", "strike",
                                            "instrument_type")
    assert migration.APP_BROKER_UPDATE_COLUMNS == ("broker_symbol", "lot_size", "tick_size", "freeze_limit")
    assert dict(migration.GUARDED_TABLES)["public.broker_instruments"] == ("broker_instruments_guard",)


class _FakeConn:
    """No database: answers the catalogue SELECT with `rows` and records every write, so apply_update's planning
    (load, validate, domain update, self-check, write plan) runs as pure code."""

    def __init__(self, rows: list | None = None) -> None:
        self.rows = rows or []
        self.writes: list[tuple[str, object]] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        rows = self.rows

        class _Result:
            def all(self):
                return rows

            def scalar_one(self):
                return 0  # the post-write "contracts without a zerodha row" check

        if sql.startswith("SELECT d.id,"):  # delisted candidates for reinstatement (W-057, ADR-059): none here
            rows = []
        if sql.startswith(("SELECT c.id,", "SELECT d.id,", "SELECT count(*)")):
            return _Result()
        if not sql.startswith("SELECT pg_advisory_xact_lock"):
            self.writes.append((sql.split()[0], params))
        return None

    def begin_nested(self):
        """Emulates a SAVEPOINT: writes recorded inside it are discarded when it exits with an exception."""
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


async def test_planning_into_an_empty_catalogue_writes_every_in_scope_contract_without_a_database() -> None:
    """Reproduces CI run 36979206662 without PostgreSQL: the first write into an empty table must plan 22 inserts."""
    conn = _FakeConn()
    result = await apply_update(conn, _fixture(), as_of=AS_OF)
    assert (result.added, result.seen, result.newly_unlisted) == (22, 0, 0)
    assert [kind for kind, _ in conn.writes] == ["INSERT", "INSERT"]  # contracts, then their zerodha rows
    assert sorted(p["exchange_token"] for p in conn.writes[0][1]) == sorted(
        c.contract.exchange_token for c in _in_scope(_fixture()))
    assert set(conn.writes[0][1][0]) == {"exchange_segment", "exchange_token", "name", "expiry", "strike",
                                         "instrument_type"}
    assert sorted(p["broker_token"] for p in conn.writes[1][1]) == sorted(_token(c) for c in _in_scope(_fixture()))
    assert {p["broker"] for p in conn.writes[1][1]} == {"zerodha"}


async def test_planning_over_stored_rows_marks_seen_and_unlisted_without_a_database() -> None:
    from types import SimpleNamespace

    stored = [SimpleNamespace(id=i + 1, currently_listed=True, exchange_segment=c.contract.exchange_segment,
                             exchange_token=c.contract.exchange_token, name=c.contract.name, expiry=c.contract.expiry,
                             strike=c.contract.strike, instrument_type=c.contract.instrument_type,
                             **{k: getattr(c.ref("zerodha"), k) for k in (
                                 "broker", "broker_token", "broker_symbol", "broker_segment", "lot_size", "tick_size",
                                 "freeze_limit", "seen_on")}) for i, c in enumerate(_in_scope(_fixture()))]
    conn = _FakeConn(stored)
    next_day = [c for c in _fixture() if c.contract.expiry != date(2026, 10, 6)]
    result = await apply_update(conn, next_day, as_of=datetime(2026, 10, 7, 9, 0, tzinfo=IST))
    assert (result.added, result.seen, result.newly_unlisted, result.retired) == (0, 18, 4, 4)
    assert [kind for kind, _ in conn.writes] == ["UPDATE", "UPDATE", "UPDATE"]  # retired (W-057), seen, listed
    expired_ids = sorted(r.id for r in stored if r.expiry == date(2026, 10, 6))
    assert len(expired_ids) == 4 and conn.writes[0][1] == {"ids": expired_ids}  # the 4 expired: retired, ADR-057
    assert len(conn.writes[1][1]) == 18
    assert [(p["listed"], len(p["tokens"])) for _, p in conn.writes[2:]] == [(True, 18)]
    assert conn.writes[2][1]["segments"] == sorted(
        c.contract.exchange_segment for c in next_day if Catalogue._in_scope(c.contract))
    refused = _FakeConn(stored)
    with pytest.raises(ValueError, match="refused: would drop 8 of 11 live NIFTY contracts"):  # ADR-058: > 10%
        await apply_update(refused, _without_nifty_options(_fixture()), as_of=AS_OF)
    assert refused.writes == []


def _without_nifty_options(contracts: list[ListedContract]) -> list[ListedContract]:
    """A truncated list (ADR-058): the 8 NIFTY options of the fixture's 11 live NIFTY contracts are missing (72.7%)."""
    return [c for c in contracts if not (c.contract.name == "NIFTY" and c.contract.is_option())]


def _stored_rows() -> list:
    from types import SimpleNamespace

    return [SimpleNamespace(id=i + 1, currently_listed=True, exchange_segment=c.contract.exchange_segment,
                             exchange_token=c.contract.exchange_token, name=c.contract.name, expiry=c.contract.expiry,
                             strike=c.contract.strike, instrument_type=c.contract.instrument_type,
                             **{k: getattr(c.ref("zerodha"), k) for k in (
                                 "broker", "broker_token", "broker_symbol", "broker_segment", "lot_size", "tick_size",
                                 "freeze_limit", "seen_on")}) for i, c in enumerate(_in_scope(_fixture()))]


async def test_planning_a_revised_lot_size_writes_one_revise_without_a_database() -> None:
    conn = _FakeConn(_stored_rows())
    revised = [with_terms(c, lot_size=75) if _sym(c) == "NIFTY26OCTFUT" else c for c in _fixture()]
    result = await apply_update(conn, revised, as_of=AS_OF)
    assert (result.added, result.revised, result.seen, result.newly_unlisted) == (0, 1, 22, 0)
    assert [kind for kind, _ in conn.writes] == ["UPDATE", "UPDATE"]  # no expiry changed: no contract revise
    seen = conn.writes[0][1]
    assert len(seen) == 22
    # fixture row: 12468226,48704,NIFTY26OCTFUT,NIFTY,0,2026-10-27,0,0.1,65,FUT,NFO-FUT,NFO
    assert [p for p in seen if p["exchange_token"] == 48704] == [{
        "exchange_segment": "NSE_FO", "exchange_token": 48704, "broker": "zerodha", "broker_symbol": "NIFTY26OCTFUT",
        "lot_size": 75, "tick_size": Decimal("0.1"), "freeze_limit": None}]
    assert len(conn.writes[1][1]["tokens"]) == 22  # every present contract listed


# W-057: a strike change is a revision (ADR-057); another instrument_type is a token reuse, i.e. a new contract
# (ADR-059, tested in test_contract_identity_lifecycle.py); what stays refused is a Zerodha identity change.
@pytest.mark.parametrize("field, value", [("exchange_token", 1), ("broker_segment", "NFO-FUT"),
                                          ("broker_token", "1")])
async def test_planning_an_identity_change_is_refused_with_no_write(field: str, value) -> None:
    conn = _FakeConn(_stored_rows())
    changed = [with_terms(c, **{field: value}) if _sym(c) == "NIFTY26O0625050CE" else c for c in _fixture()]
    with pytest.raises(CatalogueStoreError, match=rf"NIFTY26O0625050CE .*{field} .* identity never changes"):
        await apply_update(conn, changed, as_of=AS_OF)
    assert conn.writes == []


async def test_forced_update_writes_its_audit_event_only_after_the_catalogue_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ofo.audit.catalogue import EventType
    from ofo_app import catalogue_store

    order: list[str] = []
    calls: list[tuple] = []

    async def fake_append(conn, event_type, **kwargs):
        order.append("audit")
        calls.append((conn, event_type, kwargs))

    monkeypatch.setattr(catalogue_store.audit_store, "append", fake_append)
    conn = _FakeConn(_stored_rows())
    original_execute = conn.execute

    async def tracking_execute(stmt, params=None):
        if not str(stmt).startswith("SELECT"):
            order.append("write")
        return await original_execute(stmt, params)

    conn.execute = tracking_execute  # type: ignore[method-assign]
    truncated = [c for c in _fixture() if _sym(c) != "NIFTY26O1325050CE"]
    await apply_update(conn, truncated, as_of=AS_OF, force=True, reason="broker delisted", actor="admin-1")
    assert order[-1] == "audit" and order.count("audit") == 1 and "write" in order[:-1]
    assert calls[0][0] is conn and calls[0][1] is EventType.ADMIN_CHANGE_RECORDED
    payload = calls[0][2]["payload"]
    assert payload["action"] == "catalogue_force_update" and payload["dropped_tradingsymbols"] == [["zerodha", "NIFTY26O1325050CE"]]
    assert calls[0][2]["actor"] == "admin-1" and calls[0][2]["timestamp"] == AS_OF

    # a failed catalogue write leaves no audit event
    calls.clear()
    failing = _FakeConn(_stored_rows())

    async def failing_execute(stmt, params=None):
        if str(stmt).startswith("UPDATE"):
            raise RuntimeError("write failed")
        return await _FakeConn.execute(failing, stmt, params)

    failing.execute = failing_execute  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="write failed"):
        await apply_update(failing, truncated, as_of=AS_OF, force=True, reason="broker delisted", actor="admin-1")
    assert calls == []


async def test_a_refused_audit_append_rolls_back_the_forced_delisting_without_a_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audit append runs inside the savepoint after the writes: when it raises, the writes are discarded."""
    from ofo_app import catalogue_store

    seen_writes: list[int] = []
    conn = _FakeConn(_stored_rows())

    async def refusing_append(c, event_type, **kwargs):
        seen_writes.append(len(conn.writes))
        raise ValueError("audit store refused")

    monkeypatch.setattr(catalogue_store.audit_store, "append", refusing_append)
    truncated = [c for c in _fixture() if _sym(c) != "NIFTY26O1325050CE"]
    with pytest.raises(ValueError, match="audit store refused"):
        await apply_update(conn, truncated, as_of=AS_OF, force=True, reason="broker delisted", actor="admin-1")
    assert seen_writes and seen_writes[0] > 0, "append must run after the writes, inside the savepoint"
    assert conn.writes == [], "the savepoint must discard the delisting when the audit append is refused"


# ---------------------------------------------------------------------------------------------------------------
# AC-2 through the database, as the application role
# ---------------------------------------------------------------------------------------------------------------


async def test_fixture_round_trips_unchanged_with_exact_decimals(app_engine: AsyncEngine) -> None:
    scoped = _in_scope(_fixture())
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            result = await apply_update(conn, _fixture(), as_of=AS_OF)
            assert (result.added, result.seen, result.newly_unlisted) == (22, 0, 0)
            assert await _count(conn) == 22  # the two out-of-scope rows are not stored
            catalogue = await load_catalogue(conn)
            stored = {e.id: e for e in catalogue.all_entries()}
            assert set(stored) == {c.id for c in scoped}
            for c in scoped:
                entry = stored[c.id]
                assert entry.contract == c.contract and entry.currently_listed
                stored_ref = entry.ref("zerodha")
                assert dataclasses.replace(stored_ref, seen_on=None) == c.ref("zerodha")
                assert stored_ref.seen_on is not None
                assert isinstance(entry.contract.strike, Decimal) and isinstance(entry.contract.tick_size, Decimal)
            raw = (await conn.execute(text(
                f"SELECT c.strike::text, b.tick_size::text, b.lot_size, c.expiry, c.first_seen_at = c.last_seen_at "
                f"FROM {TABLE} AS c JOIN {BROKER} AS b ON b.contract_id = c.id WHERE b.broker_symbol = 'NIFTY26OCTFUT'"
            ))).one()
            assert tuple(raw) == ("0.00", "0.1000", 65, date(2026, 10, 27), True)
            sensex = await conn.execute(text(f"SELECT c.strike::text, b.tick_size::text FROM {TABLE} AS c "
                                             f"JOIN {BROKER} AS b ON b.contract_id = c.id "
                                             "WHERE b.broker_symbol = 'SENSEX26O0882100PE'"))
            assert tuple(sensex.one()) == ("82100.00", "0.0500")
        finally:
            await trans.rollback()


async def check_truncated_update_refused(conn: AsyncConnection) -> None:
    """A truncated list (ADR-058: 8 of the 11 live NIFTY contracts missing, more than 10%) plus one new contract is
    refused, and every row keeps every column (listedness and stamps included); nothing is inserted."""
    before = await _snapshot(conn)
    truncated = _without_nifty_options(_fixture())
    extra = with_terms(_by_symbol(_fixture(), "NIFTY26O1325050CE"), exchange_token=99999, broker_token="99999999",
                       broker_symbol="NEW-CONTRACT")
    try:
        await apply_update(conn, truncated + [extra], as_of=AS_OF)
    except ValueError as exc:
        assert "refused: would drop 8 of 11 live NIFTY contracts" in str(exc), exc
        assert await _snapshot(conn) == before
        return
    raise AssertionError(f"not refused: truncated update ({len(await _snapshot(conn))} rows now)")


async def test_update_that_drops_an_unexpired_contract_is_refused_with_no_row_changed(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await check_truncated_update_refused(conn)
        finally:
            await trans.rollback()


async def test_expired_contracts_roll_off_as_unlisted_and_are_never_deleted(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            before = {r.broker_symbol: r for r in (await conn.execute(SNAPSHOT)).all()}
            next_day = [c for c in _fixture() if c.contract.expiry != date(2026, 10, 6)]  # the 4 NIFTY 6-Oct options expired
            result = await apply_update(conn, next_day, as_of=datetime(2026, 10, 7, 9, 0, tzinfo=IST))
            assert (result.added, result.seen, result.newly_unlisted) == (0, 18, 4)
            after = {r.broker_symbol: r for r in (await conn.execute(SNAPSHOT)).all()}
            assert set(after) == set(before) and len(after) == 22
            gone = {s for s, r in after.items() if not r.currently_listed}
            assert gone == {"NIFTY26O0625050CE", "NIFTY26O0625000CE", "NIFTY26O0625050PE", "NIFTY26O0625000PE"}
            for symbol, row in after.items():
                assert row.first_seen_at == before[symbol].first_seen_at
                if symbol in gone:
                    assert row.last_seen_at == before[symbol].last_seen_at
                else:
                    assert row.last_seen_at > before[symbol].last_seen_at
            retired = (await conn.execute(text(
                f"SELECT b.broker_symbol FROM {TABLE} AS c JOIN {BROKER} AS b ON b.contract_id = c.id "
                f"WHERE c.retired AND b.retired"))).scalars().all()
            assert set(retired) == gone  # W-057: expired before the load date -> retired, still stored (ADR-057)
            catalogue = await load_catalogue(conn)  # live contracts only
            assert len(catalogue.all_entries()) == 18 and all(e.currently_listed for e in catalogue.all_entries())
        finally:
            await trans.rollback()


HISTORY = "public.catalogue_term_changes"


async def test_revised_lot_size_follows_zerodha_with_one_history_row(
    app_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q257: lot_size 65 -> 75 on a stored contract is accepted; the row shows 75 and the history holds one row
    (token, field, old 65, new 75, database-stamped time)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            clock_before = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            revised = [with_terms(c, lot_size=75) if _sym(c) == "NIFTY26OCTFUT" else c for c in _fixture()]
            result = await apply_update(conn, revised, as_of=AS_OF)
            clock_after = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            assert (result.added, result.revised, result.newly_unlisted) == (0, 1, 0)
            lot = (await conn.execute(text(
                f"SELECT lot_size FROM {BROKER} WHERE broker = 'zerodha' AND broker_token = '12468226'"))).scalar_one()
            assert lot == 75
            history = (await conn.execute(text(
                f"SELECT c.exchange_segment, c.exchange_token, h.broker, h.field, h.old_value, h.new_value, h.changed_at "
                f"FROM {HISTORY} AS h JOIN {TABLE} AS c ON c.id = h.contract_id"))).all()
            assert [tuple(h)[:6] for h in history] == [("NSE_FO", 48704, "zerodha", "lot_size", "65", "75")]
            assert clock_before <= history[0].changed_at <= clock_after
            catalogue = await load_catalogue(conn)
            entry = catalogue.get(_by_symbol(_fixture(), "NIFTY26OCTFUT").id)
            assert entry.contract.lot_size == 75 and entry.ref("zerodha").lot_size == 75
            with capsys.disabled():
                print(f"\nW-053 PROOF revise NIFTY26OCTFUT lot_size row={lot} history={[tuple(h) for h in history]}")
        finally:
            await trans.rollback()


# W-057: strike is a revision (ADR-057) and instrument_type a token reuse (ADR-059); a Zerodha token change stays refused
@pytest.mark.parametrize("field, value", [("broker_token", "1")])
async def test_an_identity_change_is_refused_with_nothing_written(
    app_engine: AsyncEngine, capsys: pytest.CaptureFixture[str], field: str, value
) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            before = await _snapshot(conn)
            changed = [with_terms(c, **{field: value}) if _sym(c) == "NIFTY26O0625050CE" else c
                       for c in _fixture()]
            with pytest.raises(CatalogueStoreError, match=rf"NIFTY26O0625050CE .*{field} .* identity never changes"):
                await apply_update(conn, changed, as_of=AS_OF)
            after = await _snapshot(conn)
            history = (await conn.execute(text(f"SELECT count(*) FROM {HISTORY}"))).scalar_one()
            assert after == before and history == 0
            with capsys.disabled():
                print(f"\nW-053 PROOF identity change {field} refused; rows identical={after == before} history={history}")
        finally:
            await trans.rollback()


async def test_history_dates_are_iso_whatever_the_session_datestyle(app_engine: AsyncEngine) -> None:
    """The guard pins DateStyle: a 'SQL, DMY' session revising an expiry still records YYYY-MM-DD."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await conn.execute(text("SET LOCAL DateStyle = 'SQL, DMY'"))
            assert (await conn.execute(text("SELECT DATE '2026-10-27'::text"))).scalar_one() == "27/10/2026"
            revised = [with_terms(c, expiry=date(2026, 10, 28)) if _sym(c) == "NIFTY26OCTFUT" else c
                       for c in _fixture()]
            await apply_update(conn, revised, as_of=AS_OF)
            history = (await conn.execute(text(f"SELECT broker, field, old_value, new_value FROM {HISTORY}"))).all()
            assert [tuple(h) for h in history] == [(None, "expiry", "2026-10-27", "2026-10-28")]
        finally:
            await trans.rollback()


async def test_a_refused_audit_append_leaves_the_catalogue_and_audit_log_unchanged(
    app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ofo_app import catalogue_store
    from ofo_app.audit_store import read_anchor

    async def refusing_append(conn, event_type, **kwargs):
        raise ValueError("audit store refused")

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            before, head = await _snapshot(conn), await read_anchor(conn)
            monkeypatch.setattr(catalogue_store.audit_store, "append", refusing_append)
            truncated = [c for c in _fixture() if _sym(c) != "NIFTY26O1325050CE"]
            with pytest.raises(ValueError, match="audit store refused"):
                await apply_update(conn, truncated, as_of=AS_OF, force=True, reason="broker delisted", actor="admin-1")
            assert await _snapshot(conn) == before and await read_anchor(conn) == head
        finally:
            await trans.rollback()


async def test_forced_update_unlists_and_appends_one_audit_event_on_the_same_connection(app_engine: AsyncEngine) -> None:
    from ofo_app.audit_store import load_log, read_anchor

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            head = await read_anchor(conn)
            now = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            truncated = [c for c in _fixture() if _sym(c) != "NIFTY26O1325050CE"]
            await apply_update(conn, truncated, as_of=now, force=True, reason="broker delisted", actor="admin-1")
            listed = (await conn.execute(text(
                f"SELECT currently_listed FROM {TABLE} WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'NIFTY26O1325050CE')"))).scalar_one()
            assert listed is False
            log, anchor = await load_log(conn)
            assert anchor.count == head.count + 1 and log.verify(anchor).ok
            event = log.events[-1]
            from ofo.audit.catalogue import EventType

            assert event.event_type is EventType.ADMIN_CHANGE_RECORDED
            assert event.payload["action"] == "catalogue_force_update" and event.actor == "admin-1"
        finally:
            await trans.rollback()


async def test_app_role_cannot_delete_or_rewrite_contracts(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await _expect_refused(conn, f"DELETE FROM {TABLE}", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"TRUNCATE {TABLE}", INSUFFICIENT_PRIVILEGE)
            # W-057: strike is app-updatable since 0005 (a revision, ADR-057); name never is
            await _expect_refused(conn, f"UPDATE {TABLE} SET name = 'SENSEX'", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET last_seen_at = now()", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(
                conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, strike, instrument_type, "
                      "currently_listed) VALUES ('NSE_FO', 1, 'NIFTY', 0, 'FUT', FALSE)", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"ALTER TABLE {TABLE} DISABLE TRIGGER ALL", INSUFFICIENT_PRIVILEGE)
            cid = (await conn.execute(text(f"SELECT min(id) FROM {TABLE}"))).scalar_one()
            await _expect_refused(conn, f"INSERT INTO {HISTORY} (contract_id, broker, field, old_value, new_value) "
                                        f"VALUES ({cid}, 'zerodha', 'lot_size', '65', '75')", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"DELETE FROM {BROKER}", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"TRUNCATE {BROKER}", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET broker_token = '1'", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET seen_on = '2000-01-01'", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {HISTORY} SET new_value = 'x'", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"DELETE FROM {HISTORY}", INSUFFICIENT_PRIVILEGE)
            assert await _count(conn) == 22
        finally:
            await trans.rollback()


async def check_owner_cannot_delete_or_change_terms(conn: AsyncConnection) -> None:
    """Even the owner (who bypasses grants) cannot delete a contract, change its identity, or rewrite the term-change
    history: the triggers refuse.

    The DELETE targets a contract with no broker row and no history row, inserted here by the owner (a full V1
    identity), so the guard is the ONLY barrier on it: a contract with a broker row is also held by the
    broker_instruments foreign key (23503), which would hide a weakened guard (W-056 fix round 2)."""
    await conn.execute(text(f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, expiry, strike, "
                            "instrument_type) VALUES ('NSE_FO', 99997, 'NIFTY', '2026-10-27', 25000, 'CE')"))
    bare = "exchange_segment = 'NSE_FO' AND exchange_token = 99997"
    referenced = (await conn.execute(text(
        f"SELECT (SELECT count(*) FROM {BROKER} b JOIN {TABLE} c ON c.id = b.contract_id WHERE c.{bare.replace(' AND ', ' AND c.')}) "
        f"+ (SELECT count(*) FROM public.catalogue_term_changes h JOIN {TABLE} c ON c.id = h.contract_id "
        f"WHERE c.{bare.replace(' AND ', ' AND c.')})"))).scalar_one()
    assert referenced == 0, "the deleted row must have no foreign-key references, or the guard is not the only barrier"
    await _expect_refused(conn, f"DELETE FROM {TABLE} WHERE {bare}", CATALOGUE_SQLSTATE)
    await _expect_refused(conn, f"UPDATE {TABLE} SET exchange_token = 1 WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'NIFTY26OCTFUT')",
                          CATALOGUE_SQLSTATE)
    await _expect_refused(conn, f"UPDATE {TABLE} SET instrument_type = 'CE' WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'NIFTY26OCTFUT')",
                          CATALOGUE_SQLSTATE)


async def test_owner_cannot_rewrite_or_delete_term_change_history(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await conn.execute(text(f"UPDATE {BROKER} SET lot_size = 75 WHERE broker_symbol = 'NIFTY26OCTFUT'"))
            assert (await conn.execute(text(f"SELECT count(*) FROM {HISTORY}"))).scalar_one() == 1
            await _expect_refused(conn, f"UPDATE {HISTORY} SET new_value = '65'", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"DELETE FROM {HISTORY}", CATALOGUE_SQLSTATE)
        finally:
            await trans.rollback()


async def test_owner_cannot_delete_or_change_terms_and_cannot_backdate_first_seen(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await check_owner_cannot_delete_or_change_terms(conn)
            stamp = (await conn.execute(text(f"SELECT first_seen_at FROM {TABLE} WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'NIFTY26OCTFUT')"))).scalar_one()
            await conn.execute(text(f"UPDATE {TABLE} SET first_seen_at = '2000-01-01' WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'NIFTY26OCTFUT')"))
            again = (await conn.execute(text(f"SELECT first_seen_at FROM {TABLE} WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'NIFTY26OCTFUT')"))).scalar_one()
            assert again == stamp
        finally:
            await trans.rollback()


async def test_stored_nan_strike_stops_the_reload_naming_the_row(admin_engine: AsyncEngine) -> None:
    """Fail closed on read: the CHECK forbids NaN; with it dropped by the owner (rolled back) load_catalogue names the row."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            constraint = (await conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'public.catalogue_contracts'::regclass "
                "AND pg_get_constraintdef(oid) LIKE '%strike%NaN%'"))).scalar_one()
            await conn.execute(text(f'ALTER TABLE {TABLE} DROP CONSTRAINT "{constraint}"'))
            await conn.execute(text(f"ALTER TABLE {TABLE} DISABLE TRIGGER catalogue_contracts_guard"))
            await conn.execute(text(f"UPDATE {TABLE} SET strike = 'NaN' WHERE id = (SELECT contract_id FROM public.broker_instruments WHERE broker_symbol = 'SENSEX26O1582000PE')"))
            with pytest.raises(CatalogueStoreError, match=r"SENSEX26O1582000PE \(instrument_token 282293253\): strike NaN"):
                await load_catalogue(conn)
        finally:
            await trans.rollback()


async def test_head_allowlist_function_holds_blocks_one_to_eight(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        body = (await conn.execute(text("SELECT pg_get_functiondef('public.ofo_assert_app_role_allowlist'::regproc)"))).scalar_one()
    markers = ["-- 1. attributes", "-- 2. membership", "-- 3. ownership", "-- 4. database privileges",
               "-- 5. schema public", "-- 6. exactly SELECT", "-- 7. audit store", "-- 8. catalogue store",
               "-- 9. broker instruments"]
    missing = [m for m in markers if m not in body]
    assert not missing, missing


async def check_allowlist(conn: AsyncConnection, role: str) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text("SELECT public.ofo_assert_app_role_allowlist(:r, 'post')"), {"r": role})
    except DBAPIError as exc:
        assert _sqlstate(exc) == ALLOWLIST_SQLSTATE, f"unexpected error {_sqlstate(exc)}: {exc}"
        raise AssertionError(str(exc.orig)) from None


async def test_allowlist_holds_with_the_catalogue_table(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn, conn.begin():
        await check_allowlist(conn, _role(app_engine))


async def test_live_function_bodies_equal_the_pins(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        for signature, digest in _migration().PINNED_BODIES.items():
            live = (await conn.execute(text("SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure(:f)"),
                                       {"f": signature})).scalar_one()
            assert live == digest, signature


# ---------------------------------------------------------------------------------------------------------------
# Mutation tests: weaken one guard (rolled back) and show the matching check turns red
# ---------------------------------------------------------------------------------------------------------------

_ANCHOR_BODY = """
CREATE OR REPLACE FUNCTION public.audit_events_advance_anchor() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $fn$ BEGIN RETURN NULL; END $fn$"""
_LEDGER_BODY = """
CREATE OR REPLACE FUNCTION public.ledger_entries_trusted_clock() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp AS $fn$ BEGIN RETURN NEW; END $fn$"""
_GUARD_BODY = """
CREATE OR REPLACE FUNCTION public.catalogue_contracts_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $fn$ BEGIN IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $fn$"""
_BROKER_BODY = """
CREATE OR REPLACE FUNCTION public.broker_instruments_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp SET DateStyle = 'ISO, YMD'
AS $fn$ BEGIN IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $fn$"""
_HISTORY_BODY = """
CREATE OR REPLACE FUNCTION public.catalogue_term_changes_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp AS $fn$ BEGIN IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $fn$"""


@pytest.mark.parametrize(
    "mutation, match",
    [
        ('GRANT DELETE ON public.catalogue_contracts TO "{role}"', "has DELETE on catalogue_contracts"),
        ('GRANT TRUNCATE ON public.catalogue_contracts TO "{role}"', "has TRUNCATE on catalogue_contracts"),
        ('GRANT INSERT ON public.catalogue_contracts TO "{role}"', "has table-wide INSERT on catalogue_contracts"),
        ('GRANT UPDATE (name) ON public.catalogue_contracts TO "{role}"', "has UPDATE on catalogue_contracts column name"),
        ('GRANT UPDATE (last_seen_at) ON public.catalogue_contracts TO "{role}"',
         "has UPDATE on catalogue_contracts column last_seen_at"),
        ('GRANT INSERT (currently_listed) ON public.catalogue_contracts TO "{role}"',
         "has INSERT on catalogue_contracts column currently_listed"),
        ('GRANT INSERT (id) ON public.catalogue_contracts TO "{role}"', "has INSERT on catalogue_contracts column id"),
        ('REVOKE INSERT (strike) ON public.catalogue_contracts FROM "{role}"',
         "lacks INSERT on catalogue_contracts column strike"),
        ('REVOKE UPDATE (currently_listed) ON public.catalogue_contracts FROM "{role}"',
         "lacks UPDATE on catalogue_contracts column currently_listed"),
        ('GRANT SELECT ON SEQUENCE public.catalogue_contracts_id_seq TO "{role}"',
         "has SELECT on the catalogue id sequence"),
        ('GRANT EXECUTE ON FUNCTION public.catalogue_contracts_guard() TO "{role}"',
         "has EXECUTE on public.catalogue_contracts_guard"),
        ("ALTER TABLE public.catalogue_contracts DISABLE TRIGGER catalogue_contracts_guard",
         "trigger catalogue_contracts_guard is missing or not enabled"),
        (("ALTER TABLE public.catalogue_contracts ADD COLUMN note TEXT",
          'GRANT INSERT (note) ON public.catalogue_contracts TO "{role}"'),
         "has INSERT on catalogue_contracts column note"),
        # (a) tgtype: each guarded trigger re-created with the wrong timing / event
        ("CREATE OR REPLACE TRIGGER audit_events_link_and_clock BEFORE UPDATE ON public.audit_events "
         "FOR EACH ROW EXECUTE FUNCTION public.audit_events_link_and_clock()",
         "trigger audit_events_link_and_clock is not BEFORE ROW INSERT"),
        ("CREATE OR REPLACE TRIGGER audit_events_advance_anchor BEFORE INSERT ON public.audit_events "
         "FOR EACH ROW EXECUTE FUNCTION public.audit_events_advance_anchor()",
         "trigger audit_events_advance_anchor is not AFTER ROW INSERT"),
        ("CREATE OR REPLACE TRIGGER ledger_entries_trusted_clock AFTER INSERT ON public.ledger_entries "
         "FOR EACH ROW EXECUTE FUNCTION public.ledger_entries_trusted_clock()",
         "trigger ledger_entries_trusted_clock is not BEFORE ROW INSERT"),
        ("CREATE OR REPLACE TRIGGER catalogue_contracts_guard BEFORE INSERT OR UPDATE ON public.catalogue_contracts "
         "FOR EACH ROW EXECUTE FUNCTION public.catalogue_contracts_guard()",
         "trigger catalogue_contracts_guard is not BEFORE ROW INSERT OR UPDATE OR DELETE"),
        ("CREATE OR REPLACE TRIGGER ledger_entries_trusted_clock BEFORE INSERT ON public.ledger_entries "
         "FOR EACH ROW EXECUTE FUNCTION public.audit_events_advance_anchor()",
         "trigger ledger_entries_trusted_clock does not call public.ledger_entries_trusted_clock"),
        ("CREATE OR REPLACE TRIGGER catalogue_term_changes_guard BEFORE INSERT ON public.catalogue_term_changes "
         "FOR EACH ROW EXECUTE FUNCTION public.catalogue_term_changes_guard()",
         "trigger catalogue_term_changes_guard is not BEFORE ROW INSERT OR UPDATE OR DELETE"),
        # item 2: WHEN condition, column list, arguments, extra triggers
        ("CREATE OR REPLACE TRIGGER catalogue_contracts_guard BEFORE INSERT OR UPDATE OR DELETE ON "
         "public.catalogue_contracts FOR EACH ROW WHEN (false) EXECUTE FUNCTION public.catalogue_contracts_guard()",
         "trigger catalogue_contracts_guard has a WHEN condition"),
        ("CREATE OR REPLACE TRIGGER audit_events_link_and_clock BEFORE INSERT ON public.audit_events "
         "FOR EACH ROW WHEN (false) EXECUTE FUNCTION public.audit_events_link_and_clock()",
         "trigger audit_events_link_and_clock has a WHEN condition"),
        ("CREATE OR REPLACE TRIGGER catalogue_contracts_guard BEFORE INSERT OR UPDATE OF currently_listed OR DELETE "
         "ON public.catalogue_contracts FOR EACH ROW EXECUTE FUNCTION public.catalogue_contracts_guard()",
         "trigger catalogue_contracts_guard is limited to a column list"),
        ("CREATE OR REPLACE TRIGGER audit_events_link_and_clock BEFORE INSERT ON public.audit_events "
         "FOR EACH ROW EXECUTE FUNCTION public.audit_events_link_and_clock('x')",
         "trigger audit_events_link_and_clock has arguments"),
        ("CREATE TRIGGER zz_extra BEFORE UPDATE ON public.catalogue_contracts "
         "FOR EACH ROW EXECUTE FUNCTION public.ledger_entries_trusted_clock()",
         "table public.catalogue_contracts has an unexpected trigger"),
        ("CREATE TRIGGER zz_extra BEFORE UPDATE ON public.audit_anchor "
         "FOR EACH ROW EXECUTE FUNCTION public.ledger_entries_trusted_clock()",
         "table public.audit_anchor has an unexpected trigger"),
        ("CREATE TRIGGER zz_extra AFTER INSERT ON public.ledger_entries "
         "FOR EACH ROW EXECUTE FUNCTION public.ledger_entries_trusted_clock()",
         "table public.ledger_entries has an unexpected trigger"),
        # rewrite rules on a guarded table; the guard's pinned DateStyle
        ("CREATE RULE zz_rule AS ON UPDATE TO public.catalogue_contracts DO INSTEAD NOTHING",
         "table public.catalogue_contracts has a rewrite rule"),
        ("CREATE RULE zz_rule AS ON INSERT TO public.audit_events DO INSTEAD NOTHING",
         "table public.audit_events has a rewrite rule"),
        ("ALTER FUNCTION public.catalogue_contracts_guard() RESET DateStyle",
         "function public.catalogue_contracts_guard does not pin DateStyle"),
        # the term-change history: SELECT only, nothing on its sequence; guard SECURITY DEFINER
        ('GRANT INSERT (field) ON public.catalogue_term_changes TO "{role}"',
         "has INSERT on catalogue_term_changes column field"),
        ('GRANT UPDATE (new_value) ON public.catalogue_term_changes TO "{role}"',
         "has UPDATE on catalogue_term_changes column new_value"),
        ('GRANT DELETE ON public.catalogue_term_changes TO "{role}"', "has DELETE on catalogue_term_changes"),
        ('GRANT USAGE ON SEQUENCE public.catalogue_term_changes_id_seq TO "{role}"',
         "has USAGE on the term-change id sequence"),
        ('GRANT UPDATE (instrument_type) ON public.catalogue_contracts TO "{role}"',
         "has UPDATE on catalogue_contracts column instrument_type"),
        ('REVOKE UPDATE (expiry) ON public.catalogue_contracts FROM "{role}"',
         "lacks UPDATE on catalogue_contracts column expiry"),
        # W-056 block 9 and the moved columns
        ("ALTER TABLE public.catalogue_contracts ADD COLUMN instrument_token BIGINT",
         "catalogue_contracts holds a broker column"),
        ("ALTER TABLE public.catalogue_contracts ADD COLUMN tradingsymbol TEXT",
         "catalogue_contracts holds a broker column"),
        ('GRANT DELETE ON public.broker_instruments TO "{role}"', "has DELETE on broker_instruments"),
        ('GRANT TRUNCATE ON public.broker_instruments TO "{role}"', "has TRUNCATE on broker_instruments"),
        ('GRANT UPDATE (broker_token) ON public.broker_instruments TO "{role}"',
         "has UPDATE on broker_instruments column broker_token"),
        ('GRANT UPDATE (seen_on) ON public.broker_instruments TO "{role}"',
         "has UPDATE on broker_instruments column seen_on"),
        ('REVOKE UPDATE (lot_size) ON public.broker_instruments FROM "{role}"',
         "lacks UPDATE on broker_instruments column lot_size"),
        ('ALTER TABLE public.broker_instruments OWNER TO "{role}"',
         "table public.broker_instruments is not owned by the catalogue table owner"),
        ('GRANT EXECUTE ON FUNCTION public.broker_instruments_guard() TO "{role}"',
         "has EXECUTE on public.broker_instruments_guard"),
        ("ALTER TABLE public.broker_instruments DISABLE TRIGGER broker_instruments_guard",
         "trigger broker_instruments_guard is missing or not enabled"),
        ("ALTER FUNCTION public.broker_instruments_guard() SECURITY INVOKER",
         "function public.broker_instruments_guard is not SECURITY DEFINER"),
        (_BROKER_BODY, "function public.broker_instruments_guard body differs from its pinned body"),
        ("ALTER FUNCTION public.catalogue_contracts_guard() SECURITY INVOKER",
         "function public.catalogue_contracts_guard is not SECURITY DEFINER"),
        ('GRANT EXECUTE ON FUNCTION public.catalogue_term_changes_guard() TO "{role}"',
         "has EXECUTE on public.catalogue_term_changes_guard"),
        # (b) pinned bodies: each replaced, attributes kept, so only the body differs
        (_HISTORY_BODY, "function public.catalogue_term_changes_guard body differs from its pinned body"),
        (_ANCHOR_BODY, "function public.audit_events_advance_anchor body differs from its pinned body"),
        (_LEDGER_BODY, "function public.ledger_entries_trusted_clock body differs from its pinned body"),
        (_GUARD_BODY, "function public.catalogue_contracts_guard body differs from its pinned body"),
    ],
    ids=lambda v: str(v).strip()[:60],
)
async def test_mutation_weakening_a_guard_is_refused_by_the_allowlist(
    admin_engine: AsyncEngine, app_engine: AsyncEngine, mutation: str | tuple[str, ...], match: str
) -> None:
    role = _role(app_engine)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await check_allowlist(conn, role)
            for statement in (mutation if isinstance(mutation, tuple) else (mutation,)):
                await conn.execute(text(statement.format(role=role)))
            with pytest.raises(AssertionError, match=match):
                await check_allowlist(conn, role)
        finally:
            await trans.rollback()


@pytest.mark.parametrize(
    "mutation",
    [_GUARD_BODY, "ALTER TABLE public.catalogue_contracts DISABLE TRIGGER catalogue_contracts_guard"],
    ids=["guard-body-replaced", "guard-disabled"],
)
async def test_mutation_weakening_the_guard_lets_the_owner_delete(admin_engine: AsyncEngine, mutation: str) -> None:
    """The behavioural check turns red too: without the guard the owner's DELETE is not refused."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await conn.execute(text(mutation))
            with pytest.raises(AssertionError, match="not refused: DELETE"):
                await check_owner_cannot_delete_or_change_terms(conn)
        finally:
            await trans.rollback()


async def test_mutation_bypassing_the_q244_guard_turns_the_refusal_check_red(
    app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store whose ADR-058 counting guard is bypassed no longer refuses the truncated list, and the store then
    writes (delisting the missing contracts): the refusal check goes red."""
    from ofo.instruments import catalogue as domain_catalogue

    def no_guard(*args, **kwargs):
        return None

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await check_truncated_update_refused(conn)
            monkeypatch.setattr(domain_catalogue, "_refuse_truncation", no_guard)  # the guards live in the domain
            with pytest.raises(AssertionError, match="not refused: truncated update"):
                await check_truncated_update_refused(conn)
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Core proof on the real file (network; runs in CI with OFO_REQUIRE_DB_TESTS=1)
# ---------------------------------------------------------------------------------------------------------------

PROOF_CATEGORIES = [("NIFTY", "NSE_FO", t) for t in ("CE", "PE", "FUT")] + [
    ("SENSEX", "BSE_FO", t) for t in ("CE", "PE", "FUT")]


@pytest.mark.network
async def test_real_zerodha_file_round_trips_and_a_truncated_update_is_refused(
    app_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    from ofo.instruments.downloader import download_instruments_csv

    raw = download_instruments_csv()
    contracts = parse_rows_naming_the_row(io.StringIO(raw))
    in_scope = _in_scope(contracts)

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            as_of = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            # ADR-059 / REQ-053: the store skips in-scope rows already expired on the load date (the live file keeps
            # listing a just-expired expiry for a day); the oracle applies the same rule (Catalogue.update's
            # `expiry is None or expiry >= update_date`, which is inline there and so cannot be imported)
            load_day = as_of.astimezone(IST).date()
            scoped = [c for c in in_scope if c.contract.expiry is None or c.contract.expiry >= load_day]
            excluded_expired = len(in_scope) - len(scoped)
            assert excluded_expired >= 0
            file_counts = Counter(
                (c.contract.name, c.contract.exchange_segment, c.contract.instrument_type) for c in scoped)
            assert all(file_counts[k] > 0 for k in PROOF_CATEGORIES), file_counts
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            result = await apply_update(conn, contracts, as_of=as_of)
            rows = (await conn.execute(text(
                f"SELECT name, exchange_segment, instrument_type, count(*) FROM {TABLE} GROUP BY 1, 2, 3"))).all()
            table_counts = Counter({(r[0], r[1], r[2]): r[3] for r in rows})
            assert table_counts == file_counts
            assert result.added == len(scoped) == sum(table_counts.values())

            # 5 named contracts, chosen deterministically from the file: the nearest NIFTY and SENSEX futures and
            # the lowest-exchange-token NIFTY CE, NIFTY PE and SENSEX CE of the nearest expiry
            def first(name: str, kind: str) -> ListedContract:
                pool = [c for c in scoped if c.contract.name == name and c.contract.instrument_type == kind]
                nearest = min(c.contract.expiry for c in pool)
                return min((c for c in pool if c.contract.expiry == nearest), key=lambda c: c.contract.exchange_token)

            named = [first("NIFTY", "FUT"), first("SENSEX", "FUT"), first("NIFTY", "CE"), first("NIFTY", "PE"),
                     first("SENSEX", "CE")]
            lines = [f"W-053 PROOF file rows={len(contracts)} in_scope={len(in_scope)} excluded_expired={excluded_expired} loaded={len(scoped)} table={sum(table_counts.values())}"]
            lines += [f"W-053 PROOF count {k[0]}/{k[1]}/{k[2]} file={file_counts[k]} table={table_counts[k]}"
                      for k in PROOF_CATEGORIES]
            for c in named:
                row = (await conn.execute(text(
                    f"SELECT c.exchange_segment, c.exchange_token, c.name, c.expiry, c.strike, c.instrument_type, "
                    f"b.broker_token, b.broker_symbol, b.broker_segment, b.lot_size, b.tick_size FROM {TABLE} AS c "
                    f"JOIN {BROKER} AS b ON b.contract_id = c.id AND b.broker = 'zerodha' "
                    f"WHERE c.exchange_segment = :s AND c.exchange_token = :t"),
                    {"s": c.contract.exchange_segment, "t": c.contract.exchange_token})).one()
                ref = c.ref("zerodha")
                for field in ("exchange_segment", "exchange_token", "name", "expiry", "strike", "instrument_type"):
                    assert getattr(row, field) == getattr(c.contract, field), (_sym(c), field)
                for field in ("broker_token", "broker_symbol", "broker_segment", "lot_size", "tick_size"):
                    assert getattr(row, field) == getattr(ref, field), (_sym(c), field)
                assert isinstance(row.strike, Decimal) and isinstance(row.tick_size, Decimal)
                lines.append(f"W-053 PROOF match {ref.broker_symbol} token={ref.broker_token} strike={row.strike} "
                             f"expiry={row.expiry} lot={row.lot_size} tick={row.tick_size} (file strike="
                             f"{c.contract.strike} tick={ref.tick_size})")

            # the refused update: one unexpired contract removed from a copy
            before = await _snapshot(conn)
            victim = named[2]
            assert victim.contract.expiry >= as_of.astimezone(IST).date()
            nifty = [c for c in scoped if c.contract.name == "NIFTY"]
            cut = {c.id for c in nifty[: len(nifty) * 4 // 10]} | {victim.id}  # ADR-058: a 40% cut is refused
            copy = [c for c in contracts if c.id not in cut]
            with pytest.raises(ValueError, match="refused: would drop .* live NIFTY contracts"):
                await apply_update(conn, copy, as_of=as_of)
            after = await _snapshot(conn)
            assert after == before
            lines.append(f"W-053 PROOF refused removing {len(cut)} NIFTY incl. {_sym(victim)} (expiry {victim.contract.expiry}); "
                         f"rows before={len(before)} after={len(after)} identical={after == before}")
            with capsys.disabled():
                print("\n" + "\n".join(lines))
        finally:
            await trans.rollback()
