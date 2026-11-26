"""Which side of an entered strategy is closed, and which plan rules still fit (ADR-330 (2), P7).

Pure and stdlib only. A side (call = CE legs, put = PE legs) is CLOSED when the strategy was entered with legs of that
type, none of them is open now, and the other side still has an open leg. One leg of a side exited, a leg rolled to
another strike, nothing exited, every leg exited (the strategy is closed: its alerts close with it) and an unreadable
entry or position (absent: never a guess) are NOT a closed side. ``side_scope.json`` says per trigger id which side it
needs: ``none`` (it reads P&L, the clock, the market or the remaining shorts, so it still fits), ``call``, ``put`` or
``both`` (T-05 compares the two sides). Nothing here exits or adds a position (ADR-003).
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

CALL: Final = "call"
PUT: Final = "put"
_KIND_SIDE: Final = {"CE": CALL, "PE": PUT}
SCOPE: Final[dict[str, str]] = json.loads(Path(__file__).with_name("side_scope.json").read_text(encoding="utf-8"))
#: the closed side -> the catalogue template of the shape that remains (ADR-330 (2) (b)); data, not code (AC-5)
REMAINING_SHAPE: Final[dict[str, str]] = json.loads(
    Path(__file__).with_name("side_remaining_shape.json").read_text(encoding="utf-8"))


def _sides(legs: Iterable[Any]) -> frozenset[str]:
    return frozenset(_KIND_SIDE[x.type] for x in legs if getattr(x, "type", None) in _KIND_SIDE)


def open_sides(legs: Iterable[Any] | None) -> frozenset[str]:
    """The sides ("call" / "put") that have at least one leg in ``legs``; empty when it cannot be said."""
    return frozenset() if legs is None else _sides(legs)


def closed_sides(entry_legs: Iterable[Any] | None, open_legs: Iterable[Any] | None) -> frozenset[str]:
    """The sides entered with legs and left with none (see the module note); empty when it cannot be said."""
    if entry_legs is None or open_legs is None:
        return frozenset()
    entered, still = _sides(entry_legs), _sides(open_legs)
    if not still:  # nothing open: the strategy is closed, not a side
        return frozenset()
    return entered - still


def _needs(trigger_id: str, closed: frozenset[str]) -> bool:
    """True when the trigger needs a closed side; an id with no entry is not marked (its own evaluator answers)."""
    scope = SCOPE.get(trigger_id, "none")
    return bool(closed) if scope == "both" else scope in closed


def rule_notes(body: Mapping | None, closed: frozenset[str]) -> dict[str, frozenset[str]]:
    """Rule id -> the closed side(s) that make it "Not applicable: the <call or put> side is closed" (the sentence is a
    catalogue line pending the owner's read; no words are built here), for each rule that no longer fits. An any_of
    rule stops fitting when every trigger needs a closed side, an all_of rule when one does."""
    if not closed or not isinstance(body, Mapping):
        return {}
    out: dict[str, frozenset[str]] = {}
    for rule in body.get("rules") or ():
        any_of, all_of = rule.get("any_of") or (), rule.get("all_of") or ()
        gone = ((bool(any_of) and all(_needs(t, closed) for t in any_of))
                or (bool(all_of) and any(_needs(t, closed) for t in all_of)))
        if gone:
            out[rule["id"]] = closed
    return out
