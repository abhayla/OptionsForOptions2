"""Match a resolved leg set back to the template (if any) it came from (AC-4).

Spec: spec/requirements/REQ-028.md AC-4 -- "Any combination not matching a template is valid as a Custom
Strategy (Q52)." Matching is **structural**: it never uses the current spot or an absolute at-the-money
strike. Two strategies with the same shape (same actions, instruments, expiry order, and strike spacing
between legs, same quantity ratios) match the same template regardless of where that shape sits on the
strike ladder -- shifting a whole Iron Condor two strikes away from today's ATM does not stop it being an
Iron Condor. Legs that share (action, instrument, relative strike offset, expiry rank) are merged by
summed quantity before comparing, so one SELL leg of quantity 2 and two SELL legs of quantity 1 at the
same strike read identically (a Butterfly's middle strike, sold twice).
"""
from __future__ import annotations

from fractions import Fraction
from math import gcd
from typing import Sequence

from ofo.engine.legs import Instrument
from ofo.engine.strategy import Strategy
from ofo.strategy.model import EXPIRY_SLOTS, Template

CUSTOM_STRATEGY = "Custom Strategy"

# (action, instrument, offset_steps, expiry_rank) -- the merge key before quantities are folded in.
_MergeKey = tuple[object, object, int, int]


def _merge(raw: list[tuple[_MergeKey, int]]) -> dict[_MergeKey, int]:
    """Sum quantities for legs sharing one (action, instrument, offset, expiry_rank) key."""
    merged: dict[_MergeKey, int] = {}
    for key, quantity in raw:
        merged[key] = merged.get(key, 0) + quantity
    return merged


def _normalize(merged: dict[_MergeKey, int]) -> frozenset[tuple[object, object, int, int, Fraction]]:
    """Translation-invariant, ratio-invariant shape: subtract the minimum option offset used, and
    express every quantity as a ratio to the smallest quantity present (so absolute lot size and
    absolute strike position never matter, only the pattern)."""
    option_offsets = [offset for (_, instrument, offset, _), _ in merged.items() if instrument is not Instrument.FUT]
    min_offset = min(option_offsets) if option_offsets else 0

    quantities = list(merged.values())
    base = quantities[0]
    for q in quantities[1:]:
        base = gcd(base, q)

    shape: set[tuple[object, object, int, int, Fraction]] = set()
    for (action, instrument, offset, expiry_rank), quantity in merged.items():
        relative_offset = 0 if instrument is Instrument.FUT else offset - min_offset
        shape.add((action, instrument, relative_offset, expiry_rank, Fraction(quantity, base)))
    return frozenset(shape)


def _strategy_shape(strategy: Strategy, *, strike_gap) -> frozenset | None:
    """The strategy's legs as a translation-invariant shape, or ``None`` if not on this ``strike_gap``."""
    distinct_expiries = sorted({leg.expiry for leg in strategy.legs})
    if len(distinct_expiries) > len(EXPIRY_SLOTS):
        return None  # no template in this catalogue shape spans more slots than EXPIRY_SLOTS
    expiry_rank = {expiry: i for i, expiry in enumerate(distinct_expiries)}

    raw: list[tuple[_MergeKey, int]] = []
    for leg in strategy.legs:
        if leg.instrument is Instrument.FUT:
            offset_steps = 0
        else:
            offset = (leg.strike) / strike_gap
            if offset != offset.to_integral_value():
                return None  # strike isn't on this grid's steps -- can't match any template
            offset_steps = int(offset)
        raw.append(((leg.action, leg.instrument, offset_steps, expiry_rank[leg.expiry]), leg.quantity))
    return _normalize(_merge(raw))


def _template_shape(template: Template) -> frozenset:
    """A template's legs as the same translation-invariant shape, keyed by EXPIRY_SLOTS' canonical
    order (not the order slots first appear in the file -- a reverse calendar and a calendar are not
    the same shape, and a calendar written next-leg-first must still match itself)."""
    slot_rank = {slot: EXPIRY_SLOTS.index(slot) for slot in {leg.expiry_slot for leg in template.legs}}
    raw: list[tuple[_MergeKey, int]] = [
        (
            (leg.action, leg.instrument, leg.offset_steps, slot_rank[leg.expiry_slot]),
            leg.quantity_multiplier,
        )
        for leg in template.legs
    ]
    return _normalize(_merge(raw))


def match_template(strategy: Strategy, templates: Sequence[Template], *, strike_gap) -> Template | None:
    """Return the first catalogue template ``strategy`` structurally matches, or ``None`` (Custom Strategy).

    Structural = translation-invariant on the strike ladder (an Iron Condor shifted away from today's
    ATM is still an Iron Condor) and merge-invariant on quantity (one leg of quantity 2 reads the same
    as two legs of quantity 1 at the same strike). Two or more templates can share one shape (this
    catalogue's ``cash_secured_put`` has the same single-leg shape as a hypothetical repeat entry); the
    first match in ``templates`` order wins, deterministically.
    """
    candidate = _strategy_shape(strategy, strike_gap=strike_gap)
    if candidate is None:
        return None
    for template in templates:
        if _template_shape(template) == candidate:
            return template
    return None
