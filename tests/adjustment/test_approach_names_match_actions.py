# ruff: noqa: PLR2004 - leg counts of the approaches
"""GC-ICFIX u509 (ADR-214, ADR-238, ADR-239, ADR-003): the shown name of an approach states what its built legs do.

Each rule reads the key words of the shown name and checks them against the builder's own trades (no name is typed here
beyond the word rules). Also: the name table, the built-id list and the kinds table hold the same ids
(finding approach-name-list-split-from-built-list)."""
from __future__ import annotations

import re
from collections import Counter

import pytest
from ofo.adjustment import approaches as ap
from ofo.errors.explanations import BUILT_APPROACH_NAMES
from test_approaches import CFG, IC_IDS, inputs, load  # the scenario helpers of the builder tests


def _width(legs, kind):
    strikes = sorted(x.strike for x in legs if x.type == kind)
    return strikes[-1] - strikes[0]


def _checks(name, position, built):
    """Yield (rule, ok) for every key word of ``name`` that makes a claim about the legs."""
    expiry = {x.expiry for x in position.legs}
    opened, closed = built.trades, built.closed
    if re.search(r"\bout\b", name) or "next expiry" in name or "in time" in name:
        yield "out/next expiry: an opened leg is on a later expiry", any(t.expiry > min(expiry) for t in opened)
    if "same expiry" in name:
        yield "same expiry: every opened leg on the position's expiry", all(t.expiry in expiry for t in opened)
    if "same strikes" in name:
        yield "same strikes: no strike changes", {t.strike for t in opened} == {c.strike for c in closed}
    if "same width" in name:
        for kind in ("CE", "PE"):
            before = [c for c in closed if c.type == kind]
            now = [t for t in opened if t.type == kind]
            if len(before) == 2 and len(now) == 2:
                yield "same width: the spread's width is unchanged", _width(before, kind) == _width(now, kind)
    yield from _closed_leg_checks(name, closed)


def _closed_leg_checks(name, closed):
    if re.search(r"\ba leg\b", name):
        yield "a leg: exactly one leg is closed", len(closed) == 1
    if re.match(r"Close the (un)?tested side", name):
        yield "side: the short and its wing are both closed", len(closed) == 2
    if "move both shorts" in name and "wings keep their distance" not in name:
        # a name that says only the shorts move must not be built with orders on the wings
        yield "only shorts move: no wing is closed", all(c.side == "SELL" for c in closed)
    if "wings keep their distance" in name:
        yield "wings move with the shorts: a wing is closed too", any(c.side == "BUY" for c in closed)
    if "wing stays" in name:
        yield "wing stays: one short closed, nothing else", len(closed) == 1 and closed[0].side == "SELL"


def test_every_shown_name_states_what_its_built_legs_do():
    seen: Counter = Counter()
    for sid in IC_IDS:
        sc = load(sid)
        position, chain, spot = inputs(sc)
        for built in ap.applicable_approaches(position, chain, spot, CFG):
            if built.refusal is not None:
                continue
            for rule, ok in _checks(built.name, position, built):
                seen[(built.id, rule)] += 1
                assert ok, (sid, built.id, built.name, rule)
    assert seen, "no name rule was exercised"


def _direction_checks(name, position, spot, built):
    """A direction claim in the name ("away from spot", "toward spot", "call spread up, put spread down") must hold
    for every short the approach re-places, whatever side of spot the short sits on."""
    old = {c.type: c.strike for c in built.closed if c.side == "SELL"}
    new = {t.type: t.strike for t in built.trades if t.action == "SELL"}
    for kind in old.keys() & new.keys():
        was, now = abs(old[kind] - spot), abs(new[kind] - spot)
        if re.search(r"\baway\b", name):
            yield "away from spot: the short ends farther from spot", now > was
        if "toward spot" in name:
            yield "toward spot: the short ends nearer spot", now < was
        if "call spread up" in name and kind == "CE":
            yield "call spread up: the call short's strike rises", new[kind] > old[kind]
        if "put spread down" in name and kind == "PE":
            yield "put spread down: the put short's strike falls", new[kind] < old[kind]
    if "wings keep their distance" in name:
        for kind in ("CE", "PE"):
            gap = {s: {x.side: x.strike for x in legs if x.type == kind} for s, legs in
                   (("was", position.legs), ("now", built.after))}
            yield "wings keep their distance: wing - short unchanged", \
                gap["was"]["BUY"] - gap["was"]["SELL"] == gap["now"]["BUY"] - gap["now"]["SELL"]


def _spots(position, spot):
    """The scenario's own spot plus the tested short out of the money, at the money and in the money."""
    found = ap.tested_side(position, spot)
    if found is None:
        return [spot]
    is_call = found == ap.CALL
    short = next(x.strike for x in position.legs if x.side == "SELL" and x.type == ("CE" if is_call else "PE"))
    sign = -1 if is_call else 1  # a call short is out of the money when spot is below it
    return [spot, short + sign * 300, short, short - sign * 300]


def test_direction_claims_hold_out_of_at_and_in_the_money():
    seen: Counter = Counter()
    for sid in IC_IDS:
        position, chain, spot0 = inputs(load(sid))
        for spot in _spots(position, spot0):
            for built in ap.applicable_approaches(position, chain, spot, CFG):
                if built.refusal is not None:
                    continue
                for rule, ok in _direction_checks(built.name, position, spot, built):
                    seen[(built.id, rule)] += 1
                    assert ok, (sid, spot, built.id, built.name, rule)
    assert {r for _, r in seen} >= {"wings keep their distance: wing - short unchanged"}, seen


@pytest.mark.parametrize("aid,rule", [
    ("A-05", "out/next expiry"), ("A-06", "a leg"), ("A-26", "side")])
def test_names_that_made_a_false_claim_are_gone(aid, rule):
    """The three names the user-test notes and ADR-238 (3) / ADR-239 (3) found misleading no longer carry the claim."""
    name = BUILT_APPROACH_NAMES[aid]
    assert not any(r.startswith(rule) for r, _ in _false_claims(name)), name


def _false_claims(name):
    # a name that says "out" without "in time"/"next expiry" reads as a time roll; "a leg" and "untested side" claim
    # one leg / both legs. Built facts (checked above): A-05 keeps the expiry, A-06 moves two legs, A-26 closes one.
    if re.search(r"\bout\b", name) and "in time" not in name:
        yield "out/next expiry", False
    if re.search(r"\ba leg\b", name):
        yield "a leg", False
    if re.match(r"Close the untested side", name):
        yield "side", False


def test_name_table_built_list_and_kinds_hold_the_same_ids():
    """A name without a builder, or a builder without a name, is the finding's class."""
    assert set(BUILT_APPROACH_NAMES) == set(ap.APPROACH_IDS) == set(ap.KINDS) == set(ap.NAMES)
    assert len(ap.APPROACH_IDS) == len(set(ap.APPROACH_IDS))
