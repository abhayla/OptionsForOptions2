"""W-125 (REQ-082 AC-2..AC-6): the probability of profit, checked against calculations written separately in this file.

Core / AC-4: a single sold NIFTY put (K 22,800, premium 100, 75 units) with forward 22,900, 7 days, volatility 15 %:
breakeven = K - premium = 22,700, so the probability of profit is P(S_T > 22,700) under the lognormal model about the
forward, computed here with math.erf (not the engine's code path), to within 0.1 percentage point before rounding.
"""
from __future__ import annotations

import ast
import datetime
import math
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.pop import Unavailable, Why, probability_of_profit, whole_percent
from ofo.engine.strategy import Strategy

D = Decimal
ZERO = D(0)
EXPIRY = datetime.date(2026, 10, 6)
FORWARD, YEARS, VOL = D(22900), D(7) / D(365), D("0.15")
ROOT = Path(__file__).resolve().parents[2]


def _leg(action, kind, strike, price, expiry=EXPIRY, qty=75):
    return Leg(action=action, instrument=kind, strike=D(strike), expiry=expiry, quantity=qty, entry_price=D(price))


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _p_above(level: float) -> float:
    """P(S_T > level), ln S_T ~ N(ln F - s^2/2, s^2), s = vol sqrt(T): written independently of the engine."""
    s = float(VOL) * math.sqrt(float(YEARS))
    return 1 - _cdf((math.log(level / float(FORWARD)) + s * s / 2) / s)


def _pop(strategy, charges=ZERO):
    return probability_of_profit(strategy, forward=FORWARD, years=YEARS, vol=VOL, charges=charges)


def test_core_ac4_single_sold_put_matches_the_independent_calculation_within_a_tenth_of_a_point():
    """Core / AC-4: sold 22,800 PE at 100 -> P(S_T > 22,700), independent erf calculation, |diff| < 0.001."""
    sold_put = Strategy(legs=(_leg(Action.SELL, Instrument.PE, 22800, 100),))
    expected = _p_above(22700)
    assert 0.4 < expected < 0.9  # a real, non-trivial case, not a corner
    assert abs(float(_pop(sold_put)) - expected) < 0.001


def test_ac2_charges_move_the_breakeven_the_probability_is_net_of_charges():
    """AC-2: 150 rupees round trip on 75 units = 2 points: breakeven 22,702, so the figure is P(S_T > 22,702)."""
    sold_put = Strategy(legs=(_leg(Action.SELL, Instrument.PE, 22800, 100),))
    assert abs(float(_pop(sold_put, D(150))) - _p_above(22702)) < 0.001
    assert _pop(sold_put, D(150)) < _pop(sold_put)


def test_ac2_a_loss_between_two_zeros_counts_both_tails():
    """AC-2 (finding loss-region-inferred-from-breakevens): a bought straddle at 22,800 for 100 + 100 loses BETWEEN
    22,600 and 23,000; it profits in both tails: P(S<22,600) + P(S>23,000)."""
    straddle = Strategy(legs=(_leg(Action.BUY, Instrument.CE, 22800, 100), _leg(Action.BUY, Instrument.PE, 22800, 100)))
    expected = (1 - _p_above(22600)) + _p_above(23000)
    assert abs(float(_pop(straddle)) - expected) < 0.001


def test_ac2_a_sold_straddle_profits_only_between_the_breakevens():
    """AC-2: the same legs sold: P(22,600 < S < 23,000), the complement of the bought straddle."""
    straddle = Strategy(legs=(_leg(Action.SELL, Instrument.CE, 22800, 100), _leg(Action.SELL, Instrument.PE, 22800, 100)))
    assert abs(float(_pop(straddle)) - (_p_above(22600) - _p_above(23000))) < 0.001


def test_ac2_a_covered_call_uses_the_open_upper_tail():
    """AC-2: bought future at 22,900 + sold 23,000 CE at 60: profit when S > 22,840 (open tail capped, still profit)."""
    future = Leg(action=Action.BUY, instrument=Instrument.FUT, strike=None, expiry=EXPIRY, quantity=75,
                 entry_price=D(22900))
    covered = Strategy(legs=(future, _leg(Action.SELL, Instrument.CE, 23000, 60)))
    assert abs(float(_pop(covered)) - _p_above(22840)) < 0.001


@pytest.mark.parametrize(("forward", "years", "vol", "why"), [
    (FORWARD, YEARS, None, Why.NO_VOLATILITY), (FORWARD, YEARS, D(0), Why.NO_VOLATILITY),
    (FORWARD, None, VOL, Why.NO_VOLATILITY), (None, YEARS, VOL, Why.NO_FORWARD), (D(0), YEARS, VOL, Why.NO_FORWARD)])
def test_ac5_missing_inputs_give_a_dash_reason_never_a_number(forward, years, vol, why):
    """AC-5: no IV, no time or no forward -> Unavailable with the closed reason."""
    sold_put = Strategy(legs=(_leg(Action.SELL, Instrument.PE, 22800, 100),))
    with pytest.raises(Unavailable) as e:
        probability_of_profit(sold_put, forward=forward, years=years, vol=vol)
    assert e.value.why is why


def test_ac5_legs_on_different_expiries_give_the_mixed_expiry_reason():
    """AC-5 (attack case): mixed expiries -> a dash with the reason, never a figure."""
    mixed = Strategy(legs=(_leg(Action.SELL, Instrument.CE, 22800, 100),
                           _leg(Action.BUY, Instrument.CE, 22800, 120, expiry=datetime.date(2026, 10, 13))))
    with pytest.raises(Unavailable) as e:
        _pop(mixed)
    assert e.value.why is Why.MIXED_EXPIRIES


@pytest.mark.parametrize(("p", "percent"), [
    (D("0.614"), 61), (D("0.605"), 60), (D("0.615"), 62), (D("0.9996"), 99), (D("0.0004"), 1), (D(1), 100), (D(0), 0)])
def test_ac3_whole_percent_half_even_and_never_a_promise(p, percent):
    """AC-3: a whole percent, half-even; strictly between 0 and 1 never prints 0 or 100."""
    assert whole_percent(p) == percent


@pytest.mark.repo_scan
def test_ac6_the_figure_is_never_a_sort_or_rank_key_anywhere_in_the_backend():
    """AC-6: no sorted/sort/min/max/nlargest call whose key expression names the probability (allow-list: none)."""
    bad = []
    for path in sorted((ROOT / "backend").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "key" and any(
                            isinstance(n, (ast.Name, ast.Attribute)) and "probability_of_profit" in
                            (n.id if isinstance(n, ast.Name) else n.attr) or "pop" == (
                                n.id if isinstance(n, ast.Name) else getattr(n, "attr", ""))
                            for n in ast.walk(kw.value)):
                        bad.append(f"{path.name}:{node.lineno}")
    assert bad == []
