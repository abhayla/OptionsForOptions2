"""GC-MU step 4 (REQ-165 AC-2/AC-3, REQ-166 AC-1..AC-3, REQ-115 AC-4/AC-9): the background cycle without a database.
The provider is scenario ADJ-02's fed ``KiteProvider`` (the real frame parser) behind a thin wrapper that can set the
feed health, close the market, drop a leg or move a price; the recorder seam is a fake, so no check touches the store.
Clocks are injected; nothing sleeps for real.
"""
from __future__ import annotations

import dataclasses
import datetime
import itertools
import json
import pathlib
import time
from decimal import Decimal

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.marketdata.shared_compute import FeedScope
from ofo.marketdata.spot_source import resolve_spot
from ofo.outcome import service as outcome_service
from ofo.rules.inputs import DataHealth
from ofo.scenario import levels as scenario_levels
from ofo.scenario import views as scenario_views
from ofo.table import model as table_model
from ofo_app import adjustment_check, adjustment_readers, background, calc_speeds, scenario_mode
from ofo_app.routes.adjustment import Tracked
from ofo_app.routes.outcome import MarketContext

RATE = Decimal("0.065")
FIRST_ID = 100  # the first watched strategy id
MANY = 1000
CHECKS_AFTER_CHANGE = 3
STOP_AFTER = 5
CYCLES = 10
SLOW_CYCLES = 2
TIMED_CALLS = 100
IV_STEP = Decimal("0.05")  # 5 IV points as a fraction
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

    def move_spot(self, ltp: Decimal, at: datetime.datetime) -> None:
        self.spot = dataclasses.replace(self.spot, ltp=ltp, timestamp=at)

    def leg_id(self, strike: str, kind: str) -> str:
        return next(q.instrument_id for q in self.real.option_chain_snapshot("NIFTY", datetime.date(2026, 11, 9))
                    if q.strike == Decimal(strike) and q.instrument_type.value == kind)

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
    return [background.Watched("owner", FIRST_ID + i, t, {}, True, "owner", "weekly") for i in range(n)]


class Calls:
    def __init__(self, clock=None, slow: datetime.timedelta | None = None) -> None:
        self.states: list[tuple[int, object]] = []
        self._clock, self.slow = clock, slow

    async def __call__(self, w, state):
        self.states.append((w.strategy_id, state))
        if self.slow is not None:
            self._clock[0] += self.slow  # an injected slow maths step


def _worker(prov, watched, now, recorder, **kw) -> background.Worker:
    async def lister():
        return watched
    return background.Worker(provider_for=lambda _o: prov, lister=lister, clock=lambda: now[0], rate=RATE,
                             recorder=recorder, **kw)


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
    monkeypatch.setitem(calc_speeds._STAND_IN, calc_speeds.KEY_BACKGROUND, Decimal(1))
    prov, now = Prov(scn), [scn.clock_at]
    calls = Calls()
    w = None

    async def recorder(wd, state):
        await calls(wd, state)
        if len(calls.states) == CHECKS_AFTER_CHANGE:
            calc_speeds._STAND_IN[calc_speeds.KEY_BACKGROUND] = Decimal(3)  # the admin changes the setting
        if len(calls.states) == STOP_AFTER:
            w.stop()

    async def sleep(seconds):
        now[0] += datetime.timedelta(seconds=seconds)
        prov.move_spot(prov.spot.ltp + 1, now[0])  # a price changes every tick

    w = _worker(prov, _watched(scn), now, recorder, sleep=sleep)
    await w.run()
    times = [t for _, t in w.checks]
    assert [int((b - a).total_seconds()) for a, b in itertools.pairwise(times)] == [1, 1, 3, 3]


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
        seen.append(w.background_seconds())
    assert seen[:2] == [Decimal(2), Decimal(5)] and seen[-1] == Decimal(1)
    assert [step for _, step, _ in w.valve.log] == [1, 2, 0]
    assert all("maths reply" in r for _, _, r in w.valve.log[:2]) and "under its limits" in w.valve.log[2][2]
    assert len(calls.states) == CYCLES


def test_valve_steps_on_backlog_too():
    v = calc_speeds.Valve()
    at = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=datetime.UTC)
    v.observe(at, Decimal(0), calc_speeds.VALVE_BACKLOG_LIMIT + 1)
    assert v.step == 1 and "backlog" in v.log[0][2] and v.slowed(Decimal(1)) == Decimal(2)


def test_a_missing_speed_setting_fails_closed(monkeypatch):
    monkeypatch.setitem(calc_speeds._STAND_IN, calc_speeds.KEY_BACKGROUND, Decimal(0))
    with pytest.raises(calc_speeds.SpeedSettingRefused):
        calc_speeds.read_speeds()


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

    async def recorder(wd, _state):
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


async def _screen_state(prov, tracked, at, body) -> pe.StrategyState:
    """The screen's state for the same prices: its own reader (``read_market``), spot answer and ``state_of``, with a
    margin read that failed (the background has none)."""
    ctx = MarketContext(prov, lambda: at, RATE)
    market = await adjustment_readers.read_market(tracked, ctx)
    spot = resolve_spot(market.feed, None, market.last_close, now=market.now)
    return adjustment_check.state_of(tracked, market, spot, None, None, adjustment_check.prices_fresh(ctx), body)


def _background_state(prov, watched, at) -> pe.StrategyState:
    read = background.read_prices(prov, watched, at)
    assert read.state is background.PriceState.FRESH
    return background.background_state(watched, read, FeedScope(background.SharedCompute(), "owner"), at, RATE)


def _system_body(stype: str) -> dict:
    path = pathlib.Path(pe.__file__).with_name("system_playbooks.json")
    return next(pb["body"] for pb in json.loads(path.read_text(encoding="utf-8"))["playbooks"]
                if pb["strategy_type"] == stype)


async def _both(scn) -> tuple[dict, pe.StrategyState, pe.StrategyState]:
    prov = Prov(scn)
    at = _price_time(prov)  # the screen's clock reads the price's own time
    body = _system_body("ic")
    w = dataclasses.replace(_watched(scn)[0], body=body, expiry_kind=None)
    return body, await _screen_state(prov, w.tracked, at, body), _background_state(prov, w, at)


async def test_core_background_state_equals_the_screens_state_field_by_field(scn, scenario_on):
    _body, screen, bg = await _both(scn)
    assert bg == screen  # the whole dataclass, every field
    for name in ("max_loss", "max_profit", "atm_iv", "expiry_pnl_at_spot", "pnl", "spot"):
        assert getattr(screen, name) is not None, name  # a real figure on both sides, never two Nones agreeing
    assert all(s.abs_delta is not None for s in screen.shorts)
    assert screen.margin is None


def _with(body: dict, trigger: str, cmp: str) -> dict:
    out = {**body, "triggers": {**body["triggers"]}}
    out["triggers"][trigger] = {**body["triggers"][trigger], "cmp": cmp, "weekly": ["0", "0", "0"],
                                "monthly": ["0", "0", "0"]}
    return out


def _verdict(body: dict, state: pe.StrategyState, trigger: str):
    ev = pe.evaluate(body, state, None, None)  # no entry state: a true rule fires (not "already true at entry")
    return next((r for r in ev.results if r.trigger_id == trigger), None)  # None: evaluated false (no result)


@pytest.mark.parametrize(("trigger", "field_name"), [("T-06", "max_loss"), ("T-07", "max_profit"),
                                                     ("T-11", "atm_iv")])
async def test_a_trigger_on_a_formerly_dropped_field_fires_in_the_background_as_on_the_screen(
        scn, scenario_on, trigger, field_name):
    base, screen, bg = await _both(scn)
    if trigger == "T-11":  # an entry IV 5 points below today's on both sides
        screen = dataclasses.replace(screen, entry_atm_iv=screen.atm_iv - IV_STEP)
        bg = dataclasses.replace(bg, entry_atm_iv=None if bg.atm_iv is None else bg.atm_iv - IV_STEP)
    fired = [(cmp, _verdict(_with(base, trigger, cmp), screen, trigger)) for cmp in ("ge", "le")]
    cmp, on_screen = next((c, r) for c, r in fired if isinstance(r, pe.Flag))  # it fires on the screen
    assert getattr(screen, field_name) is not None
    assert _verdict(_with(base, trigger, cmp), bg, trigger) == on_screen  # and fires the same in the background


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
    started = time.perf_counter()
    for _ in range(TIMED_CALLS):
        background.background_state(w, read, shared, at, RATE)
    each = (time.perf_counter() - started) / TIMED_CALLS
    print(f"STATE-OF-TIMING calls={TIMED_CALLS} each_ms={each * 1000:.2f}")
    assert each < 1  # seconds
