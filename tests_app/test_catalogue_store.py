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
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import Contract
from ofo_app.catalogue_store import (
    CatalogueStoreError,
    apply_update,
    check_storable,
    load_catalogue,
    parse_rows_naming_the_row,
)

INSUFFICIENT_PRIVILEGE = "42501"
CATALOGUE_SQLSTATE = "OF006"
ALLOWLIST_SQLSTATE = "OF002"
IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 2, 10, 0, tzinfo=IST)  # the fixture's download day; fixed, never the wall clock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests_app" / "fixtures" / "zerodha_instruments_nifty_sensex_2026-10-02.csv"
TABLE = "public.catalogue_contracts"
SNAPSHOT = text(f"SELECT * FROM {TABLE} ORDER BY id")
FIELDS = ("tradingsymbol", "strike", "expiry", "lot_size", "tick_size", "instrument_type", "exchange", "name",
          "exchange_token", "segment")


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0003_catalogue_store.py"
    spec = importlib.util.spec_from_file_location("ofo_migration_0003_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _fixture_text() -> str:
    return "".join(line for line in FIXTURE.read_text(encoding="utf-8").splitlines(True) if not line.startswith("#"))


def _fixture() -> list[Contract]:
    return parse_rows_naming_the_row(io.StringIO(_fixture_text()))


def _in_scope(contracts: list[Contract]) -> list[Contract]:
    return [c for c in contracts if Catalogue._in_scope(c)]


def _by_symbol(contracts: list[Contract], symbol: str) -> Contract:
    return next(c for c in contracts if c.tradingsymbol == symbol)


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
    assert dict(_migration().SUPPORTED) == SUPPORTED_UNDERLYINGS == {"NIFTY": "NFO", "SENSEX": "BFO"}


def test_fixture_holds_real_nifty_and_sensex_rows() -> None:
    contracts = _fixture()
    scoped = _in_scope(contracts)
    assert len(contracts) == 24 and len(scoped) == 22
    assert Counter((c.name, c.exchange, c.instrument_type) for c in scoped) == {
        ("NIFTY", "NFO", "FUT"): 3, ("NIFTY", "NFO", "CE"): 4, ("NIFTY", "NFO", "PE"): 4,
        ("SENSEX", "BFO", "FUT"): 3, ("SENSEX", "BFO", "CE"): 4, ("SENSEX", "BFO", "PE"): 4,
    }
    assert {c.lot_size for c in scoped if c.name == "NIFTY"} == {65}
    assert {c.lot_size for c in scoped if c.name == "SENSEX"} == {20}


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
    contract = replace(_by_symbol(_fixture(), "NIFTY26O0625050CE"), **{field: value})
    with pytest.raises(CatalogueStoreError, match=match):
        check_storable(contract)
    check_storable(replace(contract, strike=Decimal("25050.50"), tick_size=Decimal("0.0500")))  # fits: accepted


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
    }
    assert all(re.fullmatch(r"[0-9a-f]{32}", d) for d in migration.PINNED_BODIES.values())
    assert [(t, g) for _, t, _, g, _ in migration.GUARDED_TRIGGERS] == [
        ("ledger_entries_trusted_clock", 7), ("audit_events_link_and_clock", 7),
        ("audit_events_advance_anchor", 5), ("catalogue_contracts_guard", 31),
    ]


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
            stored = {e.contract.instrument_token: e for e in catalogue.all_entries()}
            assert set(stored) == {c.instrument_token for c in scoped}
            for c in scoped:
                entry = stored[c.instrument_token]
                assert entry.contract == c and entry.currently_listed
                assert isinstance(entry.contract.strike, Decimal) and isinstance(entry.contract.tick_size, Decimal)
            raw = (await conn.execute(text(
                f"SELECT strike::text, tick_size::text, lot_size, expiry, first_seen_at = last_seen_at "
                f"FROM {TABLE} WHERE tradingsymbol = 'NIFTY26OCTFUT'"
            ))).one()
            assert tuple(raw) == ("0.00", "0.1000", 65, date(2026, 10, 27), True)
            sensex = await conn.execute(text(f"SELECT strike::text, tick_size::text FROM {TABLE} "
                                             "WHERE tradingsymbol = 'SENSEX26O0882100PE'"))
            assert tuple(sensex.one()) == ("82100.00", "0.0500")
        finally:
            await trans.rollback()


async def check_truncated_update_refused(conn: AsyncConnection) -> None:
    """A list missing one unexpired contract (NIFTY26O1325050CE, expiry 2026-10-13) plus one new contract is
    refused, and every row keeps every column (listedness and stamps included); nothing is inserted."""
    before = await _snapshot(conn)
    truncated = [c for c in _fixture() if c.tradingsymbol != "NIFTY26O1325050CE"]
    extra = replace(_by_symbol(_fixture(), "NIFTY26O1325050CE"), instrument_token=99999999,
                    tradingsymbol="NEW-CONTRACT")
    try:
        await apply_update(conn, truncated + [extra], as_of=AS_OF)
    except ValueError as exc:
        assert "refused: would drop 1 contract" in str(exc), exc
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
            before = {r.tradingsymbol: r for r in (await conn.execute(SNAPSHOT)).all()}
            next_day = [c for c in _fixture() if c.expiry != date(2026, 10, 6)]  # the 4 NIFTY 6-Oct options expired
            result = await apply_update(conn, next_day, as_of=datetime(2026, 10, 7, 9, 0, tzinfo=IST))
            assert (result.added, result.seen, result.newly_unlisted) == (0, 18, 4)
            after = {r.tradingsymbol: r for r in (await conn.execute(SNAPSHOT)).all()}
            assert set(after) == set(before) and len(after) == 22
            gone = {s for s, r in after.items() if not r.currently_listed}
            assert gone == {"NIFTY26O0625050CE", "NIFTY26O0625000CE", "NIFTY26O0625050PE", "NIFTY26O0625000PE"}
            for symbol, row in after.items():
                assert row.first_seen_at == before[symbol].first_seen_at
                if symbol in gone:
                    assert row.last_seen_at == before[symbol].last_seen_at
                else:
                    assert row.last_seen_at > before[symbol].last_seen_at
            catalogue = await load_catalogue(conn)
            assert sum(not e.currently_listed for e in catalogue.all_entries()) == 4
        finally:
            await trans.rollback()


async def test_a_contract_whose_terms_changed_is_refused_with_nothing_written(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            before = await _snapshot(conn)
            changed = [replace(c, lot_size=75) if c.tradingsymbol == "NIFTY26OCTFUT" else c for c in _fixture()]
            with pytest.raises(CatalogueStoreError, match="NIFTY26OCTFUT .* terms never change"):
                await apply_update(conn, changed, as_of=AS_OF)
            assert await _snapshot(conn) == before
        finally:
            await trans.rollback()


async def test_app_role_cannot_delete_or_rewrite_contracts(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await _expect_refused(conn, f"DELETE FROM {TABLE}", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"TRUNCATE {TABLE}", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET strike = strike + 1", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {TABLE} SET last_seen_at = now()", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(
                conn, f"INSERT INTO {TABLE} (exchange, instrument_token, exchange_token, tradingsymbol, name, strike, "
                      "tick_size, lot_size, instrument_type, segment, currently_listed) VALUES ('NFO', 1, 1, 'X', "
                      "'NIFTY', 0, 0.05, 65, 'FUT', 'NFO-FUT', FALSE)", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"ALTER TABLE {TABLE} DISABLE TRIGGER ALL", INSUFFICIENT_PRIVILEGE)
            assert await _count(conn) == 22
        finally:
            await trans.rollback()


async def check_owner_cannot_delete_or_change_terms(conn: AsyncConnection) -> None:
    """Even the owner (who bypasses grants) cannot delete a contract or change its terms: the trigger refuses."""
    await _expect_refused(conn, f"DELETE FROM {TABLE} WHERE tradingsymbol = 'NIFTY26OCTFUT'", CATALOGUE_SQLSTATE)
    await _expect_refused(conn, f"UPDATE {TABLE} SET lot_size = 75 WHERE tradingsymbol = 'NIFTY26OCTFUT'",
                          CATALOGUE_SQLSTATE)


async def test_owner_cannot_delete_or_change_terms_and_cannot_backdate_first_seen(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await check_owner_cannot_delete_or_change_terms(conn)
            stamp = (await conn.execute(text(f"SELECT first_seen_at FROM {TABLE} WHERE tradingsymbol = 'NIFTY26OCTFUT'"))).scalar_one()
            await conn.execute(text(f"UPDATE {TABLE} SET first_seen_at = '2000-01-01' WHERE tradingsymbol = 'NIFTY26OCTFUT'"))
            again = (await conn.execute(text(f"SELECT first_seen_at FROM {TABLE} WHERE tradingsymbol = 'NIFTY26OCTFUT'"))).scalar_one()
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
            await conn.execute(text(f"UPDATE {TABLE} SET strike = 'NaN' WHERE tradingsymbol = 'SENSEX26O1582000PE'"))
            with pytest.raises(CatalogueStoreError, match=r"SENSEX26O1582000PE \(instrument_token 282293253\): strike NaN"):
                await load_catalogue(conn)
        finally:
            await trans.rollback()


async def test_head_allowlist_function_holds_blocks_one_to_eight(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        body = (await conn.execute(text("SELECT pg_get_functiondef('public.ofo_assert_app_role_allowlist'::regproc)"))).scalar_one()
    markers = ["-- 1. attributes", "-- 2. membership", "-- 3. ownership", "-- 4. database privileges",
               "-- 5. schema public", "-- 6. exactly SELECT", "-- 7. audit store", "-- 8. catalogue store"]
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
CREATE OR REPLACE FUNCTION public.catalogue_contracts_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp AS $fn$ BEGIN IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $fn$"""


@pytest.mark.parametrize(
    "mutation, match",
    [
        ('GRANT DELETE ON public.catalogue_contracts TO "{role}"', "has DELETE on catalogue_contracts"),
        ('GRANT TRUNCATE ON public.catalogue_contracts TO "{role}"', "has TRUNCATE on catalogue_contracts"),
        ('GRANT INSERT ON public.catalogue_contracts TO "{role}"', "has table-wide INSERT on catalogue_contracts"),
        ('GRANT UPDATE (strike) ON public.catalogue_contracts TO "{role}"', "has UPDATE on catalogue_contracts column strike"),
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
        # (b) pinned bodies: each replaced, attributes kept, so only the body differs
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
    """A store whose domain call judges expiry against the wrong date (here: year 2100, so nothing is "unexpired")
    no longer refuses the truncated list, and the store then writes: the refusal check goes red."""
    original = Catalogue.update

    def wrong_date(self, contracts, *, as_of, **kwargs):
        return original(self, contracts, as_of=datetime(2100, 1, 1, tzinfo=IST), **kwargs)

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await check_truncated_update_refused(conn)
            monkeypatch.setattr(Catalogue, "update", wrong_date)
            with pytest.raises(AssertionError, match="not refused: truncated update"):
                await check_truncated_update_refused(conn)
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Core proof on the real file (network; runs in CI with OFO_REQUIRE_DB_TESTS=1)
# ---------------------------------------------------------------------------------------------------------------

PROOF_CATEGORIES = [("NIFTY", "NFO", t) for t in ("CE", "PE", "FUT")] + [("SENSEX", "BFO", t) for t in ("CE", "PE", "FUT")]


@pytest.mark.network
async def test_real_zerodha_file_round_trips_and_a_truncated_update_is_refused(
    app_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    from ofo.instruments.downloader import download_instruments_csv

    raw = download_instruments_csv()
    contracts = parse_rows_naming_the_row(io.StringIO(raw))
    scoped = _in_scope(contracts)
    file_counts = Counter((c.name, c.exchange, c.instrument_type) for c in scoped)
    assert all(file_counts[k] > 0 for k in PROOF_CATEGORIES), file_counts

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            as_of = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            result = await apply_update(conn, contracts, as_of=as_of)
            rows = (await conn.execute(text(
                f"SELECT name, exchange, instrument_type, count(*) FROM {TABLE} GROUP BY 1, 2, 3"))).all()
            table_counts = Counter({(r[0], r[1], r[2]): r[3] for r in rows})
            assert table_counts == file_counts
            assert result.added == len(scoped) == sum(table_counts.values())

            # 5 named contracts, chosen deterministically from the file: the nearest NIFTY and SENSEX futures and
            # the lowest-token NIFTY CE, NIFTY PE and SENSEX CE of the nearest expiry
            def first(name: str, kind: str) -> Contract:
                pool = [c for c in scoped if c.name == name and c.instrument_type == kind]
                nearest = min(c.expiry for c in pool)
                return min((c for c in pool if c.expiry == nearest), key=lambda c: c.instrument_token)

            named = [first("NIFTY", "FUT"), first("SENSEX", "FUT"), first("NIFTY", "CE"), first("NIFTY", "PE"),
                     first("SENSEX", "CE")]
            lines = [f"W-053 PROOF file rows={len(contracts)} in_scope={len(scoped)} table={sum(table_counts.values())}"]
            lines += [f"W-053 PROOF count {k[0]}/{k[1]}/{k[2]} file={file_counts[k]} table={table_counts[k]}"
                      for k in PROOF_CATEGORIES]
            for c in named:
                row = (await conn.execute(text(
                    f"SELECT {', '.join(FIELDS)} FROM {TABLE} WHERE exchange = :e AND instrument_token = :t"),
                    {"e": c.exchange, "t": c.instrument_token})).one()
                for field in FIELDS:
                    assert getattr(row, field) == getattr(c, field), (c.tradingsymbol, field)
                assert isinstance(row.strike, Decimal) and isinstance(row.tick_size, Decimal)
                lines.append(f"W-053 PROOF match {c.tradingsymbol} token={c.instrument_token} strike={row.strike} "
                             f"expiry={row.expiry} lot={row.lot_size} tick={row.tick_size} (file strike={c.strike} "
                             f"tick={c.tick_size})")

            # the refused update: one unexpired contract removed from a copy
            before = await _snapshot(conn)
            victim = named[2]
            assert victim.expiry >= as_of.astimezone(IST).date()
            copy = [c for c in contracts if c.instrument_token != victim.instrument_token]
            with pytest.raises(ValueError, match="refused: would drop 1 contract"):
                await apply_update(conn, copy, as_of=as_of)
            after = await _snapshot(conn)
            assert after == before
            lines.append(f"W-053 PROOF refused removing {victim.tradingsymbol} (expiry {victim.expiry}); "
                         f"rows before={len(before)} after={len(after)} identical={after == before}")
            with capsys.disabled():
                print("\n" + "\n".join(lines))
        finally:
            await trans.rollback()
