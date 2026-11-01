"""GC-TP step 5b (REQ-109 AC-7; F-72): the paper expiry settlement job.

Spec basis (quoted): REQ-109 AC-7 "settles with a "settle" order at its intrinsic value from the official closing value
of its index that day"; F-72 (Kite's DAY candle close = BSE's published SENSEX close, 73,246.03). The brief's threat
model: never a guessed price (no close -> no write), never twice (a second run, a second process, the database's unique
index), never more than the open quantity.

Core proof (test_core_...): the REAL shapes of today's three SENSEX paper strategies of
tests/fixtures/paper/before-2026-10-29.json (52, 60, 61: SENSEX 2026-10-29 legs, their sides, quantities and entry
prices) are opened on the real database, ``settle_expired`` runs with the injected close 73,246.03 and every open leg
gets exactly one settle order at the intrinsic value computed by hand below; each strategy is flat with booked = total;
a second run writes nothing. The SENSEX 2026-10-29 contracts are not in the committed instrument list (2026-10-08), so
the test loads them as rows of that list's own shape (Zerodha's columns) with the fixture's exchange tokens.
Every test rolls back.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import json
import pathlib
from decimal import Decimal

import pytest
from ofo import settings
from ofo.engine.legs import Action
from ofo.settings import calc
from ofo.strategy import stored_form as sf
from ofo.timeutil import IST
from ofo.tracking.orderbook import net_positions
from ofo_app import paper_settlement as ps
from ofo_app import paper_store, settings_store
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update, parse_rows_naming_the_row
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_strategy_store import AS_OF, FIXTURE, _fixture_rows, _user
from ofo.settings import calc as _calc, defaults as _defaults

_MAX_DELIST = _calc.max_delist_percent(_defaults())

D = Decimal
ROOT = pathlib.Path(__file__).resolve().parents[1]
STRATEGIES = json.loads((ROOT / "tests/fixtures/paper/before-2026-10-29.json").read_text(encoding="utf-8"))
EXPIRY = datetime.date(2026, 10, 29)
CLOSE = D("73246.03")  # F-72's real value (BSE's official SENSEX close; here injected for 29 Oct)
OPENED = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
AFTER = datetime.datetime(2026, 10, 29, 15, 50, tzinfo=IST)  # today, after 15:45 IST
BEFORE = datetime.datetime(2026, 10, 29, 14, 0, tzinfo=IST)  # today, before 15:45 IST
NEXT_DAY = datetime.datetime(2026, 10, 30, 9, 0, tzinfo=IST)  # the expiry was yesterday
DAY_BEFORE = datetime.datetime(2026, 10, 28, 16, 0, tzinfo=IST)  # the expiry is tomorrow
FUT_TOKEN = 999001
HEADER = ("instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,"
          "instrument_type,segment,exchange")


def _legs(sid: int) -> list[dict]:
    return next(s for s in STRATEGIES["strategies"] if s["strategy_id"] == sid)["legs"]


def _token(leg: dict) -> int:
    return int(leg["instrument_id"].split(":")[1])


def _rows():
    """The fixture's SENSEX 2026-10-29 contracts (and one SENSEX future) as instrument-list rows."""
    seen: dict[int, str] = {}
    for sid in (52, 60, 61):
        for leg in _legs(sid):
            strike = int(D(leg["strike"]))
            seen[_token(leg)] = (f"{800000000 + _token(leg)},{_token(leg)},SENSEX26O29{strike}{leg['instrument']},"
                                 f"SENSEX,0,2026-10-29,{strike},0.05,20,{leg['instrument']},BFO-OPT,BFO")
    seen[FUT_TOKEN] = (f"{800000000 + FUT_TOKEN},{FUT_TOKEN},SENSEX26OCTFUT,SENSEX,0,2026-10-29,0,0.05,20,FUT,"
                       "BFO-FUT,BFO")
    return list(parse_rows_naming_the_row(io.StringIO("\n".join([HEADER, *seen.values()]) + "\n")))


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _catalogue(db) -> dict[int, int]:
    """Loads the committed list plus the SENSEX 2026-10-29 rows; exchange token -> catalogue id."""
    extra = _rows()
    assert len(extra) == 6, "every SENSEX 2026-10-29 row (5 options, 1 future) must parse"  # noqa: PLR2004
    assert FIXTURE.exists()
    await apply_update(db, [*_fixture_rows(), *extra], as_of=AS_OF, max_delist_percent=_MAX_DELIST)
    rows = await db.execute(text("SELECT exchange_token, id FROM public.catalogue_contracts WHERE expiry = :e "
                                 "AND name = 'SENSEX'"), {"e": EXPIRY})
    return {int(r[0]): int(r[1]) for r in rows}


async def _strategy(db, ids: dict[int, int], orders: list[tuple[int, str, int, str, str]]) -> tuple[str, int]:
    """A SENSEX strategy holding ``orders`` = (exchange token, side, quantity, price, kind) as paper orders."""
    user = _user()
    opens = [o for o in orders if o[4] == "open"]
    saved = await store.build_definition(db, "SENSEX", [sf.LegChoice(ids[t], Action(side), qty)
                                                       for t, side, qty, _p, _k in opens])
    stored = await store.save_draft(db, user, saved)
    await paper_store.place(db, user, stored.id, [paper_store.NewOrder(ids[t], side, qty, D(price), kind, OPENED)
                                                  for t, side, qty, price, kind in orders])
    return user, stored.id


async def _real(db, ids: dict[int, int], sid: int) -> int:
    return (await _strategy(db, ids, [(_token(leg), leg["action"], leg["quantity"], leg["entry_price"], "open")
                                      for leg in _legs(sid)]))[1]


def _close_of(answer: Decimal | None = CLOSE, calls: list | None = None):
    async def close_of(underlying: str, expiry: datetime.date) -> Decimal | None:
        if calls is not None:
            calls.append((underlying, expiry))
        return answer if (underlying, expiry) == ("SENSEX", EXPIRY) else None
    return close_of


async def _settles(db, sid: int) -> list[tuple]:
    rows = await db.execute(text("SELECT contract_id, side, quantity, price, placed_at, reason "
                                 "FROM public.paper_orders WHERE strategy_id = :s AND kind = 'settle' "
                                 "ORDER BY contract_id"), {"s": sid})
    return [tuple(r) for r in rows]


async def _book(db, sid: int):
    return net_positions([o.order.as_paper() for o in await paper_store.load(db, sid)], {})


def _mine(run: ps.SettleRun, sids: set[int]) -> list[ps.Settled]:
    return [s for s in run.settled if s.strategy_id in sids]


# Hand-computed at the close 73,246.03 (REQ-109 AC-7): (token, settle side, quantity, price) per strategy, and the
# booked total once flat = sum over legs of (sell price - buy price) x 20.
EXPECTED = {
    52: ([(863181, "BUY", 20, D("0.00")), (876359, "BUY", 20, D("246.03"))],   # PE 72600 OTM; CE 73000 ITM
         D("7473.40")),   # (322.95 - 0) x 20 + (296.75 - 246.03) x 20 = 6459.00 + 1014.40
    60: ([(863683, "BUY", 20, D("0.00")), (877367, "BUY", 20, D("46.03"))],    # PE 72800 OTM; CE 73200 ITM
         D("9907.40")),   # 257.35 x 20 + (284.05 - 46.03) x 20 = 5147.00 + 4760.40
    61: ([(862808, "SELL", 20, D("0.00")), (863181, "BUY", 20, D("0.00"))],    # long PE 73000 OTM; short PE 72600 OTM
         D("-3161.00")),  # (0 - 349.20) x 20 + 191.15 x 20 = -6984.00 + 3823.00
}


async def test_core_real_sensex_strategies_settle_once_at_intrinsic_value_and_are_flat(db):
    ids = await _catalogue(db)
    sids = {sid: await _real(db, ids, sid) for sid in EXPECTED}
    calls: list = []
    run = await ps.settle_expired(db, AFTER, _close_of(calls=calls))
    assert calls.count(("SENSEX", EXPIRY)) == 1  # one read per (underlying, expiry) group
    placed = datetime.datetime(2026, 10, 29, 15, 30, tzinfo=IST)
    for real, sid in sids.items():
        want, booked = EXPECTED[real]
        assert await _settles(db, sid) == sorted(
            [(ids[t], side, qty, price, placed, ps.SETTLE_REASON) for t, side, qty, price in want])
        view = await _book(db, sid)
        assert all(p.net_quantity == 0 for p in view.positions)
        assert (view.booked, view.total) == (booked, booked)
    assert len(_mine(run, set(sids.values()))) == 6  # noqa: PLR2004
    again = await ps.settle_expired(db, AFTER, _close_of())
    assert _mine(again, set(sids.values())) == []
    assert [len(await _settles(db, sid)) for sid in sids.values()] == [2, 2, 2]


@pytest.mark.parametrize("answer", ["none", "raises"])
async def test_no_official_close_writes_nothing_and_names_the_reason(db, answer):
    ids = await _catalogue(db)
    sid = await _real(db, ids, 52)

    async def close_of(_u, _e):
        if answer == "raises":
            raise TimeoutError("kite read")
    run = await ps.settle_expired(db, AFTER, close_of)
    assert await _settles(db, sid) == []
    assert ps.Skipped("SENSEX", EXPIRY, "settlement price not available") in run.skipped


@pytest.mark.parametrize(("now", "settles"), [(NEXT_DAY, True), (AFTER, True), (BEFORE, False), (DAY_BEFORE, False)])
async def test_only_contracts_past_expiry_or_today_after_1545_settle(db, now, settles):
    ids = await _catalogue(db)
    sid = await _real(db, ids, 60)
    await ps.settle_expired(db, now, _close_of())
    assert len(await _settles(db, sid)) == (2 if settles else 0)


async def test_a_flat_leg_is_skipped_and_a_partly_exited_leg_settles_only_its_open_quantity(db):
    ids = await _catalogue(db)
    _, sid = await _strategy(db, ids, [(876359, "SELL", 40, "296.75", "open"), (863181, "SELL", 20, "322.95", "open"),
                                       (876359, "BUY", 20, "250.00", "exit"), (863181, "BUY", 20, "10.00", "exit")])
    await ps.settle_expired(db, AFTER, _close_of())
    assert [(c, s, q, p) for c, s, q, p, *_ in await _settles(db, sid)] == [(ids[876359], "BUY", 20, D("246.03"))]


async def test_an_itm_put_and_a_future_settle_at_their_intrinsic_value(db):
    ids = await _catalogue(db)
    sid = await _real(db, ids, 61)  # long PE 73000, short PE 72600
    _, fut = await _strategy(db, ids, [(FUT_TOKEN, "BUY", 20, "73100.00", "open")])
    await ps.settle_expired(db, AFTER, _close_of(D("72500.00")))
    assert [(c, s, p) for c, s, _q, p, *_ in await _settles(db, sid)] == sorted(
        [(ids[862808], "SELL", D("500.00")), (ids[863181], "BUY", D("100.00"))])
    assert [(s, q, p) for _c, s, q, p, *_ in await _settles(db, fut)] == [("SELL", 20, D("72500.00"))]


async def test_the_database_refuses_a_second_settle_of_one_contract(db):
    ids = await _catalogue(db)
    sid = await _real(db, ids, 52)
    await ps.settle_expired(db, AFTER, _close_of())
    with pytest.raises(IntegrityError, match="paper_orders_settle_once"):
        async with db.begin_nested():
            await db.execute(text("INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, "
                                  "kind, placed_at) VALUES (:s, :c, 'BUY', 20, 1.00, 'settle', now())"),
                             {"s": sid, "c": ids[876359]})


async def test_a_zero_price_is_refused_by_the_database_for_every_kind_but_settle(db):
    ids = await _catalogue(db)
    _, sid = await _strategy(db, ids, [(876359, "SELL", 20, "296.75", "open")])
    with pytest.raises(IntegrityError, match="paper_orders_price_check"):
        async with db.begin_nested():
            await db.execute(text("INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, "
                                  "kind, placed_at) VALUES (:s, :c, 'BUY', 20, 0, 'exit', now())"),
                             {"s": sid, "c": ids[876359]})


@pytest.mark.parametrize(("now", "retry", "expected"), [
    (datetime.datetime(2026, 10, 29, 10, 0, tzinfo=IST), False, datetime.datetime(2026, 10, 29, 15, 45, tzinfo=IST)),
    (datetime.datetime(2026, 10, 29, 15, 46, tzinfo=IST), False, datetime.datetime(2026, 10, 30, 15, 45, tzinfo=IST)),
    (datetime.datetime(2026, 10, 29, 15, 46, tzinfo=IST), True, datetime.datetime(2026, 10, 29, 16, 1, tzinfo=IST)),
    (datetime.datetime(2026, 10, 29, 18, 0, tzinfo=IST), True, datetime.datetime(2026, 10, 30, 15, 45, tzinfo=IST)),
    (datetime.datetime(2026, 10, 30, 16, 0, tzinfo=IST), False, datetime.datetime(2026, 11, 2, 15, 45, tzinfo=IST)),
])
def test_next_run_is_1545_on_trading_days_with_15_minute_retries_until_1800(now, retry, expected):
    holidays = {2026: frozenset()}
    values = settings.defaults()  # the registry defaults, passed explicitly (no silent fallback in the job)
    assert ps.next_run(now, retry, holidays, settle_from=calc.paper_settle_from(values),
                       retry_until=calc.paper_retry_until(values)) == expected  # Fri 30 Oct 16:00 -> Mon 2 Nov


# ---- GC-SET step 5a (REQ-167 AC-4, AC-5): the settlement window is the setting in force at each run -------------
_RAW_SETTING = text("INSERT INTO public.app_settings (key, value, effective_from, set_by) "
                    "VALUES (:k, :v, clock_timestamp(), 'raw-test')")


def test_the_settlement_window_defaults_are_exactly_the_old_1545_and_1800():
    values = settings.defaults()
    assert calc.paper_settle_from(values) == datetime.time(15, 45)
    assert calc.paper_retry_until(values) == datetime.time(18, 0)


@pytest.mark.parametrize(("hour", "minute", "settles"), [(15, 47, False), (15, 51, True)])
async def test_a_changed_settle_from_moves_when_a_paper_settlement_runs(db, hour, minute, settles):
    """facts.paper_settle_from = 15:50 (saved through the admin write, in force now): a run at 15:47 on expiry day
    settles nothing (the default 15:45 would have settled), a run at 15:51 settles."""
    ids = await _catalogue(db)
    sid = await _real(db, ids, 60)
    await settings_store.add_setting(db, calc.PAPER_SETTLE_FROM, "1550", set_by="admin-test", correlation_id="t")
    await ps.settle_expired(db, datetime.datetime(2026, 10, 29, hour, minute, tzinfo=IST), _close_of())
    assert len(await _settles(db, sid)) == (2 if settles else 0)


async def test_at_1547_the_default_window_settles(db):
    """The control for the test above: with no stored row the default 15:45 is in force and 15:47 settles."""
    ids = await _catalogue(db)
    sid = await _real(db, ids, 60)
    await ps.settle_expired(db, datetime.datetime(2026, 10, 29, 15, 47, tzinfo=IST), _close_of())
    assert len(await _settles(db, sid)) == 2  # noqa: PLR2004


def test_next_run_follows_changed_settle_from_and_retry_until():
    holidays = {2026: frozenset()}
    at = datetime.datetime(2026, 10, 29, 16, 30, tzinfo=IST)
    wake = ps.next_run(at, True, holidays, settle_from=datetime.time(16, 45), retry_until=datetime.time(16, 0))
    assert wake == datetime.datetime(2026, 10, 29, 16, 45, tzinfo=IST)  # retries stopped at 16:00; the run is 16:45


async def test_a_malformed_stored_settle_time_fails_closed_and_settles_nothing(db):
    """A stored 1575 (no 75th minute) written past the admin write: the run raises, nothing is settled on a guess."""
    ids = await _catalogue(db)
    sid = await _real(db, ids, 60)
    await db.execute(_RAW_SETTING, {"k": calc.PAPER_SETTLE_FROM, "v": D("1575")})
    with pytest.raises(settings_store.SettingsError, match=r"facts.paper_settle_from"):
        await ps.settle_expired(db, NEXT_DAY, _close_of())
    assert await _settles(db, sid) == []


async def test_run_forever_schedules_from_the_settings_read_after_each_run(monkeypatch):
    """The job reads the two times at each wake-up (no restart): a changed settle_from moves the next sleep."""
    stored = iter([D("1700"), D("1600")])  # the admin changes the setting between the two wake-ups
    reads: list[int] = []

    async def in_force(_conn):
        reads.append(1)
        return {**settings.defaults(), calc.PAPER_SETTLE_FROM: next(stored)}

    async def no_run(_connect, _factory, _now):
        return ps.SettleRun((), (), ())

    class _Conn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    slept: list[float] = []

    async def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 2:  # noqa: PLR2004
            raise asyncio.CancelledError

    monkeypatch.setattr(ps, "run_once", no_run)
    monkeypatch.setattr(ps.settings_store, "settings_in_force", in_force)
    ten = datetime.datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    with pytest.raises(asyncio.CancelledError):
        await ps.run_forever(_Conn, None, clock=lambda: ten, sleep=sleep,  # type: ignore[arg-type]
                             holidays={2026: frozenset()})
    assert slept == [7 * 3600, 6 * 3600]  # 10:00 -> 17:00, then -> 16:00: each wake-up uses the value in force then
    assert len(reads) == 2  # noqa: PLR2004 - one read per wake-up, never one at start held for the life of the job


@pytest.mark.parametrize(("instrument", "strike", "close", "price"), [
    ("CE", "73000", "73246.03", "246.03"), ("CE", "73300", "73246.03", "0"),
    ("PE", "73300", "73246.03", "53.97"), ("PE", "73000", "73246.03", "0"), ("FUT", "0", "73246.03", "73246.03")])
def test_settle_price_is_the_intrinsic_value(instrument, strike, close, price):
    from ofo.engine.legs import Instrument  # noqa: PLC0415
    assert ps.settle_price(Instrument(instrument), D(strike), D(close)) == D(price)
