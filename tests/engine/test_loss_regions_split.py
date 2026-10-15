"""W-066 round 7 (issue #172, ADR-072, REQ-034 AC-7): a loss split by single zero points is ONE region carrying those
points as "except" levels - bounded and unbounded, at 1, 2 and 3 strikes - checked against a brute-force scan.

The shapes are GENERATED, not hand-listed. Each is a target payoff written by hand as knots (level, per-unit P&L):
zero touches Z1..Zm at strikes, a dip of -a*gap/2 at each midpoint, and on each side either an open loss (slope away
from zero to the end of the range: unbounded) or a turn back up through zero at a crossing (bounded). The target is
synthesised from legs (one FUT for the linear part, one CE or PE per kink, chosen at random; BUY or SELL by the sign of
the slope change), so every shape mixes BUY/SELL and CE/PE/FUT.

Expected values come from the construction and the scan, never from the code under test:
- the region bounds are the hand-solved crossings (L - b*h/c below, R + b'*h'/c' above) or None when open;
- the except levels are exactly Z1..Zm;
- the brute-force scan of `Strategy.expiry_pnl_at` (the locked per-level formula) on a 2.5-point grid agrees with
  "inside a region and not an except level" at every grid level, and the scan equals the target at every knot.
"""
from __future__ import annotations

import datetime
import random
from decimal import Decimal as D
from fractions import Fraction

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy, strategy_metrics
from ofo.outcome.service import _start_losing

EXP = datetime.date(2026, 10, 13)
UNIT = 65
SEED = 20261015
DRAWS = 30  # per (m, lower kind, upper kind): 3 x 2 x 2 x 30 = 360 shapes
SLOPES = (1, 2, 4)  # per-unit slopes; every crossing and FUT entry then terminates within 2 decimals


def _target(rng: random.Random, m: int, bounded_lo: bool, bounded_hi: bool):
    """(knots [(level, value)], slope below the first knot, slope above the last, expected regions)."""
    z = [rng.choice(range(21800, 22401, 100))]
    knots: list[tuple[int, int]] = []
    for _ in range(m - 1):
        gap = rng.choice((200, 300, 400))
        a = rng.choice(SLOPES)
        knots += [(z[-1], 0), (z[-1] + gap // 2, -a * gap // 2)]
        z.append(z[-1] + gap)
    knots.append((z[-1], 0))
    b, b2 = rng.choice(SLOPES), rng.choice(SLOPES)
    if bounded_lo:
        h, c = rng.choice((100, 200)), rng.choice(SLOPES)
        knots.insert(0, (z[0] - h, -b * h))
        s_below, lo = -c, D(z[0] - h) - D(b * h) / D(c)
    else:
        s_below, lo = b, None
    if bounded_hi:
        h2, c2 = rng.choice((100, 200)), rng.choice(SLOPES)
        knots.append((z[-1] + h2, -b2 * h2))
        s_above, hi = c2, D(z[-1] + h2) + D(b2 * h2) / D(c2)
    else:
        s_above, hi = -b2, None
    excepts = tuple(D(x) for x in z)
    return knots, s_below, s_above, ((lo, hi, excepts),)


def _target_at(knots, s_below: int, s_above: int, x: Fraction) -> Fraction:
    if x <= knots[0][0]:
        return knots[0][1] + s_below * (x - knots[0][0])
    if x >= knots[-1][0]:
        return knots[-1][1] + s_above * (x - knots[-1][0])
    for (x0, v0), (x1, v1) in zip(knots, knots[1:]):
        if x0 <= x <= x1:
            return v0 + Fraction(v1 - v0, x1 - x0) * (x - x0)
    raise AssertionError("unreachable")


def _legs(rng: random.Random, knots, s_below: int, s_above: int) -> tuple[Leg, ...] | None:
    """Legs whose per-unit expiry P&L is the target: FUT for the linear part, one CE or PE per kink; None if the
    random CE/PE choice leaves no FUT slope or a FUT entry that is not a positive price (the caller redraws)."""
    slopes = [s_below] + [Fraction(v1 - v0, x1 - x0) for (x0, v0), (x1, v1) in zip(knots, knots[1:])] + [s_above]
    legs, linear, const = [], Fraction(s_below), _target_at(knots, s_below, s_above, Fraction(0))
    for (x, _), left, right in zip(knots, slopes, slopes[1:]):
        delta = right - left
        if delta == 0:
            continue
        assert delta.denominator == 1
        put = rng.random() < 0.5
        if put:  # max(S-x,0) = (S - x) + max(x-S,0): a PE carries the kink, the FUT the extra slope
            linear += delta
            const -= delta * x
        legs.append(Leg(Action.BUY if delta > 0 else Action.SELL, Instrument.PE if put else Instrument.CE, D(x), EXP,
                        UNIT * abs(int(delta)), D(0)))
    if linear == 0:
        return None
    entry = -const / linear  # FUT P&L per unit: linear * (S - entry)
    if entry <= 0 or (entry * 100).denominator != 1:
        return None
    legs.append(Leg(Action.BUY if linear > 0 else Action.SELL, Instrument.FUT, None, EXP, UNIT * abs(int(linear)),
                    D(entry.numerator) / D(entry.denominator)))
    return tuple(legs)


def _shapes():
    rng = random.Random(SEED)
    for m in (1, 2, 3):
        for bounded_lo in (True, False):
            for bounded_hi in (True, False):
                made = 0
                while made < DRAWS:
                    knots, s_below, s_above, expected = _target(rng, m, bounded_lo, bounded_hi)
                    legs = _legs(rng, knots, s_below, s_above)
                    if legs is None:
                        continue
                    made += 1
                    yield m, bounded_lo, bounded_hi, knots, s_below, s_above, expected, Strategy(legs)


SHAPES = list(_shapes())


def _losing(regions, x: D) -> bool:
    for lo, hi, *excepts in regions:
        if (lo is None or x > lo) and (hi is None or x < hi):
            return not (excepts and x in excepts[0])
    return False


def test_the_generator_covers_every_class_member() -> None:
    """AC-7: 1, 2 and 3 split points x bounded/open below x bounded/open above, with BUY+SELL and CE, PE and FUT."""
    kinds = {(m, lo, hi) for m, lo, hi, *_ in SHAPES}
    assert kinds == {(m, lo, hi) for m in (1, 2, 3) for lo in (True, False) for hi in (True, False)}
    legs = [leg for *_, s in SHAPES for leg in s.legs]
    assert {leg.instrument for leg in legs} == set(Instrument)
    assert {leg.action for leg in legs} == set(Action)
    assert len(SHAPES) == 12 * DRAWS


@pytest.mark.parametrize("index", range(len(SHAPES)))
def test_ac7_a_loss_split_by_single_zero_points_is_one_region_with_except_levels(index: int) -> None:
    """AC-7: regions equal the hand-solved shape, agree with a brute-force scan, and render without raising."""
    m, bounded_lo, bounded_hi, knots, s_below, s_above, expected, strategy = SHAPES[index]
    for x, v in knots:  # the synthesis is right: the locked per-level P&L equals the hand target at every knot
        assert strategy.expiry_pnl_at(D(x)) == D(v * UNIT), (x, v)
    regions = strategy_metrics(strategy).loss_regions
    if expected[0][:2] == (None, None):
        expected = ((None, None, expected[0][2]),)
    assert regions == expected
    x, top = D(max(knots[0][0] - 2000, 0)), D(knots[-1][0] + 2000)
    while x <= top:
        assert _losing(regions, x) == (strategy.expiry_pnl_at(x) < 0), (x, regions)
        x += D("2.5")
    for far in (D(0), top + D(10) ** 9):
        assert _losing(regions, far) == (strategy.expiry_pnl_at(far) < 0), (far, regions)
    text = str(_start_losing(regions, "NIFTY"))
    assert "except exactly" in text and text.endswith("at expiry.")
    assert all(f"{int(z):,}" in text for z in expected[0][2])  # every split level is named (5-digit grouping)
