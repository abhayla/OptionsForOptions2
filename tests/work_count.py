"""Deterministic cost measurement for tests: count the work done, never the seconds it took (W-033).

A wall-clock threshold measures how busy the machine is (finding wall-clock-assertion-flakes-under-load). The number
of Python and C function calls a piece of code makes does not change with load, and it grows quadratically exactly
when the code re-does work per item. ``assert_linear`` runs the code at two sizes and fails if doubling the input
much more than doubles the calls.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

#: Doubling the input may cost up to this many times the calls. Linear code is ~2.0; quadratic code is ~4.0.
DOUBLING_LIMIT = 2.5


def count_calls(run: Callable[[], Any]) -> int:
    """Number of function calls (Python and C) made while ``run()`` executes."""
    calls = 0

    def profiler(frame: Any, event: str, arg: Any) -> None:
        nonlocal calls
        if event in ("call", "c_call"):
            calls += 1

    previous = sys.getprofile()
    sys.setprofile(profiler)
    try:
        run()
    finally:
        sys.setprofile(previous)
    return calls


def call_ratio(make_run: Callable[[int], Callable[[], Any]], n: int) -> tuple[int, int, float]:
    """Calls at size ``n``, at size ``2 * n``, and their ratio. ``make_run(size)`` builds a fresh setup, returns the work."""
    small = count_calls(make_run(n))
    large = count_calls(make_run(2 * n))
    return small, large, large / small


def assert_linear(make_run: Callable[[int], Callable[[], Any]], n: int) -> None:
    """Fail if the work at ``2 * n`` items is more than DOUBLING_LIMIT times the work at ``n`` items."""
    small, large, ratio = call_ratio(make_run, n)
    assert small > 0, "the measured code made no calls: the test measures nothing"
    assert ratio < DOUBLING_LIMIT, f"{n} items -> {small} calls, {2 * n} items -> {large} calls (x{ratio:.2f}): not linear"
