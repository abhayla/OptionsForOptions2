
"""Issue 65 (entry baseline fallback) and ADR-268 (2) (T-01 at or beyond the short strike), on scenario ADJ-42.

Spec basis: REQ-159 / F-71; ADR-258; ADR-268 (2) "T-01 also flags when spot is at or beyond the short strike".
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

from ofo.adjustment.playbook_eval import AlreadyTrue, Flag, ShortLeg, short_breached
from test_adjust_scenarios import load
from test_playbook_eval import body_of, entry_of, evaluate, state_of

F71 = "ADJ-42"  # short CE 23000, spot 22920 now and at entry: T-01 (0.5 %) true at entry


def _rule(ev, rid):
    return next(r for r in ev.results if r.rule_id == rid)


def _kinds(state):
    """The scenario's shorts with their kind (the app's state carries it, ADR-268)."""
    sc = load(F71)
    kinds = {D(x["strike"]): x["type"] for x in sc["position"]["legs"] if x["side"] == "SELL"}
    return replace(state, shorts=tuple(replace(s, kind=kinds[s.strike]) for s in state.shorts))


def test_entry_baseline_from_the_entry_not_the_first_check():
    """Entry at spot 22850 (T-01 false: 150 points from both shorts), first check at 22920 (true): it flags."""
    sc = load(F71)
    body, state = body_of(sc), state_of(sc)
    entry = replace(entry_of(sc), spot=D("22850"))
    ev = evaluate(body, state, {}, entry, entry_fallback=state)
    assert isinstance(_rule(ev, "T-01"), Flag)
    assert ev.memory["T-01"] == {"held_at_entry": False, "seen_clear": False}


def test_entry_crossing_stays_quiet():
    sc = load(F71)
    body, state = body_of(sc), state_of(sc)
    ev = evaluate(body, state, {}, entry_of(sc), entry_fallback=state)
    assert isinstance(_rule(ev, "T-01"), AlreadyTrue)


def test_a_rule_not_computable_at_entry_takes_the_first_check_never_not_held():
    """The entry state has no Greeks: a delta rule takes its entry value from the first check (fallback); with no
    fallback it counts as not held (the old answer, kept for callers that pass none)."""
    sc = load(F71)
    body, state = body_of(sc), state_of(sc)
    entry = entry_of(sc)
    with_fb = evaluate(body, state, {}, entry, entry_fallback=state)
    no_fb = evaluate(body, state, {}, entry)
    on_state = evaluate(body, state, {}, state)
    for rid, mem in with_fb.memory.items():
        expected_held = on_state.memory[rid]["held_at_entry"]
        if no_fb.memory[rid]["held_at_entry"] != expected_held:  # a rule the entry state could not compute
            assert mem["held_at_entry"] == expected_held, rid


def test_t01_flags_beyond_the_short_call():
    """ADR-268 (2): spot 23235 is 235 points beyond the sold 23000 CE (1.01 % away): T-01 flags with value 0."""
    sc = load(F71)
    body, state = body_of(sc), _kinds(state_of(sc))
    beyond = replace(state, spot=D("23235"))
    ev = evaluate(body, beyond, {"T-01": {"held_at_entry": True, "seen_clear": True}}, None)
    flag = _rule(ev, "T-01")
    assert isinstance(flag, Flag) and flag.value == D(0) and flag.threshold == D("0.5"), flag
    assert flag.beyond == ("CE", D("23000"), D("235")), flag  # the line names the short and the points past it
    rv = next(v for v in ev.values if v.rule_id == "T-01")
    assert rv.beyond == flag.beyond, rv  # the record the worker opens carries it too
    assert short_breached(D("23235"), beyond.shorts).strike == D("23000")


def test_t01_at_the_strike_flags_and_inside_is_unchanged():
    shorts = (ShortLeg(D("23000"), None, None, "CE"), ShortLeg(D("22000"), None, None, "PE"))
    assert short_breached(D("23000"), shorts).strike == D("23000")  # at the strike
    assert short_breached(D("21990"), shorts).strike == D("22000")  # beyond the put
    assert short_breached(D("22500"), shorts) is None  # between the shorts
    assert short_breached(D("23100"), (ShortLeg(D("23000"), None, None),)) is None  # kind unknown: no breach


def test_t01_inside_the_gap_carries_no_beyond():
    sc = load(F71)
    body, state = body_of(sc), _kinds(state_of(sc))
    ev = evaluate(body, state, {"T-01": {"held_at_entry": True, "seen_clear": True}}, None)
    flag = _rule(ev, "T-01")
    assert isinstance(flag, Flag) and flag.beyond is None and flag.value != D(0), flag
