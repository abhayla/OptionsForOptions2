"""Match a resolved leg set back to the template (if any) it came from (AC-4).

Spec: spec/requirements/REQ-028.md AC-4 -- "Any combination not matching a template is valid as a Custom
Strategy (Q52)." Matching needs the same ``spot``/``strike_gap`` context the resolver used, because a
template's legs are stored relative to the at-the-money strike, not as absolute strikes.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from fractions import Fraction
from math import gcd
from typing import Sequence

from ofo.engine.legs import Instrument
from ofo.engine.strategy import Strategy
from ofo.strategy.model import Template, atm_strike

CUSTOM_STRATEGY = "Custom Strategy"


def _strategy_signature(strategy: Strategy, *, spot: Decimal, strike_gap: Decimal) -> Counter | None:
    """The strategy's legs as a comparable multiset, or ``None`` if it can't be expressed on this grid."""
    atm = atm_strike(spot, strike_gap)
    distinct_expiries = sorted({leg.expiry for leg in strategy.legs})
    if len(distinct_expiries) > 2:
        return None  # no template in this catalogue shape spans more than near/next
    expiry_rank = {expiry: i for i, expiry in enumerate(distinct_expiries)}

    quantities = [leg.quantity for leg in strategy.legs]
    base = quantities[0]
    for q in quantities[1:]:
        base = gcd(base, q)

    signature: Counter = Counter()
    for leg in strategy.legs:
        if leg.instrument is Instrument.FUT:
            offset_steps = 0
        else:
            offset = (leg.strike - atm) / strike_gap
            if offset != offset.to_integral_value():
                return None  # strike isn't on this grid's steps -- can't match any template
            offset_steps = int(offset)
        ratio = Fraction(leg.quantity, base)
        signature[(leg.action, leg.instrument, offset_steps, expiry_rank[leg.expiry], ratio)] += 1
    return signature


def _template_signature(template: Template) -> Counter:
    multipliers = [leg.quantity_multiplier for leg in template.legs]
    base = multipliers[0]
    for m in multipliers[1:]:
        base = gcd(base, m)
    slot_rank = {slot: i for i, slot in enumerate(dict.fromkeys(leg.expiry_slot for leg in template.legs))}
    signature: Counter = Counter()
    for leg in template.legs:
        ratio = Fraction(leg.quantity_multiplier, base)
        signature[(leg.action, leg.instrument, leg.offset_steps, slot_rank[leg.expiry_slot], ratio)] += 1
    return signature


def match_template(
    strategy: Strategy, templates: Sequence[Template], *, spot: Decimal, strike_gap: Decimal
) -> Template | None:
    """Return the first cataloque template ``strategy`` structurally matches, or ``None`` (Custom Strategy).

    Two or more templates can share one leg set (this catalogue's ``cash_secured_put`` and
    ``wheel_strategy`` both resolve to a single short OTM put); the first match in ``templates`` order
    wins, deterministically.
    """
    candidate = _strategy_signature(strategy, spot=spot, strike_gap=strike_gap)
    if candidate is None:
        return None
    for template in templates:
        if _template_signature(template) == candidate:
            return template
    return None
