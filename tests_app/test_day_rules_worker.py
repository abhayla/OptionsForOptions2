"""GC-IC1 step 1a core proof (REQ-159 AC-4, REQ-170, ADR-216): the iron condor's switched-on expiry-day rule
(14:30, close a spread whose short is within 0.3% of spot, action 5) opens ONE record through the alert gate, run by
the REAL background Worker with a pinned clock on a fresh database. Scenarios ADJ-51 (short CE 0.21% from spot, far
short PE below Rs 2) and ADJ-52 (nearest short 0.4% away) are seeded through the app's own stores, as
``test_background_worker.py`` does. Records are counted by SQL against ``public.adjustment_suggestions``."""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
from decimal import Decimal

from _scenario_catalogue import load_library
from ofo.adjustment.preferences import from_values
from ofo.errors.explanations import PLAYBOOK_DAY_RULE_ACTION_TEXT
from ofo.settings import defaults as registry_defaults
from ofo.timeutil import IST
from ofo_app import background, playbook_store, scenario_mode, strategy_alert_style_store, user_preferences_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
RID = "day.expiry.1430.5"
T1429 = datetime.datetime(2026, 11, 3, 14, 29, 0, tzinfo=IST)
T1430 = T1429 + datetime.timedelta(minutes=1)
LAST_SECOND = 59


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


async def _app_db(app_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()


async def _seeded(app_engine, monkeypatch, sid_name: str) -> tuple[int, scenario_mode.Scenario]:
    await _app_db(app_engine, monkeypatch)
    monkeypatch.setenv("OFO_SCENARIO", sid_name)
    scn = scenario_mode.load(sid_name)
    await load_library(app_engine)  # the whole library's list, once per database
    sid = await seed_mod.seed(sid_name)
    async with app_engine.connect() as conn:  # 1-minute candles (REQ-170 Q-AD-2), as the worker tests pin
        await strategy_alert_style_store.set_pin(conn, "owner", sid, "intraday")
        await conn.commit()
    return sid, scn


def _push_spot(scn: scenario_mode.Scenario, spot: str, received: datetime.datetime) -> None:
    quote = scn.provider.underlying_quote("NIFTY")
    token = int(quote.instrument_id.split(":")[-1])
    lc = next(x for x in scn.provider.instrument_master() if str(x.contract.exchange_token) == str(token))
    packet = scenario_mode._index_packet(int(lc.broker_refs[0].broker_token), spot, int(received.timestamp()))
    scn.provider.on_frame(scenario_mode._frame([packet]), received)


class _Draining(background.Worker):
    """The real Worker with its writer queue written at the end of each cycle (#636 r4; no writer task here)."""

    async def cycle(self) -> None:
        await super().cycle()
        await self.drain_writes()


def _worker(scn: scenario_mode.Scenario, clock, overrides: dict | None = None) -> background.Worker:
    """``overrides``: admin values that differ from the registry defaults (the admin layer, so also the user's)."""
    def settings(_at):  # the settings in force at the worker clock, from memory (#636 r4 settings cache seam)
        return {**registry_defaults(), **(overrides or {})}

    async def preferences(_user_ref):
        return from_values(registry_defaults())

    async def user_values(_user_ref):
        # the store's own record shape (``values_for``: no own value, every key "default"); a plain mapping has no
        # user layer and the carry gap resolver fails closed (setting_user_unreadable, ADR-245)
        values = {**registry_defaults(), **(overrides or {})}
        return user_preferences_store.UserValues(
            {k: user_preferences_store.Answer(k, values[k], "default", values[k], None)
             for k in user_preferences_store.preference_keys()})
    return _Draining(provider_for=lambda _owner: scn.provider,
                     lister=lambda: background.owner_lister(scn.provider), clock=clock,
                     settings=settings, preferences=preferences, user_values=user_values)


async def _day_rows(engine, sid: int) -> list[tuple]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, outcome, trigger_id, timeline->0->>'approach', timeline->0->>'label', value, threshold, "
            "timeline->0->>'group' "
            "FROM public.adjustment_suggestions WHERE strategy_id = :s AND rule_id = :r ORDER BY id"),
            {"s": sid, "r": RID})).all()
    return [tuple(r) for r in rows]


async def _run(worker, now, scn, spot: str, start: datetime.datetime, seconds: int) -> None:  # noqa: PLR0913
    """One check a second from ``start`` for ``seconds``; a fresh spot frame each second (the feed keeps ticking)."""
    for s in range(seconds):
        now[0] = start + datetime.timedelta(seconds=s)
        _push_spot(scn, spot, now[0])
        await worker.cycle()


async def test_core_expiry_rule_opens_one_record_at_1430_through_the_gate_and_never_at_1429(app_engine, monkeypatch):
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-51")
    try:
        now = [T1429]
        # #663: at 23400 ADJ-51 also opens T-01 (twice), T-07, T-09 and T-10b by 14:42, so the default daily limit
        # (6, ADR-237 (7)) held the re-armed day record as daily_limit (measured 2026-11-08 gate trace); the admin
        # limit at its registry maximum keeps this test on the re-arm (ADR-237 (1)), the cap has its own tests
        worker = _worker(scn, lambda now=now: now[0], overrides={"alerts.intraday.daily_cap": Decimal("20")})
        await _run(worker, now, scn, "23400", T1429, LAST_SECOND + 1)  # 14:29:00 .. 14:29:59
        assert worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE, worker.errors
        at_1429 = await _day_rows(app_engine, sid)
        assert at_1429 == [], at_1429
        await _run(worker, now, scn, "23400", T1430, 75)  # 14:30:00 .. 14:31:14: the 14:30 candle closes at 14:31
        at_1431 = await _day_rows(app_engine, sid)
        assert len(at_1431) == 1, at_1431
        rec = at_1431[0]
        assert rec[1:5] == ("open", RID, "A-28,A-27", PLAYBOOK_DAY_RULE_ACTION_TEXT["5"]), rec
        # B1 (GC-IC1 1a review): opened BY alert_gate.step at the first 1-minute candle close at or after 14:30, i.e.
        # 14:31:00 (gate_group = the close the gate processed), never at the 14:30:00 check a direct write would use
        assert rec[7] == background.gate_group(sid, T1430 + datetime.timedelta(minutes=1)), rec
        await _run(worker, now, scn, "23400", T1430 + datetime.timedelta(seconds=75), 300)  # 5 more closes
        later = await _day_rows(app_engine, sid)
        assert later == at_1431 and worker.errors == [], (later, worker.errors)
        # B1, ADR-237 (1) yes/no re-arm: dismissed while still true -> no new record; a false close re-arms it
        async with app_engine.connect() as conn:
            await playbook_store.dismiss(conn, "owner", rec[0])
            await conn.commit()
        await worker.rebuild()  # the rebuild task feeds the dismissed row to alert_gate.dismiss (ADR-236)
        t2 = T1430 + datetime.timedelta(seconds=375)
        await _run(worker, now, scn, "23400", t2, 180)  # still within 0.3%: three more closes
        held = await _day_rows(app_engine, sid)
        assert [r[:2] for r in held] == [(rec[0], "dismissed")], held
        t3 = t2 + datetime.timedelta(seconds=180)
        await _run(worker, now, scn, "23356.55", t3, 120)  # 0.4% away: a false close re-arms the rule
        t4 = t3 + datetime.timedelta(seconds=120)
        await _run(worker, now, scn, "23400", t4, 120)  # true again: the next close opens a NEW record
        rearmed = await _day_rows(app_engine, sid)
        assert len(rearmed) == len(held) + 1 and rearmed[1][1] == "open" and worker.errors == [], \
            (rearmed, worker.errors)
        print(f"CORE-PROOF ADJ-51 sid={sid} rows_at_1429={len(at_1429)} rows_after_1431_close={len(at_1431)} "
              f"rows_after_5_more_closes={len(later)} record={rec}")
    finally:
        await app_db.close_db()
        _reset_engine()


async def test_short_04_pct_away_opens_no_record(app_engine, monkeypatch):
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-52")
    try:
        now = [T1429]
        worker = _worker(scn, lambda now=now: now[0])
        await _run(worker, now, scn, "23356.55", T1429, 60 + 180)  # 14:29 .. 14:32:59
        rows = await _day_rows(app_engine, sid)
        assert rows == [] and worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE, \
            (rows, worker.errors)
        print(f"CORE-PROOF ADJ-52 sid={sid} rows={len(rows)}")
    finally:
        await app_db.close_db()
        _reset_engine()


# ---- GC-IC1 1b: the carry check (before-weekend / before-holiday, 15:00, action 0) -----------------------------
CARRY_RID = "day.beforeWeekend.1500.0"
FRI_1459 = datetime.datetime(2026, 10, 30, 14, 59, 0, tzinfo=IST)
WED_1459 = datetime.datetime(2026, 10, 28, 14, 59, 0, tzinfo=IST)


async def _carry_rows(engine, sid: int) -> list[tuple]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, outcome, rule_id, timeline->0->>'group', timeline->0->'carry' "
            "FROM public.adjustment_suggestions WHERE strategy_id = :s AND rule_id LIKE 'day.before%' ORDER BY id"),
            {"s": sid})).all()
    return [tuple(r) for r in rows]


def _assert_gap_matches_generator(sid_name: str, up: Decimal, down: Decimal) -> None:
    """REQ-159 AC-4: the record's 2% gap figures against the generator's own values (its own leg model, never the
    app's carry code). The worker solves each leg's IV from prices rounded to the 0.05 tick, so the bound is one
    tick per leg per unit of quantity: 0.05 x quantity x legs (Rs 26 for ADJ-53)."""
    exp = scenario_mode.read(sid_name)
    legs = exp["position"]["legs"]
    tol = Decimal("0.05") * sum(leg["quantity"] for leg in legs)
    carry = exp["expected"]["carry"]
    assert abs(up - Decimal(carry["gap_up"])) <= tol, (sid_name, "up", up, carry["gap_up"], tol)
    assert abs(down - Decimal(carry["gap_down"])) <= tol, (sid_name, "down", down, carry["gap_down"], tol)


async def test_core_carry_check_friday_opens_one_record_at_the_1501_close_with_gap_figures(app_engine, monkeypatch):
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-53")
    try:
        now = [FRI_1459]
        worker = _worker(scn, lambda now=now: now[0])
        await _run(worker, now, scn, "23100", FRI_1459, LAST_SECOND + 1)  # 14:59:00 .. 14:59:59
        assert worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE, worker.errors
        at_1459 = await _carry_rows(app_engine, sid)
        assert at_1459 == [], at_1459
        t1500 = FRI_1459 + datetime.timedelta(minutes=1)
        await _run(worker, now, scn, "23100", t1500, 75)  # the 15:00 candle closes at 15:01
        rows = await _carry_rows(app_engine, sid)
        assert len(rows) == 1, rows
        rec = rows[0]
        assert rec[1:4] == ("open", CARRY_RID, background.gate_group(sid, t1500 + datetime.timedelta(minutes=1))), rec
        carry = rec[4]
        assert carry["gap_pct"] == "2" and carry["gap_reason"] is None, carry
        up, down = Decimal(carry["gap_up"]), Decimal(carry["gap_down"])
        assert up == up.quantize(Decimal("0.01")) and down == down.quantize(Decimal("0.01")) and up != down, carry
        _assert_gap_matches_generator("ADJ-53", up, down)
        assert carry["margin"] is None and carry["margin_reason"] == "adjust_trigger_missing_margin", carry
        assert carry["next_open"] == "2026-11-02T09:15:00+05:30", carry
        await _run(worker, now, scn, "23100", t1500 + datetime.timedelta(seconds=75), 300)  # 5 more closes
        later = await _carry_rows(app_engine, sid)
        assert later == rows and worker.errors == [], (later, worker.errors)
        print(f"CORE-PROOF ADJ-53 sid={sid} rows_at_1459={len(at_1459)} rows_after_1501_close={len(rows)} "
              f"rows_after_5_more_closes={len(later)} record={rec}")
    finally:
        await app_db.close_db()
        _reset_engine()


async def test_carry_check_wednesday_opens_no_record(app_engine, monkeypatch):
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-54")
    try:
        now = [WED_1459]
        worker = _worker(scn, lambda now=now: now[0])
        await _run(worker, now, scn, "23100", WED_1459, 60 + 180)  # 14:59 .. 15:02:59
        rows = await _carry_rows(app_engine, sid)
        assert rows == [] and worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE, \
            (rows, worker.errors)
        print(f"CORE-PROOF ADJ-54 sid={sid} rows={len(rows)}")
    finally:
        await app_db.close_db()
        _reset_engine()


MON_1459 = datetime.datetime(2026, 11, 9, 14, 59, 0, tzinfo=IST)


async def test_carry_check_monday_before_the_holiday_opens_exactly_one_record(app_engine, monkeypatch):
    """ADJ-55: Monday 9 Nov, Tuesday 10 Nov a listed holiday. Monday is not before a weekend: one before-holiday
    record only (never also a before-weekend one), with gap figures inside the generator's tolerance."""
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-55")
    try:
        now = [MON_1459]
        worker = _worker(scn, lambda now=now: now[0])
        await _run(worker, now, scn, "23100", MON_1459, LAST_SECOND + 1)  # 14:59:00 .. 14:59:59
        assert await _carry_rows(app_engine, sid) == []
        t1500 = MON_1459 + datetime.timedelta(minutes=1)
        await _run(worker, now, scn, "23100", t1500, 75)  # the 15:00 candle closes at 15:01
        rows = await _carry_rows(app_engine, sid)
        assert len(rows) == 1 and worker.errors == [], (rows, worker.errors)
        rec = rows[0]
        assert rec[1:3] == ("open", "day.beforeHoliday.1500.0"), rec
        carry = rec[4]
        assert carry["next_open"] == "2026-11-11T09:15:00+05:30", carry
        _assert_gap_matches_generator("ADJ-55", Decimal(carry["gap_up"]), Decimal(carry["gap_down"]))
        print(f"CORE-PROOF ADJ-55 sid={sid} rows={len(rows)} record={rec}")
    finally:
        await app_db.close_db()
        _reset_engine()
