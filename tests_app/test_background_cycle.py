"""GC-MU step 4 (REQ-165 AC-2/AC-3, REQ-166 AC-1..AC-3, REQ-115 AC-4/AC-9): the background cycle without a database.
The provider is scenario ADJ-02's fed ``KiteProvider`` (the real frame parser) behind a thin wrapper that can set the
feed health, close the market, drop a leg or move a price; the recorder seam is a fake, so no check touches the store.
Clocks are injected; nothing sleeps for real.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import itertools
import json
import pathlib
import time
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.adjustment.preferences import from_values
from ofo.marketdata.shared_compute import FeedScope
from ofo.marketdata.spot_source import resolve_spot
from ofo.outcome import service as outcome_service
from ofo.rules.inputs import DataHealth
from ofo.scenario import levels as scenario_levels
from ofo.scenario import views as scenario_views
from ofo.settings import defaults as registry_defaults
from ofo.table import model as table_model
from ofo_app import adjustment_check, adjustment_readers, background, calc_speeds, db, scenario_mode, strategy_store
from ofo_app.routes.adjustment import Tracked
from ofo_app.routes.outcome import MarketContext, ctx_in_force

RATE = Decimal("0.065")  # the registry default of pricing.risk_free_rate (the screen side of the comparisons)
DEFAULTS = registry_defaults()  # the settings in force for the worker: the registry defaults, passed explicitly
PREFS = from_values(DEFAULTS)  # the owner's preferences: the registry defaults (REQ-168 AC-1)
FIRST_ID = 100  # the first watched strategy id
MANY = 1000
CHECKS_AFTER_CHANGE = 3
STOP_AFTER = 5
CYCLES = 10
SECOND = 2  # the second read / check / cycle of a test
SLOW_CYCLES = 2
TIMED_CALLS = 100
IV_STEP = Decimal("0.05")  # 5 IV points as a fraction
#: a playbook body with no rule (the evaluator refuses ``{}``: a body always has a schema and both stage lists)
NO_RULES = {"schema": 1, "stages": {k: [{"name": "all", "from": 0, "to": None}] for k in ("weekly", "monthly")}}
#: REQ-166 AC-2: what "the full table" is (ADR-220: the scenario table of the one engine); each one is refused
FULL_TABLE = ((scenario_views, "scenario_values"), (outcome_service, "scenario_values"),
              (scenario_levels, "build_level_set"), (outcome_service, "build_level_set"),
              (table_model, "build_table"), (outcome_service, "build_table"), (outcome_service, "build_outcome"),
              (outcome_service, "payoff_table"))


class Prov:
    """ADJ-02's provider with switches for every answer state of the price read."""

    def __init__(self, scn: scenario_mode.Scenario) -> None:
        self.real, self.health, self.closed = scn.provider, DataHealth.AVAILABLE, False
        self.drop: set[str] = set()
        self.moved: dict[str, object] = {}
        self.spot = self.real.underlying_quote("NIFTY")
        self.feed = self  # feed_health.market_closed_for reads provider.feed.market_closed(now)

    def market_closed(self, _now) -> bool:
        return self.closed

    def status(self):
        return dataclasses.replace(self.real.status(), health=self.health)

    def underlying_quote(self, _u):
        return self.spot

    def option_chain_snapshot(self, u, e):
        return [self.moved.get(q.instrument_id, q) for q in self.real.option_chain_snapshot(u, e)
                if q.instrument_id not in self.drop]

    def instrument_master(self):
        return self.real.instrument_master()

    def latest_day_stats(self, iid, now=None):
        """The real provider's day values of the index (the scenario's index packet through the real decoder), unless
        a test set ``day`` (an answer state of the read)."""
        return self.day if getattr(self, "day", None) is not None else self.real.latest_day_stats(iid, now)

    def move_spot(self, ltp: Decimal, at: datetime.datetime) -> None:
        self.spot = dataclasses.replace(self.spot, ltp=ltp, timestamp=at)

    def leg_id(self, strike: str, kind: str) -> str:
        return next(q.instrument_id for q in self.real.option_chain_snapshot("NIFTY", datetime.date(2026, 11, 9))
                    if q.strike == Decimal(strike) and q.instrument_type.value == kind)

    def held_quote(self, iid: str, _now=None):
        """One instrument's held quote (the cheap tick test): the spot or the chain row with that id."""
        if self.spot is not None and self.spot.instrument_id == iid:
            return self.spot
        return next((q for e in {datetime.date(2026, 11, 9)} for q in self.option_chain_snapshot("NIFTY", e)
                     if q.instrument_id == iid), None)

    def move_leg(self, iid: str, ltp: Decimal, at: datetime.datetime) -> None:
        q = next(q for q in self.real.option_chain_snapshot("NIFTY", datetime.date(2026, 11, 9))
                 if q.instrument_id == iid)
        self.moved[iid] = dataclasses.replace(q, ltp=ltp, timestamp=at)


@pytest.fixture(scope="module")
def scn():
    return scenario_mode.load("ADJ-02")


def _tracked(scn) -> Tracked:
    legs = tuple(PositionLeg(x["side"], x["type"], Decimal(x["strike"]), datetime.date.fromisoformat(x["expiry"]),
                             x["lots"], Decimal(x["entry"]), x["tradingsymbol"]) for x in scn.data["position"]["legs"])
    return Tracked(Position("NIFTY", scn.data["lot"], "weekly", datetime.date.min, legs),
                   Decimal(scn.data["position"]["booked_pnl"]), None, adjustments_used=0)


def _watched(scn, n: int = 1) -> list[background.Watched]:
    t = _tracked(scn)
    return [background.Watched("owner", FIRST_ID + i, t, NO_RULES, True, "owner", None, None,
                               resolved=None) for i in range(n)]


class Calls:
    """``states``: every state a check built (the worker's ``observe`` seam); ``writes``: every recorder call (a DB
    write in the real role, made only when the evaluation flags or its memory changed)."""

    def __init__(self, clock=None, slow: datetime.timedelta | None = None) -> None:
        self.states: list[tuple[int, object]] = []
        self.writes: list[tuple[int, object]] = []
        self._clock, self.slow = clock, slow

    def seen(self, w, state) -> None:
        self.states.append((w.strategy_id, state))
        if self.slow is not None:
            self._clock[0] += self.slow  # an injected slow maths step

    async def __call__(self, w, state, _prefs=None):
        self.writes.append((w.strategy_id, state))


def _all_styles(seconds):
    """ADR-235 (1): the same interval for every trading style (ADJ-02 is weekly, so its own key gates it)."""
    return dict.fromkeys(calc_speeds.BACKGROUND_KEYS.values(), seconds)


class FakeGate:
    """The worker's gate store seam with no database: no stored record, no pin; every applied event is kept."""

    def __init__(self) -> None:
        self.events: list[tuple[int, object]] = []

    async def load(self, _w, _today):
        return background.GateLoad(alert_gate.GateRows((), 0))

    async def apply(self, w, events, _ctx):
        self.events.extend((w.strategy_id, e) for e in events)
        return {}


def _settings(values=None):
    """The worker's settings seam: ``values`` (a dict a test may change between cycles), else the registry defaults."""
    # tests written for a 1 s check speed pin it here; the registry default (30 s, ADR-233) has its own tests below
    held = {**DEFAULTS, **_all_styles(Decimal(1))} if values is None else values

    def read(_at):  # #636 r4: the worker resolves its settings from memory at its clock (settings_cache.at)
        return held
    return read


class Draining(background.Worker):
    """The real Worker with its writer task's work done at the end of each cycle (#636 r4: writes leave the check path
    through one writer queue; a test that calls ``cycle`` directly has no writer task running)."""

    async def cycle(self) -> None:
        await super().cycle()
        await self.drain_writes()


async def _prefs(_user_ref):
    return PREFS


def _worker(prov, watched, now, recorder, settings=None, **kw) -> background.Worker:
    async def lister():
        return watched
    if isinstance(recorder, Calls):
        kw.setdefault("observe", recorder.seen)
    kw.setdefault("gate_store", FakeGate())
    return Draining(provider_for=lambda _o: prov, lister=lister, clock=lambda: now[0],
                    settings=settings or _settings(), preferences=_prefs, recorder=recorder, **kw)


# ---- answer states of the price read ---------------------------------------------------------------------------
async def test_fresh_price_runs_one_check_through_the_screens_builder(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert [s for s, _ in calls.states] == [100] and w.status[100] is background.MonitoringStatus.ACTIVE
    state = calls.states[0][1]
    assert state.spot == Decimal("23420") and state.margin is None  # no margin read in the background
    assert isinstance(state.max_loss, Decimal) and isinstance(state.max_profit, Decimal)  # the screen's own figures
    assert {s.strike: s.ltp for s in state.shorts}[Decimal("23500")] is not None
    assert all(isinstance(s.abs_delta, Decimal) for s in state.shorts)  # the shared per-option delta, exact Decimal
    ce = {s.strike: s.abs_delta for s in state.shorts}[Decimal("23500")]
    assert Decimal("0.39") < ce < Decimal("0.43"), ce  # ADJ-02 states 0.4103 for the tested short (T-03)


@pytest.mark.parametrize(("health", "reason"), [(DataHealth.STALE, background.PriceState.STALE),
                                                (DataHealth.UNAVAILABLE, background.PriceState.DISCONNECTED)])
async def test_stale_or_disconnected_feed_pauses_and_runs_no_check(scn, health, reason):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.health = health
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert calls.states == [] and w.status[100] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[100] is reason


async def test_a_stale_quote_of_one_leg_pauses(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    iid = prov.leg_id("23500", "CE")
    q = next(q for q in prov.option_chain_snapshot("NIFTY", datetime.date(2026, 11, 9)) if q.instrument_id == iid)
    prov.moved[iid] = dataclasses.replace(q, health=DataHealth.STALE)
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.STALE


async def test_no_price_for_one_leg_pauses(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.drop.add(prov.leg_id("23500", "CE"))
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.LEG_MISSING


async def test_market_closed_recomputes_nothing(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.closed = True
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert calls.states == [] and FIRST_ID not in w.status and w.cache.computations == 0


async def test_first_check_after_a_gap_reads_only_the_fresh_snapshot(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    prov.health = DataHealth.STALE
    now[0] += datetime.timedelta(seconds=2)
    prov.move_spot(Decimal("23600"), now[0])  # a move during the gap is never checked
    await w.cycle()
    assert len(calls.states) == 1 and w.status[100] is background.MonitoringStatus.PAUSED
    prov.health = DataHealth.AVAILABLE
    now[0] += datetime.timedelta(seconds=2)
    prov.move_spot(Decimal("23300"), now[0])
    await w.cycle()
    assert [st.spot for _, st in calls.states] == [Decimal("23420"), Decimal("23300")]


async def test_no_price_change_no_check_and_at_most_once_per_speed(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    now[0] += datetime.timedelta(milliseconds=300)
    await w.cycle()  # same prices: no check
    prov.move_spot(Decimal("23421"), now[0])
    await w.cycle()  # changed, but 0.3 s after the last check: not yet
    now[0] += datetime.timedelta(milliseconds=700)
    await w.cycle()
    # REQ-165 AC-2: on a change only, never more than once per background speed
    assert [st.spot for _, st in calls.states] == [Decimal("23420"), Decimal("23421")]


# ---- REQ-166 AC-1: speed read on every cycle ------------------------------------------------------------------
async def test_speed_change_from_1s_to_3s_takes_effect_without_restart(scn, monkeypatch):
    values = {**DEFAULTS, **_all_styles(Decimal(1))}
    prov, now = Prov(scn), [scn.clock_at]
    calls = Calls()
    w = None

    def observe(wd, state):
        calls.seen(wd, state)
        if len(calls.states) == CHECKS_AFTER_CHANGE:
            values.update(_all_styles(Decimal(3)))  # the admin changes the setting
        if len(calls.states) == STOP_AFTER:
            w.stop()

    async def sleep(seconds):
        now[0] += datetime.timedelta(seconds=seconds)
        prov.move_spot(prov.spot.ltp + 1, now[0])  # a price changes every tick

    w = _worker(prov, _watched(scn), now, calls, settings=_settings(values), sleep=sleep, observe=observe)
    await w.run()
    times = [t for _, t in w.checks]
    assert [int((b - a).total_seconds()) for a, b in itertools.pairwise(times)] == [1, 1, 3, 3]


async def test_each_cycle_reads_the_speed_itself_not_only_the_sleep(scn, monkeypatch):
    """The cycle's own "at most once per speed" gate reads the speed on every cycle: cycles driven every 1 s (not by
    ``run``'s sleep) with a price change each time check every 1 s, then every 3 s once the setting is 3 s."""
    values = {**DEFAULTS, **_all_styles(Decimal(1))}
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls, settings=_settings(values))
    for tick in range(CYCLES):
        if tick == SLOW_CYCLES:
            values.update(_all_styles(Decimal(3)))  # the admin changes the setting
        await w.cycle()
        now[0] += datetime.timedelta(seconds=1)
        prov.move_spot(prov.spot.ltp + 1, now[0])
    times = [t for _, t in w.checks]
    assert [int((b - a).total_seconds()) for a, b in itertools.pairwise(times)] == [1, 3, 3]


# ---- REQ-166 AC-3: safety valve -------------------------------------------------------------------------------
async def test_valve_steps_1_2_5_under_a_slow_maths_step_and_back_to_1_when_calm(scn):
    prov, now = Prov(scn), [scn.clock_at]
    calls = Calls(now, slow=datetime.timedelta(milliseconds=600))
    w = _worker(prov, _watched(scn), now, calls)
    seen = []
    for i in range(CYCLES):
        if i == SLOW_CYCLES:
            calls.slow = None  # the load drops
        now[0] += datetime.timedelta(seconds=6)
        prov.move_spot(Decimal(23420 + i), now[0])
        await w.cycle()
        seen.append(w.background_seconds()["weekly"])
    assert seen[:2] == [Decimal(2), Decimal(5)] and seen[-1] == Decimal(1)
    assert [step for _, step, _ in w.valve.log] == [1, 2, 0]
    assert all("maths reply" in r for _, _, r in w.valve.log[:2]) and "under its limits" in w.valve.log[2][2]
    assert len(calls.states) == CYCLES


def test_valve_steps_on_backlog_too():
    v = calc_speeds.Valve()
    at = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=datetime.UTC)
    steps = calc_speeds.valve_steps(DEFAULTS)
    v.observe(at, Decimal(0), calc_speeds.VALVE_BACKLOG_LIMIT + 1, steps)
    assert v.step == 1 and "backlog" in v.log[0][2] and v.slowed(Decimal(1), steps) == Decimal(2)


def test_the_valve_steps_are_the_settings_in_force():
    """REQ-166 AC-3 with the steps as settings (REQ-167): a changed step 2 is the slowed speed at step 2."""
    v = calc_speeds.Valve()
    at = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=datetime.UTC)
    steps = calc_speeds.valve_steps({**DEFAULTS, calc_speeds.VALVE_STEP_KEYS[1]: Decimal(4)})
    v.observe(at, Decimal(0), calc_speeds.VALVE_BACKLOG_LIMIT + 1, steps)
    assert steps == (Decimal(1), Decimal(4), Decimal(5)) and v.slowed(Decimal(1), steps) == Decimal(4)


def test_a_missing_speed_setting_fails_closed():
    with pytest.raises(calc_speeds.SpeedSettingRefused):
        calc_speeds.read_speeds({**DEFAULTS, **_all_styles(Decimal(0))})
    with pytest.raises(calc_speeds.SpeedSettingRefused):  # a key the read did not hold: never a guessed speed
        calc_speeds.read_speeds({k: v for k, v in DEFAULTS.items() if k != calc_speeds.KEY_PER_OPTION})


async def test_a_failing_settings_read_keeps_the_last_good_read(scn):
    """REQ-115 AC-9 for the one settings read per cycle: a failed read keeps the last good values (speed 3 s here);
    with no good read yet the cycle checks nothing."""
    values, fail = {**DEFAULTS, **_all_styles(Decimal(3))}, [True]

    def read(_at):
        if fail[0]:
            raise ConnectionError("database blip")
        return values
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls, settings=read)
    await w.cycle()
    assert calls.states == [] and w.errors  # no good read yet: nothing checked on a guessed setting
    fail[0] = False
    await w.cycle()
    assert len(calls.states) == 1
    fail[0] = True
    now[0] += datetime.timedelta(seconds=1)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w.cycle()  # the read fails; the last good 3 s still gates: 1 s after the last check, so no new check
    assert len(calls.states) == 1
    now[0] += datetime.timedelta(seconds=3)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w.cycle()
    assert len(calls.states) == SECOND


# ---- B4 (a): per-cycle cap, the rest roll on ------------------------------------------------------------------
async def test_per_cycle_cap_rolls_later_strategies_to_the_next_cycle(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn, 3), now, calls, max_per_cycle=1)
    for _ in range(3):
        await w.cycle()
    assert [s for s, _ in calls.states] == [100, 101, 102]  # the last strategy is still checked


async def test_one_strategy_failing_does_not_stop_the_others(scn):
    prov, now = Prov(scn), [scn.clock_at]
    seen = []

    async def recorder(wd, _state, _prefs):
        if wd.strategy_id == FIRST_ID:
            raise RuntimeError("boom")
        seen.append(wd.strategy_id)
    w = _worker(prov, _watched(scn, 2), now, recorder)
    await w.cycle()
    assert seen == [FIRST_ID + 1] and w.errors == [(FIRST_ID, "RuntimeError")]


# ---- REQ-166 AC-2 / REQ-165 AC-3: no full table, per-option figures once for every holder --------------------
async def test_1000_strategies_make_no_full_table_call_and_share_each_option_figure(scn, monkeypatch):
    def refused(*_a, **_k):
        raise AssertionError("the full table was called from a background check")
    for module, name in FULL_TABLE:  # the scenario table, its levels, the chain table and the whole outcome
        monkeypatch.setattr(module, name, refused)
    priced = []
    real_price_after = adjustment_check.price_after

    def counted(*a, **k):
        priced.append(1)
        return real_price_after(*a, **k)
    monkeypatch.setattr(adjustment_check, "price_after", counted)  # the strategy's own legs: allowed, counted
    prov, now = Prov(scn), [scn.clock_at]
    one = _worker(prov, _watched(scn), now, Calls())
    await one.cycle()
    many_calls = Calls()
    many = _worker(prov, _watched(scn, MANY), now, many_calls, max_per_cycle=MANY)
    await many.cycle()
    assert len(many_calls.states) == MANY and many.errors == [] and len(priced) == 1 + MANY
    assert many.cache.computations == one.cache.computations > 0  # once per option, not once per strategy
    now[0] += datetime.timedelta(seconds=1)
    iid = prov.leg_id("23500", "CE")
    prov.move_leg(iid, Decimal("80.00"), now[0])  # one option's price changes
    first = one.cache.computations
    await one.cycle()
    per_update = one.cache.computations - first
    before = many.cache.computations
    await many.cycle()
    assert many.errors == [] and many.cache.computations - before == per_update


def test_the_role_names_its_start_module_and_help_starts_nothing(capsys):
    from ofo_app import roles  # noqa: PLC0415
    assert roles.BACKGROUND.start_module == "ofo_app.background"
    with pytest.raises(SystemExit) as stop:
        background.main(["--help"])
    assert stop.value.code == 0 and "background" in capsys.readouterr().out


# ---- CORE (round 2): one state builder for the screen and the background ---------------------------------------
@pytest.fixture
def scenario_on(monkeypatch):
    """The screen's reader and the background read the same scenario switch (prev close, expiry kind)."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")


def _price_time(prov) -> datetime.datetime:
    chain = prov.option_chain_snapshot("NIFTY", datetime.date(2026, 11, 9))
    return max([prov.underlying_quote("NIFTY").timestamp, *(q.timestamp for q in chain)])


async def _screen_state(prov, tracked, at, body, resolved=None) -> pe.StrategyState:
    """The screen's state for the same prices: its own reader (``read_market``), spot answer and ``state_of``, with a
    margin read that failed (the background has none)."""
    ctx = ctx_in_force(MarketContext(prov, lambda: at, RATE), DEFAULTS)  # the same settings read as the worker's
    market = await adjustment_readers.read_market(tracked, ctx)
    spot = resolve_spot(market.feed, None, market.last_close, now=market.now, windows=ctx.feed_windows)
    return adjustment_check.state_of(tracked, market, spot, None, None, adjustment_check.prices_fresh(ctx), body,
                                     config=PREFS.approach, user_values=None, strategy_layer=None,
                                     entry_facts=None, resolved=resolved)


def _background_state(prov, watched, at) -> pe.StrategyState:
    read = background.read_prices(prov, watched, at)
    assert read.state is background.PriceState.FRESH
    return background.background_state(watched, read, FeedScope(background.SharedCompute(), "owner"), at, DEFAULTS,
                                       PREFS, user_values=None)


def test_a_quiet_but_live_spot_is_read_never_withheld(scn):
    """GC-ALERT1 wire-b round 2 RCA (finding staleness-by-last-change-age): the spot's last tick is 9 s old (Kite sends
    only changes; the 3 s feed-age window called it "no spot") while the feed is live. The check reads it: the state
    has the spot and the evaluation is not withheld (a withheld check gives the gate None for every rule, so a record
    whose value cleared the band never lapsed)."""
    prov = Prov(scn)
    at = _price_time(prov) + datetime.timedelta(seconds=9)
    w = dataclasses.replace(_watched(scn)[0], body=_system_body("ic"))
    state = _background_state(prov, w, at)
    assert state.spot == prov.spot.ltp
    assert pe.evaluate(w.body, state, {}, state, gap_until="09:30").withheld is None
    read = background.read_prices(prov, w, at)
    assert background.feed_spot(read, at).at == at  # a FRESH read is current now; its last change is information
    later = at + datetime.timedelta(seconds=1)
    future = dataclasses.replace(read, spot=dataclasses.replace(read.spot, timestamp=later))
    assert background.feed_spot(future, at).at > at  # a future time is kept, so resolve_spot still refuses it
    with pytest.raises(ValueError, match="fresh read"):
        background.feed_spot(background.PriceRead(background.PriceState.STALE), at)


def _system_body(stype: str) -> dict:
    path = pathlib.Path(pe.__file__).with_name("system_playbooks.json")
    return next(pb["body"] for pb in json.loads(path.read_text(encoding="utf-8"))["playbooks"]
                if pb["strategy_type"] == stype)


async def _both(scn, body: dict | None = None) -> tuple[dict, pe.StrategyState, pe.StrategyState]:
    """``body`` None -> the system iron condor; a stop line is read from the body the strategy follows (step 3), so a
    test changing a stop trigger passes its body here."""
    prov = Prov(scn)
    at = _price_time(prov)  # the screen's clock reads the price's own time
    body = _system_body("ic") if body is None else body
    w = dataclasses.replace(_watched(scn)[0], body=body, resolved=_followed(body))
    return body, await _screen_state(prov, w.tracked, at, body, w.resolved), _background_state(prov, w, at)


def _followed(body: dict) -> adjustment_check.Resolved:
    """The strategy follows ``body`` (the route's and the worker's own resolution, step 3: ``resolved`` is required)."""
    return adjustment_check.Resolved("active", body, None, None, False, saved_before_adr247=False)


async def test_core_background_state_equals_the_screens_state_field_by_field(scn, scenario_on):
    _body, screen, bg = await _both(scn)
    assert bg == screen  # the whole dataclass, every field
    for name in ("max_loss", "max_profit", "atm_iv", "expiry_pnl_at_spot", "pnl", "spot"):
        assert getattr(screen, name) is not None, name  # a real figure on both sides, never two Nones agreeing
    assert all(s.abs_delta is not None for s in screen.shorts)
    assert screen.margin is None


MIN_STOP_PCT = "0.01"  # the smallest stop % a line accepts is above 0: any loss of 0.01 % of max loss crosses it


def _with(body: dict, trigger: str, cmp: str) -> dict:
    out = {**body, "triggers": {**body["triggers"]}}
    out["triggers"][trigger] = {**body["triggers"][trigger], "cmp": cmp, "weekly": ["0", "0", "0"],
                                "monthly": ["0", "0", "0"]}
    return out


def _verdict(body: dict, state: pe.StrategyState, trigger: str):
    # no entry state: a true rule fires (not "already true at entry")
    ev = pe.evaluate(body, state, None, None, gap_until=PREFS.gap_until)
    return next((r for r in ev.results if r.trigger_id == trigger), None)  # None: evaluated false (no result)


@pytest.mark.parametrize(("trigger", "field_name"), [("T-06", "max_loss"), ("T-07", "max_profit"),
                                                     ("T-11", "atm_iv")])
async def test_a_trigger_on_a_formerly_dropped_field_fires_in_the_background_as_on_the_screen(
        scn, scenario_on, trigger, field_name):
    if trigger == "T-06":  # a stop line (step 3): read from the followed body's T-06 at the stage, (0, 100] % only
        await _a_max_loss_stop_fires_the_same_on_both_sides(scn)
        return
    base, screen, bg = await _both(scn)
    if trigger == "T-11":  # an entry IV 5 points below today's on both sides
        screen = dataclasses.replace(screen, entry_atm_iv=screen.atm_iv - IV_STEP)
        bg = dataclasses.replace(bg, entry_atm_iv=None if bg.atm_iv is None else bg.atm_iv - IV_STEP)
    fired = [(cmp, _verdict(_with(base, trigger, cmp), screen, trigger)) for cmp in ("ge", "le")]
    cmp, on_screen = next((c, r) for c, r in fired if isinstance(r, pe.Flag))  # it fires on the screen
    assert getattr(screen, field_name) is not None
    assert _verdict(_with(base, trigger, cmp), bg, trigger) == on_screen  # and fires the same in the background


async def _a_max_loss_stop_fires_the_same_on_both_sides(scn) -> None:
    body = _system_body("ic")
    body = {**body, "triggers": {**body["triggers"], "T-06": {**body["triggers"]["T-06"], "on": True,
                                                              "weekly": [MIN_STOP_PCT] * 3,
                                                              "monthly": [MIN_STOP_PCT] * 3}}}
    _base, screen, bg = await _both(scn, body)
    assert screen.max_loss is not None
    on_screen = _verdict(body, screen, "T-06")
    assert isinstance(on_screen, pe.Flag), on_screen  # it fires on the screen
    assert _verdict(body, bg, "T-06") == on_screen  # and fires the same in the background


async def test_margin_and_prev_close_rules_answer_the_same_not_checked_as_the_screen(scn, scenario_on, monkeypatch):
    """T-16 reads the margin, which the background never reads (as a screen whose margin read failed); T-13 reads the
    previous close with the day open, which no reader gives yet. Both answer the same NotChecked on both sides. ADJ-02
    states no previous close, so the running scenario is given one (both readers read the same scenario)."""
    monkeypatch.setitem(scenario_mode.current().data["market"], "prev_close", "23300")
    base, screen, bg = await _both(scn)
    assert bg == screen
    assert screen.prev_close == Decimal("23300")
    for trigger in ("T-16", "T-13"):
        verdict = _verdict(base, bg, trigger)
        assert isinstance(verdict, pe.NotChecked), trigger
        assert verdict == _verdict(base, screen, trigger), trigger


def test_state_of_prices_only_the_strategys_own_legs_and_is_light(scn, scenario_on, monkeypatch):
    """REQ-166 AC-2 measurement: ``state_of`` -> ``price_after`` on ADJ-02 never reaches the full table; 100 calls are
    timed (printed for the report)."""
    def refused(*_a, **_k):
        raise AssertionError("the full table was called")
    for module, name in FULL_TABLE:
        monkeypatch.setattr(module, name, refused)
    prov = Prov(scn)
    at = _price_time(prov)
    w = _watched(scn)[0]
    read = background.read_prices(prov, w, at)
    shared = FeedScope(background.SharedCompute(), "owner")
    priced = []
    real_price_after = adjustment_check.price_after

    def counted(*a, **k):
        priced.append(1)
        return real_price_after(*a, **k)
    monkeypatch.setattr(adjustment_check, "price_after", counted)
    started = time.perf_counter()
    for _ in range(TIMED_CALLS):
        background.background_state(w, read, shared, at, DEFAULTS, PREFS, user_values=None)
    per_call = (time.perf_counter() - started) / TIMED_CALLS
    print(f"STATE-OF-TIMING calls={TIMED_CALLS} each_ms={per_call * 1000:.2f} computations={shared.cache.computations}")
    assert len(priced) == TIMED_CALLS  # one own-legs pricing per check (work counted, never wall time)


# ---- REQ-115 AC-9 / AC-4: no exception outside one check stops the role -------------------------------------------
class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


def _patch_store(monkeypatch, scn, ids) -> None:
    monkeypatch.setattr(db, "get_sessionmaker", lambda: _Session)

    async def list_strategies(_db, _owner):
        return [type("S", (), {"id": i})() for i in ids]

    async def read_tracked(_sid, _x):
        return _tracked(scn)
    monkeypatch.setattr(strategy_store, "list_strategies", list_strategies)
    monkeypatch.setattr(adjustment_readers, "read_tracked", read_tracked)


async def test_a_failing_list_reread_keeps_the_last_good_list_and_still_checks(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    good, reads = _watched(scn, 2), []

    async def lister():
        reads.append(1)
        if len(reads) == SECOND:
            raise ConnectionError("database blip")
        return good
    w = Draining(provider_for=lambda _o: prov, lister=lister, clock=lambda: now[0], settings=_settings(),
                          preferences=_prefs, recorder=calls, observe=calls.seen, gate_store=FakeGate())
    await w.cycle()
    now[0] += datetime.timedelta(seconds=background.REBUILD_SECONDS)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w._rebuild_safely()  # the re-read (its own task in ``run``), and it fails
    await w.cycle()
    assert len(reads) == SECOND and w.monitors == good
    assert [s for s, _ in calls.states] == [100, 101, 100, 101]  # both strategies checked again
    assert w.errors  # counted, not hidden


async def test_owner_lister_skips_the_one_strategy_whose_playbook_lookup_raises(scn, monkeypatch):
    _patch_store(monkeypatch, scn, [FIRST_ID, FIRST_ID + 1])

    async def resolve(_db, _owner, sid, _stype):
        if sid == FIRST_ID:
            raise RuntimeError("playbook lookup failed")
        return type("R", (), {"body": {}, "is_system": True, "strategy_layer": None})()  # Resolved's read fields
    monkeypatch.setattr(adjustment_check, "resolve", resolve)
    out = await background.owner_lister(Prov(scn))
    assert [x.strategy_id for x in out] == [FIRST_ID + 1]


async def test_owner_lister_skips_a_strategy_whose_instrument_list_raises(scn, monkeypatch):
    _patch_store(monkeypatch, scn, [FIRST_ID])
    prov = Prov(scn)

    def refuse():
        raise RuntimeError("no instrument list")
    prov.instrument_master = refuse
    assert await background.owner_lister(prov) == []


async def test_a_failing_speed_read_keeps_the_last_good_speed(scn, monkeypatch):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    three = _settings({**DEFAULTS, **_all_styles(Decimal(3))})
    w = _worker(prov, _watched(scn), now, calls, settings=three)
    await w.cycle()

    def refuse(_values):
        raise ValueError("setting refused")
    monkeypatch.setattr(calc_speeds, "read_speeds", refuse)
    now[0] += datetime.timedelta(seconds=1)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w.cycle()  # no crash; the last good 3 s still gates: 1 s after the last check, so no new check
    assert len(calls.states) == 1
    now[0] += datetime.timedelta(seconds=3)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w.cycle()
    assert len(calls.states) == SECOND


async def test_a_failing_speed_read_with_no_good_speed_skips_the_cycle_and_logs(scn, monkeypatch, caplog):
    def refuse(_values):
        raise ValueError("setting refused")
    monkeypatch.setattr(calc_speeds, "read_speeds", refuse)
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert calls.states == [] and "speed" in caplog.text


async def test_run_keeps_looping_after_a_cycle_raises_once(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()

    async def sleep(seconds):
        now[0] += datetime.timedelta(seconds=seconds)
    w = _worker(prov, _watched(scn), now, calls, sleep=sleep)
    real, runs = w.cycle, []

    async def flaky():
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("cycle blew up")
        await real()
        w.stop()
    w.cycle = flaky
    await w.run()
    assert len(runs) == SECOND and len(calls.states) == 1 and w.errors


async def test_run_does_not_swallow_cancellation(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)

    async def cancelled():
        raise asyncio.CancelledError
    w.cycle = cancelled
    with pytest.raises(asyncio.CancelledError):
        await w.run()


async def test_a_check_that_raises_after_active_leaves_the_strategy_paused_not_active(scn):
    prov, now = Prov(scn), [scn.clock_at]

    async def recorder(_w, _state, _prefs):
        raise RuntimeError("boom")
    w = _worker(prov, _watched(scn), now, recorder)
    await w.cycle()
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
    assert w.errors == [(FIRST_ID, "RuntimeError")]


def test_recent_checks_and_errors_are_bounded():
    kept: list = []
    for i in range(background.RECENT_KEPT + 500):
        background._keep_recent(kept, i)
    assert len(kept) == background.RECENT_KEPT and kept[0] == 500 and kept[-1] == background.RECENT_KEPT + 499  # noqa: PLR2004 - the 500 overflow


# ---- GC-LIVE3 D3/D4: the role's log shows its checks, the speed counters and each recorded opportunity ----------
def _summaries(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("background: minute ")]


async def test_one_summary_line_per_wall_clock_minute_counts_only_real_recomputes(scn, caplog):
    caplog.set_level("INFO", logger="ofo_app.background")
    prov, now, calls = Prov(scn), [scn.clock_at.replace(second=5, microsecond=0)], Calls()
    w = _worker(prov, _watched(scn, 2), now, calls)
    first_minute = now[0].astimezone(background.IST).strftime("%H:%M")
    await w.cycle()  # minute 1, cycle 1: both strategies recomputed
    now[0] += datetime.timedelta(seconds=10)
    await w.cycle()  # same prices: unchanged signature, nothing recomputed, still a cycle
    now[0] += datetime.timedelta(seconds=10)
    prov.move_spot(Decimal("23421"), now[0])
    await w.cycle()  # price moved: both recomputed again
    assert _summaries(caplog) == []  # still inside the first minute
    now[0] += datetime.timedelta(seconds=40)  # minute 2
    prov.move_spot(Decimal("23422"), now[0])
    await w.cycle()
    now[0] += datetime.timedelta(seconds=60)  # minute 3 flushes minute 2
    prov.move_spot(Decimal("23423"), now[0])
    await w.cycle()
    lines = _summaries(caplog)
    assert len(lines) == SECOND
    assert lines[0].startswith(f"background: minute {first_minute} cycles=3 checks=4 ")
    assert "recomputes {100: 2, 101: 2}" in lines[0] and "legs {100: 4, 101: 4}" in lines[0]
    assert ("valve_step=1 speed={'intraday': Decimal('1'), 'weekly': Decimal('1'), 'monthly': Decimal('1')}s "
            in lines[0])  # ADR-235 (1): the per-style speed map in force (this worker's settings: 1 s each)
    assert " cycles=1 checks=2 " in lines[1] and "recomputes {100: 1, 101: 1}" in lines[1]


async def test_a_market_closed_minute_logs_zero_recomputes(scn, caplog):
    caplog.set_level("INFO", logger="ofo_app.background")
    prov, now, calls = Prov(scn), [scn.clock_at.replace(second=5, microsecond=0)], Calls()
    prov.closed = True
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    now[0] += datetime.timedelta(seconds=60)
    await w.cycle()
    [line] = _summaries(caplog)
    assert " cycles=1 checks=0 recomputes {} " in line and calls.states == []


async def test_an_opportunity_record_is_logged_once_with_strategy_rule_and_time(scn, caplog):
    caplog.set_level("INFO", logger="ofo_app.background")
    prov, now = Prov(scn), [scn.clock_at]

    async def recorder(_w, _state, _prefs=None):
        return {"T-01": 7}  # what record_check returns: rule id -> the open record's id
    w = _worker(prov, _watched(scn), now, recorder)
    await w.cycle()
    now[0] += datetime.timedelta(seconds=2)
    prov.move_spot(Decimal("23421"), now[0])
    await w.cycle()  # the same record is still open: not logged again
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("background: opportunity ")]
    assert len(lines) == 1
    assert "strategy=100" in lines[0] and "rule=T-01" in lines[0] and "record=7" in lines[0]
    stamp = scn.clock_at.astimezone(background.IST).isoformat(sep=" ", timespec="seconds")
    assert lines[0].endswith(" written " + stamp)  # a form the log redactor leaves alone (letters + numbers run)


def test_main_configures_info_logging_before_the_loop_starts(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(background.logging, "basicConfig", lambda **kw: order.append(f"basicConfig {kw}"))

    def fake_run(coro):
        coro.close()
        order.append("run")
        return 0
    monkeypatch.setattr(background.asyncio, "run", fake_run)
    assert background.main([]) == 0
    assert order == ["basicConfig {'level': 20}", "run"]


# ---- GC-LIVE3 D3: the role holds the tokens it monitors in its own provider ----------------------------------------
THREE_HELD = 3


class _Redis:
    """The bus client of the worker, recording every key written."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def set(self, key, _value, **_kw):
        self.keys.append(key)


async def _hold_cycle(worker, at) -> None:
    await worker._rebuild_safely()  # the monitored list, as each cycle's rebuild
    await worker._write_wants(at)


def _real_provider():
    import sys  # noqa: PLC0415
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests"))
    from marketdata import _kite_fixture as kf  # noqa: PLC0415
    return kf


def _straddle(*, strikes=("22550",)) -> list[background.Watched]:
    legs = tuple(PositionLeg("SELL", kind, Decimal(k), datetime.date(2026, 10, 13), 1, Decimal("100"), "x")
                 for k in strikes for kind in ("CE", "PE"))
    t = Tracked(Position("NIFTY", 65, "weekly", datetime.date.min, legs), Decimal(0), None, adjustments_used=0)
    return [background.Watched("owner", FIRST_ID, t, NO_RULES, True, "owner", None, None, resolved=None)]


async def test_a_frame_for_a_monitored_leg_reads_available_and_fresh_with_no_screen(scn):
    kf = _real_provider()
    provider, clock, _items = kf.new_provider()
    frames = kf.recorded_frames()
    now = [frames[0][0]]
    redis = _Redis()
    worker = _worker(provider, _straddle(), now, Calls(), want_client=redis)
    await _hold_cycle(worker, now[0])  # the cycle holds the monitored strategy's tokens in the provider
    provider.on_connected(frames[0][0])
    for at, frame in frames:
        clock.now = now[0] = at
        provider.on_frame(frame, at)
    assert provider.status().health is DataHealth.AVAILABLE  # before the fix: STALE (heartbeat only, nothing held)
    read = background.read_prices(provider, _straddle()[0], now[0])
    assert read.state is background.PriceState.FRESH


async def test_without_the_hold_every_frame_is_a_heartbeat_and_the_read_is_stale(scn):
    kf = _real_provider()
    provider, clock, _items = kf.new_provider()
    frames = kf.recorded_frames()
    provider.on_connected(frames[0][0])
    for at, frame in frames:
        clock.now = at
        provider.on_frame(frame, at)
    assert provider.status().health is DataHealth.STALE
    assert background.read_prices(provider, _straddle()[0], frames[-1][0]).state is background.PriceState.STALE


async def test_a_token_no_longer_wanted_is_released(scn):
    kf = _real_provider()
    provider, _clock, _items = kf.new_provider()
    now = [kf.recorded_frames()[0][0]]
    watched = _straddle()
    worker = _worker(provider, watched, now, Calls(), want_client=_Redis())
    await _hold_cycle(worker, now[0])
    assert len(provider.subscribed_tokens()) == THREE_HELD  # the two legs and the index
    watched.clear()  # the strategy is gone
    await _hold_cycle(worker, now[0])
    assert provider.subscribed_tokens() == []


async def test_the_worker_writes_only_the_background_want_key(scn):
    kf = _real_provider()
    provider, _clock, _items = kf.new_provider()
    now = [kf.recorded_frames()[0][0]]
    redis = _Redis()
    worker = _worker(provider, _straddle(), now, Calls(), want_client=redis)
    await _hold_cycle(worker, now[0])
    from ofo_app import feed_bus  # noqa: PLC0415
    assert redis.keys == [feed_bus.background_want_key("owner")]


# ---- GC-LIVE3 D3 round 2 (after the independent review) ------------------------------------------------------------
async def test_each_check_reads_its_own_clock_so_a_tick_during_the_cycle_is_not_in_the_future(scn):
    """Finding 1: one ``now`` per cycle made every tick that arrived during the cycle "in the future" (spot refused,
    every rule withheld_no_spot). A check that takes 5 s while the spot ticks: the second strategy still has a spot."""
    prov, now = Prov(scn), [scn.clock_at]
    seen = []

    def observe(wd, state):  # on the check path (#636 r4: the recorder is off it, on the writer task)
        seen.append((wd.strategy_id, state.spot))
        now[0] += datetime.timedelta(seconds=5)  # this check took 5 s ...
        prov.move_spot(prov.spot.ltp + 1, now[0])  # ... and the spot ticked meanwhile
    w = _worker(prov, _watched(scn, 2), now, Calls(), observe=observe)
    await w.cycle()
    assert [s for s, _ in seen] == [FIRST_ID, FIRST_ID + 1]
    assert seen[1][1] == Decimal("23421")  # before: None (tick_in_future -> withheld_no_spot)


async def test_a_cycle_makes_no_lister_or_preferences_call(scn):
    """Finding 3: the strategy list and each user's preferences are read by the rebuild (its own task), never by a
    cycle; preferences once per rebuild per user."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    lists, prefs = [], []

    async def lister():
        lists.append(1)
        return _watched(scn, 3)

    async def preferences(user_ref):
        prefs.append(user_ref)
        return PREFS
    w = Draining(provider_for=lambda _o: prov, lister=lister, clock=lambda: now[0], settings=_settings(),
                          preferences=preferences, recorder=calls, observe=calls.seen, gate_store=FakeGate())
    await w._rebuild_safely()
    assert (len(lists), prefs) == (1, ["owner"])  # three strategies, one user: one preferences read
    for _ in range(3):
        now[0] += datetime.timedelta(seconds=1)
        prov.move_spot(prov.spot.ltp + 1, now[0])
        await w.cycle()
    assert (len(lists), prefs) == (1, ["owner"]) and len(calls.states) == 3 * 3  # 3 cycles x 3


async def test_a_user_with_no_preferences_read_is_paused_not_checked_on_a_guess(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()

    async def refuse(_user_ref):
        raise ConnectionError("database blip")
    w = _worker(prov, _watched(scn), now, calls)
    w._preferences = refuse
    await w.cycle()
    assert calls.states == [] and w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED


def _two_strategies(scn) -> tuple[list[background.Watched], tuple[str, str]]:
    """Strategy 100 holds every ADJ-02 leg; 101 all but the last. Returns them and the last leg's strike and type."""
    full = _tracked(scn)
    part = dataclasses.replace(full, position=dataclasses.replace(full.position, legs=full.position.legs[:-1]))
    last = full.position.legs[-1]
    watched = [background.Watched("owner", FIRST_ID, full, NO_RULES, True, "owner", None, None, resolved=None),
               background.Watched("owner", FIRST_ID + 1, part, NO_RULES, True, "owner", None, None, resolved=None)]
    return watched, (str(last.strike), last.type)


async def test_only_a_strategy_whose_tokens_ticked_is_read_and_checked(scn, monkeypatch):
    """Item c, every answer state of the tick test: no previous price -> read; not ticked -> not read; ticked -> read;
    a quote whose health changed with no tick -> read (and paused)."""
    reads = []
    real = background.read_prices

    def counted(provider, watched, *a, **k):
        reads.append(watched.strategy_id)
        return real(provider, watched, *a, **k)
    monkeypatch.setattr(background, "read_prices", counted)
    prov, now, calls = Prov(scn), [scn.clock_at.replace(second=5, microsecond=0)], Calls()
    watched, (strike, kind) = _two_strategies(scn)
    w = _worker(prov, watched, now, calls)
    await w.cycle()
    assert reads == [FIRST_ID, FIRST_ID + 1]  # no previous price: both read
    now[0] += datetime.timedelta(seconds=2)
    await w.cycle()
    assert reads == [FIRST_ID, FIRST_ID + 1]  # nothing ticked: nothing read
    prov.move_leg(prov.leg_id(strike, kind), Decimal("80.00"), now[0])  # only strategy 100 holds this leg
    now[0] += datetime.timedelta(seconds=2)
    await w.cycle()
    assert reads[2:] == [FIRST_ID] and [s for s, _ in calls.states] == [FIRST_ID, FIRST_ID + 1, FIRST_ID]
    other = watched[1].tracked.position.legs[0]
    oid = prov.leg_id(str(other.strike), other.type)
    q = next(q for q in prov.option_chain_snapshot("NIFTY", other.expiry) if q.instrument_id == oid)
    prov.moved[oid] = dataclasses.replace(q, health=DataHealth.STALE)  # no new tick, the quote went stale
    now[0] += datetime.timedelta(seconds=2)
    await w.cycle()
    assert w.paused_reason[FIRST_ID + 1] is background.PriceState.STALE


async def test_an_unchanged_clear_check_makes_no_recorder_call(scn):
    """Item d: the first check writes (the stored memory is not known yet); a later check whose evaluation flags
    nothing and leaves memory, flagged and clear rules as they were writes nothing."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    now[0] += datetime.timedelta(seconds=2)
    prov.move_spot(Decimal("23421"), now[0])
    await w.cycle()
    assert len(calls.states) == SECOND and len(calls.writes) == 1


def _flag(*rule_ids: str) -> pe.Evaluation:
    flags = tuple(pe.Flag(r, "T-01", None, Decimal(1), Decimal(1), "ge") for r in rule_ids)
    return pe.Evaluation(None, None, flags, {})


async def _checks(w, prov, now, n: int) -> None:
    for i in range(n):
        if i:
            now[0] += datetime.timedelta(seconds=2)
            prov.move_spot(Decimal(23421 + i), now[0])
        await w.cycle()


async def test_the_same_flag_on_three_checks_makes_one_recorder_call(scn, monkeypatch):
    """Round 3 (D3 speed): a flag already flagged and stored is not written again."""
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: _flag("R-1"))
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await _checks(w, prov, now, 3)
    assert len(calls.states) == len(calls.writes) + 2 and len(calls.writes) == 1


async def test_flag_then_clear_writes_twice(scn, monkeypatch):
    seq = iter([_flag("R-1"), _flag("R-1"), pe.Evaluation(None, None, (), {}, clear=("R-1",))])
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: next(seq))
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await _checks(w, prov, now, 3)
    assert len(calls.writes) == SECOND  # the first check, then the clear closing the record


async def test_a_new_second_flag_beside_an_open_one_writes(scn, monkeypatch):
    seq = iter([_flag("R-1"), _flag("R-1"), _flag("R-1", "R-2"), _flag("R-1", "R-2")])
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: next(seq))
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await _checks(w, prov, now, 4)
    assert len(calls.writes) == SECOND  # the first check, then R-2 appearing


async def test_the_first_check_after_process_start_writes_even_if_a_flag_is_open(scn, monkeypatch):
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: _flag("R-1"))
    for _ in range(2):  # a new Worker is a new process: nothing known about the stored state
        prov, now, calls = Prov(scn), [scn.clock_at], Calls()
        w = _worker(prov, _watched(scn), now, calls)
        await _checks(w, prov, now, 2)
        assert len(calls.writes) == 1


async def test_a_recorder_that_raised_is_retried_on_the_next_check_with_the_same_flag(scn, monkeypatch):
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: _flag("R-1"))
    prov, now, calls, boom = Prov(scn), [scn.clock_at], Calls(), [True]

    async def recorder(wd, state, prefs=None):
        if boom[0]:
            boom[0] = False
            raise RuntimeError("db down")
        await calls(wd, state, prefs)
    w = _worker(prov, _watched(scn), now, recorder)
    await _checks(w, prov, now, 3)
    assert len(calls.writes) == 1  # check 1 raised (fail closed), check 2 wrote, check 3 unchanged


async def test_the_minute_line_counts_withheld_and_not_checked_reasons(scn, monkeypatch, caplog):
    """Item g (the detection upgrade): a minute where every rule is withheld for no spot says so in the line."""
    caplog.set_level("INFO", logger="ofo_app.background")
    ev = pe.Evaluation(None, None, (pe.NotChecked("R-1", "T-01", "adjust_trigger_withheld_no_spot"),), {},
                       withheld="adjust_trigger_withheld_no_spot")
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: ev)
    prov, now, calls = Prov(scn), [scn.clock_at.replace(second=5, microsecond=0)], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    now[0] += datetime.timedelta(seconds=60)
    await w.cycle()
    [line] = _summaries(caplog)
    assert "outcomes {'not_checked adjust_trigger_withheld_no_spot': 1, " \
           "'withheld adjust_trigger_withheld_no_spot': 1}" in line, line


async def test_the_background_holds_the_screens_atm_window_of_the_first_expiry(scn):
    """Item e (finding 2): beside the legs and the index, the role holds the calls and puts of the screen's strike
    window (``chain_push.strike_window`` around ``atm_strike`` of the live spot, ``limits.chain_strikes_each_side``
    each side), so the forward and the ATM IV read the same book as the screen."""
    from ofo.settings import calc as settings_calc  # noqa: PLC0415
    from ofo_app import chain_push  # noqa: PLC0415
    kf = _real_provider()
    provider, clock, _items = kf.new_provider()
    frames = kf.recorded_frames()
    now = [frames[0][0]]
    worker = _worker(provider, _straddle(), now, Calls(), want_client=_Redis())
    worker._settings_safely(now[0])
    await _hold_cycle(worker, now[0])
    provider.on_connected(frames[0][0])
    for at, frame in frames:
        clock.now = now[0] = at
        provider.on_frame(frame, at)
    await _hold_cycle(worker, now[0])  # the live spot is known now: the window is held
    options, _by_id = worker._tokens_of(provider)
    expiry = datetime.date(2026, 10, 13)
    grid = sorted({k[2] for k in options if k[0] == "NIFTY" and k[1] == expiry and k[2] is not None})
    each = settings_calc.chain_strikes_each_side(DEFAULTS)
    window = chain_push.strike_window(grid, chain_push.atm_strike(grid, provider.underlying_quote("NIFTY").ltp),
                                      each, each)
    want = {options[("NIFTY", expiry, k, side)] for k in window for side in ("CE", "PE")}
    assert len(window) > 1 and want <= set(provider.subscribed_tokens())


async def test_a_recorded_write_is_logged_and_its_stored_memory_is_the_next_checks_memory(scn, caplog):
    """``record_check`` returns ``Recorded``: its open records are logged, and the memory it STORED (which can differ
    from this process's guess, e.g. after a restart) is what the next check evaluates against: evaluated with it, an
    unchanged clear check writes nothing (evaluated with ``{}`` instead, the memory would differ and it would write)."""
    caplog.set_level("INFO", logger="ofo_app.background")
    stored = pe.Evaluation(None, None, (), {"R-1": {"held_at_entry": True, "seen_clear": False}})
    prov, now, seen = Prov(scn), [scn.clock_at], []

    async def recorder(_w, _state, _prefs=None):
        seen.append(1)
        return background.Recorded({"T-01": 7}, stored)
    w = _worker(prov, _watched(scn), now, recorder)
    await w.cycle()
    assert w._memory[FIRST_ID] == stored.memory
    assert any("record=7" in r.getMessage() for r in caplog.records)
    now[0] += datetime.timedelta(seconds=2)
    prov.move_spot(Decimal("23421"), now[0])
    await w.cycle()
    assert len(seen) == 1 and len(w.checks) == SECOND


# ---- ADR-233: 30 s default per strategy, the worker still wakes about once a second -----------------------------
BACKGROUND_DEFAULT = Decimal(30)
WAKE_SECONDS = 1.0


def test_the_registry_default_of_the_background_check_is_30_seconds():
    assert DEFAULTS[calc_speeds.BACKGROUND_KEYS["weekly"]] == BACKGROUND_DEFAULT


async def test_run_wakes_every_second_when_the_setting_is_30(scn):
    prov, now, calls, slept = Prov(scn), [scn.clock_at], Calls(), []
    values = {**DEFAULTS, **_all_styles(BACKGROUND_DEFAULT)}

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += datetime.timedelta(seconds=seconds)
        if len(slept) == THREE_HELD:
            w.stop()
    w = _worker(prov, _watched(scn), now, calls, settings=_settings(values), sleep=sleep)
    await w.run()
    assert slept == [WAKE_SECONDS] * THREE_HELD


async def test_a_strategy_is_rechecked_only_after_30_seconds_and_only_when_a_price_changed(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    values = {**DEFAULTS, **_all_styles(BACKGROUND_DEFAULT)}
    w = _worker(prov, _watched(scn), now, calls, settings=_settings(values))
    await w.cycle()  # checked at t
    start = now[0]
    for _ in range(int(BACKGROUND_DEFAULT) - 1):  # t+1 .. t+29: prices change every second, no recheck
        now[0] += datetime.timedelta(seconds=1)
        prov.move_spot(prov.spot.ltp + 1, now[0])
        await w.cycle()
    assert len(w.checks) == 1
    now[0] = start + datetime.timedelta(seconds=int(BACKGROUND_DEFAULT) + 1)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w.cycle()  # past t+30 and the price changed since the check: rechecked
    assert len(w.checks) == SECOND
