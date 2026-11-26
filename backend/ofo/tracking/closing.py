"""Which legs a close names, and how: the shared step of every exit (modular doors Phase 4, PLAN 5.4.2).

``open_legs_to_close(net, only)``: one ``Close`` per non-zero net, on the opposite side, for the whole open quantity,
in the order of ``only`` (or of ``net`` when ``only`` is None). A key of ``only`` whose net is 0 or absent is left out,
so a quantity-0 order is never built; a key repeated in ``only`` closes once. Nothing is sorted (the paper store puts
BUY exits first itself, D-02; the real path keeps the plan's own order) and no number is rounded: a quantity that is
not a whole number is refused. Stdlib only; the callers (paper exit door, the real path in Phase 6) own prices,
locks and writes.

Spec basis: REQ-109 AC-4 (an exit closes what is open on the opposite side); ADR-117 / D-02 (buys first, by the store).
"""
from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

BUY = "BUY"
SELL = "SELL"


@dataclass(frozen=True)
class Close:
    """One close: the contract key, the side that closes it and the whole open quantity (always above 0)."""

    key: Any
    side: str
    quantity: int


def _whole(quantity: Any) -> int:
    if type(quantity) is not int:  # a float, a bool or a string is a caller error: never rounded into a quantity
        raise TypeError(f"a net quantity is a whole number, not {type(quantity).__name__}")
    return quantity


def open_legs_to_close(net: Mapping[Hashable, int], only: Sequence[Hashable] | None = None) -> list[Close]:
    """The closes for ``net`` (contract key -> signed open quantity, long above 0), see the module docstring."""
    for quantity in net.values():
        _whole(quantity)
    keys = list(net) if only is None else list(dict.fromkeys(only))
    closes = []
    for key in keys:
        held = net.get(key, 0)
        if held:
            closes.append(Close(key, SELL if held > 0 else BUY, abs(held)))
    return closes
