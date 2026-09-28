"""Core proof (W-005 round 3): parametric templates resolve and match back, with their parameters.

Spec: REQ-028 AC-3/AC-4; ADR-006 Q8 (a template is a shape the system builds from simple answers), Q52 (a leg
set fitting no template is a valid Custom Strategy); ADR-042 (NIFTY gap 50, SENSEX gap 100). R1-R14 are the
independent reviewer's reproductions (round-2 review, 2026-09-29), each with its exact expected answer.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from itertools import product

import pytest

from ofo.engine.legs import Action, Instrument, Leg
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import Custom, MatchResult, match, match_shape, template_shape
from ofo.strategy.model import EqualConstraint, OrderConstraint, SignConstraint, TemplateError, resolve_template

CATALOGUE = load_templates()
BY_ID = {t.id: t for t in CATALOGUE}
NEAR = datetime.date(2026, 10, 30)
NEXT = datetime.date(2026, 11, 27)
NIFTY = (Decimal("23200"), Decimal("50"))
SENSEX = (Decimal("79800"), Decimal("100"))

B, S = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def _leg(action: Action, instrument: Instrument, strike: str | None, qty: int = 75, expiry=NEAR) -> Leg:
    return Leg(action, instrument, None if strike is None else Decimal(strike), expiry, qty, Decimal("10"))


# (case id, market, legs, expected template id or None, expected params, expected near-miss id, reason fragment)
CASES = [
    ("R1 NIFTY condor 1 step wide", NIFTY,
     [_leg(B, PE, "23050"), _leg(S, PE, "23100"), _leg(S, CE, "23300"), _leg(B, CE, "23350")],
     "iron_condor", {"p": 2, "q": 2, "w_put": 1, "w_call": 1}, None, None),
    ("R2 NIFTY condor 3 steps wide", NIFTY,
     [_leg(B, PE, "22950"), _leg(S, PE, "23100"), _leg(S, CE, "23300"), _leg(B, CE, "23450")],
     "iron_condor", {"p": 2, "q": 2, "w_put": 3, "w_call": 3}, None, None),
    ("R3 SENSEX condor 1 step wide", SENSEX,
     [_leg(B, PE, "79500"), _leg(S, PE, "79600"), _leg(S, CE, "80000"), _leg(B, CE, "80100")],
     "iron_condor", {"p": 2, "q": 2, "w_put": 1, "w_call": 1}, None, None),
    ("R4 2-step condor shifted 3 steps off ATM", NIFTY,
     [_leg(B, PE, "23150"), _leg(S, PE, "23250"), _leg(S, CE, "23450"), _leg(B, CE, "23550")],
     "iron_condor", {"p": -1, "q": 5, "w_put": 2, "w_call": 2}, None, None),
    ("R5 bull put 1 step", NIFTY, [_leg(S, PE, "23200"), _leg(B, PE, "23150")],
     "bull_put_spread", {"k": 0, "w": 1}, None, None),
    ("R6 short strangle 12 steps each side", NIFTY, [_leg(S, CE, "23800"), _leg(S, PE, "22600")],
     "short_strangle", {"c": 12, "k": -12}, None, None),
    ("R7 butterfly 1-step wing", NIFTY,
     [_leg(B, CE, "23150"), _leg(S, CE, "23200", 150), _leg(B, CE, "23250")],
     "butterfly_spread", {"m": 0, "w": 1}, None, None),
    ("R8 ITM short put is not a Cash-Secured Put", NIFTY, [_leg(S, PE, "24000")],
     None, None, "cash_secured_put", "sign constraint"),
    ("R9 straddle 36 steps off ATM is not Straddle (Short)", NIFTY, [_leg(S, CE, "25000"), _leg(S, PE, "25000")],
     None, None, "short_straddle", "strikes do not fit"),
    ("R10 FUT + ITM short call is not a Covered Call", NIFTY, [_leg(B, FUT, None), _leg(S, CE, "22000")],
     None, None, "covered_call", "outside its bounds"),
    ("R11 condor with unequal wings", NIFTY,
     [_leg(B, PE, "23000"), _leg(S, PE, "23100"), _leg(S, CE, "23300"), _leg(B, CE, "23450")],
     None, None, "iron_condor", "equal constraint"),
    ("R12 reverse calendar is not a Calendar Spread", NIFTY,
     [_leg(B, CE, "23200", expiry=NEAR), _leg(S, CE, "23200", expiry=NEXT)], None, None, None, None),
    ("R13 strike off the strike grid", NIFTY, [_leg(S, PE, "23025")], None, None, None, None),
    ("R14 bull call spread in a 1:3 ratio", NIFTY, [_leg(B, CE, "23200"), _leg(S, CE, "23300", 225)],
     None, None, "bull_call_spread", "quantity ratio"),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_reviewer_reproductions(case):
    """AC-4: R1-R14 give the exact template and parameters, or Custom with the named near miss and reason."""
    _, (spot, gap), legs, template_id, params, near_id, reason = case
    result = match(legs, spot=spot, strike_gap=gap, templates=CATALOGUE)
    if template_id is not None:
        assert isinstance(result, MatchResult)
        assert result.template.id == template_id
        assert dict(result.params) == params
        assert result.base_quantity == 75
        return
    assert isinstance(result, Custom)
    assert result.label == "Custom Strategy"
    if near_id is None:
        return
    near = {n.template.id: n.reason for n in result.nearest}
    assert near_id in near
    assert reason in near[near_id]


def _sweep_points(template):
    """One-at-a-time sweep of each param over its bounds within -8..8, then widths 1..6 x distances 0..8
    (both signs) applied together."""
    defaults = template.defaults()
    points = []
    for param in template.params:
        for value in range(max(param.min, -8), min(param.max, 8) + 1):
            points.append({**defaults, param.name: value})
    widths = [p.name for p in template.params if p.must_be_positive]
    distances = [p.name for p in template.params if not p.must_be_positive]
    for width, distance in product(range(1, 7), range(0, 9)):
        for signs in product((1, -1), repeat=len(distances)):
            point = dict(defaults)
            point.update({name: width for name in widths})
            point.update({name: sign * distance for name, sign in zip(distances, signs)})
            points.append(point)
    return points


@pytest.mark.parametrize("market", [NIFTY, SENSEX], ids=["NIFTY-50", "SENSEX-100"])
@pytest.mark.parametrize("template_id", sorted(BY_ID))
def test_round_trip_resolve_then_match(template_id, market):
    """AC-3/AC-4 property: for every template, every allowed parameter set resolves and matches back to the
    same template with the same parameters; every disallowed set is refused by resolve."""
    template = BY_ID[template_id]
    spot, gap = market
    expiries = {"near": NEAR, "next": NEXT}
    prices = [Decimal("10")] * len(template.legs)
    checked = refused = 0
    for point in _sweep_points(template):
        if template.violations(point):
            with pytest.raises(TemplateError):
                resolve_template(template, spot=spot, strike_gap=gap, expiries=expiries, prices=prices,
                                 base_quantity=75, overrides=point)
            refused += 1
            continue
        strategy = resolve_template(template, spot=spot, strike_gap=gap, expiries=expiries, prices=prices,
                                    base_quantity=75, overrides=point)
        result = match(strategy, spot=spot, strike_gap=gap, templates=CATALOGUE)
        assert isinstance(result, MatchResult), (template_id, point, result)
        assert (result.template.id, dict(result.params), result.base_quantity) == (template_id, point, 75)
        checked += 1
    assert checked > 0


def test_core_iron_condor_across_widths_and_distances():
    """Core: the Iron Condor round-trips for widths 1..6 and distances 0..8 at both real strike gaps."""
    template = BY_ID["iron_condor"]
    count = 0
    for (spot, gap), w, d in product([NIFTY, SENSEX], range(1, 7), range(1, 9)):
        values = {"p": d, "q": d, "w_put": w, "w_call": w}
        strategy = resolve_template(template, spot=spot, strike_gap=gap, expiries={"near": NEAR},
                                    prices=[Decimal("10")] * 4, base_quantity=75, overrides=values)
        result = match(strategy, spot=spot, strike_gap=gap, templates=CATALOGUE)
        assert result.template.id == "iron_condor" and dict(result.params) == values
        count += 1
    assert count == 96


# --- Mutation tests: removing each constraint kind makes a known-wrong leg set match. --------------------


def _without(template, kind):
    kept = tuple(c for c in template.constraints if not isinstance(c, kind))
    assert len(kept) < len(template.constraints)
    return dataclasses.replace(template, constraints=kept)


def test_mutation_equal_constraint_is_load_bearing():
    """Unequal-wing condor: refused by the real template, accepted once the equal constraint is removed."""
    condor = BY_ID["iron_condor"]
    shape = template_shape(condor, {"p": 2, "q": 2, "w_put": 2, "w_call": 3})
    assert isinstance(match_shape(shape, [condor]), Custom)
    assert isinstance(match_shape(shape, [_without(condor, EqualConstraint)]), MatchResult)


def test_mutation_order_constraint_is_load_bearing():
    """Condor whose short put is not below its short call: refused, accepted without the order constraint."""
    condor = BY_ID["iron_condor"]
    shape = template_shape(condor, {"p": -3, "q": 2, "w_put": 2, "w_call": 2})
    assert isinstance(match_shape(shape, [condor]), Custom)
    assert isinstance(match_shape(shape, [_without(condor, OrderConstraint)]), MatchResult)


def test_mutation_sign_constraint_is_load_bearing():
    """ITM short put: refused as a Cash-Secured Put, accepted once the sign constraint is removed."""
    csp = BY_ID["cash_secured_put"]
    shape = template_shape(csp, {"k": 16})
    assert isinstance(match_shape(shape, [csp]), Custom)
    assert isinstance(match_shape(shape, [_without(csp, SignConstraint)]), MatchResult)


def test_mutation_bounds_are_load_bearing():
    """A 30-step-wide bull call spread is outside the width bound (max 20); widening the bound accepts it."""
    spread = BY_ID["bull_call_spread"]
    shape = template_shape(spread, {"k": 0, "w": 30})
    assert isinstance(match_shape(shape, [spread]), Custom)
    widened = dataclasses.replace(
        spread, params=tuple(dataclasses.replace(p, max=40) if p.name == "w" else p for p in spread.params)
    )
    assert isinstance(match_shape(shape, [widened]), MatchResult)


def test_resolve_overrides_fail_closed():
    """Red cases: unknown param, out-of-bounds value, a broken constraint, a bool, each raise TemplateError."""
    condor = BY_ID["iron_condor"]
    kwargs = dict(spot=NIFTY[0], strike_gap=NIFTY[1], expiries={"near": NEAR}, prices=[Decimal("10")] * 4)
    for overrides in ({"width": 2}, {"w_put": 0, "w_call": 0}, {"w_put": 2, "w_call": 3}, {"p": True}, {"p": 99}):
        with pytest.raises(TemplateError):
            resolve_template(condor, overrides=overrides, **kwargs)
