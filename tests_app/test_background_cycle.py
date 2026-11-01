"""GC-MU step 4 (REQ-165 AC-2/AC-3, REQ-166 AC-1..AC-3, REQ-115 AC-4/AC-9): the background cycle without a database.
The provider is scenario ADJ-02's fed ``KiteProvider`` (the real frame parser) behind a thin wrapper that can set the
feed health, close the market, drop a leg or move a price; the recorder seam is a fake, so no check touches the store.
Clocks are injected; nothing sleeps for real.
"""
from __future__ import annotations

import dataclasses
import datetime
import itertools
from decimal import Decimal

import pytest
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.rules.inputs import DataHealth
from ofo_app import adjustment_check, background, calc_speeds, scenario_mode
from ofo_app.routes import adjustment as adjustment_route
from ofo_app.routes.adjustment import Tracked

RATE = Decimal("0.065")
FIRST_ID = 100  # the first watched strategy id
MANY = 1000
CHECKS_AFTER_CHANGE = 3
STOP_AFTER = 5
CYCLES = 10
SLOW_CYCLES = 2


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
async def test_fresh_price_runs_one_check_on_light_sums(scn):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls)
    await w.cycle()
    assert [s for s, _ in calls.states] == [100] and w.status[100] is background.MonitoringStatus.ACTIVE
    state = calls.states[0][1]
    assert state.spot == Decimal("23420") and state.max_loss is None and state.margin is None
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
    monkeypatch.setattr(adjustment_route, "price_after", refused)
    monkeypatch.setattr(adjustment_check, "price_after", refused)
    monkeypatch.setattr(adjustment_check, "state_of", refused)
    prov, now = Prov(scn), [scn.clock_at]
    one = _worker(prov, _watched(scn), now, Calls())
    await one.cycle()
    many_calls = Calls()
    many = _worker(prov, _watched(scn, MANY), now, many_calls, max_per_cycle=MANY)
    await many.cycle()
    assert len(many_calls.states) == MANY and many.errors == []
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
