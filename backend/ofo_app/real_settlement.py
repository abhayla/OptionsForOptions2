"""Real (non-paper) expiry settlement step (GC-ICGUIDE g22, audit C6).

Spec basis: ADR-083 ("a leg whose contract has expired is closed in the platform at the exchange settlement price";
the price source is UNPROVEN, so none is ever guessed); REQ-060 AC-2; ADR-016..019 (no silent fix); ADR-008.

``settle_expired_real(conn, now, price_of)`` finds every real strategy leg that is held (``execute_plan.held_units``
over its plans and adopted holdings: the one netting path) on a contract expired at ``now`` (the same
``is_expired`` rule and ``EXPIRY_DAY_SETTLE_FROM`` as ``ofo.reconciliation.settlement``) and names it:

- price absent (``price_of`` answers None: today ALWAYS, no stored exchange settlement price exists) -> AWAITING;
- contract not in the catalogue -> AWAITING with its own reason;
- price stated -> PRICED, not written: the real order book has no append-only settle table yet (a migration on the
  insert-only book); the leg is logged and left open until that table exists. shortcut: upgrade with that migration.
- a strategy whose read fails -> nothing written, logged by type, listed in ``failed``, retried next cycle.

Nothing here writes, so the step is idempotent; paper legs are not read (``paper_settlement`` owns them).
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo.engine.legs import Instrument
from ofo.reconciliation.settlement import is_expired
from sqlalchemy import text

from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import order_book_store as books
from ofo_app import paper_settlement
from ofo_app.catalogue_store import load_catalogue

log = logging.getLogger(__name__)

AWAITING: Final = "awaiting"
PRICED: Final = "priced"
REASON_NO_PRICE: Final = "settlement price not available"
REASON_NO_CONTRACT: Final = "contract not found in the catalogue"
REASON_NO_TABLE: Final = "settlement price known, real settle row not yet supported"

#: (underlying, instrument, strike | None, expiry) -> the exchange settlement price, or None. Nothing stores one yet.
PriceOf = Callable[[tuple], "Decimal | None"]


def no_stored_price(_contract: tuple) -> Decimal | None:
    return None


@dataclass(frozen=True)
class RealLeg:
    strategy_id: int
    instrument_id: str
    units: int  # signed: BUY +, SELL -
    expiry: datetime.date | None
    state: str
    reason: str


@dataclass(frozen=True)
class RealRun:
    legs: tuple[RealLeg, ...]
    failed: tuple[int, ...]  # strategy ids whose read failed (retried next run)


_CANDIDATES = (
    "SELECT s.id, s.user_ref FROM public.strategies AS s WHERE s.deleted_at IS NULL AND {scope} AND "
    "(EXISTS (SELECT 1 FROM public.execution_plan_orders o WHERE o.strategy_id = s.id) OR "
    "EXISTS (SELECT 1 FROM public.adopted_holdings a WHERE a.strategy_id = s.id)) ORDER BY s.id")


def _iid(text_id: str) -> Any:
    from ofo.instruments.models import InstrumentId  # noqa: PLC0415
    segment, token = text_id.split(":")
    return InstrumentId(segment, int(token))


async def settle_expired_real(conn: Any, now: datetime.datetime, price_of: PriceOf = no_stored_price) -> RealRun:
    from ofo_app.scenario_mode import scope_clause  # noqa: PLC0415 - the one isolation helper
    clause, params = scope_clause("s")
    rows = (await conn.execute(text(_CANDIDATES.format(scope=clause)), params)).all()
    catalogue = await load_catalogue(conn)
    legs: list[RealLeg] = []
    failed: list[int] = []
    for r in rows:
        sid = int(r.id)
        try:
            held = ep.held_units(await plans.plans_for(conn, r.user_ref, sid),
                                 await books.adopted_for(conn, r.user_ref, sid))
        except Exception as exc:  # noqa: BLE001 - nothing written; the next cycle retries
            log.error("real settlement: strategy %s not read: %s", sid, type(exc).__name__)
            failed.append(sid)
            continue
        for instrument_id, units in sorted(held.items()):
            try:
                entry = catalogue.get(_iid(instrument_id))
            except ValueError:
                entry = None
            if entry is None:
                legs.append(RealLeg(sid, instrument_id, units, None, AWAITING, REASON_NO_CONTRACT))
                continue
            c = entry.contract
            kind = Instrument(c.instrument_type)
            key = (c.name, kind, None if kind is Instrument.FUT else c.strike, c.expiry)
            if not is_expired(key, now):
                continue
            price = price_of(key)
            legs.append(RealLeg(sid, instrument_id, units, c.expiry, AWAITING if price is None else PRICED,
                                REASON_NO_PRICE if price is None else REASON_NO_TABLE))
    for leg in legs:
        log.warning("real settlement: strategy %s %s %+d expired %s: %s", leg.strategy_id, leg.instrument_id,
                    leg.units, leg.expiry, leg.reason)
    return RealRun(tuple(legs), tuple(failed))


async def run_forever(connect: Callable[[], Any], *, price_of: PriceOf = no_stored_price,
                      clock: Callable[[], datetime.datetime] | None = None,
                      sleep: Callable[[float], Any] = asyncio.sleep) -> None:
    """Paper settlement's cadence (its ``next_run``); retries in 15 minutes while a leg awaits or a read failed."""
    from ofo.settings import calc  # noqa: PLC0415

    from ofo_app import settings_store  # noqa: PLC0415
    now_of = clock or (lambda: datetime.datetime.now(datetime.UTC))
    while True:
        try:
            async with connect() as conn:
                run = await settle_expired_real(conn, now_of(), price_of)
            retry = bool(run.failed or run.legs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the job never dies on one failed run
            log.error("real settlement run failed: %s", type(exc).__name__)
            retry = True
        now = now_of()
        try:
            async with connect() as conn:
                values = await settings_store.settings_in_force(conn)
            wake = paper_settlement.next_run(now, retry, None, settle_from=calc.paper_settle_from(values),
                                             retry_until=calc.paper_retry_until(values))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("real settlement: the settings could not be read: %s", type(exc).__name__)
            wake = now + datetime.timedelta(minutes=paper_settlement.RETRY_MINUTES)
        await sleep(max(0.0, (wake - now).total_seconds()))


def start() -> asyncio.Task[None]:
    from ofo_app.db import get_engine  # noqa: PLC0415
    return asyncio.get_running_loop().create_task(run_forever(get_engine().connect), name="real-settlement")


def start_if(market: object | None) -> asyncio.Task[None] | None:
    """The lifespan's entry: runs only when the live market is on (like paper settlement)."""
    return start() if market is not None else None


stop = paper_settlement.stop
