"""The paper stop-loss monitor: a live tick crossing an armed paper trigger records stop orders once (GC-TP step 7a).

Spec basis: REQ-109 AC-8 ("fires each trigger once (also across a restart)"); ADR-207 (5) (Conditional Exit on the
index - exit all legs - and a per-leg stop-loss, Sensibull screens 221-224); ADR-015 (stale is never live); ADR-119
(the market calendar); ADR-003 (decision-support wording); RD-121 (paper trades are stated plainly as not real).

One asyncio task, started by the app lifespan only when the live market is on, stopped on shutdown (the
catalogue_refresh pattern). It never reaches Zerodha: it records PAPER orders only, through paper_store.place
(tests_app/test_paper_order_door.py walks this module's import graph).

- Load: every armed trigger in ONE query (paper_trigger_store.armed), their strategies' orders in ONE query, their
  contracts in one batch; subscribes on the market's fan-out the index of every armed trigger (S-20), the contract of
  each leg stop and every open contract of a strategy with a conditional exit (prices read from the provider).
  Reloads when a route adds or cancels a trigger (``notify``), every ``RELOAD_SECONDS``, and when the market's feed
  object changes (a new login).
- On a quote: per-tick work is the armed triggers watching that instrument. Nothing fires outside market hours (a
  trigger set after hours arms at 09:15) or on a price that is not live (stops.crossed).
- A fire is ONE transaction: the open quantity is re-read; none open -> the strategy's (or the leg's) triggers are
  cancelled; any open contract without a live price -> nothing is written and the trigger stays armed; otherwise
  ``claim_fire`` (no row -> another tick, monitor or a run before a restart already fired it: nothing), then one stop
  order per open contract for its whole open quantity on the opposite side at that contract's live price from ONE
  provider read (a leg stop: the tick's own price), and the alert row. A write that fails or times out rolls back and
  is logged by type; the next crossing tick retries. A paper exit is never back-dated: it is recorded at the tick that
  fires it.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo.engine.legs import Instrument
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.instruments.models import FUTURE_TYPE
from ofo.marketdata.quote import NormalizedQuote
from ofo.outcome import read_snapshot
from ofo.strategy.definition import display_contract
from ofo.tracking import paper, stops
from ofo.tracking.orderbook import net_positions
from ofo.tracking.paper_alert import ALERT_BODY_TEMPLATES, STOP_LINE_TEMPLATES, alert_body, stop_reason_at

# may_act.market_open is the ONE market-open rule (#740); the settings-reader guard names this file by line number
from ofo_app import actionable_alerts, may_act, monitoring_state, paper_exit, paper_store, tracked_contracts
from ofo_app import paper_trigger_store as triggers
from ofo_app.live_push import LiveFeed
from ofo_app.routes.outcome import SettingsReader, feed_scope, with_rate_in_force

log = logging.getLogger(__name__)
# ADR-330 (3)(b): a fired stop is raised through ofo_app.actionable_alerts.inform, never a table write of its own

RELOAD_SECONDS: Final = 60.0
POLL_SECONDS: Final = 0.5
FIRE_TIMEOUT_SECONDS: Final = 10.0

#: A leg-price reader: (feed, underlying, feed keys) -> each key's paper price answer, from ONE provider read.
LegPrices = Callable[[LiveFeed, str, Sequence[str]], Mapping[str, paper.Price]]
Sessions = Callable[[], Any]  # an async_sessionmaker: ``async with sessions() as session``


def provider_prices(feed: LiveFeed, underlying: str, keys: Sequence[str]) -> Mapping[str, paper.Price]:
    """The routes' price rule: one snapshot of the provider, each key's live-P&L price answer (paper.leg_price)."""
    ctx = feed.ctx
    snapshot = read_snapshot(ctx.provider, underlying, list(keys), ctx.clock(), ctx.rate, feed_scope(ctx),
                         quality=ctx.forward_quality)
    return {k: paper.leg_price(snapshot, k) for k in keys}


# Lane FE (28 Nov, review F2) - one judge for every armed exit. ``_exits_with_reading`` compares each exit with ONE
# reading: a feed tick (``on_quote``) or, every pass of ``step``, the newer of this feed's own live quote and the
# reading the worker used to call the trade watched (``monitoring_state.read_index`` / ``read_leg``: feed tick or REST
# stand-in, with its time). No reading within the age -> the exit is NOT evaluated and its trade is reported not run
# (``monitoring_state.ExitsPublisher``: the trade reads "Monitoring paused", never watched). No order is retried.
#: a crossed exit that could not run (no live leg price) is tried again from the polled reading no sooner than this
POLLED_RETRY_SECONDS: Final = 5.0
FIRST_LOAD_RETRY_SECONDS = 5.0  # a monitor that has never loaded its exits retries sooner than the reload period
#: a ``_Reading`` of this monitor's own feed quote (its ticks judge it); the worker's are "feed" / "rest"
OWN_FEED: Final = "own"
#: The kind an "exit could not run" message is stored under: the closest informational kind the alert table's kind
#: check allows (a kind of its own needs a migration).
EXIT_NOT_RUN_KIND: Final = "stop_fired"
#: How long a stop's fire waits for an index value the held feed does not show yet (``market_read``'s own hold)
INDEX_WAIT_SECONDS: Final = 1.0


#: Lane FE3 item 6: the wordings of the line of a leg stop that HAS fired (past tense, the figure at the fill), for
#: reading a stored line back (``actionable_alerts.inform`` ``restore``); the list in ``paper_alert`` is not
#: this lane's.
FIRED_LINE_TEMPLATES: Final = ("paper_leg_stop_fired", "paper_leg_stop_fired_unlimited", "paper_leg_stop_fired_unknown")
#: Lane FE3 item 2: a reload that could not read the book (armed triggers, position kinds, orders) is tried again this
#: soon, and the last known watch list is kept for at most ``BOOK_UNREAD_MAX_S`` of failure (the same two minutes as the
#: heartbeat rule, ``monitoring_state.SNAPSHOT_STALE_S``): past it no exit is judged and every trade is reported
#: "not watched: could not read the book".
READ_RETRY_SECONDS: Final = 5.0
BOOK_UNREAD_MAX_S: Final = float(monitoring_state.SNAPSHOT_STALE_S)


def exit_not_run_rule(trigger_id: int) -> str:
    """The ONCE-A-DAY rule of the "exit could not run" message (ADR-330 (44)): one message per exit (trigger) per India
    day, however many blocked ticks that day. The rule is this id: ``actionable_alerts.inform_once_per_day`` writes the
    message only when no stored row of this id falls in the India day of the tick, so a restart cannot repeat it."""
    return f"info:exit_not_run:{trigger_id}"


@dataclass(frozen=True)
class _NoPrice:
    """An exit that cannot run: the first contract without a live price (its price is stale, missing or unreadable)."""

    contract_id: int


_bus: Any = None  # the one Redis client of this process (created at first use)


def _bus_client() -> Any:
    """The bus client (Redis), or None when this process has no bus (in-process feed: no worker, no reading). One
    client per process; a test replaces this function."""
    global _bus  # noqa: PLW0603
    from ofo_app import feed_bus, feed_mode  # noqa: PLC0415 - late: only a bus process needs them
    if feed_mode.feed_mode() != feed_mode.BUS:
        return None
    if _bus is None:
        _bus = feed_bus.new_client(feed_mode.redis_url())
    return _bus


@dataclass(frozen=True)
class _Reading:
    """The one index value an exit is judged on: its quote time and where it came from (``OWN_FEED``, or the worker's
    "feed" tick / "rest" stand-in)."""

    value: Decimal
    at: datetime.datetime
    source: str


def _no_listener(_quote: Any) -> None:
    """The monitor drains its queue itself (fanout.drain); a tick alone calls nothing."""


@dataclass
class _Watch:
    armed: triggers.ArmedTrigger
    key: str


def _contract_text(found: tracked_contracts.TrackedContract) -> ExplanationText:
    if found.stored is None:
        raise RuntimeError(f"contract id {found.contract_id} has no stored row ({found.state})")
    c = found.stored.listed.contract
    strike = None if c.instrument_type == FUTURE_TYPE else c.strike
    return display_contract((c.name, Instrument(c.instrument_type), strike, c.expiry))  # type: ignore[return-value]


#: kind of position -> the report's why for an armed exit this monitor does not judge (any other kind: not run)
_NOT_APPLICABLE_WHY: dict[str, str] = {"real": monitoring_state.EXIT_NOT_APPLICABLE}


class BookUnreadError(RuntimeError):
    """A read of the book (armed triggers, position kinds, orders) answered nothing usable: the last watch is kept."""


class PaperMonitor:
    _held_count: int | None = None  # last logged count (class default: tests skip __init__)
    def __init__(self, sessions: Sessions, feed: Callable[[], LiveFeed | None], *,  # noqa: PLR0913 - seams
                 read_settings: SettingsReader,
                 leg_prices: LegPrices = provider_prices,
                 reload_seconds: float = RELOAD_SECONDS, monotonic: Callable[[], float] | None = None,
                 index_wait: Any = None) -> None:
        self._sessions = sessions
        self._index_wait = index_wait  # a ``market_read.Wait`` (tests inject the clock); None: INDEX_WAIT_SECONDS
        self._told: dict[int, datetime.date] = {}  # trigger id -> India day it was told (a short cut, not the record)
        # REQ-167 AC-4 (GC-SET step 5a): the risk-free rate and forward settings are read at each fire, never the
        # live feed's context captured when the socket started (which holds the registry default)
        self._read_settings = read_settings
        self._feed_source = feed
        self._leg_prices = leg_prices
        self._reload_seconds = reload_seconds
        self._monotonic = monotonic or asyncio.get_running_loop().time
        self._feed: LiveFeed | None = None
        self._feed_asked: LiveFeed | None = None  # the feed the last reload (even a failed one) was made for
        self._handle: int | None = None
        self._standing_feed: LiveFeed | None = None
        self._standing: list[int] = []  # the standing hold's fan-out handles (open paper legs + their indexes)
        self._watch: dict[str, list[_Watch]] = {}
        self._exits: list[_Watch] = []  # every armed index exit, whether or not a feed holds its index
        self._index_age: datetime.timedelta | None = None  # the index age rule in force
        self._index_age_at: float | None = None  # monotonic time it was last read
        self._retry_at: dict[int, float] = {}  # trigger id -> monotonic time of its next polled attempt
        self._judged: dict[int, tuple[Decimal, datetime.datetime]] = {}  # trigger id -> the reading it last crossed on
        self._blocked: set[int] = set()  # trigger ids crossed on a reading that did not run (reported not run)
        self._carried: list[NormalizedQuote] = []  # ticks queued on a handle a reload replaced: judged, never lost
        self._exits_publisher: tuple[Any, monitoring_state.ExitsPublisher] | None = None
        self._dirty = True
        self._loaded_at: float | None = None
        self._na_strategies: dict[int, str] = {}  # strategy -> why its armed exits are not judged here (review F2)
        self.not_applicable: dict[int, str] = {}  # trigger id -> the position kind that has no stops here (told once)
        self._ever_loaded = False  # review F3: no armed exit is known until a reload has succeeded; no claim is made
        self.book_unread_since: float | None = None  # FE3 item 2: monotonic time of the first failed reload in a row
        self.read_failures = 0  # reloads that could not read the book (the counter the tests and the log name)
        self.fires = 0
        self.failures = 0

    def notify(self) -> None:
        """A route added or cancelled a trigger: reload before the next quote is handled."""
        self._dirty = True

    def watched(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._watch.items()}

    def book_unread_too_long(self) -> bool:
        """FE3 item 2: reloads have failed for longer than ``BOOK_UNREAD_MAX_S``: the kept watch list is no longer
        judged (a position kind that cannot be read is never stopped here, ADR-330 (64): fail closed)."""
        return self.book_unread_since is not None and self._monotonic() - self.book_unread_since > BOOK_UNREAD_MAX_S

    async def reload(self) -> None:
        """Armed triggers (one query), their orders (one query), contracts (one batch); resubscribes the fan-out.

        FE3 item 2: a read that fails (the database, ``strategy_store.kinds_of``) never empties the list: the last known
        watch is kept, the failure is counted and logged, and the next try is ``READ_RETRY_SECONDS`` away. The error
        goes on to the caller (``step`` and ``run_forever`` log it); only a failure that lasts longer than
        ``BOOK_UNREAD_MAX_S`` changes what the trades read (``book_unread_too_long``)."""
        self._dirty = False
        self._loaded_at = self._monotonic()
        self._feed_asked = self._feed_source()  # review F2: a failed first load must not look like a new feed
        try:
            await self._reload()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.read_failures += 1
            if self.book_unread_since is None:
                self.book_unread_since = self._monotonic()
                log.warning("paper monitor: the book could not be read; the last watch is kept", exc_info=True)
            due_after = (self._reload_seconds if self._ever_loaded
                         else min(self._reload_seconds, FIRST_LOAD_RETRY_SECONDS))
            self._loaded_at = self._monotonic() - due_after + min(due_after, READ_RETRY_SECONDS)  # review F2
            raise
        self.book_unread_since = None

    async def _reload(self) -> None:
        feed = self._feed_source()
        async with self._sessions() as session:
            armed = await self._paper_only(session, await triggers.armed(session))
            orders = await triggers.orders_of(session, sorted({a.trigger.strategy_id for a in armed}))
            open_ids = {sid: _open(o) for sid, o in orders.items()}
            ids = sorted({a.trigger.contract_id for a in armed if a.trigger.contract_id is not None}
                         | {c for a in armed if a.trigger.kind == "conditional_exit"
                            for c in open_ids[a.trigger.strategy_id]})
            found = {c.contract_id: c for c in await tracked_contracts.resolve(session, ids)}
            watch: dict[str, list[_Watch]] = {}
            extra: set[str] = set()
            for a in armed:
                t = a.trigger
                if feed is None:
                    break
                index_key = feed.ctx.provider.index_id(a.underlying)  # type: ignore[attr-defined]
                if t.kind == "conditional_exit":
                    key = index_key
                    extra.update(k for k in (found[c].feed_key for c in open_ids[t.strategy_id]) if k is not None)
                else:
                    key = found[t.contract_id].feed_key  # type: ignore[index]
                if index_key is not None:
                    extra.add(index_key)  # S-20: an armed trigger holds its index: a fire's record carries its value
                if key is not None:
                    watch.setdefault(key, []).append(_Watch(a, key))
            self._watch = watch
            self._exits = [_Watch(a, self._key_of(feed, a, found)) for a in armed]  # index exits AND leg stops
            live_ids = {w.armed.trigger.id for w in self._exits}
            self._judged = {k: v for k, v in self._judged.items() if k in live_ids}
            self._retry_at = {k: v for k, v in self._retry_at.items() if k in live_ids}
            self._blocked &= live_ids
            self._resubscribe(feed, sorted(set(watch) | extra))
            # hotfix 27 Nov (DB pool 2 on the PC): the hold's two reads use THIS session, not a second checkout
            await self._reload_hold(feed, found, session)  # AFTER the stop watch: a failed hold never unwatches a stop
        self._ever_loaded = True

    async def _paper_only(self, session: Any, armed: Sequence[triggers.ArmedTrigger]) -> list[triggers.ArmedTrigger]:
        """ADR-330 (64): stops and alerts here cover PAPER trades only; a real position has no stop in this app. An
        armed trigger of a strategy whose position is real, or whose kind could not be read (fail closed), is never
        evaluated or fired: it is left as it is and told once as not applicable. One read for every armed strategy."""
        from ofo_app import position_kind, strategy_store  # noqa: PLC0415 - late: the one kind rule and its reader
        kinds = await strategy_store.kinds_of(session, sorted({a.trigger.strategy_id for a in armed}))
        if armed and self._ever_loaded and all(k == position_kind.UNKNOWN for k in kinds.values()):
            # Lane FE3 (review F3): ``kinds_of`` answers "unknown" for every id when its read FAILS (it swallows the
            # error until Lane FD4 makes it raise); every kind unknown after a list was known is that failure, not a new
            # fact: the last list is kept (and the age rule applies), never replaced by an empty one
            raise BookUnreadError("the position kinds of every armed strategy could not be read")
        keep: list[triggers.ArmedTrigger] = []
        self._na_strategies = {}
        for a in armed:
            kind = kinds.get(a.trigger.strategy_id, position_kind.UNKNOWN)
            if kind == position_kind.PAPER:
                keep.append(a)
                self.not_applicable.pop(a.trigger.id, None)  # review F4: it reads paper again
                continue
            self._na_strategies[a.trigger.strategy_id] = _NOT_APPLICABLE_WHY.get(
                kind, monitoring_state.INDEX_EXITS_NOT_RUN)
            if a.trigger.id not in self.not_applicable:
                self.not_applicable[a.trigger.id] = kind
                log.info("paper trigger %s of strategy %s not applicable: the position is %s (ADR-330 (64))",
                         a.trigger.id, a.trigger.strategy_id, kind)
        live = {a.trigger.id for a in armed}
        self.not_applicable = {k: v for k, v in self.not_applicable.items() if k in live}
        return keep

    async def _read_index_age(self) -> None:
        """The index age rule in force (the one the worker's read applies), read at most once per reload period and
        only when a worker reading exists to be judged (a bus). A store that cannot answer leaves the last value; none
        yet means no worker reading is trusted (the exits then rest on this feed's own index)."""
        from ofo.settings import calc as settings_calc  # noqa: PLC0415 - late: read only when a bus holds a reading
        if self._index_age_at is not None and self._monotonic() - self._index_age_at < self._reload_seconds:
            return
        self._index_age_at = self._monotonic()
        try:
            windows = settings_calc.feed_windows(await self._read_settings())
        except Exception as exc:  # noqa: BLE001 - the age stays as it was; the exits are never judged on a guessed age
            log.error("paper monitor: the index age rule could not be read: %s", type(exc).__name__)
            return
        self._index_age = windows.index_quote_max_age

    @staticmethod
    def _key_of(feed: LiveFeed | None, a: triggers.ArmedTrigger,
                found: Mapping[int, tracked_contracts.TrackedContract]) -> str:
        """The feed key an armed trigger is judged on ("" = none: no feed, or the contract has no live feed key)."""
        if feed is None:
            return ""
        if a.trigger.kind == "conditional_exit":
            return feed.ctx.provider.index_id(a.underlying) or ""  # type: ignore[attr-defined]
        contract = found.get(a.trigger.contract_id) if a.trigger.contract_id is not None else None
        return (contract.feed_key if contract is not None else None) or ""

    async def _reload_hold(self, feed: LiveFeed | None, found: Mapping[int, tracked_contracts.TrackedContract],
                           session: Any) -> None:
        """Read (on the reload's own session) and apply the standing hold. A failure is logged and the LAST hold is kept
        (REQ-114, REQ-049)."""
        try:
            open_legs = await triggers.open_legs(session)
            standing = {c.contract_id: c for c in await tracked_contracts.resolve(
                session, sorted({cid for cid, _u in open_legs} - set(found)))}
            self._hold_open_legs(feed, self._standing_keys(feed, open_legs, {**standing, **found}))
        except Exception:  # the stops are already watched; the hold is retried at the next reload
            log.exception("paper monitor: the standing hold of open legs could not be refreshed; keeping the last hold")

    def _resubscribe(self, feed: LiveFeed | None, keys: list[str]) -> None:
        old_feed, old = self._feed, self._handle
        self._feed, self._handle = feed, None
        if feed is not None and keys:
            self._handle = feed.fanout.subscribe(_no_listener, keys)  # new first: no vendor unsubscribe/resubscribe
        if old_feed is not None and old is not None:
            self._carried.extend(old_feed.fanout.drain(old))  # ticks the old handle still holds are judged, not dropped
            old_feed.fanout.unsubscribe(old)

    @staticmethod
    def _standing_keys(feed: LiveFeed | None, open_legs: Sequence[tuple[int, str]],
                       contracts: Mapping[int, tracked_contracts.TrackedContract]) -> list[str]:
        """The feed keys of every open paper leg and its index (the standing hold's set)."""
        if feed is None:
            return []
        keys: set[str] = set()
        for contract_id, underlying in open_legs:
            found = contracts.get(contract_id)
            if found is not None and found.feed_key is not None:
                keys.add(found.feed_key)
            index_key = feed.ctx.provider.index_id(underlying)  # type: ignore[attr-defined]
            if index_key is not None:
                keys.add(index_key)
        return sorted(keys)

    def _hold_open_legs(self, feed: LiveFeed | None, keys: list[str]) -> None:
        """STANDING hold (REQ-133; REQ-118): every open paper leg and its index stay subscribed for as long as the
        strategy is open, not only while a trigger is armed, so a request's own hold-and-read releases only ITS
        reference and never parks the quote (the fan-out unsubscribes the vendor only when the last holder leaves).
        New holds first, old after: no vendor unsubscribe/resubscribe. An id the feed cannot hold (an expired
        contract has no token) is skipped on its own; it never drops the others."""
        old_feed, old = self._standing_feed, self._standing
        new: list[int] = []
        try:
            if feed is not None and keys:
                try:
                    new = [feed.fanout.subscribe(_no_listener, keys, max_queue=1)]  # never drained: keep one quote
                except KeyError:
                    for key in keys:
                        with contextlib.suppress(KeyError):
                            new.append(feed.fanout.subscribe(_no_listener, [key], max_queue=1))
        except BaseException:
            for handle in new:  # a half-made new set is released; the OLD hold stays as it was
                feed.fanout.unsubscribe(handle)  # type: ignore[union-attr]
            raise
        self._standing_feed, self._standing = feed, new
        if len(keys) != self._held_count:  # hotfix 27 Nov: one line per change, not per reload
            self._held_count = len(keys)
            log.info("paper monitor holds %d feed keys (open legs + indexes)", len(keys))
        if old_feed is not None:
            for handle in old:
                with contextlib.suppress(Exception):
                    old_feed.fanout.unsubscribe(handle)

    def close(self) -> None:
        self._resubscribe(None, [])
        self._hold_open_legs(None, [])

    async def step(self) -> int:
        """One pass: reload when due, then handle every queued quote in arrival order. Returns the fires recorded."""
        if self._dirty or self._feed_source() is not self._feed_asked or self._loaded_at is None or \
                self._monotonic() - self._loaded_at >= (self._reload_seconds if self._ever_loaded
                                                        else min(self._reload_seconds, FIRST_LOAD_RETRY_SECONDS)):
            try:
                await self.reload()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - FE3 item 2: the kept watch goes on being judged this pass
                log.error("paper monitor reload failed: %s", type(exc).__name__)
        fired = 0
        carried, self._carried = self._carried, []
        for quote in carried:
            fired += await self.on_quote(quote)
        if self._feed is not None and self._handle is not None:
            for quote in self._feed.fanout.drain(self._handle):
                fired += await self.on_quote(quote)
        if not self._ever_loaded:  # nothing loaded: no exit is known, so no claim is made (review F3)
            return fired
        return fired + await self._index_pass()

    async def on_quote(self, quote: NormalizedQuote) -> int:
        watching = self._watch.get(quote.instrument_id)
        if not watching or self._feed is None or self.book_unread_too_long():
            return 0
        now = self._feed.ctx.clock()
        if not may_act.market_open(self._feed.ctx, now):  # the ONE market rule (the feed's own answer)
            return 0
        try:
            price = paper.price_of(quote, quote.instrument_id)
        except ValueError:  # a price finer than a paisa is never stored
            return 0
        if price.price is None:  # a stale or missing price is not a reading
            return 0
        # a tick is one reading: the same judge as the polled reading (index exits and leg stops alike)
        return await self._exits_with_reading(watching, _Reading(price.price, quote.timestamp, "feed"), now,
                                              polled=False)

    async def _exits_with_reading(self, watches: Sequence[_Watch], reading: _Reading | None, now: datetime.datetime,
                                  *, polled: bool) -> int:
        """THE one judge of index exits (review F2): each exit is compared with ``reading`` and fires when crossed. No
        reading (None) -> nothing is evaluated; the caller reports the trade as not run. ``polled``: a reading
        that crossed an exit which then did not run (no live leg price: the exit stays armed, the message is told once a
        day) is not judged again by a pass for ``POLLED_RETRY_SECONDS``, so a quiet feed never makes a database
        transaction every pass; a tick is always judged."""
        if reading is None:
            return 0
        fired = 0
        stamp = (reading.value, reading.at)
        for w in tuple(watches):
            tid = w.armed.trigger.id
            if polled and self._judged.get(tid) == stamp and self._retry_at.get(tid, 0.0) > self._monotonic():
                continue  # this very reading was judged (a tick, or an earlier pass) and could not run: not yet again
            price = paper.Price(w.key or w.armed.underlying, paper.LIVE, reading.value, reading.at)
            if not stops.crossed(w.armed.trigger, price):
                self._blocked.discard(tid)  # not crossed on this reading: nothing is waiting to run
                continue
            self._judged[tid] = stamp
            self._retry_at[tid] = self._monotonic() + POLLED_RETRY_SECONDS
            if await self._fire_guarded(w, price, now):
                fired += 1
                self._blocked.discard(tid)
            else:
                self._blocked.add(tid)  # crossed and not run (no live leg price here, a failed write): reported
        return fired

    async def _index_reading(self, feed: LiveFeed, underlying: str, now: datetime.datetime,
                             readings: monitoring_state.Readings | None) -> _Reading | None:
        """The index reading an exit of ``underlying`` is judged on: the newer of this feed's own live index and the
        reading the worker used (never an older one over a newer one; none within the age -> None). Both are live by the
        one age rule: this feed's quote by its health, the worker's by ``index_quote_max_age`` from its own time."""
        own = None
        held = self._index_now(feed, underlying)
        if held is not None and held.price is not None and held.at is not None \
                and held.at - now <= monitoring_state.FUTURE_SKEW:  # a quote stamped in the future is no reading
            own = _Reading(held.price, held.at, OWN_FEED)
        worker = None
        if readings is not None and self._index_age is not None:
            found = readings.index(underlying, now, self._index_age)
            if found is not None and _is_paise(found.value):
                worker = _Reading(found.value, found.at, found.source)
        if own is not None and (worker is None or worker.at <= own.at):
            return own
        return worker

    async def _leg_reading(self, feed: LiveFeed, key: str, now: datetime.datetime,
                           readings: monitoring_state.Readings | None) -> _Reading | None:
        """The reading a leg-price exit on ``key`` is judged on: the newer of this feed's own live quote of that
        contract and the price the worker used (``monitoring_state.read_leg``); none -> None (not evaluated and
        reported)."""
        own = None
        held = getattr(feed.ctx.provider, "held_quote", None)
        if held is not None and key:
            try:
                quote = held(key, now)
                answer = paper.price_of(quote, key)
            except ValueError:
                answer, quote = None, None
            if answer is not None and paper.is_live(answer) and answer.price is not None \
                    and quote.timestamp is not None and quote.timestamp - now <= monitoring_state.FUTURE_SKEW:
                own = _Reading(answer.price, quote.timestamp, OWN_FEED)
        worker = None
        if readings is not None and key:
            found = readings.leg(key, now)
            if found is not None and _is_paise(found.value):
                worker = _Reading(found.value, found.at, found.source)
        if own is not None and (worker is None or worker.at <= own.at):
            return own
        return worker

    async def _index_pass(self) -> int:
        """Every pass: judge every armed exit (index exits and leg stops) on its reading through the one judge
        (``_exits_with_reading``), and report to ``monitoring_state`` which trades' exits were NOT evaluated.
        Market closed: nothing is expected to be evaluated (a trigger set after hours arms at 09:15); the report is
        empty."""
        feed = self._feed
        now = feed.ctx.clock() if feed is not None else datetime.datetime.now(datetime.UTC)
        not_run: dict[int, str] = {}
        judged: list[_Watch] = []
        fired = 0
        if self.book_unread_too_long() or feed is None:  # FE3 item 2: no list that cannot be confirmed is judged
            not_run = self._not_judged()
        elif may_act.market_open(feed.ctx, now):
            judged = list(self._exits)
            client = _bus_client()
            readings = None
            if client is not None and judged:  # the worker's prices: one read of its snapshot per pass
                await self._read_index_age()
                readings = await monitoring_state.read_readings(client, now)
            groups: dict[tuple[str, str], list[_Watch]] = {}
            for w in judged:
                kind = w.armed.trigger.kind
                groups.setdefault((kind, w.armed.underlying if kind == "conditional_exit" else w.key), []).append(w)
            for (kind, subject), group in sorted(groups.items()):
                reading = await (self._index_reading(feed, subject, now, readings) if kind == "conditional_exit"
                                 else self._leg_reading(feed, subject, now, readings))
                if reading is None:
                    not_run.update({w.armed.trigger.strategy_id: _why_of(w) for w in group})
                elif reading.source != OWN_FEED:  # this feed's own quote is judged tick by tick (``on_quote``), once
                    fired += await self._exits_with_reading(group, reading, now, polled=True)
            self._report_not_applicable(not_run)
            self._report_blocked(judged, not_run)
        await self._report_exits(judged, not_run, now)
        return fired

    def _not_judged(self) -> dict[int, str]:
        """Every exit of the list is reported not run: no feed, or the book unread for longer than allowed (review F4: a
        real position's old stop is named in this report as well, never left to the worker's "watched")."""
        unread = self.book_unread_too_long()
        not_run = {w.armed.trigger.strategy_id: monitoring_state.BOOK_NOT_READ if unread else _why_of(w)
                   for w in self._exits}
        self._report_not_applicable(not_run)
        return not_run

    def _report_blocked(self, judged: Sequence[_Watch], not_run: dict[int, str]) -> None:
        """Crossed on a reading but not run: the trade is not being checked through to the exit."""
        for w in judged:
            if w.armed.trigger.id in self._blocked:
                not_run.setdefault(w.armed.trigger.strategy_id, monitoring_state.EXIT_NOT_PRICED)

    def _report_not_applicable(self, not_run: dict[int, str]) -> None:
        """Review F2: a strategy whose armed exit is not judged here (a real position, or a kind that could not be read)
        is named in the report, so the trade never reads "watched" because of silence."""
        for sid, why in self._na_strategies.items():
            not_run.setdefault(sid, why)

    async def _report_exits(self, judged: Sequence[_Watch], not_run: Mapping[int, str],
                            now: datetime.datetime) -> None:
        """The monitor's one write of which trades' exits it is (or is not) judging; never raises."""
        client = _bus_client()
        if client is None:
            return
        if self._exits_publisher is None or self._exits_publisher[0] is not client:
            self._exits_publisher = (client, monitoring_state.ExitsPublisher(client))
        watching = {w.armed.trigger.strategy_id for w in judged}
        await self._exits_publisher[1].publish(watching, not_run, now)

    async def _fire_guarded(self, w: _Watch, price: paper.Price, now: datetime.datetime) -> bool:
        try:
            done = await asyncio.wait_for(self._fire(w, price, now), FIRE_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a database failure or timeout; rolled back, retried on the next tick
            self.failures += 1
            log.error("paper trigger %s not fired: %s", w.armed.trigger.id, type(exc).__name__)
            return False
        if done is None:
            return False
        fired, cancelled = done["fired"], done["cancelled"]
        finished = fired | cancelled  # fired, already fired, or cancelled: never watched again
        for key, items in tuple(self._watch.items()):
            self._watch[key] = [i for i in items if i.armed.trigger.id not in finished]
        self._exits = [i for i in self._exits if i.armed.trigger.id not in finished]
        self._dirty = True
        return w.armed.trigger.id in fired

    async def _fire(self, w: _Watch, price: paper.Price,  # noqa: PLR0911 - one answer per way a fire can end
                    now: datetime.datetime) -> dict[str, set[int]] | None:
        """One transaction (module docstring). None = keep armed; else the ids now fired or cancelled."""
        a, t = w.armed, w.armed.trigger
        feed = self._feed
        if feed is None:
            return None
        # the settings in force at THIS tick (one read; a store that cannot answer raises: the fire is not recorded
        # and the next crossing tick retries, never priced on a held or default rate)
        feed = LiveFeed(await with_rate_in_force(feed.ctx, self._read_settings), feed.fanout)
        async with self._sessions() as session, session.begin():
            if not await self._still_paper(session, t.strategy_id):
                return None  # review F5: the kind is read again in the fire; not paper (or unreadable) = left armed
            book = await paper_store.load(session, t.strategy_id)
            open_net = {int(p.instrument_id): p.net_quantity
                        for p in net_positions([o.order.as_paper() for o in book], {}).positions if p.net_quantity}
            if not open_net:
                return {"cancelled": set(await triggers.cancel(session, t.strategy_id)), "fired": set()}
            if t.kind == "leg_stop" and t.contract_id not in open_net:
                return {"cancelled": set(await triggers.cancel(session, t.strategy_id, t.id)), "fired": set()}
            targets = [t.contract_id] if t.kind == "leg_stop" else sorted(open_net)
            found = {c.contract_id: c for c in await tracked_contracts.resolve(session, targets)}
            prices = self._exit_prices(feed, a, w, price, targets, found)
            if isinstance(prices, _NoPrice):  # a contract without a live price: not yet, the trigger stays armed
                await self._tell_exit_not_run(session, a, prices, found, now)  # #732: once a day, never blocks
                return None
            texts = {c: _contract_text(found[c]) for c in targets}
            reason = stop_reason_at(self._reason(t, texts), a.underlying, await self._index_at_fire(feed, a, price))
            # the door: the strategy lock FIRST, the net read under it (a lot added since the look above is closed
            # too), then the claim, then the write (a stop: never a first fill)
            done = await paper_exit.exit_strategy(
                session, user_ref=a.user_ref, strategy_id=t.strategy_id, kind="stop", prices=prices, placed_at=now,
                only=[t.contract_id] if t.kind == "leg_stop" else sorted, reason=str(reason), trigger_id=t.id,
                before_write=lambda: triggers.claim_fire(session, t.id),
                write=lambda orders: paper_store.place(session, a.user_ref, t.strategy_id, orders, entry=None))
            if not isinstance(done, paper_exit.Exited):
                return await self._not_written(session, t, done)
            stored = done.book
            # D-02: the stored (buys first) order
            recorded = [o.order.contract_id for o in stored if o.order.trigger_id == t.id]
            body = alert_body(reason, [(texts[c], prices[c]) for c in recorded], names_contract=t.kind == "leg_stop")
            line = await self._max_loss_line(session, a, t, book, open_net, prices, now, texts)
            # ADR-330 (3b), owner Q2: the fired exit is an informational message (History + pop-up, never the bell),
            # raised through the one alert module in this same transaction
            values: dict[str, Any] = {"body": body} if line is None else {"body": body, "line": line}
            await actionable_alerts.inform(
                session, a.user_ref, t.strategy_id, "stop_fired",
                "stop_fired_note" if line is None else "stop_fired_note_with_line", values, at=now,
                restore={"body": ALERT_BODY_TEMPLATES, "line": STOP_LINE_TEMPLATES + FIRED_LINE_TEMPLATES})
        self.fires += 1
        return {"fired": {t.id}, "cancelled": set()}

    @staticmethod
    async def _still_paper(session: Any, strategy_id: int) -> bool:
        """ADR-330 (64), review F5: whether the strategy is a paper position NOW (one read inside the fire's own
        transaction, before anything is claimed). A real or unreadable kind: no stop is written."""
        from ofo_app import position_kind, strategy_store  # noqa: PLC0415 - late: the one kind rule and its reader
        try:
            return (await strategy_store.kinds_of(session, [strategy_id])).get(strategy_id) == position_kind.PAPER
        except Exception:  # noqa: BLE001 - fail closed
            return False

    async def _tell_exit_not_run(self, session: Any, a: triggers.ArmedTrigger, blocked: _NoPrice,
                                found: Mapping[int, tracked_contracts.TrackedContract],
                                now: datetime.datetime) -> None:
        """#732 (ADR-330 (44), (39)): the exit is set, a tick crossed it, and a contract has no live price (the price
        reader's verdict: missing, stale, not live, or the leg's own price absent). ONE informational message per exit
        per India day ("Your exit at 26,100.00 could not run: <contract> has no live price. It is still set."): History
        row + pop-up, never the bell, through the one alert module. The exit stays armed and runs at the next check when
        prices are back; no order is placed. The answer is the stored rows (``exit_not_run_rule``); ``_told`` only saves
        a query per tick. A store that fails: logged by type, the exit path is untouched (the trigger stays armed), and
        no retry on the next tick the same day (no tight retry, REQ-100 AC-18)."""
        t = a.trigger
        day = now.astimezone(paper.IST).date()
        if self._told.get(t.id) == day:
            return
        self._told = {k: v for k, v in self._told.items() if v == day}
        self._told[t.id] = day
        try:
            await actionable_alerts.inform_once_per_day(
                session, a.user_ref, t.strategy_id, EXIT_NOT_RUN_KIND, exit_not_run_rule(t.id),
                "exit_not_run_no_price", {"level": t.level, "contract": _contract_text(found[blocked.contract_id])},
                at=now, restore={"contract": ("contract_display",)})
        except Exception as exc:  # noqa: BLE001 - the message is a courtesy: the exit stays armed whatever happens here
            log.error("exit-not-run message of trigger %s not written: %s", t.id, type(exc).__name__)

    async def _index_at_fire(self, feed: LiveFeed, a: triggers.ArmedTrigger, price: paper.Price) -> Decimal | None:
        """#734: the index value the fire's reason carries. A conditional exit: always the crossing tick itself, the
        value the decision was made on (Lane M item 2). A leg stop (decided on the leg's own tick, quoted as the exit
        price): the held index reading; when it is not there yet (a fire in the first second after ``reload``), the one
        market reader (``market_read.read_market``, a short hold). Truly unknown -> None, and the reason says "not
        available" (never a made-up value)."""
        if a.trigger.kind == "conditional_exit":  # a missing value is "not available", never the held reading
            # Lane M item 2 (PC #196, 27 Nov): the tick that fired it IS the index value the decision was made on
            # (on_quote: live, market open); a held reading is another reading and may sit on the other side of the
            # level ("crossed above 25,800.00; NIFTY was at 25,796.75"), so it is never quoted for an index exit
            return price.price
        held = self._index_now(feed, a.underlying)
        if held is not None:
            return held.price
        from ofo_app import market_read  # noqa: PLC0415 - late: market_read imports the live feed
        try:
            wait = self._index_wait or market_read.Wait(INDEX_WAIT_SECONDS)
            read = await market_read.read_market(feed.ctx, feed, a.underlying, [], True, "stop_fire", wait=wait)
        except Exception as exc:  # noqa: BLE001 - the value is a record detail: never block a stop on it
            log.error("index value of fired trigger %s not read: %s", a.trigger.id, type(exc).__name__)
            return None
        index = read.index
        return index.price if index is not None and index.state == paper.LIVE else None

    @staticmethod
    async def _max_loss_line(session: Any, a: Any, t: stops.Trigger, book: Sequence[Any],  # noqa: PLR0913
                             open_net: Mapping[int, int], prices: Mapping[int, Any], now: datetime.datetime,
                             texts: Mapping[int, ExplanationText] | None = None) -> ExplanationText | None:
        """UX-A03 (27 Nov), Lane FE3 item 6 (PC note 27 Nov 09:43): a stop that has ALREADY FIRED never carries the
        preview's "If this stop fires, max loss becomes ... (now ...)": that is a future case and its "now" figure is
        the one from before the fire. It says what happened, in the past tense, with the figure at the fill:

        - a LEG stop: "Stop fired: <leg> reached <level>; max loss at that point Rs <figure>" (or "there was no fixed
          maximum loss at that point"; "the maximum loss at that point was not worked out" when the engine answered yes
          with no figure). The figure is the engine's answer for the book after this leg's exit at the FILL price (the
          one ``routes.paper.leg_stop_answer`` the Stops panel uses, on the book BEFORE the exit was written); a book
          left with no loss (a profit) or an answer of no / cannot_tell writes no line.
        - an index exit (closes every open leg): a line only when the exit confirmation's own check says yes.

        The exit and its record never wait on it (the exit already happened): the read runs in a savepoint so a failed
        statement cannot poison the fire; any failure is logged and the message is written without the line."""
        from ofo_app.routes import paper as paper_routes  # noqa: PLC0415 - the routes import this module
        try:
            async with session.begin_nested():
                names, terms = await paper_routes.names_and_terms(session, a.underlying, book)
                if t.kind == "leg_stop":
                    answer = paper_routes.leg_stop_answer(book, open_net[t.contract_id], t.contract_id,
                                                          prices[t.contract_id], names, terms, now, a.underlying)
                else:
                    answer = paper_routes.index_exit_answer(book, {c: prices[c] for c in sorted(open_net)}, terms,
                                                            names, now)
            if answer.state != "yes":
                return None
            if t.kind != "leg_stop":
                return answer.warning_text
            return _fired_leg_line(t, (texts or {}).get(t.contract_id), answer)  # review F9: inside the guard
        except Exception as exc:  # noqa: BLE001 - the message is written without the line, never not at all
            log.error("max-loss line of fired trigger %s left out: %s", t.id, type(exc).__name__)
            return None

    @staticmethod
    async def _not_written(session: Any, t: stops.Trigger, done: Any) -> dict[str, set[int]] | None:
        """The door wrote nothing: flat since the look (cancel), no live price (not yet: stays armed), or the trigger
        fired before (another tick, monitor or run)."""
        if isinstance(done, paper_exit.Flat):
            gone = None if done.strategy_flat or t.kind != "leg_stop" else t.id
            return {"cancelled": set(await triggers.cancel(session, t.strategy_id, gone)), "fired": set()}
        if isinstance(done, paper_exit.NotYet):
            return None
        return {"fired": set(), "cancelled": {t.id}}

    def _exit_prices(self, feed: LiveFeed, a: triggers.ArmedTrigger, w: _Watch,  # noqa: PLR0913
                     price: paper.Price, targets: list[int],
                     found: dict[int, tracked_contracts.TrackedContract]) -> dict[int, Decimal] | _NoPrice:
        if a.trigger.kind == "leg_stop":
            return {targets[0]: price.price} if price.price is not None else _NoPrice(targets[0])
        keys = {c: found[c].feed_key for c in targets}
        for c, k in keys.items():
            if found[c].state != tracked_contracts.LIVE or k is None:
                return _NoPrice(c)
        answers = self._leg_prices(feed, a.underlying, [k for k in keys.values() if k is not None])
        out: dict[int, Decimal] = {}
        for c, k in keys.items():
            p = answers.get(k)  # type: ignore[arg-type]
            if p is None or not paper.is_live(p) or p.price is None:
                return _NoPrice(c)
            out[c] = p.price
        return out

    @staticmethod
    def _index_now(feed: LiveFeed, underlying: str) -> paper.Price | None:
        """D-22: the index's live price answer at this moment (the provider's spot quote, with its time); None when
        it has no live price."""
        try:
            key = feed.ctx.provider.index_id(underlying)  # type: ignore[attr-defined]
            quote = feed.ctx.provider.underlying_quote(underlying)  # type: ignore[attr-defined]
            answer = paper.price_of(quote, key or underlying)
        except Exception:  # noqa: BLE001 - the value is a record detail: never block a stop on it
            return None
        return answer if paper.is_live(answer) else None

    @staticmethod
    def _reason(t: stops.Trigger, texts: Mapping[int, ExplanationText]) -> ExplanationText:
        if t.kind == "conditional_exit":
            return render_explanation("paper_stop_reason_index", underlying=t.underlying, direction=t.direction,
                                      level=t.level)
        return render_explanation("paper_stop_reason_leg", contract=texts[t.contract_id],  # type: ignore[index]
                                  direction=t.direction, level=t.level)

    async def run_forever(self, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                          poll: float = POLL_SECONDS) -> None:
        try:
            while True:
                try:
                    await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - a failed reload keeps the last watch; type only
                    log.error("paper monitor step failed: %s", type(exc).__name__)
                await sleep(poll)
        finally:
            self.close()


def _fired_leg_line(t: stops.Trigger, leg: ExplanationText | None, answer: Any) -> ExplanationText | None:
    """FE3 item 6: the past-tense line of a fired leg stop from the engine's answer (``ExitRiskOut``): a loss figure
    -> the figure (a loss is negative in the answer, said as a size, as the Stops panel does); "unlimited" -> no fixed
    maximum; no figure at all -> "not worked out"; a figure that is not a loss (the book is left in profit) -> no
    line (never "Rs 0" for a loss that was not computed that way). No leg text -> no line."""
    if leg is None:
        return None
    after = answer.max_loss_after
    if after == "unlimited":
        return render_explanation("paper_leg_stop_fired_unlimited", leg=leg, level=t.level)
    if after is None:
        return render_explanation("paper_leg_stop_fired_unknown", leg=leg, level=t.level)
    figure = Decimal(str(after))
    if figure >= 0:
        return None
    return render_explanation("paper_leg_stop_fired", leg=leg, level=t.level, figure=-figure)


def _is_paise(value: Decimal) -> bool:
    """True when ``value`` is a price that can be stored exactly (a paisa or coarser); an absurd value is not."""
    try:
        return value == value.quantize(paper.PAISE)
    except ArithmeticError:
        return False


def _why_of(w: _Watch) -> str:
    """The why a trade's exit is not judged: its index (or its leg's price) has no live reading."""
    if w.armed.trigger.kind == "conditional_exit":
        return monitoring_state.INDEX_NOT_LIVE
    return monitoring_state.LEG_NOT_LIVE


def _open(orders: Sequence[paper_store.StoredOrder]) -> list[int]:
    return [int(p.instrument_id) for p in net_positions([o.order.as_paper() for o in orders], {}).positions
            if p.net_quantity != 0]


_current: PaperMonitor | None = None


def notify() -> None:
    """Called by the trigger routes after a commit: the running monitor reloads (nothing when none runs)."""
    if _current is not None:
        _current.notify()


def start() -> asyncio.Task[None]:
    """The lifespan's entry: the real session maker and the live market's current feed, as one task."""
    from ofo_app import live_market  # noqa: PLC0415 - late: live_market imports the routes
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415
    from ofo_app.routes.outcome import get_settings_reader  # noqa: PLC0415

    global _current  # noqa: PLW0603
    _current = PaperMonitor(get_sessionmaker(), live_market.current_feed, read_settings=get_settings_reader())
    return asyncio.get_running_loop().create_task(_current.run_forever(), name="paper-monitor")


async def stop(task: asyncio.Task[None] | None) -> None:
    global _current  # noqa: PLW0603
    _current = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
