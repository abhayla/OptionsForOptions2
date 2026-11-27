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
from ofo_app import actionable_alerts, may_act, paper_exit, paper_store, tracked_contracts
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


#: The kind an "exit could not run" message is stored under: the closest informational kind the alert table's kind
#: check allows (a kind of its own needs a migration).
EXIT_NOT_RUN_KIND: Final = "stop_fired"
#: How long a stop's fire waits for an index value the held feed does not show yet (``market_read``'s own hold)
INDEX_WAIT_SECONDS: Final = 1.0


def exit_not_run_rule(trigger_id: int) -> str:
    """The ONCE-A-DAY rule of the "exit could not run" message (ADR-330 (44)): one message per exit (trigger) per India
    day, however many blocked ticks that day. The rule is this id: ``actionable_alerts.inform_once_per_day`` writes the
    message only when no stored row of this id falls in the India day of the tick, so a restart cannot repeat it."""
    return f"info:exit_not_run:{trigger_id}"


@dataclass(frozen=True)
class _NoPrice:
    """An exit that cannot run: the first contract without a live price (its price is stale, missing or unreadable)."""

    contract_id: int


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


class PaperMonitor:
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
        self._handle: int | None = None
        self._standing_feed: LiveFeed | None = None
        self._standing: list[int] = []  # the standing hold's fan-out handles (open paper legs + their indexes)
        self._watch: dict[str, list[_Watch]] = {}
        self._dirty = True
        self._loaded_at: float | None = None
        self.fires = 0
        self.failures = 0

    def notify(self) -> None:
        """A route added or cancelled a trigger: reload before the next quote is handled."""
        self._dirty = True

    def watched(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._watch.items()}

    async def reload(self) -> None:
        """Armed triggers (one query), their orders (one query), contracts (one batch); resubscribes the fan-out."""
        self._dirty = False
        self._loaded_at = self._monotonic()
        feed = self._feed_source()
        async with self._sessions() as session:
            armed = await triggers.armed(session)
            orders = await triggers.orders_of(session, sorted({a.trigger.strategy_id for a in armed}))
            open_ids = {sid: _open(o) for sid, o in orders.items()}
            ids = sorted({a.trigger.contract_id for a in armed if a.trigger.contract_id is not None}
                         | {c for a in armed if a.trigger.kind == "conditional_exit"
                            for c in open_ids[a.trigger.strategy_id]})
            found = {c.contract_id: c for c in await tracked_contracts.resolve(session, ids)}
            open_legs = await triggers.open_legs(session)
            standing = {c.contract_id: c for c in await tracked_contracts.resolve(
                session, sorted({cid for cid, _u in open_legs} - set(found)))}
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
                extra.add(index_key)  # S-20: every armed trigger holds its index, so a fire's record carries its value
            if key is not None:
                watch.setdefault(key, []).append(_Watch(a, key))
        self._watch = watch
        self._resubscribe(feed, sorted(set(watch) | extra))
        self._hold_open_legs(feed, self._standing_keys(feed, open_legs, {**standing, **found}))

    def _resubscribe(self, feed: LiveFeed | None, keys: list[str]) -> None:
        old_feed, old = self._feed, self._handle
        self._feed, self._handle = feed, None
        if feed is not None and keys:
            self._handle = feed.fanout.subscribe(_no_listener, keys)  # new first: no vendor unsubscribe/resubscribe
        if old_feed is not None and old is not None:
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
        self._standing_feed, self._standing = feed, []
        if feed is not None and keys:
            try:
                self._standing = [feed.fanout.subscribe(_no_listener, keys)]
            except KeyError:
                for key in keys:
                    with contextlib.suppress(KeyError):
                        self._standing.append(feed.fanout.subscribe(_no_listener, [key]))
        if old_feed is not None:
            for handle in old:
                old_feed.fanout.unsubscribe(handle)

    def close(self) -> None:
        self._resubscribe(None, [])
        self._hold_open_legs(None, [])

    async def step(self) -> int:
        """One pass: reload when due, then handle every queued quote in arrival order. Returns the fires recorded."""
        if self._dirty or self._feed_source() is not self._feed or self._loaded_at is None or \
                self._monotonic() - self._loaded_at >= self._reload_seconds:
            await self.reload()
        if self._feed is None or self._handle is None:
            return 0
        fired = 0
        for quote in self._feed.fanout.drain(self._handle):
            fired += await self.on_quote(quote)
        return fired

    async def on_quote(self, quote: NormalizedQuote) -> int:
        watching = self._watch.get(quote.instrument_id)
        if not watching or self._feed is None:
            return 0
        now = self._feed.ctx.clock()
        if not may_act.market_open(self._feed.ctx, now):  # the ONE market rule (the feed's own answer)
            return 0
        try:
            price = paper.price_of(quote, quote.instrument_id)
        except ValueError:  # a price finer than a paisa is never stored
            return 0
        fired = [w for w in tuple(watching) if stops.crossed(w.armed.trigger, price)
                 and await self._fire_guarded(w, price, now)]
        return len(fired)

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
        self._dirty = True
        return w.armed.trigger.id in fired

    async def _fire(self, w: _Watch, price: paper.Price, now: datetime.datetime) -> dict[str, set[int]] | None:
        """One transaction (module docstring). None = keep armed; else the ids now fired or cancelled."""
        a, t = w.armed, w.armed.trigger
        feed = self._feed
        if feed is None:
            return None
        # the settings in force at THIS tick (one read; a store that cannot answer raises: the fire is not recorded
        # and the next crossing tick retries, never priced on a held or default rate)
        feed = LiveFeed(await with_rate_in_force(feed.ctx, self._read_settings), feed.fanout)
        async with self._sessions() as session, session.begin():
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
            line = await self._max_loss_line(session, a, t, book, open_net, prices, now)
            # ADR-330 (3b), owner Q2: the fired exit is an informational message (History + pop-up, never the bell),
            # raised through the one alert module in this same transaction
            values: dict[str, Any] = {"body": body} if line is None else {"body": body, "line": line}
            await actionable_alerts.inform(
                session, a.user_ref, t.strategy_id, "stop_fired",
                "stop_fired_note" if line is None else "stop_fired_note_with_line", values, at=now,
                restore={"body": ALERT_BODY_TEMPLATES, "line": STOP_LINE_TEMPLATES})
        self.fires += 1
        return {"fired": {t.id}, "cancelled": set()}

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
        """#734: the index value the fire's reason carries. The held reading first; when it is not there yet (a fire in
        the first second after ``reload``, before the index tick arrives): the crossing tick itself when it IS the index
        (a conditional exit), else the one market reader (``market_read.read_market``, a short hold). Truly unknown ->
        None, and the reason says "not available" (never a made-up value)."""
        held = self._index_now(feed, a.underlying)
        if held is not None:
            return held
        if a.trigger.kind == "conditional_exit":
            return price.price  # the tick that fired it is the live index value (on_quote: live, market open)
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
                             open_net: Mapping[int, int],
                             prices: Mapping[int, Any], now: datetime.datetime) -> ExplanationText | None:
        """ADR-330 (6): "If this stop fires, max loss becomes Rs X (now Rs Y)", from the one engine through the SAME
        functions the Stops panel's route uses (``routes.paper``), judged on the book BEFORE the exit was written.
        A leg stop is priced AT ITS RECORDED FILL (the "exited at" price of the same message), so the figure is the
        position actually held after the exit, the one the Positions page shows (Lane J review 26 Nov: a tick that gaps
        past the level, e.g. stop 140.70 filled at 180.00, priced at the level understated max loss by Rs 2,554.50;
        without a gap the fill equals the level and the line is the one the user saw when saving). An index exit
        closes every open leg at the fill prices and gets a line only when the exit confirmation's own check says yes.
        Answer states: yes -> line;
        no / cannot_tell -> None (no figure); any failure -> logged, None. The exit and its record never wait on it
        (the exit already happened): the read runs in a savepoint so a failed statement cannot poison the fire."""
        from ofo_app.routes import paper as paper_routes  # noqa: PLC0415 - the routes import this module
        try:
            async with session.begin_nested():
                names, terms = await paper_routes.names_and_terms(session, a.underlying, book)
                if t.kind == "leg_stop":
                    answer = paper_routes.leg_stop_answer(
                        book, open_net[t.contract_id], t.contract_id, prices[t.contract_id],
                        names, terms, now)
                else:
                    answer = paper_routes.index_exit_answer(book, {c: prices[c] for c in sorted(open_net)}, terms,
                                                            names, now)
        except Exception as exc:  # noqa: BLE001 - the message is written without the line, never not at all
            log.error("max-loss line of fired trigger %s left out: %s", t.id, type(exc).__name__)
            return None
        if answer.state != "yes" or answer.warning_text is None:
            return None
        return answer.warning_text

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
    def _index_now(feed: LiveFeed, underlying: str) -> Decimal | None:
        """D-22: the index's live value at this fire (the provider's spot quote); None when it has no live price."""
        try:
            key = feed.ctx.provider.index_id(underlying)  # type: ignore[attr-defined]
            quote = feed.ctx.provider.underlying_quote(underlying)  # type: ignore[attr-defined]
            answer = paper.price_of(quote, key or underlying)
        except Exception:  # noqa: BLE001 - the value is a record detail: never block a stop on it
            return None
        return answer.price if paper.is_live(answer) else None

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
