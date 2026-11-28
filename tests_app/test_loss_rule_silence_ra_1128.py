"""Lane RA (coordinator, issue 876: strategy 207, no alert for 14 minutes): the worker's log had only a summed
counter of outcomes (already_true, not_checked <code>, ...), so a loss rule that was true and sent nothing left no line
naming the strategy and the rule. Now every loss rule or guard (T-06, the 2x-credit line, the rupee loss stop) that is
evaluated and does NOT alert writes one INFO line with the strategy, the rule and the reason code (never a price), when
the outcome is new or changed; a rule that alerts (a Flag) writes none (its alert row is its record).

Real case (PC, 27 Nov 13:13 to 13:37): plan of strategy 207 with the loss rules T-06 and the rupee stop on,
``plan.rupee_loss`` memory held_at_entry false, seen_clear true: the line must name 207, ``plan.rupee_loss`` and
``already_true`` or the not-checked code, whichever swallowed it.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from ofo.adjustment import playbook_eval as pe
from ofo_app import background

from tests_app.test_background_wire_want import FakeRedis, IndexedProv, _watched, _worker, scn  # noqa: F401 - fixture

D = Decimal
TWO, THREE = 2, 3  # the lines expected


def _ev(*results) -> pe.Evaluation:
    return pe.Evaluation(None, None, tuple(results), {})


def _true(rule: str, trigger: str) -> pe.AlreadyTrue:
    return pe.AlreadyTrue(rule, trigger, D("9782.00"), D("9000.00"))


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "loss rule" in r.getMessage()]


async def test_ra_876_a_loss_rule_true_and_not_alerted_names_the_strategy_rule_and_code_once(
        scn, caplog):  # noqa: F811
    prov, now = IndexedProv(scn), [scn.clock_at]
    w = _worker(prov, _watched(scn), now, FakeRedis())
    caplog.set_level(logging.INFO, logger=background.log.name)
    ev = _ev(_true("plan.rupee_loss", "T-06"), pe.NotChecked("T-06", "T-06", "no_stage_value"), _true("T-03", "T-03"))
    w._count_outcomes(ev, 207)
    w._count_outcomes(ev, 207)  # the next cycle, nothing changed: no second line
    lines = _lines(caplog)
    assert len(lines) == TWO, lines  # the rupee rule and T-06; T-03 is not a loss rule
    assert any("strategy=207 rule=plan.rupee_loss outcome=already_true" in x for x in lines), lines
    assert any("strategy=207 rule=T-06 outcome=not_checked no_stage_value" in x for x in lines), lines
    assert not any("9782" in x or "9000" in x for x in lines), "no prices in the line"
    ev2 = _ev(pe.NotChecked("plan.rupee_loss", "T-06", "gap_after_open"))  # the outcome changed: a new line
    w._count_outcomes(ev2, 207)
    assert len(_lines(caplog)) == THREE
    assert "outcome=not_checked gap_after_open" in _lines(caplog)[-1]
    flag = pe.Flag("plan.rupee_loss", "T-06", None, D("9782.00"), D("9000.00"), "gte")
    w._count_outcomes(_ev(flag), 207)  # it alerts: no silence line
    assert len(_lines(caplog)) == THREE
