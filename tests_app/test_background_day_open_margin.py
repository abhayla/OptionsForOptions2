"""GC-IC1 step 5b (#627 items 1 and 2, REQ-165 AC-5): T-13 (gap at the open) and T-16 (loss vs margin) answer the same
on the screen and in the background worker. Pure: the scenario provider and fakes, no database."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.broker.rate_limit import KiteBusy
from ofo.marketdata import day_open as dopen
from ofo.marketdata.provider import DayStats, DayStatsAnswer
from ofo.marketdata.spot_source import resolve_spot
from ofo.outcome.service import MARGIN_CHECKED, Margin
from ofo.timeutil import IST
from ofo_app import adjustment_check, adjustment_readers, background, scenario_mode
from ofo_app.routes.adjustment_check import current_margin
from ofo_app.routes.outcome import MarketContext, ctx_in_force
from test_background_cycle import (
    CYCLES,
    DEFAULTS,
    FIRST_ID,
    PREFS,
    RATE,
    Calls,
    Prov,
    _background_state,
    _followed,
    _system_body,
    _verdict,
    _watched,
    _worker,
)

GAP_SCENARIO = "ADJ-04"  # 2026-10-29 09:16 IST, open 23340 over previous close 23060: a 1.21% gap up
GAP_PCT = (Decimal("23340") - Decimal("23060")) * 100 / Decimal("23060")
MARGIN_X = Decimal("118250.40")
EXPIRY = datetime.date(2026, 11, 3)
EVERY_6S = 6


@pytest.fixture
def gap(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", GAP_SCENARIO)
    return scenario_mode.load(GAP_SCENARIO)


def _gap_time(prov) -> datetime.datetime:
    chain = prov.option_chain_snapshot("NIFTY", EXPIRY)
    return max([prov.underlying_quote("NIFTY").timestamp, *(q.timestamp for q in chain)])


async def _screen_with(prov, tracked, at, body, margin_of=None) -> pe.StrategyState:
    """The screen route's own steps: ``read_market``, ``current_margin`` (the route's margin read), ``state_of``."""
    ctx = ctx_in_force(MarketContext(prov, lambda: at, RATE), DEFAULTS)
    market = await adjustment_readers.read_market(tracked, ctx)
    margin = None if margin_of is None else await current_margin(margin_of, tracked, market)
    spot = resolve_spot(market.feed, None, market.last_close, now=market.now, windows=ctx.feed_windows)
    return adjustment_check.state_of(tracked, market, spot, margin, None, adjustment_check.prices_fresh(ctx), body,
                                     config=PREFS.approach, user_values=None, strategy_layer=None,
                                     entry_facts=None, resolved=_followed(body))


def _ic_watched(scn) -> background.Watched:
    body = _system_body("ic")
    return dataclasses.replace(_watched(scn)[0], body=body, resolved=_followed(body))


# ---- T-13 ---------------------------------------------------------------------------------------------------------
async def test_core_t13_gap_at_the_open_fires_the_same_on_the_screen_and_the_worker(gap):
    """CORE: the scenario's index packet (open 23340, previous close 23060) through the real decoder and
    ``QuoteBook.latest_day_stats``; both paths read day_open 23340 and T-13 fires with the same 1.21% value."""
    prov = Prov(gap)
    at = _gap_time(prov)
    assert at.astimezone(IST).strftime("%H:%M") == "09:15"  # before gap_until (09:30)
    w = _ic_watched(gap)
    screen = await _screen_with(prov, w.tracked, at, w.body)
    bg = _background_state(prov, w, at)
    assert (screen.day_open, screen.prev_close) == (Decimal("23340"), Decimal("23060"))
    assert bg == screen
    on_screen, in_bg = _verdict(w.body, screen, "T-13"), _verdict(w.body, bg, "T-13")
    assert isinstance(on_screen, pe.Flag)
    assert on_screen == in_bg
    assert on_screen.value.quantize(Decimal("0.0001")) == GAP_PCT.quantize(Decimal("0.0001")) == Decimal("1.2142")


def _stats(open_: str | None, at: datetime.datetime | None) -> DayStatsAnswer:
    return DayStatsAnswer(DayStats(None if open_ is None else Decimal(open_), None, None, Decimal("23060"),
                                   None if at is None else int(at.timestamp())))


@pytest.mark.parametrize("state", ["previous_session", "undated", "no_open", "NOT_HELD", "FEED_NOT_HEALTHY",
                                   "PACKET_WITHOUT_DAY_FIELDS"])
async def test_a_day_open_not_dated_today_or_not_stated_is_never_used_on_either_path(gap, state):
    """Attack 1: yesterday's day values (the packet Kite sends on subscribe before today's first tick) are refused;
    every other answer state of the day values -> no day open; T-13 not checked (missing_day_open) on both paths."""
    prov = Prov(gap)
    at = _gap_time(prov)
    prov.day = {"previous_session": _stats("23340", at - datetime.timedelta(days=1)),
                "undated": _stats("23340", None), "no_open": _stats(None, at)}.get(state) \
        or DayStatsAnswer.unavailable(state)
    w = _ic_watched(gap)
    screen = await _screen_with(prov, w.tracked, at, w.body)
    bg = _background_state(prov, w, at)
    assert screen.day_open is None
    assert bg == screen
    verdict = _verdict(w.body, bg, "T-13")
    assert isinstance(verdict, pe.NotChecked)
    assert verdict.code.endswith("missing_day_open")
    assert verdict == _verdict(w.body, screen, "T-13")


@pytest.mark.parametrize(("answer", "expected"), [
    (None, dopen.DayOpen(None, dopen.NOT_READ)),
    (DayStatsAnswer.unavailable("NOT_HELD"), dopen.DayOpen(None, "NOT_HELD")),
    (_stats("23340", datetime.datetime(2026, 10, 28, 15, 29, 59, tzinfo=IST)),
     dopen.DayOpen(None, dopen.PREVIOUS_SESSION)),
    (_stats("23340", None), dopen.DayOpen(None, dopen.UNDATED)),
    (_stats(None, datetime.datetime(2026, 10, 29, 9, 15, tzinfo=IST)), dopen.DayOpen(None, dopen.NO_OPEN)),
    (_stats("23340", datetime.datetime(2026, 10, 29, 9, 15, tzinfo=IST)),
     dopen.DayOpen(Decimal("23340"), dopen.STATED)),
])
def test_index_day_open_names_every_answer_state(answer, expected):
    assert dopen.index_day_open(answer, datetime.datetime(2026, 10, 29, 9, 16, tzinfo=IST)) == expected


# ---- T-16 ---------------------------------------------------------------------------------------------------------
class FakeMargin:
    """The route's ``ApproachMargin`` seam (``get_approach_margin``): legs -> Zerodha's margin; ``fail`` raises."""

    def __init__(self, at: datetime.datetime, fail: Exception | None = None) -> None:
        self.at, self.fail, self.calls = at, fail, 0

    async def __call__(self, _legs):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return Margin(MARGIN_CHECKED, "", needed=MARGIN_X, broker_needed=MARGIN_X, checked_at=self.at)


async def _worker_after_refresh(prov, w, at, fake):
    """Check 1 (no margin yet: not refreshed), one refresh pass, then check 2 one second later on a moved spot."""
    now, calls = [at], Calls()
    worker = _worker(prov, [w], now, calls, margin_of=background.screen_margin_reader(fake))
    await worker.cycle()
    assert calls.states[0][1].margin is None  # not refreshed yet -> missing_margin
    await worker.refresh_margins()
    now[0] = at + datetime.timedelta(seconds=1)
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await worker.cycle()
    return worker, calls.states[-1][1], now[0]


async def test_core_t16_stated_margin_answers_the_same_on_the_screen_and_the_worker(gap):
    prov = Prov(gap)
    at = _gap_time(prov)
    w = _ic_watched(gap)
    fake = FakeMargin(at)
    worker, bg, at2 = await _worker_after_refresh(prov, w, at, fake)
    screen = await _screen_with(prov, w.tracked, at2, w.body, fake)
    assert bg.margin == screen.margin == MARGIN_X
    assert bg == screen
    on_screen, in_bg = _verdict(w.body, screen, "T-16"), _verdict(w.body, bg, "T-16")
    assert not isinstance(on_screen, pe.NotChecked)
    assert on_screen == in_bg
    assert worker.margins.calls == {w.strategy_id: 1}


@pytest.mark.parametrize("fail", ["failed", "busy"])
async def test_a_failed_or_busy_margin_read_is_not_known_on_both_paths_never_zero(gap, fail):
    """Attack 3: KiteBusy (the rate limiter refused) or any failure -> margin not known; T-16 missing_margin."""
    prov = Prov(gap)
    at = _gap_time(prov)
    w = _ic_watched(gap)
    fake = FakeMargin(at, KiteBusy("queue full") if fail == "busy" else RuntimeError("margin endpoint down"))
    _, bg, at2 = await _worker_after_refresh(prov, w, at, fake)
    screen = await _screen_with(prov, w.tracked, at2, w.body, fake)
    assert bg.margin is None
    assert screen.margin is None
    verdict = _verdict(w.body, bg, "T-16")
    assert isinstance(verdict, pe.NotChecked)
    assert verdict.code.endswith("missing_margin")
    assert verdict == _verdict(w.body, screen, "T-16")


def _t16_off(body: dict) -> dict:
    return {**body, "triggers": {**body["triggers"], "T-16": {**body["triggers"]["T-16"], "on": False}}}


@pytest.mark.parametrize(("body", "needed"), [
    ({"triggers": {"T-16": {"on": True}}}, True),
    ({"triggers": {"T-16": {"on": False}}, "day_rules": [{"on": True, "when": "beforeWeekend", "action": 0}]}, True),
    ({"day_rules": [{"on": True, "when": "beforeHoliday", "action": 0}]}, True),
    ({"day_rules": [{"on": False, "when": "beforeWeekend", "action": 0}]}, False),
    ({"day_rules": [{"on": True, "when": "expiry", "action": 5}]}, False),
    ({"day_rules": [{"on": True, "when": "beforeWeekend", "action": 4}]}, False),
    ({"day_rules": "x"}, False),
    ({}, False),
    ({"triggers": {"T-16": {"on": False}, "T-14": {"on": True}}}, True),  # B2: T-14 is a % of the margin
    ({"triggers": {"T-16": {"on": False}, "T-14": {"on": False}}}, False),
    (None, False),
])
def test_margin_is_needed_when_t16_or_a_carry_day_rule_is_on(body, needed):
    assert background.margin_needed(body) is needed


async def test_a_carry_rule_alone_makes_the_worker_read_the_margin_the_screen_reads(gap):
    """GC-IC1 review A2: T-16 OFF, the Friday carry rule ON -> the worker still reads the margin, so its carry record
    holds the same stated margin as the screen (before: None, margin_reason missing)."""
    prov = Prov(gap)
    at = _gap_time(prov)
    off_body = _t16_off(_system_body("ic"))
    w = dataclasses.replace(_ic_watched(gap), body=off_body, resolved=_followed(off_body))
    assert any(r["when"] == "beforeWeekend" and r["on"] for r in w.body["day_rules"])
    fake = FakeMargin(at)
    worker, bg, at2 = await _worker_after_refresh(prov, w, at, fake)
    screen = await _screen_with(prov, w.tracked, at2, w.body, fake)
    assert bg.margin == screen.margin == MARGIN_X
    assert worker.margins.calls == {w.strategy_id: 1}


async def test_ten_cycles_in_a_minute_make_at_most_one_margin_call_per_strategy(gap):
    """Attack 2: a check every 6 s for a minute with a refresh pass after each -> ONE margin read per strategy; the
    next read only after ``MARGIN_REFRESH_S``; a playbook with T-16 off is never read."""
    prov = Prov(gap)
    at = _gap_time(prov)
    on = _ic_watched(gap)
    t16_off = _t16_off(on.body)  # B2: T-14 on also needs the margin (a % of it), so it is switched off here too
    off_body = {**t16_off, "day_rules": [],
                "triggers": {**t16_off["triggers"], "T-14": {**t16_off["triggers"]["T-14"], "on": False}}}
    off = dataclasses.replace(on, strategy_id=FIRST_ID + 1, body=off_body, resolved=_followed(off_body))
    fake, now, calls = FakeMargin(at), [at], Calls()
    worker = _worker(prov, [on, off], now, calls, margin_of=background.screen_margin_reader(fake))
    for i in range(CYCLES):
        now[0] = at + datetime.timedelta(seconds=EVERY_6S * i)
        prov.move_spot(prov.spot.ltp + 1, now[0])
        await worker.cycle()
        await worker.refresh_margins()
    assert fake.calls == 1
    assert worker.margins.calls == {on.strategy_id: 1}
    seen = [st.margin for sid, st in calls.states if sid == on.strategy_id]
    assert len(seen) == CYCLES
    assert seen[1:] == [MARGIN_X] * (CYCLES - 1)
    now[0] = at + datetime.timedelta(seconds=int(background.MARGIN_REFRESH_S))
    await worker.refresh_margins()
    assert worker.margins.calls == {on.strategy_id: 2}


async def test_a_margin_older_than_its_window_or_after_a_failed_refresh_is_never_used(gap):
    """The last good figure is never used without its age: older than ``MARGIN_STALE_S`` -> None; a later failed
    refresh replaces it (None), never keeps it."""
    prov = Prov(gap)
    at = _gap_time(prov)
    w = _ic_watched(gap)
    fake = FakeMargin(at)
    worker, _bg, _at2 = await _worker_after_refresh(prov, w, at, fake)
    assert worker.margins.block_for(w, at)["value"] == MARGIN_X
    assert worker.margins.block_for(w, at + datetime.timedelta(seconds=int(background.MARGIN_STALE_S) + 1)) is None
    fake.fail = RuntimeError("down")
    later = at + datetime.timedelta(seconds=int(background.MARGIN_REFRESH_S))
    worker._clock = lambda: later
    await worker.refresh_margins()
    assert worker.margins.block_for(w, later) is None
