"""GC-ICFIX issue 19, real cases from the 2026-11-13 user test (strategy 144, Friday 15:29 -> 15:31).

u311 (M-10): a stop flagged at 15:29 vanished at 15:31 because the market closed and the rule read "not checked";
the open record was dropped from the shown results. u312 (M-11): the carry reminder "day.beforeWeekend.1500.0"
reached the user as the raw id (ADR-267 amendment: a day rule names itself in a sentence). No database.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.timeutil import IST
from ofo_app import playbook_store as store
from ofo_app.routes import adjustment_check as chk
from ofo_app.routes import adjustment_opportunities as opp

CARRY = "day.beforeWeekend.1500.0"
AT = datetime.datetime(2026, 11, 13, 15, 29, tzinfo=IST)


def _day_record(label):
    return store.Suggestion(1, 144, CARRY, CARRY, None, None, None, AT, "open", None,
                            [{"cmp": None, "label": label, "group": "g"}])


@pytest.mark.parametrize("label", [None, CARRY])
def test_u312_carry_reminder_is_a_sentence_never_the_raw_id(label):
    text = str(opp.condition_text(_day_record(label)))
    assert "day." not in text and "1500.0" not in text, text
    assert "weekend" in text.lower() and "15:00" in text and "carry check" in text.lower(), text


def test_u312_a_real_label_is_kept():
    assert str(opp.condition_text(_day_record("Run the carry check"))) == "Run the carry check"


def test_u311_open_stop_record_stays_shown_when_the_rule_reads_not_checked():
    rec = SimpleNamespace(rule_id="T-06", trigger_id="T-06", stage="Entry", value=D("9.7450"), threshold=D("1"),
                          cmp="ge")
    ev = pe.Evaluation(None, None, (pe.NotChecked("T-06", "T-06", "check_prices_not_live"),), {})
    shown = chk.shown_results(ev, [rec])
    held = [r for r in shown if isinstance(r, chk.HeldFlag)]
    assert [(h.rule_id, h.value) for h in held] == [("T-06", D("9.7450"))]
    assert any(isinstance(r, pe.NotChecked) for r in shown)  # the honest "not checked" line stays beside it
