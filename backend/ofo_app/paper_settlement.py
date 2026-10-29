"""Paper expiry settlement: every open paper contract past its expiry settles once at its intrinsic value (GC-TP 5b).

Spec basis: REQ-109 AC-7 ("settles with a "settle" order at its intrinsic value from the official closing value of its
index that day"); finding F-72 (Kite's DAY candle close = BSE's published SENSEX close, 73,246.03 on 28 Oct 2026);
ADR-008 (exact decimal money); ADR-119 (the market calendar); RD-121 (paper trades are stated plainly as not real).

``settle_expired(conn, now, close_of)``:
- ONE query finds every (strategy, contract) with a non-zero open quantity whose contract expired before today (IST),
  or expires today when ``now`` is at or after 15:45 IST (the close is published by then). Deleted strategies are left
  alone (their book is not shown anywhere).
- The contracts are grouped by (underlying, expiry date); ``close_of(underlying, expiry_date)`` is awaited ONCE per
  group. None, or a read that raises, -> nothing is written for that group: its legs stay open and the group is
  reported with the reason ``SKIP_REASON`` (the next run retries). A settlement is NEVER priced without the official
  close.
- Per strategy, ONE transaction: the strategy's row lock (one writer per strategy), its book re-read under the lock, and
  for each due contract still open ONE ``settle`` order for exactly its open quantity on the closing side, at
  max(0, close - strike) for a CE, max(0, strike - close) for a PE and the close itself for a future, placed at 15:30
  IST of the expiry day, through ``paper_store.place`` (the only writer of paper_orders). A contract already flat is
  skipped. Idempotent: a second run finds nothing open; two processes serialise on the row lock and the second finds
  the contract flat; migration 0030's unique index (strategy, contract) WHERE kind = 'settle' refuses a second settle
  in the database itself. A strategy whose write fails rolls back alone (logged by type) and is retried next run.
- Transactions: when the caller's connection is not in a transaction, each strategy commits on its own and the reads
  are committed before ``close_of`` runs (no transaction is held across a Kite read); inside a caller's transaction
  each strategy is a savepoint and the caller commits (tests).

The scheduled job (``start`` / ``run_forever``, started by the app lifespan only when the live market is on): one run
at startup (catch-up after a restart), then daily at 15:45 IST on trading days, and every 15 minutes until 18:00 IST
while a group had no close. ``owner_close_of`` reads the index's DAY candle (``kite_history.KiteHistory.day_close``)
with the owner's cached Kite token; a missing session, a catalogue without the index or a failed read is None for that
run. It never reaches Zerodha's order, GTT or basket doors (tests_app/test_paper_order_door.py walks this module).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo import market_calendar
from ofo.engine.legs import Instrument
from ofo.instruments.models import INDEX_ROWS, ZERODHA
from ofo.timeutil import IST, SESSION_CLOSE
from ofo.tracking.orderbook import net_positions
from sqlalchemy import text

from ofo_app import paper_store
from ofo_app import strategy_store as store

log = logging.getLogger(__name__)

SETTLE: Final = "settle"
SETTLE_REASON: Final = "Paper - settled at expiry"
SKIP_REASON: Final = "settlement price not available"
#: The close is read from 15:45 IST (the exchange publishes the closing value after its 15:30 close).
SETTLE_FROM: Final = datetime.time(15, 45)
#: While a group had no close, the job retries every RETRY_MINUTES until RETRY_UNTIL IST.
RETRY_MINUTES: Final = 15
RETRY_UNTIL: Final = datetime.time(18, 0)
_ZERO: Final = Decimal(0)
_MIDDAY: Final = datetime.time(12, 0)

#: (underlying, expiry date) -> the index's official close that day, or None when it is not available.
CloseOf = Callable[[str, datetime.date], Awaitable[Decimal | None]]

_OPEN = text(
    "SELECT o.strategy_id, s.user_ref, o.contract_id, c.name, c.instrument_type, c.strike, c.expiry "
    "FROM public.paper_orders AS o "
    "JOIN public.strategies AS s ON s.id = o.strategy_id "
    "JOIN public.catalogue_contracts AS c ON c.id = o.contract_id "
    "WHERE s.deleted_at IS NULL AND c.expiry IS NOT NULL AND c.expiry <= :last_day "
    "GROUP BY o.strategy_id, s.user_ref, o.contract_id, c.name, c.instrument_type, c.strike, c.expiry "
    "HAVING SUM(CASE WHEN o.side = 'BUY' THEN o.quantity ELSE -o.quantity END) <> 0 "
    "ORDER BY o.strategy_id, o.contract_id")


@dataclass(frozen=True)
class DueContract:
    strategy_id: int
    user_ref: str
    contract_id: int
    underlying: str
    instrument: Instrument
    strike: Decimal
    expiry: datetime.date


@dataclass(frozen=True)
class Settled:
    strategy_id: int
    contract_id: int
    underlying: str
    expiry: datetime.date
    side: str
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class Skipped:
    underlying: str
    expiry: datetime.date
    reason: str


@dataclass(frozen=True)
class SettleRun:
    settled: tuple[Settled, ...]
    skipped: tuple[Skipped, ...]
    failed: tuple[int, ...]  # strategy ids whose write rolled back (retried next run)


def last_due_day(now: datetime.datetime) -> datetime.date:
    """The latest expiry date that settles at ``now``: today from 15:45 IST, else yesterday."""
    local = now.astimezone(IST)
    return local.date() if local.time() >= SETTLE_FROM else local.date() - datetime.timedelta(days=1)


def settle_price(instrument: Instrument, strike: Decimal, close: Decimal) -> Decimal:
    """The intrinsic value at expiry (REQ-109 AC-7): CE max(0, close - strike), PE max(0, strike - close), FUT close."""
    if instrument is Instrument.CE:
        return max(_ZERO, close - strike)
    if instrument is Instrument.PE:
        return max(_ZERO, strike - close)
    return close


def settle_time(expiry: datetime.date) -> datetime.datetime:
    """A settle order is placed at the exchange's 15:30 IST close of the expiry day."""
    return datetime.datetime.combine(expiry, SESSION_CLOSE, IST)


async def due_contracts(conn: Any, now: datetime.datetime) -> list[DueContract]:
    rows = (await conn.execute(_OPEN, {"last_day": last_due_day(now)})).all()
    return [DueContract(int(r.strategy_id), r.user_ref, int(r.contract_id), r.name, Instrument(r.instrument_type),
                        Decimal(r.strike), r.expiry) for r in rows]


async def _close(close_of: CloseOf, underlying: str, expiry: datetime.date) -> Decimal | None:
    try:
        return await close_of(underlying, expiry)
    except Exception as exc:  # noqa: BLE001 - a failed read is "not available" for this run; the class name only
        log.warning("paper settlement: close of %s %s read failed: %s", underlying, expiry, type(exc).__name__)
        return None


async def _settle_strategy(conn: Any, due: Sequence[DueContract], closes: dict[tuple[str, datetime.date], Decimal],
                           ) -> list[Settled]:
    """Under the strategy's row lock: one settle per due contract still open, for exactly its open quantity."""
    first = due[0]
    await store.lock_strategy(conn, first.user_ref, first.strategy_id)
    book = [o.order.as_paper() for o in await paper_store.load(conn, first.strategy_id)]
    open_now = {int(p.instrument_id): p.net_quantity for p in net_positions(book, {}).positions} if book else {}
    orders: list[paper_store.NewOrder] = []
    settled: list[Settled] = []
    for d in due:
        net = open_now.get(d.contract_id, 0)
        if net == 0:  # already flat (another run or process settled it, or the user exited it)
            continue
        side = "BUY" if net < 0 else "SELL"
        price = settle_price(d.instrument, d.strike, closes[(d.underlying, d.expiry)])
        orders.append(paper_store.NewOrder(d.contract_id, side, abs(net), price, SETTLE, settle_time(d.expiry),
                                           SETTLE_REASON))
        settled.append(Settled(d.strategy_id, d.contract_id, d.underlying, d.expiry, side, abs(net), price))
    if orders:
        await paper_store.place(conn, first.user_ref, first.strategy_id, orders)
    return settled


async def settle_expired(conn: Any, now: datetime.datetime, close_of: CloseOf) -> SettleRun:
    """Settles every open paper contract past its expiry (module docstring). Returns what was settled and skipped."""
    owns = not conn.in_transaction()
    due = await due_contracts(conn, now)
    if owns:
        await conn.commit()  # no transaction is held across the Kite reads below
    closes: dict[tuple[str, datetime.date], Decimal] = {}
    skipped: list[Skipped] = []
    for group in sorted({(d.underlying, d.expiry) for d in due}):
        close = await _close(close_of, *group)
        if close is None:
            log.warning("paper settlement: %s %s not settled: %s", group[0], group[1], SKIP_REASON)
            skipped.append(Skipped(group[0], group[1], SKIP_REASON))
        else:
            closes[group] = close
    by_strategy: dict[int, list[DueContract]] = {}
    for d in due:
        if (d.underlying, d.expiry) in closes:
            by_strategy.setdefault(d.strategy_id, []).append(d)
    settled: list[Settled] = []
    failed: list[int] = []
    for sid, contracts in by_strategy.items():
        try:
            async with (conn.begin() if owns else conn.begin_nested()):
                settled.extend(await _settle_strategy(conn, contracts, closes))
        except Exception as exc:  # noqa: BLE001 - this strategy rolls back alone; the next run retries it
            log.error("paper settlement: strategy %s not settled: %s", sid, type(exc).__name__)
            failed.append(sid)
    return SettleRun(tuple(settled), tuple(skipped), tuple(failed))


# --- the scheduled job -------------------------------------------------------------------------------------------


def is_trading_day(day: datetime.date, holidays: market_calendar.Holidays | None = None) -> bool:
    return market_calendar.is_market_open(datetime.datetime.combine(day, _MIDDAY, IST), holidays)


def next_run(now: datetime.datetime, retry: bool, holidays: market_calendar.Holidays | None = None,
             ) -> datetime.datetime:
    """When the job runs next: in RETRY_MINUTES while a group had no close and it is before 18:00 IST; else the next
    trading day's 15:45 IST (today's when it is still ahead)."""
    local = now.astimezone(IST)
    if retry and local.time() < RETRY_UNTIL:
        return now + datetime.timedelta(minutes=RETRY_MINUTES)
    day = local.date()
    for _ in range(15):  # longer than any real run of closed days (market_calendar's look-ahead is 14)
        at = datetime.datetime.combine(day, SETTLE_FROM, IST)
        if at > local and is_trading_day(day, holidays):
            return at
        day += datetime.timedelta(days=1)
    return now + datetime.timedelta(days=1)  # no calendar ahead: look again tomorrow, never settle on a guess


#: () -> an async connection context manager (``engine.connect``)
Connect = Callable[[], Any]
#: (connection) -> the close reader for this run
CloseFactory = Callable[[Any], Awaitable[CloseOf]]


async def run_once(connect: Connect, close_factory: CloseFactory, now: datetime.datetime) -> SettleRun:
    async with connect() as conn:
        close_of = await close_factory(conn)
        if conn.in_transaction():
            await conn.commit()  # the token read may begin a transaction; settle_expired owns its own
        result = await settle_expired(conn, now, close_of)
    for s in result.settled:
        log.info("paper settlement: strategy %s contract %s %s %s at %s", s.strategy_id, s.contract_id, s.side,
                 s.quantity, s.price)
    return result


async def run_forever(connect: Connect, close_factory: CloseFactory, *,
                      clock: Callable[[], datetime.datetime] | None = None,
                      sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                      holidays: market_calendar.Holidays | None = None) -> None:
    """Runs at once (catch-up), then at ``next_run``. A failed run is logged by type and retried as a skipped one."""
    now_of = clock or (lambda: datetime.datetime.now(datetime.UTC))
    while True:
        try:
            retry = bool((await run_once(connect, close_factory, now_of())).skipped)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the job never dies on one failed run
            log.error("paper settlement run failed: %s", type(exc).__name__)
            retry = True
        now = now_of()
        await sleep(max(0.0, (next_run(now, retry, holidays) - now).total_seconds()))


_INDEX_KEY: Final = {underlying: key for key, (_, underlying) in INDEX_ROWS.items()}


async def owner_close_of(conn: Any) -> CloseOf:
    """The production close reader: the index's Kite DAY candle with the owner's cached token. Any missing piece (no
    session, no configuration, the index not in the catalogue) answers None for every group of this run."""
    from ofo_app import catalogue_store  # noqa: PLC0415 - loads only on use
    from ofo_app.broker_config import BrokerConfigError, load_broker_config  # noqa: PLC0415
    from ofo_app.broker_crypto import TokenCipher  # noqa: PLC0415
    from ofo_app.broker_token_store import BrokerStoreError, access_token_for  # noqa: PLC0415
    from ofo_app.price_history_source import day_close_reader  # noqa: PLC0415 - the vendor pick lives there
    from ofo_app.live_market import OWNER_REF, listed_for_kite  # noqa: PLC0415

    async def unavailable(_underlying: str, _expiry: datetime.date) -> Decimal | None:
        return None

    try:
        config = load_broker_config()
        token = await access_token_for(conn, OWNER_REF, TokenCipher(config.token_key))
    except (BrokerStoreError, BrokerConfigError) as exc:
        log.warning("paper settlement: no usable broker session (%s)", type(exc).__name__)
        return unavailable
    if token is None:
        log.warning("paper settlement: no broker session")
        return unavailable
    entries = (await catalogue_store.load_catalogue(conn)).all_entries()
    rows = {(e.contract.exchange_segment, e.contract.exchange_token): e for e in entries if e.has_ref(ZERODHA)}

    async def read(underlying: str, expiry: datetime.date) -> Decimal | None:
        entry = rows.get(_INDEX_KEY.get(underlying))  # type: ignore[arg-type]
        if entry is None:
            log.warning("paper settlement: index %s not in the catalogue", underlying)
            return None
        reader = day_close_reader(listed_for_kite([entry]), api_key=config.api_key, access_token=token)
        return await asyncio.to_thread(reader.day_close, entry.broker_refs[ZERODHA].broker_token, expiry)

    return read


def start() -> asyncio.Task[None]:
    """The lifespan's entry (live market only): the real engine and the owner's close reader, as one task."""
    from ofo_app.db import get_engine  # noqa: PLC0415

    return asyncio.get_running_loop().create_task(run_forever(get_engine().connect, owner_close_of),
                                                  name="paper-settlement")


async def stop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
