"""Is a strategy's position REAL or PAPER, in one place (ADR-330 (73), owner 28 Nov 2026; (64) withdrawn).

Paper and real are one rule with one tag: a real position gets the same Exit, Stops, Add, Open and alerts on the same
screens as a paper trade; what the user stores for it is a record in the app (``real_action_records``) and nothing is
sent to the broker. The row shows the broker's quantity and P&L and ONE line (position_kind_real).

The tag is the STORED fact (``strategy_position_tags``, migration 0065; written once at the first order, never
updated), never the name: a held entry (ADR-292: a condor held at the broker is a REAL position stored as practice
orders) -> real; else the stored tag, paper or real; no order -> none (a draft: no row to protect); an order and no
stored tag, or any fact that could not be read -> unknown (fail closed: no action is stored, and the line says why).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Final, Literal

from ofo.errors.explanations import ExplanationText, render_explanation

PositionKind = Literal["paper", "real", "none", "unknown"]
PAPER: Final = "paper"
REAL: Final = "real"
NONE: Final = "none"
UNKNOWN: Final = "unknown"


def kind_of(has_order: bool | None, position_tag: str | None, held_at_broker: bool | None) -> PositionKind:
    """Lane R1: the kind is the STORED tag (``strategy_position_tags``, written once, never updated). A held entry
    (ADR-292) is a real position whatever else is stored (it is stored in the transaction of the first paper basket,
    after the tag is first written). No order -> none (a draft); an order and no stored tag, or any fact that could not
    be read, or a tag that is neither paper nor real -> unknown (fail closed)."""
    if has_order is None or held_at_broker is None:
        return UNKNOWN
    if held_at_broker:
        return REAL
    if position_tag in (PAPER, REAL):
        return position_tag  # type: ignore[return-value]
    return NONE if position_tag is None and not has_order else UNKNOWN


def takes_records(kind: str | None) -> bool:
    """Whether this kind's user actions are stored as records (ADR-330 (73)): the tag decision lives HERE, once, so no
    order-door file branches on a tag's name (tests/test_order_door_parity_live_day.py)."""
    return kind == REAL


def is_judged(kind: str | None) -> bool:
    """Whether a stop of this kind is judged by the worker (paper and real alike; an unreadable kind never is)."""
    return kind in (PAPER, REAL)


def is_known(kind: str | None) -> bool:
    """Whether a door may act on this kind (fail closed: an unreadable kind is refused)."""
    return kind in (PAPER, REAL, NONE)


def is_paper(kind: str | None) -> bool:
    return kind == PAPER


def line_of(kind: str) -> ExplanationText | None:
    """The one sentence a row carries: real and unknown only; paper and none carry none (unchanged rows)."""
    if kind == REAL:
        return render_explanation("position_kind_real")
    if kind == UNKNOWN:
        return render_explanation("position_kind_unknown")
    return None


#: RA F4 (Lane FD5 review): the refusal of a paper order on a real or unreadable position says which action it was
#: (the log and the support read the code); the sentence is the same for all three (the owner's wording, ADR-330 (64)).
EXIT_REFUSED: Final = "real_position_exit_refused"
OPEN_REFUSED: Final = "real_position_open_refused"
ADD_REFUSED: Final = "real_position_add_refused"


def refusal_code(order_kinds: Iterable[str]) -> str:
    """The one place the code of a refused order is chosen: any exit or stop -> exit, else any add -> add, else open."""
    kinds = set(order_kinds)
    if kinds & {"exit", "stop"}:
        return EXIT_REFUSED
    return ADD_REFUSED if "add" in kinds else OPEN_REFUSED
