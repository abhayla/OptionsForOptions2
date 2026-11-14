"""ADR-300 (applies ADR-216; ADR-003): the entry-guide check of a strategy's sold legs, in three states.

The guide is the playbook's own ``guards.entry_guide`` text ("shorts at 0.15 to 0.20 delta, wings ..."); its delta range
is read from that text, never typed here. The sold-leg delta is ``playbook_eval.sold_leg_delta`` (T-03's own measure).
A strategy that breaks the guide still shows and still saves: the line is a fact with both numbers, no advice.
The rule set a strategy with no stored plan yet would get is the system playbook of its shape's type
(``system_rule_set``). shortcut: a user's own edited playbook text is not read here (no database in the outcome route);
read it through ``playbook_store.active_for`` when the route gains a database reader.
Pure: no database, no clock.
"""
from __future__ import annotations

import functools
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from ofo.adjustment.playbook_eval import ShortLeg, sold_leg_delta
from ofo.errors.explanations import render_explanation

_RANGE = re.compile(r"\bshorts at (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?) delta\b")
_SEED = Path(__file__).with_name("system_playbooks.json")
State = Literal["breaks", "within", "cannot_tell"]


def parse_entry_guide(text: str | None) -> tuple[Decimal, Decimal] | None:
    """The (low, high) delta range the guide text states; None when it states none (or a reversed one)."""
    m = _RANGE.search(text or "")
    if m is None:
        return None
    low, high = Decimal(m.group(1)), Decimal(m.group(2))
    return (low, high) if low <= high else None


@dataclass(frozen=True)
class EntryGuideCheck:
    state: State
    kind: str | None = None  # "CE" / "PE": the side whose delta is shown
    delta: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None


def check_entry_guide(shorts: Sequence[ShortLeg], guide_text: str | None) -> EntryGuideCheck:
    """breaks / within / cannot_tell (a missing delta, no sold leg, or a guide with no readable range)."""
    shorts = tuple(shorts)
    rng = parse_entry_guide(guide_text)
    delta = sold_leg_delta(shorts)
    worst = max(shorts, key=lambda x: x.abs_delta) if delta is not None else None  # the leg sold_leg_delta read
    if rng is None or worst is None or worst.kind not in ("CE", "PE"):
        return EntryGuideCheck("cannot_tell")
    state: State = "within" if rng[0] <= delta <= rng[1] else "breaks"
    return EntryGuideCheck(state, worst.kind, delta, *rng)


def _line(c: EntryGuideCheck, rule_set: str):
    if c.state == "within":
        return None
    if c.state == "cannot_tell":
        return render_explanation("entry_guide_unchecked")
    side = "entry_guide_breaks_put" if c.kind == "PE" else "entry_guide_breaks_call"
    return render_explanation(side, delta=c.delta, rule_set=rule_set, low=c.low, high=c.high)


def entry_guide_line(shorts: Sequence[ShortLeg], guide_text: str | None, rule_set: str):
    """The one plain line for the screen: the breaking fact, "could not check", or None when within the guide."""
    return _line(check_entry_guide(shorts, guide_text), rule_set)


@functools.cache
def _system() -> dict[str, tuple[str, str | None]]:
    rows = json.loads(_SEED.read_text("utf-8"))["playbooks"]
    return {r["strategy_type"]: (r["name"], r["body"].get("guards", {}).get("entry_guide")) for r in rows}


def system_rule_set(strategy_type: str | None) -> tuple[str, str | None] | None:
    """(name, entry-guide text) of the system playbook of ``strategy_type``; None for a shape that has none."""
    return None if strategy_type is None else _system().get(strategy_type)


#: ADR-300 is about a condor outside its entry guide. The guide speaks of shorts out of the money, so it applies only to
#: the shapes whose sold legs are meant to be there; a shape that sells at the money by design (straddle, iron
#: butterfly, butterflies, calendars, ratios, naked shorts) would get a false alarm on every trade. Every playbook type
#: is classified here on purpose (a test fails for an unclassified one); an unknown shape (None) gets no line.
GUIDE_APPLIES: dict[str, bool] = {
    "ic": True, "strangle": True, "credit": True,
    "straddle": False, "ifly": False, "dirfly": False, "calendar": False, "debit": False, "longopt": False,
    "longvol": False, "ratio": False, "other": False,
}


@dataclass(frozen=True)
class EntryGuide:
    state: State
    line: object  # an ExplanationText (catalogue text) or None


RuleSets = Callable[[str | None], "tuple[str, str | None] | None"]


def entry_guide_for(sold: Sequence[tuple[str, Decimal | None]], strategy_type: str | None,
                    rule_sets: RuleSets = system_rule_set) -> EntryGuide | None:
    """The whole answer for a priced strategy. ``sold``: (kind, |delta|) of each sold option leg; None when there is no
    sold option leg, or when the shape is unknown or one the guide does not suit (``GUIDE_APPLIES``). For a shape it
    suits, a missing delta or a guide text that states no range is "cannot tell": never silence, never a guess."""
    if not sold or not GUIDE_APPLIES.get(strategy_type or "", False):
        return None
    shorts = tuple(ShortLeg(Decimal(0), d, None, k) for k, d in sold)
    name, text = rule_sets(strategy_type) or (None, None)
    c = check_entry_guide(shorts, text)
    return EntryGuide(c.state, _line(c, name or ""))
