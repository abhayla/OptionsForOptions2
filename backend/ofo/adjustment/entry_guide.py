"""ADR-300 (applies ADR-216; ADR-003): the entry-guide check of a strategy's sold legs, in three states.

The guide is the playbook's own ``guards.entry_guide`` text ("shorts at 0.15 to 0.20 delta, wings ..."); its delta range
is read from that text, never typed here. The sold-leg delta is ``playbook_eval.sold_leg_delta`` (T-03's own measure).
A strategy that breaks the guide still shows and still saves: the line is a fact with both numbers, no advice.
Pure: no database, no clock.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.adjustment.playbook_eval import ShortLeg, sold_leg_delta
from ofo.errors.explanations import render_explanation

_RANGE = re.compile(r"\bshorts at (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?) delta\b")


def parse_entry_guide(text: str | None) -> tuple[Decimal, Decimal] | None:
    """The (low, high) delta range the guide text states; None when it states none (or a reversed one)."""
    m = _RANGE.search(text or "")
    if m is None:
        return None
    low, high = Decimal(m.group(1)), Decimal(m.group(2))
    return (low, high) if low <= high else None


@dataclass(frozen=True)
class EntryGuideCheck:
    state: Literal["breaks", "within", "unknown"]
    kind: str | None = None  # "CE" / "PE": the side whose delta is shown
    delta: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None


def check_entry_guide(shorts: Sequence[ShortLeg], guide_text: str | None) -> EntryGuideCheck:
    """breaks / within / unknown (a missing delta, no sold leg, or a guide with no readable range)."""
    shorts = tuple(shorts)
    rng = parse_entry_guide(guide_text)
    delta = sold_leg_delta(shorts)
    worst = max(shorts, key=lambda x: x.abs_delta, default=None) if delta is not None else None  # the leg read
    if rng is None or delta is None or worst.kind not in ("CE", "PE"):
        return EntryGuideCheck("unknown")
    state = "within" if rng[0] <= delta <= rng[1] else "breaks"
    return EntryGuideCheck(state, worst.kind, delta, *rng)


def entry_guide_line(shorts: Sequence[ShortLeg], guide_text: str | None) -> str | None:
    """The one plain line for the screen: the breaking fact, "could not check", or None when within the guide."""
    c = check_entry_guide(shorts, guide_text)
    if c.state == "within":
        return None
    if c.state == "unknown":
        return str(render_explanation("entry_guide_unchecked"))
    side = "entry_guide_breaks_put" if c.kind == "PE" else "entry_guide_breaks_call"
    return str(render_explanation(side, delta=c.delta, low=c.low, high=c.high))
