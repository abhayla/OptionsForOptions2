"""GC-ICTRACK task 29: EVERY trigger evaluator, on the real iron condor body with that trigger switched on and a state
that knows only its stage (no spot, no clock, no legs, no prices, no margin, no market inputs), answers NOT CHECKED
with a reason code - never fired, never clear. A new evaluator joins this test by being in ``_EVALUATORS``."""
from __future__ import annotations

import pytest
from ofo.adjustment import playbook_eval as pe
from test_ic_new_triggers import MIDDLE, _body

EVALUATED = sorted(pe._EVALUATORS)
STOPS = sorted(pe.sl.STOP_TRIGGERS)  # T-06 / T-16: answered from the stop lines in force (none supplied here)


def test_the_population_is_every_evaluator_including_the_12_new():
    assert {"T-04", "T-05", "T-06b", "T-08", "T-11b", "T-11c", "T-12", "T-14t", "T-14v", "T-15", "T-20", "T-20b"} <= \
        set(EVALUATED)


@pytest.mark.parametrize("tid", EVALUATED + STOPS)
def test_an_empty_state_is_not_checked_never_a_pass(tid):
    empty = pe.StrategyState(stops=None, expiry_kind="weekly", days_left=MIDDLE)
    ev = pe.evaluate(_body(tid), empty, gap_until="09:30")
    got = [r for r in ev.results if r.rule_id == tid]  # a trigger on by default also has its own rule: 2 results
    assert got and tid not in ev.clear, (tid, ev.results)
    for r in got:
        assert isinstance(r, pe.NotChecked) and r.code.startswith(pe.P), r
