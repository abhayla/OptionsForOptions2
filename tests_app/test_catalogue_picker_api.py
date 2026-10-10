"""W-068 (REQ-035 AC-8, ADR-068 items 1 and 4): the Builder's leg picker API over the PostgreSQL catalogue.

Spec basis: REQ-035 AC-8 "The Builder adds and edits legs from a picker that offers only listed, not-expired contracts
of the chosen underlying (underlying, expiry, strike, CE/PE/FUT, buy/sell, lots)"; ADR-068 item 1 (planned entry = the
leg's LTP when added, or the mid of bid and ask when no LTP exists); ADR-020 Q185 ("no fake prices"); ADR-003 Q226
(every message from the template catalogue).

Every database test runs in a transaction that is rolled back, so public.catalogue_contracts stays empty.
"""

from __future__ import annotations

import datetime
import io
from datetime import date, datetime as dt, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ofo_app.catalogue_picker import database_today, pickable_contracts, pickable_expiries
from ofo_app.catalogue_store import apply_update, parse_rows_naming_the_row

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / "tests" / "fixtures" / "instruments" / "instruments_slice.csv"
FIRST_LOAD = dt(2026, 9, 28, 10, 0, tzinfo=IST)  # fixed, never the wall clock
SECOND_LOAD = dt(2026, 9, 30, 10, 0, tzinfo=IST)  # retires NIFTY 2026-09-29; the list also drops one SENSEX contract
TODAY = date(2026, 10, 7)
TABLE = "public.catalogue_contracts"
FIXED_INPUT_CODE = "USER_INPUT_002"  # user_input_request_invalid: the fixed input error, the value never echoed


def _slice():
    with SLICE.open(encoding="utf-8") as f:
        return list(parse_rows_naming_the_row(f))


async def _count(conn) -> int:
    return (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one()


async def _load_two_days(conn):
    """The slice loaded on 2026-09-28, then again on 2026-09-30 without one live SENSEX 2026-10-08 call (delisted).
    Returns the instrument id of the dropped contract."""
    rows = _slice()
    await apply_update(conn, rows, as_of=FIRST_LOAD)
    dropped = min((r for r in rows if r.contract.name == "SENSEX" and r.contract.expiry == date(2026, 10, 8)
                   and r.contract.instrument_type == "CE"), key=lambda r: r.contract.exchange_token)
    kept = [r for r in rows if r is not dropped]
    result = await apply_update(conn, kept, as_of=SECOND_LOAD)
    assert result.delisted == 1 and result.retired > 0
    return f"{dropped.contract.exchange_segment}:{dropped.contract.exchange_token}"


# ---------------------------------------------------------------------------------------------------------------
# Step 1: the store functions (deterministic slice, then the real list)
# ---------------------------------------------------------------------------------------------------------------


async def test_only_live_listed_unexpired_contracts_of_the_asked_underlying(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            dropped = await _load_two_days(conn)

            # not-expired is judged on the `today` argument: 2026-10-06 and 2026-10-01 rows are gone on 2026-10-07
            assert await pickable_expiries(conn, "NIFTY", TODAY) == [date(2026, 10, 27), date(2026, 11, 23)]
            assert await pickable_expiries(conn, "SENSEX", TODAY) == [
                date(2026, 10, 8), date(2026, 10, 15), date(2026, 10, 29), date(2026, 11, 26), date(2026, 12, 31)]
            assert await pickable_contracts(conn, "NIFTY", TODAY, date(2026, 10, 6)) == []  # past expiry: empty
            assert await pickable_contracts(conn, "NIFTY", TODAY, date(2031, 1, 1)) == []  # unknown expiry: empty

            sensex = await pickable_contracts(conn, "SENSEX", TODAY, date(2026, 10, 8))
            assert len(sensex) == 2 * 148 - 1
            assert {c.instrument_type for c in sensex} == {"CE", "PE"}
            assert all(c.expiry == date(2026, 10, 8) and c.exchange_segment == "BSE_FO" for c in sensex)
            assert [(c.strike, c.instrument_type) for c in sensex] == sorted((c.strike, c.instrument_type) for c in sensex)
            assert all(isinstance(c.strike, Decimal) and c.lot_size > 0 and c.symbol for c in sensex)
            assert all(c.instrument_id == f"{c.exchange_segment}:{c.exchange_token}" for c in sensex)

            # delisted: the dropped contract is absent although its expiry is ahead
            assert dropped not in {c.instrument_id for c in sensex}
            # retired: NIFTY 2026-09-29 expiry is on/after 2026-09-28 yet its contracts were retired on 2026-09-30
            assert date(2026, 9, 29) not in await pickable_expiries(conn, "NIFTY", date(2026, 9, 28))
            assert await pickable_contracts(conn, "NIFTY", date(2026, 9, 28), date(2026, 9, 29)) == []
            # not yet expired on the earlier day, still live: the 2026-10-01 SENSEX expiry is offered on 2026-09-28
            assert date(2026, 10, 1) in await pickable_expiries(conn, "SENSEX", date(2026, 9, 28))
            # a future has no strike
            futs = [c for c in await pickable_contracts(conn, "NIFTY", TODAY, date(2026, 10, 27))]
            assert [(c.instrument_type, c.strike) for c in futs] == [("FUT", None)]
            # only the asked underlying; out-of-scope names never appear
            everything = await pickable_contracts(conn, "SENSEX", date(2026, 9, 28))
            assert {c.exchange_segment for c in everything} == {"BSE_FO"}
            assert await pickable_expiries(conn, "SENSEX50", TODAY) == []
            assert await pickable_expiries(conn, "BANKEX", TODAY) == []
        finally:
            await trans.rollback()


@pytest.mark.network
async def test_real_list_gives_nifty_expiries_with_ce_and_pe_strikes(app_engine: AsyncEngine) -> None:
    from ofo.instruments.downloader import download_instruments_csv

    rows = parse_rows_naming_the_row(io.StringIO(download_instruments_csv()))
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            as_of = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            await apply_update(conn, rows, as_of=as_of)
            today = await database_today(conn)
            expiries = await pickable_expiries(conn, "NIFTY", today)
            assert expiries and all(e >= today for e in expiries)
            both = []
            for expiry in expiries:
                contracts = await pickable_contracts(conn, "NIFTY", today, expiry)
                ce = {c.strike for c in contracts if c.instrument_type == "CE"}
                pe = {c.strike for c in contracts if c.instrument_type == "PE"}
                if ce and pe:
                    both.append(expiry)
                assert all(c.strike is None for c in contracts if c.instrument_type == "FUT")
            assert both, "no NIFTY expiry offers both CE and PE strikes"
            assert await pickable_contracts(conn, "BANKNIFTY", today) == []
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Step 2: the two read-only catalogue routes, as the limited application role
# ---------------------------------------------------------------------------------------------------------------


async def _picker_client(session: AsyncSession, today: date) -> AsyncClient:
    from ofo_app.db import get_db
    from ofo_app.main import create_app
    from ofo_app.routes.catalogue import get_today

    app = create_app()

    async def db():
        yield session

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_today] = lambda: today
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_catalogue_routes_offer_only_pickable_contracts_with_string_strikes(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            dropped = await _load_two_days(conn)
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                async with await _picker_client(session, TODAY) as ac:
                    resp = await ac.get("/api/catalogue/SENSEX/expiries")
                    assert resp.status_code == 200, resp.text
                    assert resp.json() == {"underlying": "SENSEX", "expiries": [
                        "2026-10-08", "2026-10-15", "2026-10-29", "2026-11-26", "2026-12-31"]}
                    resp = await ac.get("/api/catalogue/SENSEX/contracts", params={"expiry": "2026-10-08"})
                    assert resp.status_code == 200, resp.text
                    body = resp.json()
                    assert set(body) == {"underlying", "contracts"} and len(body["contracts"]) == 2 * 148 - 1
                    first = body["contracts"][0]
                    assert set(first) == {"exchange_segment", "exchange_token", "instrument_type", "expiry", "strike",
                                          "lot_size", "symbol"}
                    assert isinstance(first["strike"], str) and Decimal(first["strike"]) > 0
                    assert isinstance(first["exchange_token"], int) and isinstance(first["lot_size"], int)
                    ids = {f"{c['exchange_segment']}:{c['exchange_token']}" for c in body["contracts"]}
                    assert dropped not in ids  # the delisted contract is not offered
                    fut = (await ac.get("/api/catalogue/NIFTY/contracts", params={"expiry": "2026-10-27"})).json()
                    assert [(c["instrument_type"], c["strike"]) for c in fut["contracts"]] == [("FUT", None)]
                    # past, unknown and expired expiries are an empty list, not an error
                    for expiry in ("2026-10-06", "2031-01-01"):
                        resp = await ac.get("/api/catalogue/NIFTY/contracts", params={"expiry": expiry})
                        assert (resp.status_code, resp.json()) == (200, {"underlying": "NIFTY", "contracts": []})
        finally:
            await trans.rollback()


async def test_unsupported_underlying_and_bad_input_use_catalogue_messages(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                async with await _picker_client(session, TODAY) as ac:
                    resp = await ac.get("/api/catalogue/BANKNIFTY/expiries")
                    assert resp.status_code == 422 and resp.json()["code"] == "USER_INPUT_101", resp.text
                    resp = await ac.get("/api/catalogue/BANKNIFTY/contracts", params={"expiry": "2026-10-08"})
                    assert resp.status_code == 422 and resp.json()["code"] == "USER_INPUT_101", resp.text
                    resp = await ac.get("/api/catalogue/nifty/expiries")  # not even a symbol shape: the fixed input error
                    assert resp.status_code == 422 and resp.json()["code"] == FIXED_INPUT_CODE, resp.text
                    assert "nifty" not in resp.text
                    resp = await ac.get("/api/catalogue/NIFTY/contracts")  # expiry missing
                    assert resp.status_code == 422 and resp.json()["code"] == FIXED_INPUT_CODE, resp.text
                    resp = await ac.get("/api/catalogue/NIFTY/contracts", params={"expiry": "tomorrow"})
                    assert resp.status_code == 422 and resp.json()["code"] == FIXED_INPUT_CODE, resp.text
        finally:
            await trans.rollback()


async def test_get_today_reads_the_database_clock_in_india(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            from ofo_app.routes.catalogue import get_today

            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                today = await get_today(session)
            expected = (await conn.execute(text("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date"))).scalar_one()
            assert today == expected and isinstance(today, date)
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Step 3: planned-entry capture (recorded 2026-10-08 replay; no database)
# ---------------------------------------------------------------------------------------------------------------

LIVE_ID, NO_QUOTE_ID, UNKNOWN_ID = "NSE_FO:44616", "NSE_FO:47455", "NSE_FO:1"


@pytest.fixture(scope="module")
def replay_ctx():
    from ofo_app.replay_mode import build_replay_context

    return build_replay_context()


async def _capture(body: dict, ctx=None) -> "tuple[int, dict]":
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import get_market_context

    app = create_app()
    if ctx is not None:
        app.dependency_overrides[get_market_context] = lambda: ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/planned-entry", json=body)
    return resp.status_code, resp.json()


async def test_a_live_leg_gets_its_ltp_and_a_leg_with_no_quote_gets_null(replay_ctx) -> None:
    status, body = await _capture({"underlying": "NIFTY", "instrument_ids": [LIVE_ID, NO_QUOTE_ID, UNKNOWN_ID]},
                                  replay_ctx)
    assert status == 200, body
    live, no_quote, unknown = body["entries"]
    quote = replay_ctx.provider.book.get(LIVE_ID, replay_ctx.clock())
    assert quote.ltp is not None and quote.ltp > 0
    assert live["planned_entry"] == str(quote.ltp.quantize(Decimal("0.01")))
    assert live["source"] == "ltp" and live["reason_code"] is None
    assert live["captured_at"] == replay_ctx.clock().isoformat()
    assert (live["exchange_segment"], live["exchange_token"]) == ("NSE_FO", 44616)
    assert no_quote["planned_entry"] is None and no_quote["captured_at"] is None and no_quote["source"] is None
    assert no_quote["reason_code"] == "no_live_price"
    assert unknown["planned_entry"] is None and unknown["reason_code"] == "unknown_instrument"


async def test_a_leg_on_another_underlying_has_no_planned_entry(replay_ctx) -> None:
    status, body = await _capture({"underlying": "SENSEX", "instrument_ids": [LIVE_ID]}, replay_ctx)
    assert status == 200 and body["entries"][0]["planned_entry"] is None
    assert body["entries"][0]["reason_code"] == "wrong_underlying"


async def test_without_a_provider_every_leg_is_null_never_a_default() -> None:
    status, body = await _capture({"underlying": "NIFTY", "instrument_ids": [LIVE_ID, NO_QUOTE_ID]})
    assert status == 200
    assert [(e["planned_entry"], e["source"], e["reason_code"]) for e in body["entries"]] == [
        (None, None, "not_connected")] * 2


async def test_a_disconnected_provider_gives_no_price(replay_ctx) -> None:
    from types import SimpleNamespace

    from ofo_app.routes.outcome import MarketContext

    class Down:
        def status(self):
            return SimpleNamespace(connected=False)

        def __getattr__(self, name):
            raise AssertionError(f"a disconnected provider must not be read ({name})")

    ctx = MarketContext(Down(), replay_ctx.clock, replay_ctx.rate)
    status, body = await _capture({"underlying": "NIFTY", "instrument_ids": [LIVE_ID]}, ctx)
    assert status == 200 and body["entries"][0]["reason_code"] == "not_connected"
    assert body["entries"][0]["planned_entry"] is None


@pytest.mark.parametrize("body", [
    {"underlying": "BANKNIFTY", "instrument_ids": [LIVE_ID]},
    {"underlying": "NIFTY", "instrument_ids": []},
    {"underlying": "NIFTY", "instrument_ids": ["not an id"]},
    {"underlying": "NIFTY", "instrument_ids": [LIVE_ID], "planned_entry": "1.00"},
])
async def test_planned_entry_refuses_a_bad_body(body: dict) -> None:
    status, answer = await _capture(body)
    assert status == 422 and answer["code"] == FIXED_INPUT_CODE


def test_price_rule_ltp_first_then_mid_and_nothing_else() -> None:
    from types import SimpleNamespace

    from ofo.rules.inputs import DataHealth
    from ofo_app.routes.planned_entry import _price

    def q(ltp=None, bid=None, ask=None, health=DataHealth.AVAILABLE):
        return SimpleNamespace(ltp=ltp, bid=bid, ask=ask, health=health)

    D = Decimal
    assert _price(q(ltp=D("104.65"), bid=D("1"), ask=D("2"))) == (D("104.65"), "ltp")  # LTP wins over the mid
    assert _price(q(bid=D("100.00"), ask=D("100.05"))) == (D("100.03"), "mid")  # 100.025 rounds half up
    assert _price(q(bid=D("100.00"), ask=D("101.00"))) == (D("100.50"), "mid")
    assert _price(q(bid=D("100.00"))) is None  # one side only: no mid
    assert _price(q()) is None
    assert _price(q(ltp=D("0"))) is None  # a zero LTP is not a price
    assert _price(q(ltp=D("0"), bid=D("100"), ask=D("101"))) is None  # an LTP field is present: no mid fallback
    assert _price(q(ltp=D("104.65"), health=DataHealth.STALE)) is None
    assert _price(q(ltp=D("104.65"), health=DataHealth.UNAVAILABLE)) is None
    assert _price(None) is None
