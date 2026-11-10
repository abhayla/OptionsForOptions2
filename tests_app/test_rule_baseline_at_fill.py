"""ADR-283 (1)-(2), finding rule-entry-baseline-taken-at-first-check (round 3, GC-ICGUIDE g32 fx1): the starting point
of every rule after the entry and after each adjustment basket N is the market state STORED at that basket's fill,
read by the one ``entry_baseline`` the worker, the screen check and the playbook test call; never the state of the
first check that happens to run. A clock-time rule (T-10b) is never "already true". Pure: no DB (the store reads are
replaced by their answers).

ADJ-02 (system IC, entry 3 Nov 10:00 IST, spot 23100, ATM IV 0.13): at that fill T-03 (short delta) and T-09 (short
premium) are false; at the check (spot 23420, CE short delta 0.4103, PE short price 2.70) both are true.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import types
from decimal import Decimal

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers, entry_facts_store, playbook_store
from ofo_app import background as bg
from ofo_app.entry_facts_store import BasketFacts
from ofo_app.routes.adjustment_check import result_out
from test_rule_entry_baseline import IST, _adj02

AT_FILL = datetime.datetime(2026, 11, 3, 10, 0, tzinfo=IST)


def _facts(position, prices=None, spot="23100"):
    """Basket facts as the paper route stores them: every open leg keyed (type, strike, expiry, side)."""
    legs = {(x.type, x.strike, x.expiry, x.side): (x.entry if prices is None else prices.get(x.strike))
            for x in position.legs}
    return BasketFacts(AT_FILL, Decimal(spot), Decimal("0.13"), legs)


def _after_basket(now, n=1):
    return dataclasses.replace(now, adjustments_used=n)


def _kind(ev, rule_id):
    return next(type(r).__name__ for r in ev.results if r.rule_id == rule_id)


def test_path60_basket_facts_false_at_fill_flag_at_a_later_first_check():
    """(b) adjustment 1 booked; T-03 / T-09 false at the fill, true at the frame the worker first checks marker 1 ->
    Flag. Before: entry_baseline returned None for marker > 0 and the caller used ``base or state`` (already true)."""
    _scn, position, now, body = _adj02()
    now = _after_basket(now)
    base = check.entry_baseline(None, now, position, None, 1, _facts(position))
    assert base is not None and base.spot == Decimal("23100") and base.hhmm == "10:00"
    ev = pe.evaluate(body, now, {}, base, gap_until="09:30")
    assert ev.memory["T-03"]["held_at_entry"] is False and ev.memory["T-09"]["held_at_entry"] is False
    assert _kind(ev, "T-03") == "Flag" and _kind(ev, "T-09") == "Flag", ev.results


def test_a_kept_leg_takes_its_price_at_the_basket_not_its_entry_price():
    """A leg kept through basket N is priced at N's fill (stored), never its original entry price."""
    _scn, position, now, _body = _adj02()
    at_n = {x.strike: x.entry + Decimal("10") for x in position.legs}
    base = check.entry_baseline(None, now, position, None, 1, _facts(position, at_n))
    assert {s.strike: s.ltp for s in base.shorts} == {s: at_n[s] for s in (Decimal("22700"), Decimal("23500"))}


def test_a_leg_price_missing_at_the_fill_holds_no_rule_on_it():
    _scn, position, now, body = _adj02()
    base = check.entry_baseline(None, now, position, None, 1, _facts(position, {}))
    assert all(s.ltp is None and s.abs_delta is None for s in base.shorts), base.shorts
    ev = pe.evaluate(body, _after_basket(now), {}, base, gap_until="09:30")
    assert ev.memory["T-03"]["held_at_entry"] is False and _kind(ev, "T-03") == "Flag"


@pytest.mark.parametrize("marker", [0, 1, 2])
def test_facts_absent_hold_nothing_never_the_first_check(marker):
    """No stored facts (an older basket, a live fill, no quote) -> None: no rule held, a true rule flags."""
    _scn, position, now, body = _adj02()
    base = check.entry_baseline(None, now, position, None, marker, None)
    assert base is None
    ev = pe.evaluate(body, _after_basket(now, marker), {}, base, gap_until="09:30")
    assert ev.memory["T-03"]["held_at_entry"] is False and _kind(ev, "T-03") == "Flag"


def test_a_marker_jump_reads_that_basket_facts():
    """Marker 0 -> 2: the facts of basket 2 are the starting point (the callers pass ``baskets.get(marker)``)."""
    _scn, position, now, _body = _adj02()
    baskets = {0: _facts(position, spot="23000"), 2: _facts(position, spot="23200")}
    assert check.entry_baseline(None, now, position, None, 2, baskets.get(2)).spot == Decimal("23200")


@pytest.mark.parametrize("spot", ["23100", "23300", "23420", "23600", "22800"])
def test_property_same_facts_any_first_check_frame_same_held_at_entry(spot):
    """(e) same position + same stored facts, the first check at ANY frame -> the same held_at_entry."""
    _scn, position, now, body = _adj02()
    facts = _facts(position)
    expected = pe.evaluate(body, now, {}, check.entry_baseline(None, now, position, None, 1, facts),
                           gap_until="09:30").memory
    frame = dataclasses.replace(_after_basket(now), spot=Decimal(spot))
    got = pe.evaluate(body, frame, {}, check.entry_baseline(None, frame, position, None, 1, facts),
                      gap_until="09:30").memory
    assert {k: v["held_at_entry"] for k, v in got.items()} == {k: v["held_at_entry"] for k, v in expected.items()}


def _with_time_exit(body):
    """The ADJ-02 body with a rule on the clock-time trigger T-10b (limit 14:30 in every stage)."""
    body = dict(body)
    body["rules"] = [*body["rules"], {"id": "T-10b", "any_of": ["T-10b"]}]
    trig = dict(body.get("triggers", {}).get("T-10b") or {})
    trig.update({"on": True, "unit": "time"})
    for kind in ("weekly", "monthly"):
        trig[kind] = ["14:30"] * max(1, len(trig.get(kind) or []))
    body["triggers"] = {**body.get("triggers", {}), "T-10b": trig}
    return body


def test_t10b_after_its_time_is_never_held_even_from_a_basket_after_it():
    """(a) basket at 14:20 (or after 14:30), first check 14:31: the 14:30 time exit is a Flag, never 'already true'
    (ADR-283 (2)); a stored held row of it (strategy 122/123's wrong rows) flags too."""
    _scn, position, now, body = _adj02()
    body = _with_time_exit(body)
    assert "T-10b" in pe.never_held(body)
    check_at = dataclasses.replace(_after_basket(now), hhmm="14:31")
    fill = dataclasses.replace(_facts(position), clock=AT_FILL.replace(hour=14, minute=40))  # placed AFTER 14:30
    ev = pe.evaluate(body, check_at, {}, check.entry_baseline(None, check_at, position, None, 1, fill),
                     gap_until="09:30")
    assert ev.memory["T-10b"]["held_at_entry"] is False
    assert _kind(ev, "T-10b") == "Flag", ev.results
    stale = pe.evaluate(body, check_at, {"T-10b": {"held_at_entry": True, "seen_clear": False}}, None,
                        gap_until="09:30")
    assert _kind(stale, "T-10b") == "Flag"


def _screen(monkeypatch, facts, stored=None):
    async def rule_states(_conn, _user, _sid):
        return stored or {}

    async def read_basket(_conn, _sid, marker):
        return facts if marker == 1 else None

    async def entry_facts_in(_conn, _sid):
        return None

    monkeypatch.setattr(playbook_store, "rule_states", rule_states)
    monkeypatch.setattr(entry_facts_store, "read_basket", read_basket)
    monkeypatch.setattr(adjustment_readers, "entry_facts_in", entry_facts_in)


def test_screen_check_after_a_basket_with_no_rule_memory_uses_the_stored_fill(monkeypatch):
    """(c) the screen check (``evaluate_stored``) after a basket, no stored rule memory: a rule false at the fill
    flags. Before: the screen took the current state as the starting point (already true)."""
    _scn, position, now, body = _adj02()
    _screen(monkeypatch, _facts(position))
    ev, _memory = asyncio.run(check.evaluate_stored(None, "owner", 7, body, _after_basket(now), None, position,
                                                    gap_until="09:30"))
    assert _kind(ev, "T-03") == "Flag" and _kind(ev, "T-09") == "Flag", ev.results


def test_worker_and_screen_give_the_same_answer_after_an_adjustment(monkeypatch):
    """(d) the worker's check (``Worker._evaluate_and_write``) and the screen check, same stored facts and state ->
    the same result kinds and the same held_at_entry."""
    _scn, position, now, body = _adj02()
    facts, state = _facts(position), _after_basket(now)
    _screen(monkeypatch, facts)
    screen, _ = asyncio.run(check.evaluate_stored(None, "owner", 7, body, state, None, position, gap_until="09:30"))
    w = types.SimpleNamespace(strategy_id=7, tracked=types.SimpleNamespace(position=position), entry_facts=None,
                              body=body, basket_facts={1: facts})
    stub = types.SimpleNamespace(_gate_load={}, _memory={}, _written={}, _pending={},
                                 _write_wake=asyncio.Event(), _count_outcomes=lambda ev: None)
    worker = asyncio.run(bg.Worker._evaluate_and_write(stub, w, state, types.SimpleNamespace(gap_until="09:30")))
    assert [(r.rule_id, type(r).__name__) for r in worker.results] == \
        [(r.rule_id, type(r).__name__) for r in screen.results]
    assert worker.memory == screen.memory


def test_already_true_after_adjustment_n_reads_the_adr258_wording():
    """ADR-258: a rule true at basket N's fill reads "Already true after adjustment N." (entry: unchanged)."""
    _scn, _position, now, body = _adj02()
    state = _after_basket(now, 2)
    ev = pe.evaluate(body, state, {}, state, gap_until="09:30")  # every rule true now held: shown quietly
    held = next(r for r in ev.results if isinstance(r, pe.AlreadyTrue))
    assert held.after == 2  # noqa: PLR2004 - the basket number set above
    assert "Already true after adjustment 2." == result_out(held, None)["wording"].what_happened
    entry = dataclasses.replace(held, after=0)
    assert "Already true when tracking started." == result_out(entry, None)["wording"].what_happened
