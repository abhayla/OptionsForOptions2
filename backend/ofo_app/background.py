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
3. A fresh check builds ``StrategyState`` through the SCREEN's own builder, ``adjustment_check.state_of``
   (``background_state``; never a copy of it), so a rule on max profit, max loss, ATM IV or the previous close answers
   the same here as on the screen. Its ``MarketInputs`` (``market_inputs``) is the screen reader's shape built from the
   price read: each option's IV and Greeks are the SHARED per-option figures (``FeedScope.call`` over the outcome
   service's public ``solved_iv`` and the chain values' rounded engine Greeks, REQ-050 AC-3), once per option per
   price update for every holder, never a whole-chain model. They are valued at the snapshot instant (the price's own
   time); the screen values at its clock, so the two are equal when the clock reads the price's time and otherwise
   differ only by the time decay of that gap. ``state_of`` -> ``price_after`` prices the strategy's own legs (payoff
   kinks, breakevens, POP); the full scenario table (``ofo.scenario.views.scenario_values``) is never called
   (REQ-166 AC-2). Margin is None: the background has no margin read (as a screen whose margin read failed,
   ``missing_margin``).
4. ``adjustment_check.evaluate_and_remember`` (rule memory, F-71) then the screen's own record sync
   (``routes.adjustment_check.sync_records``: one open record per flagged rule, REQ-112), so the single-outcome rule
   holds the same here as on the screen. One strategy's error is logged with its id and does not stop the others
   (REQ-115 AC-9).

Restart (REQ-115 AC-3, REQ-165 AC-5): the monitors are rebuilt from the database on start (``rebuild``); rule memory
lives in ``playbook_store.rule_state`` and an already open record is returned, never re-opened.

Not built here (named, not hidden): the Notifier alert of REQ-115 AC-6 (no heartbeat alert is sent); the screen's
GET reading the worker's latest result (REQ-165 AC-6); per-user feeds beyond the single owner (ADR-051 V1); ``_serve``
does not yet write the monitored legs into the bus's wanted set itself (it prices only what the api role holds on
the feed), so a leg no screen ever opened reads as "no price for one leg" (paused, never a guess).

Wanted tokens (GC-MU step 4c): each cycle, when a Redis client is given (``want_client``), ``_write_wants`` writes ONE
snapshot per feed owner with ``feed_bus.write_background_want``: the tokens of its monitored strategies' legs plus
each underlying's index token, so with no screen open the feed still subscribes them. Written when the set changed
and at least every ``feed_bus.WANT_REFRESH_S`` (the snapshot expires after ``WANT_TTL_MS``). Answer states:
- no monitored strategy: an EMPTY snapshot is written for an owner written before, so its stale wishes lapse within
  one cycle instead of up to ``WANT_TTL_MS``; an owner never written gets nothing (an absent key already wants nothing);
- a leg (or the underlying's index) with no token: that strategy is PAUSED with ``PriceState.LEG_MISSING`` and none of
  its tokens are written; the other strategies are written;
- Redis not answering (any exception): logged, counted in ``errors``, the cycle goes on; retried next cycle;
- more than ``feed_bus.MAX_WANTED_TOKENS``: not written (the relay would refuse it whole), logged and counted in
  ``errors``; never cut silently.
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
from ofo.adjustment.approaches import ChainRow
from ofo.engine.black_scholes import Greeks, year_fraction
from ofo.engine.legs import Instrument
from ofo.engine.model import expiry_model, greeks, iv_price
from ofo.instruments.models import ZERODHA
from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.feed_health import market_closed_for
from ofo.marketdata.forward import parity_forward
from ofo.marketdata.quote import is_live_price
from ofo.marketdata.shared_compute import FeedScope, SharedCompute
from ofo.marketdata.spot_source import SourceReading, SourceState, resolve_spot
from ofo.outcome.service import solved_iv, unit_greeks
from ofo.rules.inputs import DataHealth
from ofo.scenario.spot import spot_reading
from ofo.timeutil import IST

from ofo_app import adjustment_check as check
from ofo_app import calc_speeds, feed_bus, roles
from ofo_app.routes.adjustment import MarketInputs

log = logging.getLogger("ofo_app.background")

DEFAULT_MAX_PER_CYCLE: Final = 200  # strategies checked in one cycle; the rest roll to the next (B4 (a))
#: the recent checks and errors kept in memory for tests and status (a long-running process must not grow without end:
#: 1,000 strategies checked each second would add ~21.6 million entries in one market day)
RECENT_KEPT: Final = 1000
REBUILD_SECONDS: Final = 30  # the monitor set is re-read this often, so a newly tracked strategy joins (AC-3: 60 s)
_MICROS: Final = 1_000_000


class PriceState(enum.Enum):
    FRESH = "fresh"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    LEG_MISSING = "leg_missing"
    MARKET_CLOSED = "market_closed"
    CHECK_FAILED = "check_failed"


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
    expiries = {x.expiry for x in position.legs}
    chains = {e: tuple(provider.option_chain_snapshot(position.underlying, e)) for e in expiries}
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


def _option_greeks(em: Any, kind: Instrument, strike: Decimal, iv: Decimal) -> Greeks | None:
    """One option's per-unit Greeks exactly as the screen's chain values make them (``chain_values.chain_model``: the
    engine's rounded ``greeks``; a zero gamma replaced by the exact one); None when the engine refuses the inputs."""
    try:
        g = greeks(em, kind, strike, iv).greeks
        exact = unit_greeks(em, kind, strike, iv).gamma if g.gamma == 0 else None
    except (ValueError, ArithmeticError):
        return None
    return Greeks(g.delta, g.gamma if exact is None or exact <= 0 else exact, g.theta, g.vega)


def _figures(shared: FeedScope, at: tuple, quote: Any, em: Any) -> tuple[Decimal | None, Greeks | None]:
    """(IV, Greeks) of one option through the SHARED per-option figures (REQ-050 AC-3, REQ-166 AC-2): each computed
    once per (feed owner, underlying, expiry, snapshot instant, instrument id, exact inputs) for every holder. The
    quote refusals are the chain values' own (no live price, no IV price -> no figure). ``at`` = (underlying, expiry,
    snapshot instant)."""
    if quote.instrument_type not in (Instrument.CE, Instrument.PE) or quote.strike is None \
            or not is_live_price(quote.ltp):
        return None, None
    price = iv_price(quote)
    if price is None:
        return None, None
    where = (*at, quote.instrument_id)
    iv = shared.call(where, solved_iv, em, quote.instrument_type, price, quote.strike)
    if iv is None:
        return None, None
    return iv, shared.call(where, _option_greeks, em, quote.instrument_type, quote.strike, iv)


def market_inputs(watched: Watched, read: PriceRead, shared: FeedScope, now: datetime.datetime,
                  rate: Decimal) -> MarketInputs:
    """The screen's ``MarketInputs`` (``adjustment_readers.read_market``) from a fresh price read, every per-option
    figure from the shared cache instead of a whole-chain model: the first leg's expiry, the legs' rows, the same ATM
    IV rule (the IV of the call nearest the forward that the model prices), the same last close. Valued at the
    snapshot instant (the price's own time), so a figure is shared per price update; the screen values at its clock,
    so the two agree exactly when the clock reads the price's time (named in the module docstring).
    Not available -> None, as on the screen: no forward (spot or chain refused) -> no Greeks, no ATM IV, no forward."""
    from ofo_app import scenario_mode  # noqa: PLC0415 - read at check time (the screen's own scenario switch)
    from ofo_app.adjustment_readers import read_last_close  # noqa: PLC0415 - the screen's last-close reader
    position = watched.tracked.position
    expiry = position.legs[0].expiry
    chain = tuple(sorted(read.chains[expiry], key=lambda q: q.instrument_id))
    instant = _snapshot_instant(read, expiry)
    em = fwd = None
    try:
        fwd = shared.call((read.spot.underlying, expiry, instant, None), parity_forward, chain, read.spot, expiry,
                          instant, rate)
        em = expiry_model(spot_reading(read.spot), fwd)
    except (ValueError, ArithmeticError):  # ForwardUnavailable / SpotRefused are ValueErrors: no model figures
        em = fwd = None
    at = (read.spot.underlying, expiry, instant)
    rows: list[ChainRow] = []
    ids: dict[str, str] = {}
    leg_greeks: dict[str, Greeks] = {}
    for i, x in enumerate(position.legs):
        if x.expiry != expiry:
            continue  # the screen reads the first leg's expiry only (read_market)
        q = read.legs[i]
        g = None if em is None else _figures(shared, at, q, em)[1]
        rows.append(ChainRow(x.strike, x.type, expiry, x.tradingsymbol, q.ltp, q.bid, q.ask,
                             None if g is None else g.delta, True, True, "unknown", None))
        ids[x.tradingsymbol] = q.instrument_id
        if g is not None:
            leg_greeks[x.tradingsymbol] = g
    vol = None
    if em is not None and fwd is not None:
        calls = sorted((q for q in chain if q.instrument_type is Instrument.CE and q.strike is not None),
                       key=lambda q: (abs(q.strike - fwd.forward), -q.strike))
        for q in calls:  # read_market's _atm_vol: the call nearest the forward among those the model prices
            iv, g = _figures(shared, at, q, em)
            if iv is not None and g is not None:
                vol = iv
                break
    try:
        years = year_fraction(instant, expiry)
    except ValueError:
        years = None
    feed = SourceReading(SourceState.STATED, read.spot.ltp, read.spot.timestamp)
    last = read_last_close(read.spot, False, scenario_mode.current(), now)  # a check runs only with the market open
    return MarketInputs(tuple(rows), ids, None if fwd is None else fwd.forward, years, vol, feed, last, now,
                        watched.expiry_kind, leg_greeks)


def background_state(watched: Watched, read: PriceRead, shared: FeedScope, now: datetime.datetime,
                     rate: Decimal) -> pe.StrategyState:
    """The check's state through the SCREEN's own builder (``adjustment_check.state_of``), never a copy of it. Margin:
    the background has no margin read, so None (as a screen whose margin read failed: ``missing_margin``). Charge
    rates: None (``state_of`` reads only the gross figures, which carry no charges). The REST spot is not read (a
    check runs only on a fresh feed)."""
    market = market_inputs(watched, read, shared, now, rate)
    spot = resolve_spot(market.feed, None, market.last_close, now=now)
    return check.state_of(watched.tracked, market, spot, None, None, fresh=True, body=watched.body)


async def record_check(watched: Watched, state: pe.StrategyState, scn: Any = None) -> pe.Evaluation:
    """The check and its records in one transaction, through the screen's own functions (REQ-165 AC-5)."""
    from ofo_app import playbook_store  # noqa: PLC0415 - the database layer only when a check runs
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415
    from ofo_app.routes.adjustment_check import sync_records  # noqa: PLC0415
    async with get_sessionmaker()() as db:
        ev = await check.evaluate_and_remember(db, watched.user_ref, watched.strategy_id, watched.body, state, scn,
                                               watched.tracked.position)
        source = playbook_store.SOURCE_SYSTEM if watched.is_system else playbook_store.SOURCE_OWN
        await sync_records(db, watched.user_ref, watched.strategy_id, ev, source, watched.body)
        await db.commit()
    return ev


Lister = Callable[[], Awaitable[list[Watched]]]
Recorder = Callable[[Watched, pe.StrategyState], Awaitable[Any]]


class Worker:
    """The background role's monitors and their cycle. Every seam is injected; ``main`` wires the real ones."""

    def __init__(self, *, provider_for: Callable[[str], Any], lister: Lister,  # noqa: PLR0913
                 clock: Callable[[], datetime.datetime], rate: Decimal, recorder: Recorder = record_check,
                 cache: SharedCompute | None = None, max_per_cycle: int = DEFAULT_MAX_PER_CYCLE,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, want_client: Any = None) -> None:
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
        self._speed: Decimal | None = None  # the last good background speed (a failed read keeps it)
        self._want_client = want_client  # a Redis client (the feed bus); None = no wanted-set write
        self._token_maps: dict[int, tuple] = {}  # id(provider) -> (provider, option tokens, id -> token)
        self._wants_written: dict[str, tuple[list[int], datetime.datetime]] = {}  # owner -> (tokens, when)

    async def rebuild(self) -> None:
        """REQ-115 AC-3: the monitors from the database (the lister); a strategy's memory stays in the store."""
        monitors = await self._lister()
        self.monitors = monitors
        self._rebuilt_at = self._clock()
        log.info("background: %s strategies monitored", len(monitors))

    async def _rebuild_safely(self) -> None:
        """A failed re-read keeps the last good list and is retried next cycle (REQ-115 AC-9)."""
        try:
            await self.rebuild()
        except Exception as exc:  # contained to this step: the previous list stays
            log.exception("background: re-reading the strategy list failed; keeping the last list")
            _keep_recent(self.errors, (0, type(exc).__name__))

    def background_seconds(self) -> Decimal:
        return self.valve.slowed(calc_speeds.read_speeds().background)

    def _speed_safely(self) -> Decimal | None:
        """The speed now; a failed read keeps the last good one, None when there is none yet (REQ-115 AC-9)."""
        try:
            self._speed = self.background_seconds()
        except Exception as exc:  # contained to this step
            log.exception("background: reading the background speed failed")
            _keep_recent(self.errors, (0, type(exc).__name__))
        return self._speed

    def _tokens_of(self, provider: Any) -> tuple[dict, dict]:
        """(option key -> token, instrument id -> token) from the provider's instrument master, built once per provider
        (the one list the API side maps from; no second lookup table)."""
        kept = self._token_maps.get(id(provider))
        if kept is None or kept[0] is not provider:
            options: dict[tuple, int] = {}
            by_id: dict[str, int] = {}
            for lc in provider.instrument_master():
                c = lc.contract
                token = int(lc.ref(ZERODHA).broker_token)
                by_id[f"{c.exchange_segment}:{c.exchange_token}"] = token
                options[(c.name, c.expiry, c.strike, c.instrument_type)] = token
            kept = (provider, options, by_id)
            self._token_maps[id(provider)] = kept
        return kept[1], kept[2]

    def _strategy_tokens(self, w: Watched) -> set[int] | None:
        """The tokens one strategy needs (every leg and the underlying index); None when any has no token."""
        provider = self._provider_for(w.feed_owner)
        options, by_id = self._tokens_of(provider)
        position = w.tracked.position
        tokens = {options.get((position.underlying, x.expiry, x.strike, x.type)) for x in position.legs}
        index_id = provider.index_id(position.underlying)
        tokens.add(None if index_id is None else by_id.get(index_id))
        return None if None in tokens else tokens

    async def _write_wants(self, now: datetime.datetime) -> None:
        """Step 4c: one snapshot per feed owner (module docstring); never raises."""
        if self._want_client is None:
            return
        wanted: dict[str, set[int]] = {}
        for w in self.monitors:
            try:
                tokens = self._strategy_tokens(w)
            except Exception as exc:  # contained: this strategy is paused, the others are written
                log.exception("background: finding the tokens of strategy %s failed", w.strategy_id)
                _keep_recent(self.errors, (w.strategy_id, type(exc).__name__))
                tokens = None
            if tokens is None:
                self.status[w.strategy_id] = MonitoringStatus.PAUSED
                self.paused_reason[w.strategy_id] = PriceState.LEG_MISSING
                self._signature.pop(w.strategy_id, None)
                wanted.setdefault(w.feed_owner, set())
                continue
            wanted.setdefault(w.feed_owner, set()).update(tokens)
        for owner in self._wants_written.keys() - wanted.keys():
            wanted[owner] = set()  # no monitored strategy left for this owner: an empty snapshot
        for owner, tokens in wanted.items():
            listed = sorted(tokens)
            before = self._wants_written.get(owner)
            if before is not None and before[0] == listed \
                    and _seconds(now - before[1]) < Decimal(str(feed_bus.WANT_REFRESH_S)):
                continue
            if len(listed) > feed_bus.MAX_WANTED_TOKENS:
                log.error("background: %s wanted tokens for %s exceed the cap of %s; not written", len(listed),
                          owner, feed_bus.MAX_WANTED_TOKENS)
                _keep_recent(self.errors, (0, "WantTooLarge"))
                continue
            try:
                await feed_bus.write_background_want(self._want_client, owner, listed)
            except Exception as exc:  # Redis not answering: the cycle goes on, retried next cycle
                log.exception("background: writing the wanted tokens for %s failed", owner)
                _keep_recent(self.errors, (0, type(exc).__name__))
                continue
            self._wants_written[owner] = (listed, now)

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
        state = background_state(w, read, FeedScope(self.cache, w.feed_owner), now, self._rate)
        await self._recorder(w, state)
        self._signature[w.strategy_id] = sig
        self._last_check[w.strategy_id] = now
        _keep_recent(self.checks, (w.strategy_id, now))
        return True

    async def cycle(self) -> None:
        now = self._clock()
        if self._rebuilt_at is None or _seconds(now - self._rebuilt_at) >= REBUILD_SECONDS:
            await self._rebuild_safely()
        await self._write_wants(now)  # not behind the speed: the feed is wanted whatever the checks do
        every = self._speed_safely()  # read on EVERY cycle (REQ-166 AC-1)
        if every is None:
            log.error("background: no background speed has been read yet; this cycle is skipped")
            return
        n = len(self.monitors)
        ran, slowest, visited = 0, Decimal(0), 0
        while visited < n and ran < self._max:
            w = self.monitors[(self._cursor + visited) % n]
            visited += 1
            started = self._clock()
            try:
                ran += await self._check_one(w, now, every)
            except Exception as exc:  # REQ-115 AC-9: one strategy's failure never stops the others
                log.exception("background: strategy %s check failed", w.strategy_id)
                _keep_recent(self.errors, (w.strategy_id, type(exc).__name__))
                self.status[w.strategy_id] = MonitoringStatus.PAUSED  # not checked: never shown as active
                self.paused_reason[w.strategy_id] = PriceState.CHECK_FAILED
                self._signature.pop(w.strategy_id, None)
            slowest = max(slowest, _seconds(self._clock() - started))
        self._cursor = (self._cursor + visited) % n if n else 0
        self.valve.observe(self._clock(), slowest, n - visited)

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> None:
        while not self._stop:
            try:
                await self.cycle()
            except Exception as exc:  # one cycle's failure never ends the role (CancelledError is not an Exception)
                log.exception("background: a cycle failed; the next cycle runs")
                _keep_recent(self.errors, (0, type(exc).__name__))
            wait = self._speed_safely() or Decimal(1)  # read again for the sleep; no good speed yet -> 1 s
            await self._sleep(float(wait))  # float-ok: asyncio.sleep takes seconds as float


def _keep_recent(kept: list, item: object) -> None:
    """Append ``item`` and drop the oldest entries beyond ``RECENT_KEPT``."""
    kept.append(item)
    if len(kept) > RECENT_KEPT:
        del kept[:-RECENT_KEPT]


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
                if tracked is None:
                    continue
                spot = provider.underlying_quote(tracked.position.underlying)
                stype = check.strategy_type(tracked.position, None if spot is None else spot.ltp,
                                            provider.instrument_master())
                resolved = await check.resolve(db, OWNER_REF, s.id, stype)
            except (TrackedExited, TrackedUnreadable):
                continue
            except Exception:  # REQ-115 AC-9: one strategy's lookup failing never drops the others from the list
                log.exception("background: listing strategy %s failed; it is skipped", s.id)
                continue
            if resolved.body is not None:
                out.append(Watched(OWNER_REF, s.id, tracked, resolved.body, resolved.is_system, OWNER_REF))
    return out


async def _serve() -> int:  # pragma: no cover - the process wiring; each part is tested on its own
    from ofo_app import feed_mode  # noqa: PLC0415

    # live rows by key only (the provider's instrument list); each leg's stored id reached its terms through
    # tracked_contracts.resolve in read_tracked, never through the catalogue store here
    from ofo_app.catalogue_store import load_catalogue  # noqa: PLC0415
    from ofo_app.db import get_engine  # noqa: PLC0415
    from ofo_app.feed_bus import BusSocket  # noqa: PLC0415
    from ofo_app.live_market import (  # noqa: PLC0415
        LIVE_RATE,
        OWNER_REF,
        KiteProvider,
        listed_for_kite,
    )
    async with get_engine().connect() as conn:
        catalogue = await load_catalogue(conn)

    def clock() -> datetime.datetime:
        return datetime.datetime.now(IST)

    provider = KiteProvider(listed_for_kite(catalogue.all_entries()), clock=clock)
    socket = BusSocket(provider, user_ref=OWNER_REF, clock=clock, redis_url=feed_mode.redis_url())
    bus = feed_bus.new_client(feed_mode.redis_url())
    worker = Worker(provider_for=lambda _owner: provider, lister=functools.partial(owner_lister, provider),
                    clock=clock, rate=LIVE_RATE, want_client=bus)
    feed = asyncio.create_task(socket.run(), name="background-feed")
    try:
        await worker.run()
    finally:
        socket.stop()
        feed.cancel()
        await bus.aclose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"python -m {roles.BACKGROUND.start_module}",
        description=f"Start the {roles.BACKGROUND.name} role (REQ-165 playbook checks with no screen open).")
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(_serve())


if __name__ == "__main__":
    raise SystemExit(main())
