"""ADR-220 (1) role ``background``: ``python -m ofo_app.background`` checks every tracked strategy's playbook with no
screen open (REQ-165, REQ-115 AC-1..AC-5, REQ-166 AC-1..AC-3). Suggest-only (ADR-003, REQ-115 AC-2): nothing here
reaches an order door (``tests_app/test_paper_order_door.py`` walks this module's imports).

One cycle (``Worker.cycle``), each step with its answer state:
1. The settings and speeds are resolved NOW from memory (``settings_cache.SettingsCache.at`` at the worker clock, every
   cycle; no database call: #636 r4; the cache polls ``count(*)`` of ``app_settings`` every
   ``settings_cache.POLL_SECONDS`` on its own task, so a stored change is used within ``settings_cache.LAG_SECONDS``;
   ``calc_speeds.read_speeds``) and the safety valve applied. The
   strategy list and each user's preferences are NOT read by a cycle: ``rebuild`` reads them on its own task every
   ``REBUILD_SECONDS`` (preferences once per user per rebuild); a cycle uses the last good list.
2. Each monitored strategy, in rotation, at most ``max_per_cycle`` per cycle (the rest roll to the next cycle; B4 (a)),
   each check on ITS OWN clock read (a tick that landed while earlier checks ran is never "in the future"):
   - the feed's own answer first (``feed_state``: closed / stale / disconnected), then the tick test
     (``Worker._tick_key``, one held-quote read per leg and the spot, no chain copy): ticked (a leg's or the spot's
     price, time or health changed, or the IST minute did) -> read; not ticked -> not read (counted ``NOT_TICKED``);
     no previous fresh read, legs changed, a quote not held, or a provider with no ``held_quote`` -> read (the full
     read answers, fail closed; a token missing is ``LEG_MISSING``, paused);
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
   (REQ-166 AC-2). Margin (T-16, GC-IC1 5b): the strategy's broker margin through the SCREEN's margin reader
   (``routes.adjustment_check.current_margin``, the ``margin_of`` seam), never read in the check path: a per-strategy
   cache (``MarginCache``) refreshed on its own task (``_margin_loop``), at most once per ``MARGIN_REFRESH_S`` per
   strategy and only for a playbook with T-16 on (Kite allows about 1 REST call per second per key, shared with every
   screen). Answer states the check sees: stated and younger than ``MARGIN_STALE_S`` -> the figure; busy (rate limit)
   / failed / Zerodha stated none -> the screen's own non-stated block (``missing_margin``), never the last good
   figure; not refreshed yet, legs changed since the read, or older than ``MARGIN_STALE_S`` -> None
   (``missing_margin``). The day open (T-13): the index's day values read with the spot (``read_prices``), the rule
   ``ofo.marketdata.day_open.index_day_open`` the screen's reader applies too.
4. The playbook is evaluated (``playbook_eval.evaluate``, the rule memory last written for the strategy) and the
   rule memory is written (``record_check``: ``adjustment_check.evaluate_and_remember``) ONLY when it is needed: the
   first check of the process, or a check whose rule memory, flagged rules or clear rules differ from the last write.
   The write itself leaves the check path (#636 r4): the check queues the latest state per strategy (a newer one
   replaces it: coalesced) and ONE writer task writes it under the role's one database gate; rule memory is set only
   after the write succeeded. A queued write of a strategy removed or re-planned at a rebuild is dropped (#636 r5);
   the writer is watched (a dead writer is logged and restarted) and drained on stop.
5. The alert gate (REQ-170, ADR-237 (6): the ONE writer of suggestion records). Each check feeds
   ``gate_readings.readings(evaluation)`` into ``alert_gate.step`` with the strategy's preset (``alert_presets.
   preset_for`` of ``style_for(expiry kind, days left, pin)``); every cycle (the ~1 s wake) also steps every gated
   strategy that was not checked with EMPTY readings, so candle closes are processed with no price change
   (ADR-237 (2)). Only the gate's events touch the database (``GateStore.apply``, one transaction per step's
   events): Opened -> ``open_suggestion(worse=...)``, Held -> ``record_held``, Lapsed -> ``lapse``. The check never
   writes them (#636 r6): each step's events join the strategy's ordered queue (``GateBatch``; never merged, never
   dropped while the strategy is listed), written by the ONE writer task before any rule-memory write; the record id
   is put on the gate state when the write returns. Answer states: written -> ids attached; the write raises ->
   counted (``gate_writes_failed``), kept at the head of its queue in order and retried at the writer's next wake
   (every cycle while anything is queued); the strategy left the list while queued -> dropped with a log line
   (``gate_events_dropped``); the gate held long by the rebuild -> the loop is unaffected (it never awaits the gate).
   The gate state is restored on the first check from the store (``GateStore.load``: last record per rule, today's
   count, today's held crossings, the pin), read on the rebuild task, never per check; a dismissed record read there
   is fed to ``alert_gate.dismiss`` (ADR-236); a changed playbook body (plan change) restores the state again against
   the new ladder. A strategy whose legs all exited has its open records lapsed by the lister (strategy closed).
   Answer states: no gate load (the pin or the store read failed, none kept), no user values, a style that cannot be
   told, or a preset that cannot be built -> that strategy is paused (``CHECK_FAILED``, "Monitoring paused"), never
   checked on a default.
   Risk exits (paper triggers, stop-loss) never pass through here (AC-5).
6. The user's pause (A-38, GC-IC1 step 4a, ``ofo.adjustment.monitor_pause``): the pause end is read with the gate
   load on the rebuild task (``GateLoad.paused_until``, never a database call per check, B4 (a)); each check compares
   it with ITS OWN clock read first: in force -> ``PriceState.USER_PAUSED`` through ``_pause`` (the same path as every
   other pause, so the candle it fell in has no close), no price read, no evaluation, and the close pass skips it;
   expired (end at or before the check's time) or cleared -> checked as normal, with no action needed. Answer states:
   none / cleared -> checked; set and in force -> paused (``user_paused_until`` holds the end for the status); set and
   expired -> checked. Risk exits never read it (``tests_app/test_risk_exit_not_gated.py`` walks the paper path).
7. The user's level watches (A-37, GC-IC1 step 4c, ADR-242, ``ofo.adjustment.level_watch``): read with the gate load
   on the rebuild task (``GateLoad.watches``, never a database call per check, B4 (a)) and put on the check's state;
   the evaluator answers each as a yes/no rule ``watch.level.<direction>`` that reaches the alert gate through
   ``gate_readings`` like every other rule, so the gate is the one writer (one record per crossing episode, re-armed
   at a false close). No spot / withheld -> no reading. A watch set or cleared takes effect at the next rebuild.
   One strategy's error is logged with its id and does not stop the others
   (REQ-115 AC-9).

Restart (REQ-115 AC-3, REQ-165 AC-5): the monitors are rebuilt from the database on start (``rebuild``); rule memory
lives in ``playbook_store.rule_state``; the gate restores from the stored records and today's held crossings
(ADR-237 (5)), so an open record is never re-opened and a held episode is not held twice.

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
import collections
import dataclasses
import datetime
import enum
import functools
import logging
import sys
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from ofo.adjustment import alert_gate, alert_presets, gate_readings, monitor_pause
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.preferences import Preferences
from ofo.adjustment.preferences import from_values as prefs_from_values
from ofo.engine.black_scholes import Greeks, year_fraction
from ofo.engine.legs import Instrument
from ofo.engine.model import expiry_model, greeks, iv_price
from ofo.instruments.models import ZERODHA
from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.day_open import index_day_open
from ofo.marketdata.feed_health import market_closed_for
from ofo.marketdata.forward import parity_forward
from ofo.marketdata.quote import is_live_price
from ofo.marketdata.shared_compute import FeedScope, SharedCompute
from ofo.marketdata.spot_source import SourceReading, feed_reading, resolve_spot
from ofo.outcome.service import solved_iv, unit_greeks
from ofo.rules.inputs import DataHealth
from ofo.scenario.spot import spot_reading
from ofo.settings import RISK_FREE_RATE, value_of
from ofo.settings import calc as settings_calc
from ofo.timeutil import IST

from ofo_app import adjustment_check as check
from ofo_app import calc_speeds, feed_bus, roles, settings_cache
from ofo_app.db_gate import GATE_POLL, GATE_REBUILD, GATE_WRITER, DbGate, held
from ofo_app.routes.adjustment import MarketInputs

log = logging.getLogger("ofo_app.background")

__all__ = ["GATE_POLL", "GATE_REBUILD", "GATE_WRITER", "DbGate"]  # the role's one gate (``db_gate``)

DEFAULT_MAX_PER_CYCLE: Final = 200  # strategies checked in one cycle; the rest roll to the next (B4 (a))
#: the recent checks and errors kept in memory for tests and status (a long-running process must not grow without end:
#: 1,000 strategies checked each second would add ~21.6 million entries in one market day)
RECENT_KEPT: Final = 1000
WAKE_SECONDS: Final = Decimal(1)  # ADR-233 (6): the longest the worker sleeps between cycles
#: Internal refresh cadence, NOT a business number (no figure, threshold or wording a user sees depends on it; it only
#: bounds Kite basket-margin reads to one per strategy per 5 minutes, so it stays in code by decision GC-IC1 step 10).
MARGIN_REFRESH_S: Final = Decimal(300)
MARGIN_STALE_S: Final = 2 * MARGIN_REFRESH_S  # an entry older than this is not used (a refresh that kept failing)
REBUILD_SECONDS: Final = 30 # the monitor set is re-read this often, so a newly tracked strategy joins (AC-3: 60 s)
_MICROS: Final = 1_000_000


class PriceState(enum.Enum):
    FRESH = "fresh"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    LEG_MISSING = "leg_missing"
    MARKET_CLOSED = "market_closed"
    CHECK_FAILED = "check_failed"
    USER_PAUSED = "user_paused"  # A-38: the user paused adjustment checks until a time (module docstring, step 6)


@dataclass(frozen=True)
class PriceRead:
    state: PriceState
    spot: Any = None  # NormalizedQuote of the underlying
    legs: Mapping[int, Any] = field(default_factory=dict)  # position leg index -> NormalizedQuote
    chains: Mapping[datetime.date, tuple] = field(default_factory=dict)  # each leg expiry's chain snapshot
    listed: tuple = ()  # every listed option of the underlying (``adjustment_readers.listed_options``)
    futures: frozenset = frozenset()  # the underlying's future expiries (``adjustment_readers.future_expiries``)
    #: GC-IC1 5b: the index's day values (``latest_day_stats``) read with ``spot`` in the same read (the index is held
    #: by the worker's wanted set, as the screen reads it inside its hold); None = not read
    day: Any = None

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
    #: ADR-245: the strategy layer of the three-layer settings (``adjustment_check.Resolved.strategy_layer``: the plan
    #: copy's ``settings``; None = no plan; ``layers.Unreadable`` = a plan whose settings cannot be read), read with the
    #: body on the rebuild, never per check. REQUIRED (no default): a lister that forgets it cannot construct a
    #: Watched, so a plan's override is never silently dropped
    strategy_layer: Any
    #: ADR-243: the strategy's stored entry facts (``adjustment_readers.entry_facts_in``: ``EntryFacts``, None = none
    #: stored, ``layers.Unreadable``), read on the rebuild with the plan. REQUIRED (no default), as above: the check
    #: builds every roll on the strategy's basis in force, the same as the Compare
    entry_facts: Any
    #: contract step 3: the strategy's ``adjustment_check.Resolved`` (its stop lines in force come from it through
    #: ``settings_in_force.stops_of``). None = not supplied: every stop answers "not checked", never a pass
    resolved: Any


def _seconds(delta: datetime.timedelta) -> Decimal:
    micros = (delta.days * 86_400 + delta.seconds) * _MICROS + delta.microseconds
    return Decimal(micros) / _MICROS


def _leg_quote(chain: Iterable[Any], leg: Any) -> Any:
    for q in chain:
        if q.instrument_type is not None and q.instrument_type.value == leg.type and q.strike == leg.strike:
            return q
    return None


def feed_state(provider: Any, now: datetime.datetime) -> PriceState | None:
    """The feed's own answer before any price is read: market closed / stale / disconnected; None = available."""
    if market_closed_for(provider, now):
        return PriceState.MARKET_CLOSED
    health = provider.status().health
    if health is DataHealth.STALE:
        return PriceState.STALE
    return None if health is DataHealth.AVAILABLE else PriceState.DISCONNECTED


def read_prices(provider: Any, watched: Watched, now: datetime.datetime,
                known: tuple[tuple, frozenset] | None = None) -> PriceRead:
    """The price read of one strategy, one answer state each (module docstring, step 2). ``known``: (the provider's
    listed options, the future expiries) of the underlying when the caller already holds them (the worker keeps them
    per provider and underlying); None reads them from the provider."""
    state = feed_state(provider, now)
    if state is not None:
        return PriceRead(state)
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
    if known is None:
        known = catalogue_of(provider, position.underlying)
    return PriceRead(PriceState.FRESH, spot, legs, chains, *known, provider.latest_day_stats(spot.instrument_id, now))


def catalogue_of(provider: Any, underlying: str) -> tuple[tuple, frozenset]:
    """(listed options, future expiries) of ``underlying``: the screen's own two listings (``adjustment_readers``)."""
    from ofo_app.adjustment_readers import future_expiries, listed_options  # noqa: PLC0415 - the screen's listings
    return tuple(listed_options(provider, underlying)), future_expiries(provider, underlying)


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


def feed_spot(read: PriceRead, now: datetime.datetime) -> SourceReading:
    """The feed spot of a FRESH read stamped ``now`` (finding staleness-by-last-change-age).

    ``read_prices`` already judged freshness by the provider's connection-aware health; the quote's own timestamp is
    its LAST CHANGE, and Kite sends a packet only on a change, so a quiet but live index is current. Stamping its last
    change instead made ``resolve_spot``'s feed-age window (3 s) answer "no spot" for every check more than 3 s after
    the last tick, the evaluation was withheld, and a rule whose value cleared its band was never read (round 2 RCA:
    the 23000 frame arrived inside the 10 s check interval and was 9 s old at the next check). A timestamp in the
    future, or none, is kept so ``resolve_spot`` still refuses it (fail closed); a read that is not FRESH raises."""
    if read.state is not PriceState.FRESH or read.spot is None:
        raise ValueError(f"feed_spot needs a fresh read, got {read.state}")
    # FRESH = the feed was AVAILABLE (connected, current) and the market open at this read (``feed_state``): live.
    # The ONE rule the screen applies too (``spot_source.feed_reading``, #639 item 1).
    return feed_reading(read.spot, now, feed_live=True)


def market_inputs(watched: Watched, read: PriceRead, shared: FeedScope, now: datetime.datetime,
                  values: Mapping[str, Decimal]) -> MarketInputs:
    """The screen's ``MarketInputs`` (``adjustment_readers.read_market``) from a fresh price read, every per-option
    figure from the shared cache instead of a whole-chain model: the first leg's expiry, the legs' rows, the same ATM
    IV rule (the IV of the call nearest the forward that the model prices), the same last close. Valued at the
    snapshot instant (the price's own time), so a figure is shared per price update; the screen values at its clock,
    so the two agree exactly when the clock reads the price's time (named in the module docstring).
    Not available -> None, as on the screen: no forward (spot or chain refused) -> no Greeks, no ATM IV, no forward."""
    from ofo_app import scenario_mode  # noqa: PLC0415 - read at check time (the screen's own scenario switch)
    from ofo_app.adjustment_readers import (  # noqa: PLC0415 - the screen's own row builder, kind and last close
        chain_rows,
        expiry_kind_of,
        read_last_close,
    )
    position = watched.tracked.position
    expiry = position.legs[0].expiry
    chain = tuple(sorted(read.chains[expiry], key=lambda q: q.instrument_id))
    instant = _snapshot_instant(read, expiry)
    em = fwd = None
    rate, quality = value_of(values, RISK_FREE_RATE), settings_calc.forward_quality(values)  # the settings in force
    try:
        fwd = shared.call((read.spot.underlying, expiry, instant, None), parity_forward, chain, read.spot, expiry,
                          instant, rate, quality)
        em = expiry_model(spot_reading(read.spot), fwd)
    except (ValueError, ArithmeticError):  # ForwardUnavailable / SpotRefused are ValueErrors: no model figures
        em = fwd = None
    at = (read.spot.underlying, expiry, instant)

    def shared_greeks(_iid: str, q: Any) -> Greeks | None:  # the shared per-option figures (REQ-166 AC-2)
        return None if em is None or q is None else _figures(shared, at, q, em)[1]
    # the screen's own row builder over every listed contract of the expiry (the screen reads the first leg's expiry)
    rows, ids, leg_greeks = chain_rows(read.listed, expiry, {q.instrument_id: q for q in chain}, shared_greeks,
                                       scenario_mode.current())
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
    feed = feed_spot(read, now)
    last = read_last_close(read.spot, False, scenario_mode.current(), now)  # a check runs only with the market open
    own = {x.tradingsymbol for x in position.legs}
    by_id = {q.instrument_id: q for q in chain}
    leg_ivs = {}  # GC-IC1 1b: each own leg's IV, the same shared per-option figure as its Greeks
    if em is not None:
        for sym, iid in ids.items():
            if sym in own and iid in by_id and (iv := _figures(shared, at, by_id[iid], em)[0]) is not None:
                leg_ivs[sym] = iv
    return MarketInputs(tuple(rows), ids, None if fwd is None else fwd.forward, years, vol, feed, last, now,
                        expiry_kind_of(expiry, read.listed, read.futures, scenario_mode.current()), leg_greeks,
                        fwd, leg_ivs, index_day_open(read.day, now),
                        carry_gap_pct=values.get(settings_calc.CARRY_GAP_PERCENT),  # absent -> no figures, named reason
                        s02_delta_per_lot=values.get(settings_calc.SITUATION_NET_DELTA_PER_LOT),  # absent: not checked
                        s12_percent=values.get(settings_calc.SITUATION_BIG_WIN_PERCENT))


def background_state(watched: Watched, read: PriceRead, shared: FeedScope, now: datetime.datetime,  # noqa: PLR0913
                     values: Mapping[str, Decimal], prefs: Preferences,
                     margin: Mapping | None = None, *,
                     user_values: Mapping[str, Decimal] | None) -> pe.StrategyState:
    """The check's state through the SCREEN's own builder (``adjustment_check.state_of``), never a copy of it; the
    carry gap in force is resolved there (ADR-245) from ``user_values`` (required: the store's own-values record, or
    None for no user read path) and ``watched.strategy_layer``."""
    return state_from_market(watched, market_inputs(watched, read, shared, now, values), now, values, prefs, margin,
                             user_values=user_values)


def state_from_market(watched: Watched, market: MarketInputs, now: datetime.datetime,  # noqa: PLR0913
                      values: Mapping[str, Decimal], prefs: Preferences,
                      margin: Mapping | None, *, user_values: Mapping[str, Decimal] | None) -> pe.StrategyState:
    """``background_state`` from an already built market. Margin: the cached block of the screen's margin reader
    (``MarginCache.block_for``; None = not known: ``missing_margin``). Charge
    rates: None (``state_of`` reads only the gross figures, which carry no charges). The REST spot is not read (a
    check runs only on a fresh feed). ``values``: the settings in force this cycle (rate, forward settings, feed
    windows, REQ-167); ``prefs``: the strategy owner's preferences (the approach config, REQ-168), as the screen
    passes them."""
    spot = resolve_spot(market.feed, None, market.last_close, now=now, windows=settings_calc.feed_windows(values))
    return check.state_of(watched.tracked, market, spot, margin, None, fresh=True, body=watched.body,
                          config=prefs.approach, user_values=user_values, strategy_layer=watched.strategy_layer,
                          entry_facts=watched.entry_facts, resolved=watched.resolved)


#: the worker's margin seam: the strategy and the market of its last check -> the screen's margin block (``state``
#: ``stated`` with ``value``, or a non-stated block, or None for a failed read)
MarginOf = Callable[["Watched", MarketInputs], Awaitable[Mapping | None]]


def carry_rule_on(body: Mapping | None) -> bool:
    """A playbook with a switched-on carry day rule (its record carries the stated margin, REQ-159 AC-4)."""
    rules = body.get("day_rules") if isinstance(body, Mapping) else None
    return any(isinstance(r, Mapping) and r.get("on") is True and r.get("when") in pe.CARRY_WHENS
               and r.get("action") == pe.DAY_ACTION_CARRY_CHECK for r in rules) if isinstance(rules, list) else False


def margin_needed(body: Mapping | None, resolved: Any = None) -> bool:
    """The strategies whose margin is read: an ACTIVE % of margin stop line in force (``settings_in_force``, contract
    step 3: never the body's T-16 directly) OR a carry day rule on OR T-14 on (B2). ``resolved``: the strategy's
    ``adjustment_check.Resolved`` (a pre-ADR-247 plan's own T-16); None -> the body as a followed playbook."""
    from ofo_app import settings_in_force as sif  # noqa: PLC0415 - it imports adjustment_check, as this module does

    if body is None:
        return False
    r = resolved if resolved is not None else check.Resolved("active", body, None, None, False,
                                                             saved_before_adr247=False)
    return sif.margin_line_on(r) or carry_rule_on(body) or t14_on(body)


def t14_on(body: Mapping | None) -> bool:
    """T-14 (ic-e2e-paper design decision 8) on: its value is a % of the margin blocked, so it needs the margin read."""
    t = ((body.get("triggers") if isinstance(body, Mapping) else None) or {}).get("T-14")
    return isinstance(t, Mapping) and t.get("on") is True


@dataclass(frozen=True)
class MarginEntry:
    legs: tuple  # the position's legs the block was read for (a changed position is not refreshed yet)
    block: Mapping | None  # the screen's margin block; None = the read failed
    read_at: datetime.datetime


class MarginCache:
    """Per strategy: the last margin read and its time (module docstring, step 3). The check only reads it."""

    def __init__(self, margin_of: MarginOf | None) -> None:
        self._margin_of = margin_of
        self._entries: dict[int, MarginEntry] = {}
        self._markets: dict[int, tuple[tuple, MarketInputs]] = {}  # strategy -> (its legs, its last check's market)
        self.calls: dict[int, int] = {}  # strategy -> margin reads made (status and tests)

    def seen(self, w: Watched, market: MarketInputs) -> None:
        """A check's market (its instrument ids are the margin basket's keys); read by the next refresh."""
        if margin_needed(w.body, w.resolved):
            self._markets[w.strategy_id] = (w.tracked.position.legs, market)

    def block_for(self, w: Watched, now: datetime.datetime) -> Mapping | None:
        """The block a check uses: the entry for the current legs younger than ``MARGIN_STALE_S``, else None."""
        e = self._entries.get(w.strategy_id)
        if e is None or e.legs != w.tracked.position.legs or _seconds(now - e.read_at) > MARGIN_STALE_S:
            return None
        return e.block

    def due(self, w: Watched, now: datetime.datetime) -> bool:
        if self._margin_of is None or not margin_needed(w.body, w.resolved) or w.strategy_id not in self._markets:
            return False
        e = self._entries.get(w.strategy_id)
        return e is None or e.legs != w.tracked.position.legs or _seconds(now - e.read_at) >= MARGIN_REFRESH_S

    async def refresh(self, monitors: Iterable[Watched], clock: Callable[[], datetime.datetime]) -> None:
        """One pass: each due strategy read once (one strategy's failure is its own ``None``, never the old figure)."""
        live = set()
        for w in monitors:
            sid = w.strategy_id
            live.add(sid)
            now = clock()
            if not self.due(w, now):
                continue
            legs, market = self._markets[sid]
            if legs != w.tracked.position.legs:
                continue  # the position changed since its last check: refreshed after the next check
            self.calls[sid] = self.calls.get(sid, 0) + 1
            try:
                block = await self._margin_of(w, market)  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001 - a failed read is "margin not known", retried next window
                log.warning("background: margin of strategy %s unreadable: %s", sid, type(exc).__name__)
                block = None
            self._entries[sid] = MarginEntry(legs, block, now)
        for gone in [k for k in self._entries if k not in live]:
            self._entries.pop(gone, None)
            self._markets.pop(gone, None)


def screen_margin_reader(margin_of: Any) -> MarginOf:
    """The worker's margin seam over the SCREEN's own margin read (``routes.adjustment_check.current_margin`` with an
    ``ApproachMargin``, ``routes.adjustment.get_approach_margin``): the same legs, the same block."""
    from ofo_app.routes.adjustment_check import current_margin  # noqa: PLC0415 - the route module, at run time

    async def read(w: Watched, market: MarketInputs) -> Mapping | None:
        return await current_margin(margin_of, w.tracked, market)
    return read


@dataclass(frozen=True)
class Recorded:
    """What ``record_check`` wrote: rule id -> open record id of each flagged rule, and the evaluation it stored (its
    memory is the worker's rule memory until the next write)."""

    opened: Mapping[str, int]
    evaluation: pe.Evaluation


def _write_key(ev: pe.Evaluation) -> tuple:
    """What a write changes: the rule memory, the flagged rules and the clear rules (a clear rule lapses its record)."""
    memory = tuple(sorted((rid, tuple(sorted(m.items()))) for rid, m in ev.memory.items()))
    return memory, frozenset(r.rule_id for r in ev.results if isinstance(r, pe.Flag)), frozenset(ev.clear)


async def record_check(watched: Watched, state: pe.StrategyState, prefs: Preferences,
                       scn: Any = None) -> Recorded:
    """The check's rule memory in one transaction, through the screen's own function (REQ-165 AC-5). Opens no record:
    records are the alert gate's (``DbGateStore.apply``, ADR-237 (6)). ``opened`` is empty."""
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415 - the database layer only when a check runs
    async with get_sessionmaker()() as db:
        ev = await check.evaluate_and_remember(db, watched.user_ref, watched.strategy_id, watched.body, state, scn,
                                               watched.tracked.position, gap_until=prefs.gap_until)
        await db.commit()
    return Recorded({}, ev)


@dataclass(frozen=True)
class GateLoad:
    """What the rebuild task read for one strategy's gate (ADR-237 (5)): the last record per rule and today's count,
    today's held crossings (``playbook_store.HeldToday``, oldest first), the pinned style (None = automatic), the
    end of the user's pause (A-38; None = never paused or cleared; compared with each check's own time)."""

    rows: alert_gate.GateRows
    held: tuple = ()
    pin: str | None = None
    paused_until: datetime.datetime | None = None
    watches: tuple = ()  # A-37 (GC-IC1 4c): the user's active level watches (``level_watch.LevelWatch``)


@dataclass(frozen=True)
class GateContext:
    """The last check's evaluation and state: an event processed on a later empty step takes its words from it."""

    evaluation: pe.Evaluation
    state: pe.StrategyState


@dataclass(frozen=True)
class GateBatch:
    """One gate step's events for one strategy, queued for the writer in step order (#636 r6): ``ctx`` is the check
    the events take their words from, as at the step."""

    watched: Watched
    events: tuple
    ctx: GateContext | None
    queued_at: datetime.datetime | None = None  # the worker clock at the step (the oldest one's age is logged)


class Listed(list):
    """The lister's answer (#636 r6 review): the strategies listed, and ``unread`` = the ids whose read RAISED (the
    database down, a bad row). An unread strategy did not leave the list: its queued gate events are kept."""

    def __init__(self, items: Iterable[Watched] = (), unread: Iterable[int] = ()) -> None:
        super().__init__(items)
        self.unread = frozenset(unread)


#: ADR-237 (3) promises an intraday record within 10 s of its close: a queued event older than this is logged once
GATE_EVENT_AGE_WARN_S: Final = 10
#: while one strategy's event writes keep failing, a count line (no traceback) every this many failures
GATE_FAIL_COUNT_EVERY: Final = 10


#: a day rule record names its approaches in the one approach slot, in order: "A-28,A-27" (GC-IC1 1a)
DAY_APPROACH_SEPARATOR = ","


def _quantized(v: object) -> Decimal | None:
    from ofo_app.routes.adjustment_check import SHOWN_PLACES  # noqa: PLC0415 - the screen's shown scale
    return v.quantize(SHOWN_PLACES) if isinstance(v, Decimal) else None


def gate_group(strategy_id: int, at: datetime.datetime) -> str:
    """The record group of one candle close: every record opened at that close shares it. Letters and digits only
    (the inbox keys a group as ``<strategy>-<group>`` in an ``Identifier``, ``^[A-Za-z0-9_\\-.]{1,64}$``): the close
    in IST to the microsecond, e.g. ``7-20261102T100000000000``; never an isoformat (':' and '+' made the inbox 500)."""
    return f"{strategy_id}-{at.astimezone(IST):%Y%m%dT%H%M%S%f}"


async def _lapse_open_of(db: Any, w: Watched, rule_id: str, reason: str) -> None:
    from ofo_app import playbook_store  # noqa: PLC0415 - database layer at run time
    for rec in await playbook_store.open_suggestions(db, w.user_ref, w.strategy_id):
        if rec.rule_id == rule_id:
            await playbook_store.lapse(db, w.user_ref, rec.id, reason)


class DbGateStore:
    """The real gate store: ``playbook_store`` and the pin store, one session per call."""

    async def load(self, w: Watched, today: datetime.date) -> GateLoad:
        from ofo_app import (  # noqa: PLC0415 - database layer at run time
            playbook_store,
            strategy_alert_style_store,
            strategy_level_watch_store,
            strategy_pause_store,
        )
        from ofo_app.db import get_sessionmaker  # noqa: PLC0415
        async with get_sessionmaker()() as db:
            rows = await playbook_store.gate_rows(db, w.user_ref, w.strategy_id, today)
            held = await playbook_store.held_today(db, w.user_ref, w.strategy_id, today)
            pin = await strategy_alert_style_store.pin_of(db, w.user_ref, w.strategy_id)
            until = await strategy_pause_store.pause_of(db, w.user_ref, w.strategy_id)
            watches = await strategy_level_watch_store.watches_of(db, w.user_ref, w.strategy_id)
        return GateLoad(rows, held, pin.style, until, watches)

    async def apply(self, w: Watched, events: Iterable[alert_gate.Event], ctx: GateContext | None) -> dict[str, int]:
        """The gate's events in ONE transaction; rule id -> id of each record opened. An escalation while the
        previous record of the rule is still open lapses that one first (REQ-112: one open record per rule)."""
        from ofo_app import playbook_store  # noqa: PLC0415 - database layer at run time
        from ofo_app.db import get_sessionmaker  # noqa: PLC0415
        from ofo_app.routes.adjustment_check import cheapest, t19_record  # noqa: PLC0415 - the screen's T-19 words
        values = {} if ctx is None else {v.rule_id: v for v in ctx.evaluation.values}
        flags = {} if ctx is None else {r.rule_id: r for r in ctx.evaluation.results if isinstance(r, pe.Flag)}
        stage = None if ctx is None else ctx.evaluation.stage_name
        source = playbook_store.SOURCE_SYSTEM if w.is_system else playbook_store.SOURCE_OWN
        opened: dict[str, int] = {}
        async with get_sessionmaker()() as db:
            for e in events:
                if isinstance(e, alert_gate.Lapsed):
                    await _lapse_open_of(db, w, e.rule_id, playbook_store.LAPSE_CONDITION_STOPPED)
                    continue
                rv = values.get(e.rule_id)
                trigger = None if rv is None else rv.trigger_id
                value = _quantized(e.value)
                if value is None and rv is not None:
                    value = _quantized(rv.value)
                threshold = _quantized(getattr(e, "threshold", None))
                if threshold is None and rv is not None:
                    threshold = _quantized(rv.threshold)
                if isinstance(e, alert_gate.Held):
                    await playbook_store.record_held(db, w.user_ref, w.strategy_id, e.rule_id, trigger_id=trigger,
                                                     stage=stage, value=value, threshold=threshold, reason=e.reason)
                    continue
                if e.worse is not None:
                    await _lapse_open_of(db, w, e.rule_id, playbook_store.LAPSE_SUPERSEDED_BY_WORSE)  # finding 5
                flag = flags.get(e.rule_id)
                label, unit = check.trigger_words(w.body, trigger)
                t19 = {} if ctx is None else t19_record(trigger or "", cheapest(ctx.state))
                if not t19 and rv is not None and rv.approaches:  # a day rule names its approaches (GC-IC1 1a)
                    t19 = {"approach": DAY_APPROACH_SEPARATOR.join(rv.approaches)}
                if rv is not None and rv.carry is not None:  # the carry check's content (GC-IC1 1b)
                    t19 = {**t19, "carry": check.carry_record(rv.carry)}
                rec = await playbook_store.open_suggestion(
                    db, w.user_ref, w.strategy_id, e.rule_id, trigger_id=trigger,
                    stage=flag.stage_name if flag is not None else stage, value=value, threshold=threshold,
                    group=gate_group(w.strategy_id, e.at), source=source,
                    cmp=None if rv is None else rv.cmp, label=label, unit=unit, worse=e.worse, **t19)
                opened[e.rule_id] = rec.id
            await db.commit()
        return opened


Lister = Callable[[], Awaitable[list[Watched]]]
Recorder = Callable[[Watched, pe.StrategyState, Preferences], Awaitable[Any]]
#: every registry setting in force at the worker clock, from MEMORY (``settings_cache.SettingsCache.at``; #636 r4)
SettingsAt = Callable[[datetime.datetime], Mapping[str, Decimal]]
PreferencesRead = Callable[[str], Awaitable[Preferences]]  # one user's preferences in force now (REQ-168)
Observer = Callable[[Watched, pe.StrategyState], None]  # every state a check built (tests and status)
UserValuesRead = Callable[[str], Awaitable[Mapping[str, Decimal]]]  # one user's preference values in force (REQ-168)


class Worker:
    """The background role's monitors and their cycle. Every seam is injected; ``main`` wires the real ones."""

    def __init__(self, *, provider_for: Callable[[str], Any], lister: Lister,  # noqa: PLR0913, PLR0915
                 clock: Callable[[], datetime.datetime], settings: SettingsAt, preferences: PreferencesRead,
                 recorder: Recorder = record_check,
                 cache: SharedCompute | None = None, max_per_cycle: int = DEFAULT_MAX_PER_CYCLE,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, want_client: Any = None,
                 observe: Observer | None = None,
                 rebuild_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 db_gate: DbGate | asyncio.Lock | None = None,
                 side_tasks: tuple[Callable[[], Coroutine[Any, Any, None]], ...] = (),
                 gate_store: Any = None, user_values: UserValuesRead | None = None,
                 margin_of: MarginOf | None = None,
                 before_cycle: Callable[[], Awaitable[None]] | None = None) -> None:
        if max_per_cycle < 1:
            raise ValueError("max_per_cycle must be at least 1")
        self._provider_for, self._lister, self._clock = provider_for, lister, clock
        self._settings, self._preferences = settings, preferences
        self._values: Mapping[str, Decimal] | None = None  # the last good settings read (a failed read keeps it)
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
        self._speed: Mapping[str, Decimal] | None = None  # the last good speeds per style (a failed read keeps it)
        self._steps: tuple[Decimal, ...] | None = None  # the last good safety-valve steps
        self._want_client = want_client  # a Redis client (the feed bus); None = no wanted-set write
        self._listed: dict[tuple[int, str], tuple] = {}  # (id(provider), underlying) -> (provider, known listings)
        self._token_maps: dict[int, tuple] = {}  # id(provider) -> (provider, option tokens, id -> token)
        self._wants_written: dict[str, tuple[list[int], datetime.datetime]] = {}  # owner -> (tokens, when)
        self._held: dict[int, tuple[Any, set[str]]] = {}  # id(provider) -> (provider, instrument ids it holds)
        self._minute: str | None = None  # the IST wall-clock minute (YYYY-MM-DD HH:MM) the counters below belong to
        self._read_states: dict[str, int] = {}  # price-read answer state -> count this minute (why nothing was checked)
        self._cycles = 0  # cycles run in that minute
        self._rebuilds = 0  # state builds in that minute, all strategies (the sum of the per-strategy counts)
        self._recomputes: dict[int, int] = {}  # strategy id -> state builds (real recomputes) in that minute
        self._legs: dict[int, int] = {}  # strategy id -> its leg count, so per-option = recomputes x legs
        self._logged_records: set[tuple[int, str, int]] = set()  # (strategy, rule, record id) already logged
        self._observe, self._rebuild_sleep = observe, rebuild_sleep
        self._rebuild_tried = False  # the first rebuild runs in the first cycle (or ``run``); later ones on a task
        self._prefs_of: dict[str, Preferences] = {}  # user -> preferences, read once per rebuild (last good kept)
        self._leg_ids: dict[int, tuple[tuple, tuple[str, ...]]] = {}  # strategy -> (its legs, spot + leg ids read)
        self._tick: dict[int, tuple | None] = {}  # strategy -> tick key at its last check (``_tick_key``)
        self._memory: dict[int, dict] = {}  # strategy -> rule memory of its last write
        self._written: dict[int, tuple] = {}  # strategy -> ``_write_key`` of its last write
        self._grids: dict[tuple, tuple] = {}  # (id(provider), underlying, expiry) -> (provider, strike grid)
        self._outcomes: dict[str, int] = {}  # evaluation outcome (withheld / not checked reason) -> count this minute
        #: the ONE database gate of the role: rebuild, writer and settings poll hold it, so the role opens at
        #: most one connection at a time (ADR-048 limit 5 = API 2 + background 1 + feed 1); the cycle path never
        #: names it (#636 r6, ``tests_app/test_background_db_gate.py``); served writer, poll, rebuild (``db_gate``)
        self.db_gate = db_gate if db_gate is not None else DbGate()
        self._before_cycle = before_cycle  # scenario mode: the shared frame index is read before every cycle
        self._side_tasks = side_tasks  # e.g. the settings cache's poll loop, started and stopped with ``run``
        #: the writer queue (#636 r4 item 4): strategy -> the latest (watched, state, prefs) to write; a newer check
        #: for the same strategy replaces its entry (coalesced: one write of the latest state)
        self._pending: dict[int, tuple[Watched, pe.StrategyState, Preferences, pe.Evaluation]] = {}
        self._write_wake = asyncio.Event()
        self.writes_failed = 0
        self.writes_dropped = 0  # queued writes dropped at a rebuild (#636 r5 finding 2)
        self._writer: asyncio.Task | None = None  # the writer task, watched by ``_watch_writer`` (#636 r5 finding 3)
        self.writer_restarts = 0
        #: #636 r6: strategy -> its gate steps' events not yet written, oldest first (the writer writes them first)
        self._gate_events: dict[int, collections.deque[GateBatch]] = {}
        self.gate_writes_failed = 0
        self.gate_events_dropped = 0
        self._gate_fails: dict[int, int] = {}  # strategy -> event writes failed in a row (this outage)
        self._aged_warned: GateBatch | None = None  # the oldest batch whose age was already logged
        # the alert gate (module docstring, step 5)
        self._gate_store = gate_store if gate_store is not None else DbGateStore()
        self._user_values_read = user_values  # None: the user's alert values are the admin values in force (named)
        self._user_values: dict[str, Mapping[str, Decimal]] = {}  # user -> alert values, read once per rebuild
        self._gate: dict[int, alert_gate.GateState] = {}  # strategy -> gate state (restored on its first check)
        self._gate_load: dict[int, GateLoad] = {}  # strategy -> the last good store read (rebuild task)
        self._gate_body: dict[int, Mapping] = {}  # strategy -> the body its gate state was restored against
        self._gate_ctx: dict[int, GateContext] = {}  # strategy -> its last check's evaluation and state
        self._preset: dict[int, alert_gate.Preset] = {}  # strategy -> the preset of its last check
        # strategy -> its latest pause not yet given to its gate (applied at the next gate step, ``_gate_step``)
        self._paused_at: dict[int, datetime.datetime] = {}
        self._style: dict[int, str] = {}  # strategy -> the trading style of its last check (its check interval)
        self.user_paused_until: dict[int, datetime.datetime] = {}  # strategy -> the end of its user pause in force
        self.margins = MarginCache(margin_of)  # T-16's margin, refreshed on its own task (module docstring, step 3)

    async def rebuild(self) -> None:
        """REQ-115 AC-3: the monitors from the database (the lister); a strategy's memory stays in the store."""
        # #636 r6: no hold around the list; the lister holds the gate per strategy's reads (``owner_lister(gate=)``)
        monitors = await self._lister()
        before = {w.strategy_id: w.body for w in self.monitors}
        for w in monitors:  # a changed plan is rechecked at the next cycle, with no price tick (#636 r4 item 3)
            if w.strategy_id in before and before[w.strategy_id] != w.body:
                self._signature.pop(w.strategy_id, None)
                self._tick.pop(w.strategy_id, None)
        self._drop_stale_writes(monitors)
        self.monitors = monitors
        self._rebuilt_at = self._clock()
        for user in dict.fromkeys(w.user_ref for w in monitors):  # once per user, never per check (finding 3)
            try:
                async with held(self.db_gate, GATE_REBUILD):  # one user's reads per hold
                    self._prefs_of[user] = await self._preferences(user)
                    if self._user_values_read is not None:
                        self._user_values[user] = await self._user_values_read(user)
            except Exception as exc:  # the last good read stays; none yet -> that user's strategies are paused
                log.exception("background: reading the preferences of %s failed; keeping the last good read", user)
                _keep_recent(self.errors, (0, type(exc).__name__))
        await self._load_gates(monitors)
        log.info("background: %s strategies monitored", len(monitors))

    def _drop_stale_writes(self, monitors: list[Watched]) -> None:
        """#636 r5 finding 2: a queued write whose strategy left the list (exited, deleted, no playbook) or whose plan
        changed is dropped, never written: it was evaluated against a strategy or a ladder that no longer holds. A
        re-planned strategy is checked again at the next cycle (its signature was forgotten above) and queues anew."""
        body = {w.strategy_id: w.body for w in monitors}
        stale = [sid for sid, item in self._pending.items() if body.get(sid, _GONE) != item[0].body]
        for sid in stale:
            self._pending.pop(sid, None)
            self.writes_dropped += 1
            log.info("background: the queued write of strategy %s was dropped (%s)", sid,
                     "no longer listed" if sid not in body else "plan changed")
        unread = getattr(monitors, "unread", frozenset())  # a failed read is not a strategy leaving (r6 review)
        for sid in [k for k in self._gate_events if k not in body and k not in unread]:  # a plan change keeps them
            gone = self._gate_events.pop(sid)
            self.gate_events_dropped += len(gone)
            log.info("background: %s queued alert events of strategy %s were dropped (no longer listed)",
                     sum(len(b.events) for b in gone), sid)

    async def _load_gates(self, monitors: list[Watched]) -> None:
        """Step 5's store read, on the rebuild task: per strategy the gate rows, today's held crossings and the pin.
        A failed read keeps the last good one (none yet -> that strategy is paused at its check). A strategy gone
        from the list drops its gate; a changed body restores again against the new ladder; a dismissed record
        silences its rule (ADR-236)."""
        today = self._clock().astimezone(IST).date()
        ids = {w.strategy_id for w in monitors}
        for sid in [k for k in self._gate_load if k not in ids]:
            for kept in (self._gate, self._gate_load, self._gate_body, self._gate_ctx, self._preset, self._style,
                         self._paused_at):
                kept.pop(sid, None)
        for w in monitors:
            sid = w.strategy_id
            try:
                async with held(self.db_gate, GATE_REBUILD):  # one strategy per hold (#636 r4, r6)
                    load = await self._gate_store.load(w, today)
            except Exception as exc:  # contained: the last good read stays
                log.exception("background: reading the alert gate of strategy %s failed", sid)
                _keep_recent(self.errors, (sid, type(exc).__name__))
                continue
            self._gate_load[sid] = load
            if sid in self._gate and self._gate_body.get(sid) != w.body:
                self._gate.pop(sid, None)  # plan change: restored at the next check against the new ladder
            state = self._gate.get(sid)
            if state is None:
                continue
            for row in load.rows.last:
                if row.dismissed and alert_gate.is_dismissed(state, row.rule_id) is False and row.id is not None:
                    state = alert_gate.dismiss(state, row.rule_id, row.id)  # by record, never by rule (#639 item 2)
            self._gate[sid] = state

    async def _rebuild_loop(self) -> None:
        """The re-read on its own task, off the checks' path (finding 3): every ``REBUILD_SECONDS``."""
        while not self._stop:
            await self._rebuild_sleep(REBUILD_SECONDS)
            await self._rebuild_safely()

    async def _rebuild_safely(self) -> None:
        """A failed re-read keeps the last good list and is retried at the next re-read (REQ-115 AC-9)."""
        self._rebuild_tried = True
        try:
            await self.rebuild()
        except Exception as exc:  # contained to this step: the previous list stays
            log.exception("background: re-reading the strategy list failed; keeping the last list")
            _keep_recent(self.errors, (0, type(exc).__name__))

    def _settings_safely(self, now: datetime.datetime) -> Mapping[str, Decimal] | None:
        """The settings in force at ``now``, resolved ONCE per cycle from memory (no database call: #636 r4; a stored
        change is used within ``settings_cache.LAG_SECONDS``, REQ-166 AC-1, REQ-167 AC-4); a failed resolve keeps the
        last good one, None when there is none yet (the cycle then checks nothing, REQ-115 AC-9)."""
        try:
            self._values = self._settings(now)
        except Exception as exc:  # contained to this step
            log.exception("background: reading the settings in force failed; keeping the last good read")
            _keep_recent(self.errors, (0, type(exc).__name__))
        return self._values

    def background_seconds(self) -> Mapping[str, Decimal]:
        """Trading style -> its background check interval with the valve applied (ADR-235 (1)), from the last good
        settings read."""
        if self._values is None:
            raise calc_speeds.SpeedSettingRefused("no settings have been read yet")
        steps = calc_speeds.valve_steps(self._values)
        speeds = {k: self.valve.slowed(v, steps) for k, v in calc_speeds.read_speeds(self._values).background.items()}
        self._steps = steps
        return speeds

    def _speed_safely(self) -> Mapping[str, Decimal] | None:
        """The speed now; a failed read keeps the last good one, None when there is none yet (REQ-115 AC-9)."""
        try:
            self._speed = self.background_seconds()
        except Exception as exc:  # contained to this step
            log.exception("background: reading the background speed failed")
            _keep_recent(self.errors, (0, type(exc).__name__))
        return self._speed

    def _known_of(self, provider: Any, underlying: str) -> tuple[tuple, frozenset]:
        """(listed options, future expiries) of ``underlying``, read once per provider and underlying (as
        ``_tokens_of``)."""
        key = (id(provider), underlying)
        kept = self._listed.get(key)
        if kept is None or kept[0] is not provider:
            kept = (provider, catalogue_of(provider, underlying))
            self._listed[key] = kept
        return kept[1]

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

    def _grid_of(self, provider: Any, options: Mapping, underlying: str, expiry: datetime.date) -> list[Decimal]:
        key = (id(provider), underlying, expiry)
        kept = self._grids.get(key)
        if kept is None or kept[0] is not provider:
            grid = sorted({k[2] for k in options if k[0] == underlying and k[1] == expiry and k[2] is not None})
            kept = (provider, grid)
            self._grids[key] = kept
        return kept[1]

    def _window_tokens(self, w: Watched) -> set[int]:
        """Never raises: a window that cannot be read is no window (logged, counted); the legs are held anyway."""
        try:
            return self._window_tokens_of(w)
        except Exception as exc:  # contained: legs and index only for this strategy
            log.exception("background: reading the strike window of strategy %s failed", w.strategy_id)
            _keep_recent(self.errors, (w.strategy_id, type(exc).__name__))
            return set()

    def _window_tokens_of(self, w: Watched) -> set[int]:
        """The calls and puts of the SCREEN's strike window of the strategy's first leg expiry (the expiry the
        forward and ATM IV are read from, ``adjustment_readers.read_market``): ``chain_push.strike_window`` around
        ``chain_push.atm_strike`` of the live spot, ``limits.chain_strikes_each_side`` (the chain screen's default)
        each side (finding 2). Empty when not known: no settings read yet, no live spot, the expiry not listed."""
        from ofo_app.chain_push import window_strikes  # noqa: PLC0415 - the ONE window rule, shared with the screen
        if self._values is None:
            return set()
        provider = self._provider_for(w.feed_owner)
        options, _by_id = self._tokens_of(provider)
        position = w.tracked.position
        expiry = position.legs[0].expiry
        spot = provider.underlying_quote(position.underlying)
        grid = self._grid_of(provider, options, position.underlying, expiry)
        each = settings_calc.chain_strikes_each_side(self._values)
        window = window_strikes(grid, None if spot is None else spot.ltp, each)
        return {t for k in window for side in ("CE", "PE")
                if (t := options.get((position.underlying, expiry, k, side))) is not None}

    def _hold(self, wanted: dict[str, set[int]]) -> None:
        """The provider holds exactly the wanted tokens (its own subscription, as the API's provider does): only a
        held token counts as data for the feed's health, so without this every frame is a bare heartbeat and every
        read answers STALE. Tokens no longer wanted are released. Never raises (a failure is kept in ``errors``)."""
        per_provider: dict[int, tuple[Any, set[int]]] = {}
        for owner, tokens in wanted.items():
            provider = self._provider_for(owner)
            per_provider.setdefault(id(provider), (provider, set()))[1].update(tokens)
        for key in self._held.keys() - per_provider.keys():
            per_provider[key] = (self._held[key][0], set())  # no owner left on that provider: release all it holds
        for key, (provider, tokens) in per_provider.items():
            try:
                _options, by_id = self._tokens_of(provider)
                id_of = {token: iid for iid, token in by_id.items()}
                want = {id_of[t] for t in tokens if t in id_of}
                have = self._held.get(key, (provider, set()))[1]
                if want - have:
                    provider.subscribe(sorted(want - have))
                if have - want:
                    provider.unsubscribe(sorted(have - want))
                self._held[key] = (provider, want)
            except Exception as exc:  # contained: the other providers are held, the next cycle retries
                log.exception("background: holding the wanted tokens failed")
                _keep_recent(self.errors, (0, type(exc).__name__))

    def _merge_windows(self, wanted: dict[str, set[int]], windows: dict[str, set[int]]) -> None:
        """B4: an owner's strike windows join its wanted set only when the whole set stays within the cap (the relay
        refuses an over-cap snapshot whole), so a window never pushes the legs and the index out."""
        for owner, extra in windows.items():
            if len(wanted.get(owner, set()) | extra) <= feed_bus.MAX_WANTED_TOKENS:
                wanted.setdefault(owner, set()).update(extra)
            else:
                log.error("background: the strike windows of %s exceed the cap of %s; legs and index only", owner,
                          feed_bus.MAX_WANTED_TOKENS)
                _keep_recent(self.errors, (0, "WindowTooLarge"))

    async def _write_wants(self, now: datetime.datetime) -> None:
        """Step 4c: one snapshot per feed owner (module docstring); never raises."""
        if self._want_client is None:
            return
        wanted: dict[str, set[int]] = {}
        windows: dict[str, set[int]] = {}
        for w in self.monitors:
            try:
                tokens = self._strategy_tokens(w)
            except Exception as exc:  # contained: this strategy is paused, the others are written
                log.exception("background: finding the tokens of strategy %s failed", w.strategy_id)
                _keep_recent(self.errors, (w.strategy_id, type(exc).__name__))
                tokens = None
            if tokens is None:
                self._pause(w.strategy_id, PriceState.LEG_MISSING, now)
                wanted.setdefault(w.feed_owner, set())
                continue
            wanted.setdefault(w.feed_owner, set()).update(tokens)
            windows.setdefault(w.feed_owner, set()).update(self._window_tokens(w))
        self._merge_windows(wanted, windows)
        self._hold(wanted)
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

    def _tick_key(self, provider: Any, w: Watched, now: datetime.datetime) -> tuple | None:
        """What a tick changes, read cheaply (one held quote per leg and the spot, no chain copy): each quote's id,
        price, time and health, and the IST minute (clock rules). None = cannot say (no previous fresh read, the legs
        changed, a quote not held, a provider with no ``held_quote``): the caller reads in full (fail closed)."""
        held = getattr(provider, "held_quote", None)
        kept = self._leg_ids.get(w.strategy_id)
        if held is None or kept is None or kept[0] != w.tracked.position.legs:
            return None
        quotes = [held(i, now) for i in kept[1]]
        if any(q is None for q in quotes):
            return None
        return (tuple((q.instrument_id, q.ltp, q.bid, q.ask, q.timestamp, getattr(q, "health", None))
                      for q in quotes), now.astimezone(IST).strftime("%Y-%m-%d %H:%M"))

    def _pause(self, sid: int, reason: PriceState, now: datetime.datetime) -> None:
        """Every pause goes through here (review round 2, finding 2): the candle running at ``now`` was not fully
        watched, so the gate gets ``alert_gate.pause`` at its next step and that candle has no close."""
        self.status[sid] = MonitoringStatus.PAUSED
        self.paused_reason[sid] = reason
        self._signature.pop(sid, None)  # the first check after the gap reads the fresh snapshot
        self._tick.pop(sid, None)
        kept = self._paused_at.get(sid)
        self._paused_at[sid] = now if kept is None else max(kept, now)

    def _interval_style(self, sid: int) -> str:
        """The style whose interval gates this check (ADR-235 (1)). #639 item 3: the pin the last rebuild read wins, so
        after a style change (monthly -> intraday) the NEXT check already uses the new interval, never the old style's
        once; no pin (automatic) -> the style of the last check (it needs this check's expiry and days left); none
        yet -> "" (no interval: the first check runs)."""
        load = self._gate_load.get(sid)
        pin = None if load is None else load.pin
        return pin if pin is not None else self._style.get(sid, "")

    async def _check_one(self, w: Watched, speeds: Mapping[str, Decimal]) -> bool:
        """True when a check ran (counted against the cycle's cap)."""
        now = self._clock()  # finding 1: THIS check's clock, never the cycle's start
        if self._user_paused(w.strategy_id, now):
            return False  # A-38: no read, no evaluation until the end (module docstring, step 6)
        return await self._check_unpaused(w, speeds, now)

    async def _check_unpaused(self, w: Watched, speeds: Mapping[str, Decimal],  # noqa: PLR0911, C901
                              now: datetime.datetime) -> bool:
        """One check at ``now`` of a strategy the user has not paused."""
        sid = w.strategy_id
        provider = self._provider_for(w.feed_owner)
        early = feed_state(provider, now)
        if early is None:
            tick = self._tick_key(provider, w, now)
            if tick is not None and tick == self._tick.get(sid):
                self._read_states["NOT_TICKED"] = self._read_states.get("NOT_TICKED", 0) + 1
                return False  # nothing it depends on ticked: no read, no check (item c)
            read = read_prices(provider, w, now, self._known_of(provider, w.tracked.position.underlying))
        else:
            read = PriceRead(early)
        self._read_states[read.state.name] = self._read_states.get(read.state.name, 0) + 1  # the minute line's reads
        if read.state is PriceState.MARKET_CLOSED:
            return False  # nothing is recomputed while the market is closed
        if read.state is not PriceState.FRESH:
            self._pause(sid, read.state, now)
            return False
        self.status[sid] = MonitoringStatus.ACTIVE
        self.paused_reason.pop(sid, None)
        self._leg_ids[sid] = (w.tracked.position.legs,
                              (read.spot.instrument_id, *(read.legs[i].instrument_id for i in sorted(read.legs))))
        tick = self._tick_key(provider, w, now)  # read with the prices, before any await (a later tick is new)
        sig = read.signature(now)
        if sig == self._signature.get(sid):
            self._tick[sid] = tick
            return False
        last = self._last_check.get(sid)
        every = speeds.get(self._interval_style(sid), Decimal(0))
        if last is not None and _seconds(now - last) < every:
            return False  # changed, but too soon: the tick key stays old, so it is read again next cycle
        if self._values is None:
            return False  # no settings read yet: nothing is checked on a guessed setting
        prefs = self._prefs_of.get(w.user_ref)
        if prefs is None:  # no preferences read for this user yet: paused, never checked on a guess
            self._pause(sid, PriceState.CHECK_FAILED, now)
            return False
        load = self._gate_load.get(sid)
        user_values = self._values if self._user_values_read is None else self._user_values.get(w.user_ref)
        if load is None or user_values is None:  # no gate read / no alert values: paused, never a default preset
            self._pause(sid, PriceState.CHECK_FAILED, now)
            return False
        market = market_inputs(w, read, FeedScope(self.cache, w.feed_owner), now, self._values)
        # ADR-245: the carry gap in force (plan, else the user's own, else the admin default) is resolved inside
        # state_of; with no user read path there is no user layer (None), never the admin values posing as the user's
        own = None if self._user_values_read is None else user_values
        state = state_from_market(w, market, now, self._values, prefs, self.margins.block_for(w, now),
                                  user_values=own)
        state = dataclasses.replace(state, watches=load.watches)  # A-37: read on the rebuild (step 7), never per check
        self.margins.seen(w, market)
        self._recomputes[sid] = self._recomputes.get(sid, 0) + 1  # a real recompute (REQ-166)
        self._rebuilds += 1
        self._legs[sid] = len(w.tracked.position.legs)
        if self._observe is not None:
            self._observe(w, state)
        if not await self._evaluate_and_gate(w, now, state, prefs, (load.pin, user_values)):
            return False
        self._signature[sid] = sig
        self._tick[sid] = tick
        self._last_check[sid] = now
        _keep_recent(self.checks, (sid, now))
        return True

    def _user_paused(self, sid: int, now: datetime.datetime) -> bool:
        """Step 6: the user's pause compared with THIS check's time; in force -> paused through ``_pause``."""
        load = self._gate_load.get(sid)
        until = None if load is None else load.paused_until
        if until is None or not monitor_pause.in_force(until, now):
            self.user_paused_until.pop(sid, None)
            return False
        self._pause(sid, PriceState.USER_PAUSED, now)
        self.user_paused_until[sid] = until
        return True

    async def _evaluate_and_write(self, w: Watched, state: pe.StrategyState, prefs: Preferences) -> pe.Evaluation:
        """Module docstring, step 4: evaluated here with the last written memory (the entry state is this check's
        when the memory is empty, as ``evaluate_and_remember`` with no scenario); written only when the write key
        (rule memory, flagged rule ids, clear rule ids) changed from this process's last successful write; a repeated
        identical flag makes no call (round 3). The memory holds only two booleans per rule (``held_at_entry``,
        ``seen_clear``), no timestamp, so it is stable between checks."""
        sid = w.strategy_id
        memory = self._memory.get(sid)
        known = memory or {}
        ev = pe.evaluate(w.body, state, known, None if known else state, gap_until=prefs.gap_until)
        self._count_outcomes(ev)
        if memory is not None and _write_key(ev) == self._written.get(sid):
            return ev  # nothing a write would change (rule memory, flagged ids, clear ids): no DB call
        self._memory.pop(sid, None)  # fail closed: until this write succeeds the stored state is unknown, so the
        self._written.pop(sid, None)  # next check writes (a raising recorder leaves both empty)
        self._pending.pop(sid, None)  # re-inserted last: the latest state replaces an older one (coalesced)
        self._pending[sid] = (w, state, prefs, ev)
        self._write_wake.set()  # the writer task writes it; the check never waits for the database
        return ev

    async def _write_one(self, sid: int) -> None:
        """One queued write, holding the database gate. Rule memory is set only after the write succeeded and only
        when no newer state for the strategy was queued meanwhile (that one is written next). A raising recorder
        leaves the memory unset and forgets the strategy's signature and tick, so its next cycle checks and queues
        again (fail closed, no automatic retry of the same call)."""
        item = self._pending[sid]
        w, state, prefs, ev = item
        try:
            async with held(self.db_gate, GATE_WRITER):
                recorded = await self._recorder(w, state, prefs)
        except Exception as exc:  # contained: the other strategies' writes go on
            if self._pending.get(sid) is item:
                del self._pending[sid]
            log.exception("background: writing the check of strategy %s failed", sid)
            _keep_recent(self.errors, (sid, type(exc).__name__))
            self.writes_failed += 1
            self.status[sid] = MonitoringStatus.PAUSED  # its last check is not stored: never shown as active
            self.paused_reason[sid] = PriceState.CHECK_FAILED
            self._signature.pop(sid, None)
            self._tick.pop(sid, None)
            return
        newer = self._pending.get(sid) is not item  # a newer state queued meanwhile, or dropped at a rebuild
        if not newer:
            del self._pending[sid]
        if isinstance(recorded, Recorded):
            opened, ev = recorded.opened, recorded.evaluation
        else:
            opened = recorded
        self._log_opportunities(w, opened)
        if newer:
            return  # the memory stays unknown until the newer one is written (a dropped one: re-checked anew)
        self._memory[sid] = dict(ev.memory)
        self._written[sid] = _write_key(ev)

    async def _evaluate_and_gate(self, w: Watched, now: datetime.datetime, state: pe.StrategyState,
                                 prefs: Preferences, style_in: tuple[str | None, Mapping[str, Decimal]]) -> bool:
        """The style and preset of this check (pin + expiry kind + days left; user values + admin values), the
        evaluation and its rule-memory write, then the gate step. False = no preset (paused, never a default)."""
        sid = w.strategy_id
        pin, user_values = style_in
        try:
            style = alert_presets.style_for(state.expiry_kind, state.days_left, pin)
            preset = alert_presets.preset_for(style, user_values, self._values or {})
        except (ValueError, KeyError) as exc:  # StyleRefused is a ValueError: paused, never a guessed preset
            log.warning("background: strategy %s has no alert preset: %s", sid, exc)
            self._pause(sid, PriceState.CHECK_FAILED, now)
            return False
        ev = await self._evaluate_and_write(w, state, prefs)
        self._style[sid], self._preset[sid] = style, preset
        self._gate_ctx[sid] = GateContext(ev, state)
        await self._gate_step(w, now, preset, gate_readings.readings(ev))
        return True

    async def _gate_step(self, w: Watched, now: datetime.datetime, preset: alert_gate.Preset,
                         readings: Mapping[str, gate_readings.Reading]) -> None:
        """One gate step (module docstring, step 5); the database only when the gate gives events. A failed write
        keeps the previous state, so the same close is processed again at the next step."""
        sid = w.strategy_id
        state = self._gate.get(sid)
        if state is None:
            if not readings:
                return  # not restored yet: restored at the first check (its readings carry the ladders)
            state = self._restored(sid, now, readings)
            self._gate_body[sid] = w.body
        paused = self._paused_at.pop(sid, None)
        if paused is not None:  # a pause since the last step: the candle it fell in has no close (finding 2)
            state = alert_gate.pause(state, paused)
            self._gate[sid] = state  # kept even when the step below fails to write
        new, events = alert_gate.step(state, now=now, preset=preset, readings=readings)
        self._gate[sid] = new
        if events:  # #636 r6: queued in step order for the ONE writer; the check never waits for the database
            self._gate_events.setdefault(sid, collections.deque()).append(
                GateBatch(w, tuple(events), self._gate_ctx.get(sid), now))
            self._write_wake.set()

    async def _write_gate_batch(self, sid: int) -> bool:
        """The oldest queued gate step of ``sid`` in one transaction, holding the gate first in its order of service.
        True = written (removed, its record ids put on the gate state, logged); False = the write raised (kept at the
        head of the queue, in order, for the next wake)."""
        queue = self._gate_events[sid]
        batch = queue[0]
        try:
            async with held(self.db_gate, GATE_WRITER):
                opened = await self._gate_store.apply(batch.watched, batch.events, batch.ctx)
        except Exception as exc:  # contained: retried in order at the next wake, never dropped, never merged
            fails = self._gate_fails[sid] = self._gate_fails.get(sid, 0) + 1
            if fails == 1:  # one traceback per strategy per outage; the retries every wake are counted
                log.exception("background: writing the alert events of strategy %s failed; kept in order", sid)
            elif fails % GATE_FAIL_COUNT_EVERY == 0:
                log.error("background: the alert events of strategy %s: %s failed writes so far (%s), %s steps queued",
                          sid, fails, type(exc).__name__, len(queue))
            _keep_recent(self.errors, (sid, type(exc).__name__))
            self.gate_writes_failed += 1
            return False
        fails = self._gate_fails.pop(sid, 0)
        if fails:
            log.warning("background: the alert events of strategy %s were written again after %s failed writes", sid,
                        fails)
        if self._gate_events.get(sid) is queue and queue and queue[0] is batch:
            queue.popleft()
            if not queue:
                del self._gate_events[sid]
        self._log_opportunities(batch.watched, opened)
        later = {e.rule_id for b in self._gate_events.get(sid, ()) for e in b.events
                 if isinstance(e, alert_gate.Opened)}
        state = self._gate.get(sid)
        # the gate's record carries its stored id, so a later dismiss matches by record (#639 item 2); a rule whose
        # newer record is still queued gets that one's id when it is written
        for rid, rec_id in (opened.items() if isinstance(opened, Mapping) else ()):
            if state is not None and rid not in later:
                state = alert_gate.with_record_id(state, rid, rec_id)
        if state is not None:
            self._gate[sid] = state
        return True

    def _restored(self, sid: int, now: datetime.datetime,
                  readings: Mapping[str, gate_readings.Reading]) -> alert_gate.GateState:
        """ADR-237 (5) from the rebuild's store read, plus today's held crossings newer than the rule's last record."""
        load = self._gate_load[sid]
        specs = {rid: spec for rid, (spec, _v) in readings.items()}
        state = alert_gate.restore(load.rows, now.astimezone(IST).date(), specs)
        last_at = {r.rule_id: r.at for r in load.rows.last}
        latest: dict[str, Any] = {}
        for h in load.held:
            if last_at.get(h.rule_id) is None or h.held_at > last_at[h.rule_id]:
                latest[h.rule_id] = h
        for rid, h in latest.items():
            state = alert_gate.restore_held(state, rid, h.reason, h.threshold, specs.get(rid))
        return state

    async def _close_pass(self, checked: set[int]) -> None:
        """ADR-237 (2): every gated strategy not checked this cycle is stepped with EMPTY readings, so a candle close
        is processed with no price change. In memory only (no read, no recompute); the database only on an event."""
        for w in self.monitors:
            sid = w.strategy_id
            if sid in checked or sid not in self._gate or sid not in self._preset:
                continue
            if sid in self.user_paused_until and self._user_paused(sid, self._clock()):
                continue  # A-38: no close is processed while the user's pause holds
            try:
                await self._gate_step(w, self._clock(), self._preset[sid], {})
            except Exception as exc:  # REQ-115 AC-9: contained to this strategy, retried next wake
                log.exception("background: strategy %s alert close failed", sid)
                _keep_recent(self.errors, (sid, type(exc).__name__))

    async def drain_writes(self) -> None:
        """The writer's pass (tests call it after a cycle): every queued gate event first, each strategy's in step
        order; then every queued rule-memory state, oldest strategy first. A strategy whose event write raised is not
        retried in this pass (its next events wait behind it: order kept); the next wake retries it."""
        self._log_oldest_event()
        failed: set[int] = set()
        while True:
            ready = [sid for sid in self._gate_events if sid not in failed]
            if ready:
                if not await self._write_gate_batch(ready[0]):
                    failed.add(ready[0])
                continue
            if not self._pending:
                return
            await self._write_one(next(iter(self._pending)))

    def _log_oldest_event(self) -> None:
        """The age of the oldest queued gate event, logged once per batch when it passes ``GATE_EVENT_AGE_WARN_S``."""
        heads = [q[0] for q in self._gate_events.values() if q and q[0].queued_at is not None]
        if not heads:
            return
        oldest = min(heads, key=lambda b: b.queued_at)
        age = int((self._clock() - oldest.queued_at).total_seconds())
        if age > GATE_EVENT_AGE_WARN_S and oldest is not self._aged_warned:
            self._aged_warned = oldest
            log.warning("background: the oldest queued alert event of strategy %s has been queued %s s (promise %s s)",
                        oldest.watched.strategy_id, age, GATE_EVENT_AGE_WARN_S)

    async def _writer_loop(self) -> None:
        """The ONE writer, on its own task: wakes when a check queues a state."""
        while not self._stop:
            await self._write_wake.wait()
            self._write_wake.clear()
            await self.drain_writes()

    def _watch_writer(self) -> None:
        """#636 r5 finding 3, every cycle: the writer task is started, and a writer that ended (it raised, or returned
        while the role runs) is logged by name with its error and restarted; a write it held stays queued and is
        written by the new writer. Answer states: alive -> nothing; died -> logged + restarted (``writer_restarts``);
        stopping -> never restarted (``run`` drains what is queued instead)."""
        if self._stop:
            return
        task = self._writer
        if task is not None and not task.done():
            return
        if task is not None:
            why = "cancelled" if task.cancelled() else repr(task.exception())
            self.writer_restarts += 1
            log.error("background: the writer task (background-writer) ended (%s); restarted, %s writes queued",
                      why, len(self._pending))
            _keep_recent(self.errors, (0, "writer_restarted"))
        self._writer = asyncio.create_task(self._writer_loop(), name="background-writer")
        if self._pending or self._gate_events:  # a failed event write is retried each cycle until it lands
            self._write_wake.set()

    async def _drain_on_stop(self) -> None:
        """A normal stop writes what is queued; one failing write is logged and dropped, never blocks the stop."""
        for sid in list(self._gate_events):
            while sid in self._gate_events:
                if not await self._write_gate_batch(sid):
                    lost = self._gate_events.pop(sid)
                    log.error("background: %s queued alert steps of strategy %s were not written at stop", len(lost),
                              sid)
        while self._pending:
            sid = next(iter(self._pending))
            item = self._pending[sid]
            try:
                await self._write_one(sid)
            except Exception:  # contained: the rest still drains
                log.exception("background: the queued write of strategy %s failed at stop", sid)
                if self._pending.get(sid) is item:
                    del self._pending[sid]

    def _count_outcomes(self, ev: pe.Evaluation) -> None:
        """Item g: why rules gave no flag this minute (withheld / not checked with the reason code), and flags."""
        names = [f"not_checked {r.code}" if isinstance(r, pe.NotChecked) else
                 "flag" if isinstance(r, pe.Flag) else "already_true" for r in ev.results]
        if ev.withheld is not None:
            names.append(f"withheld {ev.withheld}")
        for name in names:
            self._outcomes[name] = self._outcomes.get(name, 0) + 1

    def _log_opportunities(self, w: Watched, recorded: Any) -> None:
        """One INFO line the first time this process sees an open opportunity record of a rule (``record_check``
        returns rule id -> record id; a record still open on later checks is not logged again). ``written_at`` is the
        worker's clock when the record's transaction had committed; a record already open before a restart is logged
        once as first seen, not as newly written (the store's return does not say which)."""
        if not isinstance(recorded, Mapping):  # a recorder that returns nothing logs nothing
            return
        for rule_id, record_id in recorded.items():
            key = (w.strategy_id, rule_id, record_id)
            if key in self._logged_records:
                continue
            self._logged_records.add(key)
            # "written <date> <time>" with a space, never "written_at=2026-11-06T11:..": the log redactor blanks a
            # 20+ character run holding letters and numbers (ofo_app.redaction), which that form is
            log.info("background: opportunity strategy=%s rule=%s record=%s written %s", w.strategy_id, rule_id,
                     record_id, self._clock().astimezone(IST).isoformat(sep=" ", timespec="seconds"))

    def _roll_minute(self, now: datetime.datetime) -> None:
        """ONE summary line per wall-clock minute (not per cycle), written when the next minute's first cycle starts."""
        minute = now.astimezone(IST).strftime("%Y-%m-%d %H:%M")
        if minute != self._minute:
            self.flush_minute()
            self._minute = minute

    def flush_minute(self) -> None:
        """Write the summary of the minute counted so far (also called when the role stops) and reset the counters."""
        if self._minute is None:
            return
        log.info("background: minute %s cycles=%s checks=%s recomputes %s legs %s valve_step=%s speed=%ss reads %s "
                 "outcomes %s", self._minute[-5:], self._cycles, self._rebuilds,
                 dict(sorted(self._recomputes.items())),
                 {k: self._legs[k] for k in sorted(self._recomputes)}, self.valve.step + 1, self._speed,
                 dict(sorted(self._read_states.items())), dict(sorted(self._outcomes.items())))
        self._cycles, self._rebuilds = 0, 0
        self._recomputes, self._legs, self._read_states, self._outcomes = {}, {}, {}, {}

    async def cycle(self) -> None:
        if self._before_cycle is not None:
            try:
                await self._before_cycle()  # e.g. move the scenario feed to the stored frame (IC e2e decision 2)
            except Exception as exc:  # fail closed: no check on a market the worker could not move to
                log.exception("background: the pre-cycle step failed; this cycle is skipped")
                _keep_recent(self.errors, (0, type(exc).__name__))
                return
        now = self._clock()
        self._roll_minute(now)
        self._cycles += 1
        if not self._rebuild_tried:  # the first list only; every later re-read runs on its own task (``run``)
            await self._rebuild_safely()
        self._settings_safely(now)  # ONE resolve per cycle, from memory: speeds, valve, rate, forward, windows
        await self._write_wants(now)  # not behind the speed: the feed is wanted whatever the checks do
        every = self._speed_safely()  # read on EVERY cycle (REQ-166 AC-1)
        if every is None:
            log.error("background: no background speed has been read yet; this cycle is skipped")
            return
        n = len(self.monitors)
        ran, slowest, visited = 0, Decimal(0), 0
        checked: set[int] = set()
        while visited < n and ran < self._max:
            w = self.monitors[(self._cursor + visited) % n]
            visited += 1
            started = self._clock()
            try:
                did = await self._check_one(w, every)
                ran += did
                if did:
                    checked.add(w.strategy_id)
            except Exception as exc:  # REQ-115 AC-9: one strategy's failure never stops the others
                log.exception("background: strategy %s check failed", w.strategy_id)
                _keep_recent(self.errors, (w.strategy_id, type(exc).__name__))
                self._pause(w.strategy_id, PriceState.CHECK_FAILED, self._clock())  # never shown as active
            slowest = max(slowest, _seconds(self._clock() - started))
        self._cursor = (self._cursor + visited) % n if n else 0
        await self._close_pass(checked)
        if self._steps is not None:
            self.valve.observe(self._clock(), slowest, n - visited, self._steps)

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> None:
        if not self._rebuild_tried:
            await self._rebuild_safely()
        rebuilder = asyncio.create_task(self._rebuild_loop(), name="background-rebuild")
        self._watch_writer()
        others = [asyncio.create_task(t(), name=f"background-side-{i}") for i, t in enumerate(self._side_tasks)]
        margins = asyncio.create_task(self._margin_loop(), name="background-margin")
        try:
            while not self._stop:
                self._watch_writer()
                try:
                    await self.cycle()
                except Exception as exc:  # one cycle's failure never ends the role (CancelledError is not one)
                    log.exception("background: a cycle failed; the next cycle runs")
                    _keep_recent(self.errors, (0, type(exc).__name__))
                # ADR-233 (6): wake about once a second whatever the setting; ``_check_one`` keeps each strategy to
                # one check per setting interval. No good speed yet -> 1 s.
                speeds = self._speed_safely()
                wait = min(min(speeds.values()) if speeds else Decimal(1), WAKE_SECONDS)
                await self._sleep(float(wait))  # float-ok: asyncio.sleep takes seconds as float
        finally:
            rebuilder.cancel()
            margins.cancel()
            for t in others:
                t.cancel()
            if self._writer is not None:
                self._writer.cancel()  # a write it held stays queued (``_write_one``) and is drained below
                await asyncio.gather(self._writer, return_exceptions=True)
                self._writer = None
        await self._drain_on_stop()  # a normal stop writes what was queued (a cancellation does not get here)
        self.flush_minute()

    async def refresh_margins(self) -> None:
        """One margin refresh pass (``MarginCache.refresh``); never inside a check (B4 (a))."""
        await self.margins.refresh(list(self.monitors), self._clock)

    async def _margin_loop(self) -> None:
        while not self._stop:
            try:
                await self.refresh_margins()
            except Exception as exc:  # one failed pass never ends the loop; the checks see no margin meanwhile
                log.exception("background: a margin refresh pass failed")
                _keep_recent(self.errors, (0, type(exc).__name__))
            await self._rebuild_sleep(float(WAKE_SECONDS))  # float-ok: asyncio.sleep takes seconds as float


def _keep_recent(kept: list, item: object) -> None:
    """Append ``item`` and drop the oldest entries beyond ``RECENT_KEPT``."""
    kept.append(item)
    if len(kept) > RECENT_KEPT:
        del kept[:-RECENT_KEPT]


_GONE = object()  # a strategy no longer listed (``_drop_stale_writes``)

#: Review round 2, finding 4: how many exited strategies' lapse writes failed in this process (each logged once).
LISTER_LAPSE_FAILURES: dict[int, int] = {}


async def _lapse_exited(db: Any, user_ref: str, sid: int) -> None:
    """Lapse an exited strategy's open records, contained to that strategy: a failing write (a record no longer open,
    the database refusing) is rolled back, counted and logged once per strategy, and never drops the other strategies
    from the list or skips their gate read (the whole lister failing kept the old list; at start-up 0 monitored)."""
    from ofo_app import playbook_store  # noqa: PLC0415 - database layer at run time only
    try:
        if await playbook_store.open_suggestions(db, user_ref, sid):
            await playbook_store.lapse_all(db, user_ref, sid, playbook_store.LAPSE_STRATEGY_CLOSED)
            await db.commit()
    except Exception:  # contained per strategy; retried at the next re-list
        await db.rollback()
        LISTER_LAPSE_FAILURES[sid] = LISTER_LAPSE_FAILURES.get(sid, 0) + 1
        if LISTER_LAPSE_FAILURES[sid] == 1:
            log.exception("background: lapsing the records of exited strategy %s failed; the others are listed", sid)


def listable(marker: str | None, mode: str | None) -> bool:
    """Isolation both ways (IC e2e decision 4): live mode (``mode`` None) lists only real strategies (marker None);
    scenario mode lists only the strategies of the current scenario."""
    from ofo_app import scenario_mode  # noqa: PLC0415 - the one isolation helper
    return scenario_mode.in_scope(marker, mode)


async def owner_lister(provider: Any, gate: Any = None) -> Listed:
    """Every strategy of the V1 owner (ADR-051) that is tracked (open paper legs) and has a playbook; its type is read
    against the provider's instrument list and spot (as the screen's check). ``gate`` (the role's ``db_gate``) is held
    for the list read, then once per strategy's reads, never for the whole list (#636 r6): a write waits one hold."""
    from ofo_app import strategy_store  # noqa: PLC0415 - database layer at run time only
    from ofo_app.adjustment_readers import (  # noqa: PLC0415
        TrackedExited,
        TrackedUnreadable,
        entry_facts_in,
        read_tracked,
    )
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415
    from ofo_app.live_market import OWNER_REF  # noqa: PLC0415
    out, unread = Listed(), set()
    # one session at a time (#636 r4 connection budget): ``read_tracked`` opens its own session, so the list's session
    # is closed before it and the playbook lookup gets a fresh one after it (never two connections held at once)
    async with held(gate, GATE_REBUILD), get_sessionmaker()() as db:
        strategies = await strategy_store.list_strategies(db, OWNER_REF)
    from ofo_app import scenario_mode  # noqa: PLC0415 - the process mode, read at list time
    mode = scenario_mode.current_id()
    for s in strategies:
        if not listable(getattr(s, "scenario_id", None), mode):  # a row read without the column is a real one
            continue  # IC e2e decision 4: a live worker never checks a scenario strategy, and the reverse
        try:
            async with held(gate, GATE_REBUILD):  # one strategy's reads per hold
                tracked = await read_tracked(s.id, None)
                if tracked is None:
                    continue
                spot = provider.underlying_quote(tracked.position.underlying)
                stype = check.strategy_type(tracked.position, None if spot is None else spot.ltp,
                                            provider.instrument_master())
                async with get_sessionmaker()() as db:
                    resolved = await check.resolve(db, OWNER_REF, s.id, stype)
                    facts = await entry_facts_in(db, s.id) if resolved.body is not None else None
        except TrackedExited:  # every leg exited: its open records lapse (REQ-112 AC-2; one writer, ADR-237 (6))
            async with held(gate, GATE_REBUILD), get_sessionmaker()() as db:  # one session at a time (#636 r4)
                await _lapse_exited(db, OWNER_REF, s.id)
            continue
        except TrackedUnreadable:
            unread.add(s.id)
            continue
        except Exception:  # REQ-115 AC-9: one strategy's lookup failing never drops the others from the list
            log.exception("background: listing strategy %s failed; it is skipped", s.id)
            unread.add(s.id)  # not read is not gone: its queued alert events stay (#636 r6 review)
            continue
        if resolved.body is not None:
            out.append(Watched(OWNER_REF, s.id, tracked, resolved.body, resolved.is_system, OWNER_REF,
                               resolved.strategy_layer, facts, resolved=resolved))
    return Listed(out, unread)


async def _serve() -> int:  # pragma: no cover - the process wiring; each part is tested on its own
    from ofo_app import scenario_mode  # noqa: PLC0415
    if scenario_mode.scenario_requested():  # provider by PROCESS mode only (IC e2e decision 7)
        return await _serve_scenario()
    return await _serve_live()


async def _settings_reads():  # pragma: no cover - the process wiring
    from ofo_app import user_preferences_store  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    async def user_values(user_ref: str) -> Mapping[str, Decimal]:
        async with get_sessionmaker()() as db:
            return await user_preferences_store.values_for(db, user_ref)

    async def preferences(user_ref: str) -> Preferences:
        return prefs_from_values(await user_values(user_ref))
    return user_values, preferences


def scenario_worker_parts(scn: Any, session: Callable[[], Any]) -> tuple[Any, Callable[[], Awaitable[None]]]:
    """The scenario worker's provider and pre-cycle step: the scenario's own fed provider (no Kite, no feed bus) and a
    read of the shared frame index before every cycle (``scenario_mode.sync_frame``)."""
    from ofo_app import scenario_mode  # noqa: PLC0415

    async def before_cycle() -> None:
        async with session() as db:
            await scenario_mode.sync_frame(db, scn)
    return scn.provider, before_cycle


async def _serve_scenario() -> int:  # pragma: no cover - the process wiring; each part is tested on its own
    from ofo_app import scenario_mode  # noqa: PLC0415
    from ofo_app.config import app_env  # noqa: PLC0415
    from ofo_app.db import get_engine, get_sessionmaker  # noqa: PLC0415
    from ofo_app.live_market import OWNER_REF  # noqa: PLC0415
    scenario_mode.require_dev_or_test(app_env())  # refused outside development/test, before anything runs
    scn = scenario_mode.current()
    provider, before_cycle = scenario_worker_parts(scn, get_sessionmaker())
    user_values, preferences = await _settings_reads()
    gate = DbGate()
    cache = settings_cache.SettingsCache(lambda: get_engine().connect(), gate=gate)
    if not await cache.refresh():
        log.error("background: the first settings load failed; no check runs until a poll loads them")
    log.info("background: scenario %s (test data, no Kite) for %s", scn.scenario_id, OWNER_REF)
    worker = Worker(provider_for=lambda _owner: provider, lister=functools.partial(owner_lister, provider, gate=gate),
                    clock=scn.clock, settings=cache.at, preferences=preferences, db_gate=gate,
                    side_tasks=(cache.poll_loop,), user_values=user_values, before_cycle=before_cycle)
    await worker.run()
    return 0


async def _serve_live() -> int:  # pragma: no cover - the process wiring; each part is tested on its own
    from ofo_app import feed_mode, user_preferences_store  # noqa: PLC0415

    # live rows by key only (the provider's instrument list); each leg's stored id reached its terms through
    # tracked_contracts.resolve in read_tracked, never through the catalogue store here
    from ofo_app.catalogue_store import load_catalogue  # noqa: PLC0415
    from ofo_app.db import get_engine, get_sessionmaker  # noqa: PLC0415
    from ofo_app.feed_bus import BusSocket  # noqa: PLC0415
    from ofo_app.live_market import OWNER_REF, KiteProvider, listed_for_kite  # noqa: PLC0415
    async with get_engine().connect() as conn:
        catalogue = await load_catalogue(conn)

    def clock() -> datetime.datetime:
        return datetime.datetime.now(IST)

    provider = KiteProvider(listed_for_kite(catalogue.all_entries()), clock=clock)
    # publish_want=False: the Worker is the one writer of this role's want key (the ``:bg`` one); the socket would
    # otherwise write the API's own key from the provider's held set
    socket = BusSocket(provider, user_ref=OWNER_REF, clock=clock, redis_url=feed_mode.redis_url(),
                       publish_want=False)
    bus = feed_bus.new_client(feed_mode.redis_url())
    async def user_values(user_ref: str) -> Mapping[str, Decimal]:
        async with get_sessionmaker()() as db:
            return await user_preferences_store.values_for(db, user_ref)

    async def preferences(user_ref: str) -> Preferences:
        return prefs_from_values(await user_values(user_ref))

    # T-16 (GC-IC1 5b): the screen's own margin read (``get_approach_margin`` over the app's margin source). Named
    # gap (#627): this process holds no Kite session of its own yet (``live_market.current_session`` answers None
    # here), so the read answers "not checked" and T-16 stays ``missing_margin`` until the session is shared.
    from ofo.settings import defaults  # noqa: PLC0415

    from ofo_app.live_market import margin_source  # noqa: PLC0415
    from ofo_app.routes.adjustment import get_approach_margin  # noqa: PLC0415
    from ofo_app.routes.outcome import MarketContext  # noqa: PLC0415
    margin_ctx = MarketContext(provider, clock, defaults()[RISK_FREE_RATE], OWNER_REF)
    gate = DbGate()  # the role's one database gate: writer, settings poll and rebuild, served in that order
    cache = settings_cache.SettingsCache(lambda: get_engine().connect(), gate=gate)
    if not await cache.refresh():  # the first load; a failure leaves the worker refusing to check until a poll loads
        log.error("background: the first settings load failed; no check runs until a poll loads them")
    worker = Worker(provider_for=lambda _owner: provider, lister=functools.partial(owner_lister, provider, gate=gate),
                    clock=clock, settings=cache.at, preferences=preferences, want_client=bus, db_gate=gate,
                    side_tasks=(cache.poll_loop,), user_values=user_values,
                    margin_of=screen_margin_reader(get_approach_margin(margin_ctx, margin_source())))
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
    logging.basicConfig(level=logging.INFO)  # as feed_main: without it the INFO lines below never reach the log
    refuse_scenario_outside_dev_or_test()
    return asyncio.run(_serve())


def refuse_scenario_outside_dev_or_test() -> None:
    """Start-up refusal (IC e2e decision 7), before any loop or database: scenario mode outside APP_ENV
    development/test raises ``ScenarioRefused`` (as the API's ``create_app``)."""
    from ofo_app import scenario_mode  # noqa: PLC0415
    from ofo_app.config import app_env  # noqa: PLC0415
    if scenario_mode.scenario_requested():
        scenario_mode.require_dev_or_test(app_env())
        from ofo_app.live_market import live_requested  # noqa: PLC0415
        scenario_mode.require_no_live_market(live_requested())  # never the real feed with test data


if __name__ == "__main__":
    raise SystemExit(main())
