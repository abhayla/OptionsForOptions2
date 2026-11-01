"""ADR-220 (1) role ``background``: ``python -m ofo_app.background`` checks every tracked strategy's playbook with no
screen open (REQ-165, REQ-115 AC-1..AC-5, REQ-166 AC-1..AC-3). Suggest-only (ADR-003, REQ-115 AC-2): nothing here
reaches an order door (``tests_app/test_paper_order_door.py`` walks this module's imports).

One cycle (``Worker.cycle``), each step with its answer state:
1. The speeds are read NOW (``calc_speeds.read_speeds``, every cycle) and the safety valve applied.
2. Each monitored strategy, in rotation, at most ``max_per_cycle`` per cycle (the rest roll to the next cycle; B4 (a)):
   its prices are read from the provider the feed bus feeds (``read_prices``):
   - market closed (``feed_health.market_closed_for``, the one market-state answer) -> nothing recomputed;
   - feed disconnected (provider health not available and not stale) -> paused, no check;
   - stale (provider stale, or any needed quote's own health not ``available``: ``availability.
     strategy_monitoring_status``, the per-strategy availability; staleness is the provider's connection-aware
     health, never a last-change age, finding staleness-by-last-change-age) -> paused, no check;
   - no price for one leg (no quote, or no LTP) -> paused, no check;
   - fresh -> checked, but only when a price it depends on (a leg, the underlying, or the IST minute a clock rule
     reads) changed since its last check, and at most once per background speed (REQ-165 AC-2).
   A paused strategy's state is ``MonitoringStatus.PAUSED`` (shown as "Monitoring paused"); the first check after it
   reads only the fresh snapshot (no crossing during the gap is claimed: nothing from the gap is kept).
3. A fresh check builds ``StrategyState`` as LIGHT sums of its own legs (``light_state``): spot, each short's LTP and
   delta, P&L, premium left, the adjustment cost and the expiry P&L at spot. The delta is the SHARED per-option
   figure (``FeedScope.call`` over the outcome service's own ``_solved_iv`` / ``_unit_greeks``, REQ-050 AC-3), once
   per option per price update for every holder. The full scenario table (``routes.adjustment.price_after``) is never
   called, so max profit / max loss and margin are None and their triggers answer NotChecked with their reason.
4. ``adjustment_check.evaluate_and_remember`` (rule memory, F-71) then the screen's own record sync
   (``routes.adjustment_check._sync_records``: one open record per flagged rule, REQ-112), so the single-outcome rule
   holds the same here as on the screen. One strategy's error is logged with its id and does not stop the others
   (REQ-115 AC-9).

Restart (REQ-115 AC-3, REQ-165 AC-5): the monitors are rebuilt from the database on start (``rebuild``); rule memory
lives in ``playbook_store.rule_state`` and an already open record is returned, never re-opened.

Not built here (named, not hidden): the Notifier alert of REQ-115 AC-6 (no heartbeat alert is sent); the screen's
GET reading the worker's latest result (REQ-165 AC-6); per-user feeds beyond the single owner (ADR-051 V1); ``_serve``
does not yet write the monitored legs into the bus's wanted set itself (it prices only what the api role holds on
the feed), so a leg no screen ever opened reads as "no price for one leg" (paused, never a guess).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import enum
import functools
import logging
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from ofo.adjustment import playbook_eval as pe
from ofo.engine import adjust_money
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import expiry_model, iv_price
from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.feed_health import market_closed_for
from ofo.marketdata.forward import parity_forward
from ofo.marketdata.shared_compute import FeedScope, SharedCompute
from ofo.outcome.service import _solved_iv, _unit_greeks
from ofo.rules.inputs import DataHealth
from ofo.scenario.spot import spot_reading
from ofo.timeutil import IST

from ofo_app import adjustment_check as check
from ofo_app import calc_speeds, roles
from ofo_app.adjustment_check import _engine_legs, _tighten

log = logging.getLogger("ofo_app.background")

DEFAULT_MAX_PER_CYCLE: Final = 200  # strategies checked in one cycle; the rest roll to the next (B4 (a))
REBUILD_SECONDS: Final = 30  # the monitor set is re-read this often, so a newly tracked strategy joins (AC-3: 60 s)
_MICROS: Final = 1_000_000


class PriceState(enum.Enum):
    FRESH = "fresh"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    LEG_MISSING = "leg_missing"
    MARKET_CLOSED = "market_closed"


@dataclass(frozen=True)
class PriceRead:
    state: PriceState
    spot: Any = None  # NormalizedQuote of the underlying
    legs: Mapping[int, Any] = field(default_factory=dict)  # position leg index -> NormalizedQuote
    chains: Mapping[datetime.date, tuple] = field(default_factory=dict)  # each leg expiry's chain snapshot

    def signature(self, now: datetime.datetime) -> tuple:
        """What a check depends on: every leg's and the spot's price and time, and the IST minute (clock rules)."""
        def part(q: Any) -> tuple:
            return (q.instrument_id, q.ltp, q.bid, q.ask, q.timestamp)
        return (part(self.spot), tuple(part(self.legs[i]) for i in sorted(self.legs)),
                now.astimezone(IST).strftime("%Y-%m-%d %H:%M"))


@dataclass
class Watched:
    """One monitored strategy: the tracked position, its resolved playbook and the feed it is priced from."""

    user_ref: str
    strategy_id: int
    tracked: Any  # routes.adjustment.Tracked
    body: Mapping
    is_system: bool
    feed_owner: str
    expiry_kind: str | None = None


def _seconds(delta: datetime.timedelta) -> Decimal:
    micros = (delta.days * 86_400 + delta.seconds) * _MICROS + delta.microseconds
    return Decimal(micros) / _MICROS


def _leg_quote(chain: Iterable[Any], leg: Any) -> Any:
    for q in chain:
        if q.instrument_type is not None and q.instrument_type.value == leg.type and q.strike == leg.strike:
            return q
    return None


def read_prices(provider: Any, watched: Watched, now: datetime.datetime) -> PriceRead:
    """The price read of one strategy, one answer state each (module docstring, step 2)."""
    if market_closed_for(provider, now):
        return PriceRead(PriceState.MARKET_CLOSED)
    health = provider.status().health
    if health is DataHealth.STALE:
        return PriceRead(PriceState.STALE)
    if health is not DataHealth.AVAILABLE:
        return PriceRead(PriceState.DISCONNECTED)
    position = watched.tracked.position
    chains = {e: tuple(provider.option_chain_snapshot(position.underlying, e)) for e in {x.expiry for x in position.legs}}
    spot = provider.underlying_quote(position.underlying)
    legs = {i: _leg_quote(chains[x.expiry], x) for i, x in enumerate(position.legs)}
    if spot is None or spot.ltp is None or any(q is None or q.ltp is None for q in legs.values()):
        return PriceRead(PriceState.LEG_MISSING)
    needed = {"spot": spot, **{str(i): q for i, q in legs.items()}}
    if strategy_monitoring_status(needed) is MonitoringStatus.PAUSED:
        return PriceRead(PriceState.STALE)
    return PriceRead(PriceState.FRESH, spot, legs, chains)


def _snapshot_instant(read: PriceRead, expiry: datetime.date) -> datetime.datetime:
    return max([read.spot.timestamp, *(q.timestamp for q in read.chains[expiry])])


def short_delta(shared: FeedScope, read: PriceRead, leg: Any, quote: Any, rate: Decimal) -> Decimal | None:
    """|delta| of one option through the SHARED per-option figures (REQ-050 AC-3): the expiry's parity forward, the
    option's IV and its Greeks, each computed once per (feed owner, expiry, snapshot instant, exact inputs)."""
    instant = _snapshot_instant(read, leg.expiry)
    chain = tuple(sorted(read.chains[leg.expiry], key=lambda q: q.instrument_id))
    underlying = read.spot.underlying
    try:
        fwd = shared.call((underlying, leg.expiry, instant, None), parity_forward, chain, read.spot, leg.expiry,
                          instant, rate)
        em = expiry_model(spot_reading(read.spot), fwd)
    except (ValueError, ArithmeticError):  # ForwardUnavailable / SpotRefused are ValueErrors: delta not available
        return None
    price, kind = iv_price(quote), Instrument(leg.type)
    if price is None:
        return None
    where = (underlying, leg.expiry, instant, quote.instrument_id)
    iv = shared.call(where, _solved_iv, em, kind, price, leg.strike)
    if iv is None:
        return None
    greeks = shared.call(where, _unit_greeks, em, kind, leg.strike, iv)
    return None if greeks.delta is None else abs(greeks.delta)


def light_state(watched: Watched, read: PriceRead, shared: FeedScope, now: datetime.datetime,  # noqa: PLR0913
                rate: Decimal) -> pe.StrategyState:
    """The check's state as light sums of the strategy's own legs (never the full table; REQ-166 AC-2)."""
    tracked = watched.tracked
    position = tracked.position
    qty = [x.lots * position.lot for x in position.legs]
    ltp = [read.legs[i].ltp for i in range(len(position.legs))]
    shorts = tuple(pe.ShortLeg(x.strike, short_delta(shared, read, x, read.legs[i], rate), ltp[i])
                   for i, x in enumerate(position.legs) if x.side == Action.SELL.value)
    booked = tracked.booked
    pnl = None if booked is None else adjust_money.pnl_now(
        booked, ((x.side, x.entry, ltp[i], qty[i]) for i, x in enumerate(position.legs)))
    left = adjust_money.premium_left((x.side, ltp[i], qty[i]) for i, x in enumerate(position.legs))
    spreads = [(read.legs[i].bid, read.legs[i].ask) for i in range(len(position.legs))]
    cost = None if any(b is None or a is None for b, a in spreads) else adjust_money.adjustment_cost(
        ((b, a, qty[i]) for i, (b, a) in enumerate(spreads)), check.COST_PER_LEG)
    spot = read.spot.ltp
    expiry_pnl = None
    if booked is not None:
        from ofo.engine.strategy import Strategy  # noqa: PLC0415 - engine type only here (as adjustment_check)
        expiry_pnl = adjust_money.with_booked(booked, Strategy(_engine_legs(position)).expiry_pnl_at(spot))
    at = now.astimezone(IST)
    expiry = min(x.expiry for x in position.legs)
    hhmm = at.strftime("%H:%M")
    return pe.StrategyState(
        expiry_kind=watched.expiry_kind or position.expiry_kind or "weekly",  # type: ignore[arg-type]
        days_left=(expiry - at.date()).days, hhmm=hhmm, spot=spot, shorts=shorts, pnl=pnl,
        max_loss=None, max_profit=None, margin=None, premium_left=left, adjustment_cost=cost,
        adjustments_used=tracked.adjustments_used, expiry_pnl_at_spot=expiry_pnl,
        tighten_percent=_tighten(watched.body, at.date(), expiry, hhmm), prices_fresh=True)


async def record_check(watched: Watched, state: pe.StrategyState, scn: Any = None) -> pe.Evaluation:
    """The check and its records in one transaction, through the screen's own functions (REQ-165 AC-5)."""
    from ofo_app import playbook_store  # noqa: PLC0415 - the database layer only when a check runs
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415
    from ofo_app.routes.adjustment_check import _sync_records  # noqa: PLC0415
    async with get_sessionmaker()() as db:
        ev = await check.evaluate_and_remember(db, watched.user_ref, watched.strategy_id, watched.body, state, scn,
                                               watched.tracked.position)
        source = playbook_store.SOURCE_SYSTEM if watched.is_system else playbook_store.SOURCE_OWN
        await _sync_records(db, watched.user_ref, watched.strategy_id, ev, source, watched.body)
        await db.commit()
    return ev


Lister = Callable[[], Awaitable[list[Watched]]]
Recorder = Callable[[Watched, pe.StrategyState], Awaitable[Any]]


class Worker:
    """The background role's monitors and their cycle. Every seam is injected; ``main`` wires the real ones."""

    def __init__(self, *, provider_for: Callable[[str], Any], lister: Lister,  # noqa: PLR0913
                 clock: Callable[[], datetime.datetime], rate: Decimal, recorder: Recorder = record_check,
                 cache: SharedCompute | None = None, max_per_cycle: int = DEFAULT_MAX_PER_CYCLE,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        if max_per_cycle < 1:
            raise ValueError("max_per_cycle must be at least 1")
        self._provider_for, self._lister, self._clock, self._rate = provider_for, lister, clock, rate
        self._recorder, self._max, self._sleep = recorder, max_per_cycle, sleep
        self.cache = cache if cache is not None else SharedCompute()
        self.valve = calc_speeds.Valve()
        self.monitors: list[Watched] = []
        self.status: dict[int, MonitoringStatus] = {}
        self.paused_reason: dict[int, PriceState] = {}
        self.checks: list[tuple[int, datetime.datetime]] = []  # (strategy id, when) of every check run
        self.errors: list[tuple[int, str]] = []
        self._signature: dict[int, tuple] = {}
        self._last_check: dict[int, datetime.datetime] = {}
        self._cursor = 0
        self._rebuilt_at: datetime.datetime | None = None
        self._stop = False

    async def rebuild(self) -> None:
        """REQ-115 AC-3: the monitors from the database (the lister); a strategy's memory stays in the store."""
        self.monitors = await self._lister()
        self._rebuilt_at = self._clock()
        log.info("background: %s strategies monitored", len(self.monitors))

    def background_seconds(self) -> Decimal:
        return self.valve.slowed(calc_speeds.read_speeds().background)

    async def _check_one(self, w: Watched, now: datetime.datetime, every: Decimal) -> bool:
        """True when a check ran (counted against the cycle's cap)."""
        read = read_prices(self._provider_for(w.feed_owner), w, now)
        if read.state is PriceState.MARKET_CLOSED:
            return False  # nothing is recomputed while the market is closed
        if read.state is not PriceState.FRESH:
            self.status[w.strategy_id] = MonitoringStatus.PAUSED
            self.paused_reason[w.strategy_id] = read.state
            self._signature.pop(w.strategy_id, None)  # the first check after the gap reads the fresh snapshot
            return False
        self.status[w.strategy_id] = MonitoringStatus.ACTIVE
        self.paused_reason.pop(w.strategy_id, None)
        sig = read.signature(now)
        last = self._last_check.get(w.strategy_id)
        if sig == self._signature.get(w.strategy_id) or (last is not None and _seconds(now - last) < every):
            return False
        state = light_state(w, read, FeedScope(self.cache, w.feed_owner), now, self._rate)
        await self._recorder(w, state)
        self._signature[w.strategy_id] = sig
        self._last_check[w.strategy_id] = now
        self.checks.append((w.strategy_id, now))
        return True

    async def cycle(self) -> None:
        now = self._clock()
        if self._rebuilt_at is None or _seconds(now - self._rebuilt_at) >= REBUILD_SECONDS:
            await self.rebuild()
        every = self.background_seconds()  # read on EVERY cycle (REQ-166 AC-1)
        n = len(self.monitors)
        ran, slowest, visited = 0, Decimal(0), 0
        while visited < n and ran < self._max:
            w = self.monitors[(self._cursor + visited) % n]
            visited += 1
            started = self._clock()
            try:
                ran += await self._check_one(w, now, every)
            except Exception as exc:  # noqa: BLE001 - REQ-115 AC-9: one strategy's failure never stops the others
                log.exception("background: strategy %s check failed", w.strategy_id)
                self.errors.append((w.strategy_id, type(exc).__name__))
            slowest = max(slowest, _seconds(self._clock() - started))
        self._cursor = (self._cursor + visited) % n if n else 0
        self.valve.observe(self._clock(), slowest, n - visited)

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> None:
        while not self._stop:
            await self.cycle()
            await self._sleep(float(self.background_seconds()))  # float-ok: asyncio.sleep takes seconds as float


async def owner_lister(provider: Any) -> list[Watched]:
    """Every strategy of the V1 owner (ADR-051) that is tracked (open paper legs) and has a playbook; its type is read
    against the provider's instrument list and spot (as the screen's check)."""
    from ofo_app import strategy_store  # noqa: PLC0415 - database layer at run time only
    from ofo_app.adjustment_readers import TrackedExited, TrackedUnreadable, read_tracked  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415
    from ofo_app.live_market import OWNER_REF  # noqa: PLC0415
    out: list[Watched] = []
    async with get_sessionmaker()() as db:
        for s in await strategy_store.list_strategies(db, OWNER_REF):
            try:
                tracked = await read_tracked(s.id, None)
            except (TrackedExited, TrackedUnreadable):
                continue
            if tracked is None:
                continue
            spot = provider.underlying_quote(tracked.position.underlying)
            stype = check.strategy_type(tracked.position, None if spot is None else spot.ltp,
                                        provider.instrument_master())
            resolved = await check.resolve(db, OWNER_REF, s.id, stype)
            if resolved.body is not None:
                out.append(Watched(OWNER_REF, s.id, tracked, resolved.body, resolved.is_system, OWNER_REF))
    return out


async def _serve() -> int:  # pragma: no cover - the process wiring; each part is tested on its own
    from ofo_app import catalogue_store, feed_mode  # noqa: PLC0415
    from ofo_app.db import get_engine  # noqa: PLC0415
    from ofo_app.feed_bus import BusSocket  # noqa: PLC0415
    from ofo_app.live_market import LIVE_RATE, OWNER_REF, KiteProvider, listed_for_kite  # noqa: PLC0415
    async with get_engine().connect() as conn:
        catalogue = await catalogue_store.load_catalogue(conn)

    def clock() -> datetime.datetime:
        return datetime.datetime.now(IST)

    provider = KiteProvider(listed_for_kite(catalogue.all_entries()), clock=clock)
    socket = BusSocket(provider, user_ref=OWNER_REF, clock=clock, redis_url=feed_mode.redis_url())
    worker = Worker(provider_for=lambda _owner: provider, lister=functools.partial(owner_lister, provider), clock=clock, rate=LIVE_RATE)
    feed = asyncio.create_task(socket.run(), name="background-feed")
    try:
        await worker.run()
    finally:
        socket.stop()
        feed.cancel()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"python -m {roles.BACKGROUND.start_module}",
        description=f"Start the {roles.BACKGROUND.name} role (REQ-165 playbook checks with no screen open).")
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(_serve())


if __name__ == "__main__":
    raise SystemExit(main())
