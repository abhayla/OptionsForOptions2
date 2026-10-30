"""The paper stop-loss monitor: a live tick crossing an armed paper trigger records stop orders once (GC-TP step 7a).

Spec basis: REQ-109 AC-8 ("fires each trigger once (also across a restart)"); ADR-207 (5) (Conditional Exit on the
index - exit all legs - and a per-leg stop-loss, Sensibull screens 221-224); ADR-015 (stale is never live); ADR-119
(the market calendar); ADR-003 (decision-support wording); RD-121 (paper trades are stated plainly as not real).

One asyncio task, started by the app lifespan only when the live market is on, stopped on shutdown (the
catalogue_refresh pattern). It never reaches Zerodha: it records PAPER orders only, through paper_store.place
(tests_app/test_paper_order_door.py walks this module's import graph).

- Load: every armed trigger in ONE query (paper_trigger_store.armed), their strategies' orders in ONE query, their
  contracts in one batch; subscribes on the market's fan-out the index of each conditional exit, the contract of each
  leg stop and every open contract of a strategy with a conditional exit (its exit prices are read from the provider).
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

from ofo import market_calendar
from ofo.engine.legs import Instrument
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.instruments.models import FUTURE_TYPE
from ofo.marketdata.quote import NormalizedQuote
from ofo.outcome import read_snapshot
from ofo.outcome.price_text import price_text
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import display_contract
from ofo.tracking import paper, stops
from ofo.tracking.orderbook import net_positions

from ofo_app import paper_store, tracked_contracts
from ofo_app import paper_trigger_store as triggers
from ofo_app.live_push import LiveFeed
from ofo_app.routes.outcome import feed_scope

log = logging.getLogger(__name__)

RELOAD_SECONDS: Final = 60.0
POLL_SECONDS: Final = 0.5
FIRE_TIMEOUT_SECONDS: Final = 10.0

#: A leg-price reader: (feed, underlying, feed keys) -> each key's paper price answer, from ONE provider read.
LegPrices = Callable[[LiveFeed, str, Sequence[str]], Mapping[str, paper.Price]]
Sessions = Callable[[], Any]  # an async_sessionmaker: ``async with sessions() as session``


def provider_prices(feed: LiveFeed, underlying: str, keys: Sequence[str]) -> Mapping[str, paper.Price]:
    """The routes' price rule: one snapshot of the provider, each key's live-P&L price answer (paper.leg_price)."""
    ctx = feed.ctx
    snapshot = read_snapshot(ctx.provider, underlying, list(keys), ctx.clock(), ctx.rate, feed_scope(ctx))
    return {k: paper.leg_price(snapshot, k) for k in keys}


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
                 leg_prices: LegPrices = provider_prices, holidays: market_calendar.Holidays | None = None,
                 reload_seconds: float = RELOAD_SECONDS, monotonic: Callable[[], float] | None = None) -> None:
        self._sessions = sessions
        self._feed_source = feed
        self._leg_prices = leg_prices
        self._holidays = holidays
        self._reload_seconds = reload_seconds
        self._monotonic = monotonic or asyncio.get_running_loop().time
        self._feed: LiveFeed | None = None
        self._handle: int | None = None
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
        watch: dict[str, list[_Watch]] = {}
        extra: set[str] = set()
        for a in armed:
            t = a.trigger
            if feed is None:
                break
            if t.kind == "conditional_exit":
                key = feed.ctx.provider.index_id(t.underlying)  # type: ignore[attr-defined]
                extra.update(k for k in (found[c].feed_key for c in open_ids[t.strategy_id]) if k is not None)
            else:
                key = found[t.contract_id].feed_key  # type: ignore[index]
            if key is not None:
                watch.setdefault(key, []).append(_Watch(a, key))
        self._watch = watch
        self._resubscribe(feed, sorted(set(watch) | extra))

    def _resubscribe(self, feed: LiveFeed | None, keys: list[str]) -> None:
        old_feed, old = self._feed, self._handle
        self._feed, self._handle = feed, None
        if feed is not None and keys:
            self._handle = feed.fanout.subscribe(_no_listener, keys)  # new first: no vendor unsubscribe/resubscribe
        if old_feed is not None and old is not None:
            old_feed.fanout.unsubscribe(old)

    def close(self) -> None:
        self._resubscribe(None, [])

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
        if not market_calendar.is_market_open(now, self._holidays):
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
            if prices is None:
                return None  # a contract without a live price: not yet, the trigger stays armed
            if not await triggers.claim_fire(session, t.id):
                return {"fired": set(), "cancelled": {t.id}}  # fired before (another tick, monitor or run)
            texts = {c: _contract_text(found[c]) for c in targets}
            reason = self._reason(t, texts)
            await paper_store.place(session, a.user_ref, t.strategy_id, [
                paper_store.NewOrder(c, "SELL" if open_net[c] > 0 else "BUY", abs(open_net[c]), prices[c], "stop",
                                     now, str(reason), t.id) for c in targets])
            legs = [render_explanation("paper_alert_leg", contract=texts[c], price=price_text(prices[c]))
                    for c in targets]
            joined = legs[0]
            for leg in legs[1:]:
                joined = render_explanation("paper_alert_legs", rest=joined, leg=leg)
            name = sf.shown_name(a.name) if a.name else render_explanation("cell_dash")
            await triggers.add_alert(session, t.strategy_id, t.id, str(render_explanation("paper_alert_title",
                                                                                          name=name)),
                                     str(render_explanation("paper_alert_body", what=reason,
                                                            count=len(targets), prices=joined)))
        self.fires += 1
        return {"fired": {t.id}, "cancelled": set()}

    def _exit_prices(self, feed: LiveFeed, a: triggers.ArmedTrigger, w: _Watch,  # noqa: PLR0913
                     price: paper.Price, targets: list[int],
                     found: dict[int, tracked_contracts.TrackedContract]) -> dict[int, Decimal] | None:
        if a.trigger.kind == "leg_stop":
            return {targets[0]: price.price} if price.price is not None else None
        keys = {c: found[c].feed_key for c in targets}
        if any(found[c].state != tracked_contracts.LIVE or k is None for c, k in keys.items()):
            return None
        answers = self._leg_prices(feed, a.underlying, [k for k in keys.values() if k is not None])
        out: dict[int, Decimal] = {}
        for c, k in keys.items():
            p = answers.get(k)  # type: ignore[arg-type]
            if p is None or not paper.is_live(p) or p.price is None:
                return None
            out[c] = p.price
        return out

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

    global _current  # noqa: PLW0603
    _current = PaperMonitor(get_sessionmaker(), live_market.current_feed)
    return asyncio.get_running_loop().create_task(_current.run_forever(), name="paper-monitor")


async def stop(task: asyncio.Task[None] | None) -> None:
    global _current  # noqa: PLW0603
    _current = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
