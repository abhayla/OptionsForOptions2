"""W-066 round 8 (ADR-072, REQ-034 AC-7; verifier's shape E): a profit stretch between two loss regions that is
narrower than the 0.01 display step is never merged away - it is reported as the region's "except" level.

The shapes are GENERATED. Each starts from a round-7 style target (zero touches Z1..Zm at strikes, dips between them,
bounded or open on each side, every slope from SLOPES) and is then lifted by a constant +q per unit with a pair of
legs that cancel in slope (SELL 1 lot CE at Z1 @ q, BUY 1 lot CE at Z1 @ 0) - the same trick as shape E. Each touch
becomes a profit peak of +q whose zeros sit q/s_left below and q/s_right above it, so the profit stretch is
q*(1/s_left + 1/s_right) wide: 0.0008 to 0.0091 points for q <= 0.05 and slopes 11-25, always under a paisa.

Two members of the class: with a slope of 11, 13 or 21 the zeros do not terminate in decimal, both round to the peak
level and the stretch must come back as an "except" level (shape E); with 12, 20 or 25 the zeros are exact and the
stretch is the gap between two separately named regions. Either way it is reported, never merged away.

Expected values never come from the code under test:
- each peak Z (from the construction) is either an except level or lies strictly between two named regions;
- a brute-force scan of `Strategy.expiry_pnl_at` (the locked per-level formula) on a 0.001-point grid around every
  strike and a 2.5-point grid over the whole range decides the sign at every level; the sentence must agree at every
  scanned level except within half a display step (0.005) of a level it names (an edge or an except level);
- every except level's own P&L is >= 0, exactly;
- the scan proves each stretch really is sub-paisa: P&L(Z) > 0 > P&L(Z - 0.01) and P&L(Z + 0.01).
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
SEED = 20261015 + 8
DRAWS = 10  # per (m, lower kind, upper kind): 3 x 2 x 2 x 10 = 120 shapes
SLOPES = (11, 12, 13, 20, 21, 25)  # 11/13/21: edges that do not terminate (round onto the peak); 12/20/25: exact edges
LIFTS = (D("0.01"), D("0.02"), D("0.03"), D("0.05"))
FINE, STEP, HALF = D("0.001"), D("0.01"), D("0.005")


def _target(rng: random.Random, m: int, bounded_lo: bool, bounded_hi: bool):
    """(knots [(level, per-unit value)], slope below the first knot, slope above the last, touch levels)."""
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
        s_below = -c
    else:
        s_below = b
    if bounded_hi:
        h2, c2 = rng.choice((100, 200)), rng.choice(SLOPES)
        knots.append((z[-1] + h2, -b2 * h2))
        s_above = c2
    else:
        s_above = -b2
    return knots, s_below, s_above, z


def _target_at(knots, s_below: int, s_above: int, x: Fraction) -> Fraction:
    if x <= knots[0][0]:
        return knots[0][1] + s_below * (x - knots[0][0])
    if x >= knots[-1][0]:
        return knots[-1][1] + s_above * (x - knots[-1][0])
    for (x0, v0), (x1, v1) in zip(knots, knots[1:]):
        if x0 <= x <= x1:
            return v0 + Fraction(v1 - v0, x1 - x0) * (x - x0)
    raise AssertionError("unreachable")


def _legs(rng: random.Random, knots, s_below: int, s_above: int) -> list[Leg] | None:
    """Legs whose per-unit expiry P&L is the target: FUT for the linear part, one CE or PE per kink; None when the
    draw leaves no FUT slope or a FUT entry that is not a positive 2-decimal price (the caller redraws)."""
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
    return legs


def _shapes():
    rng = random.Random(SEED)
    for m in (1, 2, 3):
        for bounded_lo in (True, False):
            for bounded_hi in (True, False):
                made = 0
                while made < DRAWS:
                    knots, s_below, s_above, z = _target(rng, m, bounded_lo, bounded_hi)
                    legs = _legs(rng, knots, s_below, s_above)
                    if legs is None:
                        continue
                    q = rng.choice(LIFTS)  # the shape E pair: +q per unit everywhere, no slope change
                    legs += [Leg(Action.SELL, Instrument.CE, D(z[0]), EXP, UNIT, q),
                             Leg(Action.BUY, Instrument.CE, D(z[0]), EXP, UNIT, D(0))]
                    made += 1
                    yield m, bounded_lo, bounded_hi, knots, z, q, Strategy(tuple(legs))


SHAPES = list(_shapes())


def _says_losing(regions, x: D) -> bool:
    for lo, hi, *excepts in regions:
        if (lo is None or x > lo) and (hi is None or x < hi):
            return not (excepts and x in excepts[0])
    return False


def _stated_levels(regions) -> set[D]:
    out: set[D] = set()
    for lo, hi, *excepts in regions:
        out |= {v for v in (lo, hi) if v is not None}
        if excepts:
            out |= set(excepts[0])
    return out


def _scan_levels(knots, z) -> list[D]:
    levels: list[D] = []
    for strike in z:
        levels += [D(strike) + FINE * k for k in range(-20, 21)]
    x, top = D(max(knots[0][0] - 2000, 0)), D(knots[-1][0] + 2000)
    while x <= top:
        levels.append(x)
        x += D("2.5")
    return levels + [D(0), top + D(10) ** 9]


def test_the_generator_covers_every_class_member() -> None:
    """AC-7: 1, 2 and 3 sub-paisa profit stretches x bounded/open below x bounded/open above, BUY+SELL, CE/PE/FUT."""
    kinds = {(m, lo, hi) for m, lo, hi, *_ in SHAPES}
    assert kinds == {(m, lo, hi) for m in (1, 2, 3) for lo in (True, False) for hi in (True, False)}
    legs = [leg for *_, s in SHAPES for leg in s.legs]
    assert {leg.instrument for leg in legs} == set(Instrument)
    assert {leg.action for leg in legs} == set(Action)
    assert len(SHAPES) == 12 * DRAWS


@pytest.mark.parametrize("index", range(len(SHAPES)))
def test_ac7_a_profit_stretch_narrower_than_a_paisa_is_reported_never_merged_away(index: int) -> None:
    """AC-7: every sub-paisa profit stretch is named (as an except level); the sentence agrees with a brute-force
    0.001-point scan at every level, read at 0.01."""
    m, bounded_lo, bounded_hi, knots, z, q, strategy = SHAPES[index]
    for x, v in knots:  # the synthesis is right: the locked per-level P&L equals the lifted target at every knot
        assert strategy.expiry_pnl_at(D(x)) == (D(v) + q) * UNIT, (x, v)
    for strike in z:  # the stretch is real and narrower than the display step
        assert strategy.expiry_pnl_at(D(strike)) > 0
        assert strategy.expiry_pnl_at(D(strike) - STEP) < 0 and strategy.expiry_pnl_at(D(strike) + STEP) < 0
    regions = strategy_metrics(strategy).loss_regions
    assert (regions[0][0] is None) is (not bounded_lo) and (regions[-1][1] is None) is (not bounded_hi)
    excepts = [lvl for _, _, *ex in regions for lvl in (ex[0] if ex else ())]
    gaps = [(a[1], b[0]) for a, b in zip(regions, regions[1:])]
    for strike in map(D, z):  # every stretch is reported: the peak is never called a loss (no tolerance here)
        assert not _says_losing(regions, strike), (strike, regions)
        assert strike in excepts or any(hi <= strike <= lo for hi, lo in gaps), (strike, regions)
    for hi, lo in gaps:  # never "below 22,400.00 or above 22,400": two named regions never print as touching
        assert hi.quantize(STEP) < lo.quantize(STEP), regions
    for level in excepts:
        assert strategy.expiry_pnl_at(level) >= 0, level  # an except level is never a loss
    stated = _stated_levels(regions)
    mismatches = [x for x in _scan_levels(knots, z)
                  if (strategy.expiry_pnl_at(x) < 0) != _says_losing(regions, x)
                  and not any(abs(x - s) <= HALF for s in stated)]
    assert mismatches == [], (regions, mismatches[:5])
    text = str(_start_losing(regions, "NIFTY"))
    assert text.endswith("at expiry.") and all(f"{s:,}" in text for s in excepts)


def test_both_members_of_the_class_are_generated() -> None:
    """AC-7: the generated set holds stretches whose edges do not terminate (rounded to 0.01) AND stretches with an
    exact edge finer than 0.01 (e.g. 22,399.995) - both print as the peak level at the display step."""
    kinds = set()
    for _, _, _, _, z, _, strategy in SHAPES:
        near = [b for b in strategy_metrics(strategy).breakevens if any(abs(b - D(s)) < STEP for s in z)]
        kinds |= {"exact" if b.as_tuple().exponent < -2 else "rounded" for b in near}
    assert kinds == {"exact", "rounded"}


def test_ac7_without_the_fix_the_shape_e_class_reads_every_level() -> None:
    """AC-7 (negative control): the scan check is not vacuous - the pre-round-8 answer for the first shape (one region,
    no except level) is called out as a mismatch at the strike, where the P&L is +q per unit."""
    _, _, _, knots, z, q, strategy, regions = next(
        (*s, r) for s in SHAPES if len(r := strategy_metrics(s[-1]).loss_regions) == 1 and len(r[0]) == 3)
    stripped = tuple(r[:2] for r in regions)
    strike = D(z[0])
    assert not any(abs(strike - s) <= HALF for s in _stated_levels(stripped))  # no edge excuses the mismatch
    assert strategy.expiry_pnl_at(strike) == q * UNIT
    assert _says_losing(stripped, strike) and not _says_losing(regions, strike)
