"""Lane FE2 (28 Nov 2026), item 9 (issues #861, #866; Lane Z review minor F7). Spec basis: ADR-245, ADR-250, ADR-330
(5), (47); REQ-115 AC-4.

#861 / #866 real case: a far-month trade (a leg past the last listed future) has an expiry kind that is not known; its
percent stop and T-06 read "stop lines not supplied", which does not name the missing fact. The reason code
``EXPIRY_KIND_UNKNOWN`` names it, answers fail closed through the existing "days left not available" row, and is
distinct from every other reason.

F7: a body rule that names a plan exit among other triggers is a plan exit (ADR-330 (47): "each body rule whose members
name a loss stop, the % profit target or the time exit"); the loss stops themselves are the fixed ``stop.*`` lines, so
a mixed rule never replaces or doubles a stop. Pinned here, not changed.
"""
from __future__ import annotations

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl


def test_the_unknown_expiry_kind_has_its_own_reason_and_answers_closed():
    assert sl.EXPIRY_KIND_UNKNOWN not in {sl.STAGE_UNKNOWN, sl.GUARDS_UNREADABLE, sl.STOP_VALUE_UNREADABLE}
    code = sl.not_checked_code(sl.EXPIRY_KIND_UNKNOWN)
    assert code == "adjust_trigger_missing_days_left"  # until the catalogue has its own sentence: fail closed
    assert code not in (sl.NOT_CHECKED_OTHER, sl.STOPS_NOT_SUPPLIED)
    assert pe.reason_text(code)


def test_every_reason_a_line_can_have_answers_a_code_with_a_sentence():
    for reason, code in sl.NOT_CHECKED.items():
        assert pe.reason_text(code), reason


def test_a_mixed_plan_rule_that_names_an_exit_is_a_plan_exit_and_the_fixed_stop_lines_stay():
    body = {"rules": [{"id": "MIX", "any_of": ["T-06", "T-02"]}, {"id": "PURE", "any_of": ["T-16"]},
                      {"id": "OTHER", "any_of": ["T-02"]}]}
    exits = sl.plan_exit_rule_ids(body)
    assert {"MIX", "PURE"} <= exits and "OTHER" not in exits
    assert exits >= sl.LOSS_STOP_RULES  # the stop.* lines are always there, whatever the body says
    assert sl.loss_stop_rule_ids(body) >= {"MIX", "PURE"}
