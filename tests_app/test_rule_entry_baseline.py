"""F-71 baseline from the ENTRY, never from the first check (issues 65/89/36, finding
``rule-entry-baseline-taken-at-first-check``, REQ-159, ADR-258): the background worker's rule memory comes from the
stored rule state (seeded on the rebuild), and its first check's entry baseline comes from the strategy's entry, so a
crossing that existed at entry is never raised as new, and a crossing that did not is never hidden as "already true".

Core proof (scenario ADJ-02 on a throwaway DB, real worker, counted from the DB): the scenario entry is moved past the
T-01 line, so T-01 held at entry. First worker: quiet. Restarted worker: its FIRST cycle reads T-01 as already true
(from the stored memory, not from a fresh baseline) and opens nothing. The spot clears, the worker restarts again, the
spot crosses: the restarted worker's FIRST cycle flags T-01 (the stored "seen clear" memory, never a fresh "already
true" from this check), and exactly one record opens.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import types
from decimal import Decimal
from pathlib import Path

import test_background_worker as bw
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import EntryFacts, Position, PositionLeg
from ofo.settings import layers
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers
from ofo_app import background as bg
from ofo_app import playbook_store, scenario_mode
from test_background_worker import app_db_url  # noqa: F401 - the fixture

ONE_MINUTE_AND_A_BIT = 70
ENTRY_SPOT = "23460"  # 40 points (0.17 %) under the 23500 CE short: inside every stage's T-01 limit (lowest 0.3 %)


def _t01(worker, sid: int):
    return next(r for r in worker._gate_ctx[sid].evaluation.results if r.rule_id == "T-01")


async def _run(worker, now, seconds: int) -> None:
    for _ in range(seconds):
        now[0] += bw.ONE_SECOND
        await worker.cycle()


async def test_core_entry_crossing_stays_quiet_across_a_restart_and_a_new_crossing_opens_exactly_one(
        app_db_url, monkeypatch):  # noqa: F811 - the imported fixture
    sid, scn = await bw._seeded(app_db_url, monkeypatch)
    scn.data["position"]["entry"]["spot"] = ENTRY_SPOT  # T-01 true AT ENTRY at its entry-stage limit
    monkeypatch.setattr(scenario_mode, "_loaded", {"ADJ-02": scn})  # the worker reads current(): make it this object
    await bw._pin_intraday(app_db_url, sid)
    now = [scn.clock_at]
    bw._push_spot(scn, bw.CROSS_SPOT, now[0])
    base = await bw._last_id(app_db_url, sid)
    first = bw._worker(scn, lambda: now[0])
    await _run(first, now, ONE_MINUTE_AND_A_BIT)
    assert isinstance(_t01(first, sid), pe.AlreadyTrue), _t01(first, sid)
    async with app_db_url.connect() as conn:
        state = await playbook_store.rule_state(conn, "owner", sid)
    assert state["T-01"] == (True, False), state  # held at entry, not seen clear
    first.stop()

    second = bw._worker(scn, lambda: now[0])
    now[0] += bw.ONE_SECOND
    await second.cycle()
    assert isinstance(_t01(second, sid), pe.AlreadyTrue), _t01(second, sid)
    await _run(second, now, ONE_MINUTE_AND_A_BIT)
    assert await bw._t01_rows(app_db_url, sid, base) == []

    now[0] += datetime.timedelta(seconds=5)
    bw._push_spot(scn, bw.BEFORE_CROSS_SPOT, now[0])
    await _run(second, now, ONE_MINUTE_AND_A_BIT)
    async with app_db_url.connect() as conn:
        assert (await playbook_store.rule_state(conn, "owner", sid))["T-01"] == (True, True)
    second.stop()

    now[0] += datetime.timedelta(seconds=5)
    bw._push_spot(scn, bw.CROSS_SPOT, now[0])
    third = bw._worker(scn, lambda: now[0])
    now[0] += bw.ONE_SECOND
    await third.cycle()
    first_check = _t01(third, sid)
    await _run(third, now, ONE_MINUTE_AND_A_BIT)
    rows = await bw._t01_rows(app_db_url, sid, base)
    print(f"CORE-PROOF strategy={sid} entry_spot={ENTRY_SPOT} restart_first_check="
          f"{type(first_check).__name__} records_after_new_crossing={len(rows)} rows={rows}")
    assert isinstance(first_check, pe.Flag), first_check  # memory from the DB: seen clear, so a new crossing flags
    assert len(rows) == 1 and rows[0][1] == "open", rows
    assert third.errors == [], third.errors


# ---- round 3: the entry state reproduces every rule input AT ENTRY (pure, no DB) ------------------------------------
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "adjust_scenarios"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _adj02():
    """ADJ-02 as the app reads it: the position (entry spot 23100, ATM IV 0.13 at 3 Nov 10:00), the system IC
    playbook, and a first check where T-03 and T-09 are true NOW (CE short delta 0.4103, PE short price 2.70)."""
    data = scenario_mode.read("ADJ-02")
    playbooks = json.loads((FIXTURES / "_playbooks.json").read_text(encoding="utf-8"), parse_float=Decimal)
    legs = tuple(PositionLeg(x["side"], x["type"], Decimal(x["strike"]), datetime.date.fromisoformat(x["expiry"]),
                             x["lots"], Decimal(x["entry"]), x["tradingsymbol"]) for x in data["position"]["legs"])
    position = Position(data["underlying"], 65, data["expiry_kind"], datetime.date(2026, 11, 6), legs)
    now = pe.StrategyState(stops=None, expiry_kind=data["expiry_kind"], days_left=3, hhmm="11:00",
                           spot=Decimal("23420"),
                           shorts=(pe.ShortLeg(Decimal("22700"), Decimal("0.0310"), Decimal("2.70"), "PE"),
                                   pe.ShortLeg(Decimal("23500"), Decimal("0.4103"), Decimal("88.00"), "CE")),
                           atm_iv=Decimal("0.13"), prices_fresh=True)
    return types.SimpleNamespace(data=data), position, now, pe.body_from_fixture(playbooks, data["family"])


def test_core_entry_state_carries_model_deltas_and_entry_premiums():
    """Each short's |delta| from the engine (bs_greeks) at entry spot / IV / clock, its entry premium as its price.
    Before round 3 both were None, so T-03 and T-09 took the FIRST CHECK as their entry and were held at entry."""
    scn, position, now, _body = _adj02()
    entry = check.scenario_entry(scn, now, position)
    by_strike = {s.strike: s for s in entry.shorts}
    assert {k: (s.ltp, s.kind) for k, s in by_strike.items()} == {Decimal("22700"): (Decimal("41.80"), "PE"),
                                                                Decimal("23500"): (Decimal("42.00"), "CE")}
    assert by_strike[Decimal("23500")].abs_delta == Decimal("0.1744"), by_strike  # rate 0.065, to 9 Nov 15:30
    assert by_strike[Decimal("22700")].abs_delta == Decimal("0.1352"), by_strike
    assert entry.atm_iv == entry.entry_atm_iv == Decimal("0.13")


def test_core_t03_and_t09_not_held_at_entry_so_the_first_check_flags_them():
    scn, position, now, body = _adj02()
    ev = pe.evaluate(body, now, {}, check.scenario_entry(scn, now, position), gap_until="09:30")
    assert ev.memory["T-03"]["held_at_entry"] is False, ev.memory
    assert ev.memory["T-09"]["held_at_entry"] is False, ev.memory
    flagged = {r.rule_id for r in ev.results if isinstance(r, pe.Flag)}
    assert {"T-03", "T-09"} <= flagged, ev.results


def test_entry_facts_with_no_iv_solve_each_short_from_its_entry_premium():
    """Stored entry facts (live / paper) carry no IV: each short's vol is solved by the engine from its own entry
    (fill) price at the entry spot and clock, never taken from the first check."""
    _scn, position, now, body = _adj02()
    facts = EntryFacts(Decimal("23100"), None, None, at=datetime.datetime(2026, 11, 3, 10, 0, tzinfo=IST))
    entry = check.entry_baseline(None, now, position, facts, 0)
    deltas = {s.strike: s.abs_delta for s in entry.shorts}
    assert all(d is not None and Decimal(0) < d < Decimal("0.35") for d in deltas.values()), deltas
    ev = pe.evaluate(body, now, {}, entry, gap_until="09:30")
    assert ev.memory["T-03"]["held_at_entry"] is False and ev.memory["T-09"]["held_at_entry"] is False


def test_no_entry_facts_hold_nothing_never_the_first_check():
    """ADR-283 (gap closed): no scenario and no stored facts -> None, passed to ``pe.evaluate`` as it is (the callers'
    ``base or state`` is deleted), so nothing is held and a rule true now flags."""
    _scn, position, now, body = _adj02()
    assert check.entry_baseline(None, now, position, None, 0) is None
    ev = pe.evaluate(body, now, {}, None, gap_until="09:30")
    assert ev.memory["T-03"]["held_at_entry"] is False


def _scenario(name: str):
    data = scenario_mode.read(name)
    playbooks = json.loads((FIXTURES / "_playbooks.json").read_text(encoding="utf-8"), parse_float=Decimal)
    legs = tuple(PositionLeg(x["side"], x["type"], Decimal(x["strike"]), datetime.date.fromisoformat(x["expiry"]),
                             x["lots"], Decimal(x["entry"]), x["tradingsymbol"]) for x in data["position"]["legs"])
    position = Position(data["underlying"], 65, data["expiry_kind"], datetime.date(2026, 11, 6), legs)
    now = pe.StrategyState(stops=None, expiry_kind=data["expiry_kind"], days_left=3, hhmm="11:00",
                           spot=Decimal(data["market"]["spot"]), atm_iv=Decimal(data["market"]["atm_iv"]),
                           prices_fresh=True, adjustments_used=0, s02_delta_per_lot=Decimal("0.15"))
    return types.SimpleNamespace(data=data), position, now, pe.body_from_fixture(playbooks, data["family"])


def _s02_at_entry(name: str):
    scn, position, now, body = _scenario(name)
    entry = check.scenario_entry(scn, now, position)
    assert all(h.greeks is not None for h in entry.held), entry.held  # every open leg, longs too
    now = dataclasses.replace(now, held=entry.held)  # the first check reads the same legs (no move since entry)
    ev = pe.evaluate(body, now, {}, entry, gap_until="09:30")
    return ev.memory.get("sit.S-02"), [type(r).__name__ for r in ev.results if r.rule_id == "sit.S-02"]


def test_round4_adj42_s02_held_at_entry_all_legs_carry_entry_greeks():
    """ADJ-42 entry (spot 22920, IV 0.07): net delta per lot -0.2327, |.| >= 0.15 -> S-02 held at entry."""
    assert _s02_at_entry("ADJ-42") == ({"held_at_entry": True, "seen_clear": False}, ["AlreadyTrue"])


def test_round4_adj02_s02_not_held_at_entry_net_delta_below_limit():
    """ADJ-02 entry net delta per lot -0.0159 (< 0.15) -> S-02 not held at entry, so it flags."""
    assert _s02_at_entry("ADJ-02") == ({"held_at_entry": False, "seen_clear": True}, [])  # clear now, nothing to flag


# ---- GC-ICGUIDE g04b: the baseline follows what the strategy HAS stored, not the process mode -----------------------
def _path40_frame6():
    """PATH-40 frame 6 (spot 23390, 0.47 % from the 23500 short call; the file's own entry is 3 Nov, spot 23100,
    0.22 % from the 23150 short put, so T-01 'held at entry' on the FILE's entry)."""
    data = scenario_mode.read("PATH-40", 6)
    playbooks = json.loads((FIXTURES / "_playbooks.json").read_text(encoding="utf-8"), parse_float=Decimal)
    legs = tuple(PositionLeg(x["side"], x["type"], Decimal(x["strike"]), datetime.date.fromisoformat(x["expiry"]),
                             x["lots"], Decimal(x["entry"]), x["tradingsymbol"]) for x in data["position"]["legs"])
    position = Position(data["underlying"], 65, data["expiry_kind"], datetime.date(2026, 11, 6), legs)
    now = pe.StrategyState(stops=None, expiry_kind=data["expiry_kind"], days_left=3, hhmm="11:40",
                           spot=Decimal("23390"),
                           shorts=(pe.ShortLeg(Decimal("23150"), Decimal("0.20"), Decimal("40.00"), "PE"),
                                   pe.ShortLeg(Decimal("23500"), Decimal("0.30"), Decimal("30.00"), "CE")),
                           atm_iv=Decimal("0.10"), prices_fresh=True, adjustments_used=0)
    return types.SimpleNamespace(data=data), position, now, pe.body_from_fixture(playbooks, data["family"])


OWN_FACTS = EntryFacts(Decimal("23290"), Decimal("210"), Decimal("140"),
                       at=datetime.datetime(2026, 11, 6, 11, 28, tzinfo=IST))


def _t01_of(ev):
    return next(r for r in ev.results if r.rule_id == "T-01")


async def _screen(monkeypatch, facts):
    """The screen path (``evaluate_stored``) with the two reads replaced by the stored answers."""
    async def no_memory(*_a):
        return {}

    async def read_facts(*_a):
        return facts

    monkeypatch.setattr(playbook_store, "rule_states", no_memory)
    monkeypatch.setattr(adjustment_readers, "entry_facts_in", read_facts)
    scn, position, now, body = _path40_frame6()
    ev, _memory = await check.evaluate_stored(None, "owner", 1, body, now, scn, position, gap_until="09:30")
    return _t01_of(ev)


async def test_g04b_a_builder_entered_strategy_in_scenario_mode_flags_t01(monkeypatch):
    """The measured case: stored facts (spot 23290, 6 Nov 11:28) beat the file's entry; T-01 was false at that entry."""
    got = await _screen(monkeypatch, OWN_FACTS)
    assert isinstance(got, pe.Flag), got


async def test_g04b_no_stored_facts_keeps_the_file_entry(monkeypatch):
    assert isinstance(await _screen(monkeypatch, None), pe.AlreadyTrue)


async def test_g04b_unreadable_facts_use_the_file_entry_without_raising(monkeypatch):
    assert isinstance(await _screen(monkeypatch, layers.Unreadable("entry_facts_read_failed")), pe.AlreadyTrue)


def test_g04b_facts_with_no_time_or_a_position_with_no_legs_fall_to_the_file_entry_and_no_legs_to_none():
    scn, position, now, _body = _path40_frame6()
    file_entry = check.scenario_entry(scn, now, position)
    no_time = EntryFacts(Decimal("23290"), None, None)
    assert check.entry_baseline(scn, now, position, no_time, 0) == file_entry
    assert check.entry_baseline(scn, now, dataclasses.replace(position, legs=()), OWN_FACTS, 0) is None  # no legs
    assert check.entry_baseline(scn, now, position, OWN_FACTS, 1) is None  # after a basket: unchanged


def test_g04b_t11_entry_iv_follows_the_same_choice():
    scn, position, now, _body = _path40_frame6()
    own = dataclasses.replace(now, entry_atm_iv=None)  # facts carry no IV: none, never the file's 0.10
    assert check.with_entry_iv(scn, own, position, OWN_FACTS).entry_atm_iv is None
    assert check.with_entry_iv(scn, own, position, None).entry_atm_iv == Decimal("0.10")  # the file's IV


async def test_g04b_the_worker_path_gives_the_screen_answer(monkeypatch):
    scn, position, now, body = _path40_frame6()
    monkeypatch.setattr(scenario_mode, "current", lambda: scn)
    worker = types.SimpleNamespace(_gate_load={}, _memory={}, _written={}, _pending={},
                                   _write_wake=types.SimpleNamespace(set=lambda: None),
                                   _count_outcomes=lambda _ev: None)
    watched = types.SimpleNamespace(strategy_id=1, body=body, entry_facts=OWN_FACTS, basket_facts={},
                                    tracked=types.SimpleNamespace(position=position))
    ev = await bg.Worker._evaluate_and_write(worker, watched, now, types.SimpleNamespace(gap_until="09:30"))
    assert isinstance(_t01_of(ev), pe.Flag), _t01_of(ev)
    watched.entry_facts = None
    ev = await bg.Worker._evaluate_and_write(worker, watched, now, types.SimpleNamespace(gap_until="09:30"))
    assert isinstance(_t01_of(ev), pe.AlreadyTrue)
