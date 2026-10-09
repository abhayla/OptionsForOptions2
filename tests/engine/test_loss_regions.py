"""W-066 round 5 (ADR-072): the engine's expiry LOSS REGIONS (P&L below zero) equal a brute-force scan of the payoff.

A seeded property test over 400+ random strategies; a scan ceiling that is too low clips far breakevens (the review saw
6 false mismatches at +1,000), so the scan runs to the highest strike + 10,000 and the far tail is checked by sign.
"""
import datetime
import random
from decimal import Decimal as D

from ofo.engine import Action, Instrument, Leg, Strategy, strategy_metrics

EXP = datetime.date(2026, 10, 13)
STRIKES = [D(k) for k in range(21500, 23501, 50)]
ENTRIES = [D(e) for e in (0, 25, 50, 100, 150, 200)]
SEED = 20261009
N = 600
UNIT = 65


def _random_strategy(rng: random.Random) -> Strategy:
    legs = []
    for _ in range(rng.randint(1, 4)):
        legs.append(Leg(rng.choice((Action.BUY, Action.SELL)), rng.choice((Instrument.CE, Instrument.PE)),
                        rng.choice(STRIKES), EXP, UNIT * rng.randint(1, 2), rng.choice(ENTRIES)))
    return Strategy(tuple(legs))


def _inside(regions, x: D) -> bool:
    return any((lo is None or x > lo) and (hi is None or x < hi) for lo, hi in regions)


def _check(strategy: Strategy) -> None:
    regions = strategy_metrics(strategy).loss_regions
    top = max(leg.strike for leg in strategy.legs)
    # shape: ordered, disjoint, non-empty; only the first may be open below and only the last open above
    for i, (lo, hi) in enumerate(regions):
        assert lo is None or hi is None or lo < hi
        assert lo is not None or i == 0
        assert hi is not None or i == len(regions) - 1
        if i:
            assert regions[i - 1][1] is not None and lo is not None and regions[i - 1][1] <= lo
    x = D(0)
    while x <= top + 10000:
        assert _inside(regions, x) == (strategy.expiry_pnl_at(x) < 0), (strategy.legs, regions, x)
        x += D("2.5")
    far = top + D(10) ** 9
    assert _inside(regions, far) == (strategy.expiry_pnl_at(far) < 0), (strategy.legs, regions, "far tail")


def test_loss_regions_equal_a_brute_force_scan_for_random_strategies():
    rng = random.Random(SEED)
    for _ in range(N):
        _check(_random_strategy(rng))


def _leg(action, instrument, strike, entry, qty=UNIT):
    return Leg(action, instrument, D(strike), EXP, qty, D(entry))


def _regions(*legs):
    return strategy_metrics(Strategy(legs)).loss_regions


B, S, CE, PE = Action.BUY, Action.SELL, Instrument.CE, Instrument.PE


def test_a_zero_cost_bull_put_spread_loses_below_22400_only():
    assert _regions(_leg(S, PE, 22400, 100), _leg(B, PE, 22200, 100)) == ((None, D(22400)),)


def test_a_butterfly_costing_its_width_loses_everywhere_but_22300():
    fly = _regions(_leg(B, CE, 22200, 200), _leg(S, CE, 22300, 100, 2 * UNIT), _leg(B, CE, 22400, 100))
    assert fly == ((None, D(22300)), (D(22300), None))


def test_a_zero_cost_bull_call_spread_has_no_loss_region():
    assert _regions(_leg(B, CE, 22800, 100), _leg(S, CE, 23000, 100)) == ()


def test_a_strategy_that_loses_everywhere_is_one_open_region():
    assert _regions(_leg(B, PE, 22400, 300), _leg(S, PE, 22200, 50)) == ((None, None),)


def test_a_sub_paisa_loss_is_still_a_loss_signs_are_decided_before_rounding():
    """Long 22400 CE at 0.01 per unit: the P&L is -0.01 up to 22,400, so the loss is real though it rounds to 0 at one decimal of rupee."""
    assert _regions(_leg(B, CE, 22400, "0.01", 1)) == ((None, D("22400.01")),)


def test_a_put_ratio_has_one_loss_region_below_its_lower_zero():
    assert _regions(_leg(B, PE, 22400, 100), _leg(S, PE, 22200, 50, 2 * UNIT)) == ((None, D(22000)),)
