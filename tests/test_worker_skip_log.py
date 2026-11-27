"""One worker log line per strategy per cycle when its check is skipped, with the reason (Lane J 2026-11-27).

Case A-G #207 (2026-11-27): plan approved 13:13:33, loss past its Rs 80 stop from about 13:14, no alert row for 19
minutes, and the worker log showed the minute cycle listing 207 with no not-live or skipped line: nothing said why no
check reached the gate. Spec basis: REQ-170 AC-5, ADR-267 amendment 2 ("no crossing is ever dropped without trace").
"""
from __future__ import annotations

import ast
import inspect
import logging
import textwrap

from ofo_app import background


def _bare_worker():
    w = background.Worker.__new__(background.Worker)
    w._last_skip = {}
    return w


def _returns_false(fn) -> list[int]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is False]


def test_every_skip_of_a_check_goes_through_the_one_logging_helper():
    """Structural: no early exit of a check returns a bare False; each names its reason through ``_skipped``."""
    assert _returns_false(background.Worker._check_unpaused) == []
    assert _returns_false(background.Worker._check_one) == []


def test_skipped_logs_the_strategy_and_reason(caplog):
    caplog.set_level(logging.INFO, logger="ofo_app.background")
    assert _bare_worker()._skipped(207, "prices_stale") is False
    assert [r.getMessage() for r in caplog.records] == ["background: strategy 207 check skipped: prices_stale"]


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def test_the_same_reason_on_consecutive_cycles_logs_once(caplog):
    caplog.set_level(logging.INFO, logger="ofo_app.background")
    w = _bare_worker()
    for _ in range(5):
        assert w._skipped(207, "market_closed") is False
    assert _lines(caplog) == ["background: strategy 207 check skipped: market_closed"]


def test_a_changed_reason_logs_a_new_line(caplog):
    caplog.set_level(logging.INFO, logger="ofo_app.background")
    w = _bare_worker()
    w._skipped(207, "market_closed")
    w._skipped(207, "interval")
    w._skipped(208, "interval")  # another strategy has its own last reason
    assert len(_lines(caplog)) == 3  # noqa: PLR2004


def test_a_check_in_between_resets_so_the_same_reason_logs_again(caplog):
    caplog.set_level(logging.INFO, logger="ofo_app.background")
    w = _bare_worker()
    w._skipped(207, "interval")
    w._checked(207)
    w._skipped(207, "interval")
    assert len(_lines(caplog)) == 2  # noqa: PLR2004
