"""GC-ICFIX issue 19, real cases from the 2026-11-13 user test (strategy 144, Friday 15:29 -> 15:31).

u311 (M-10): a stop flagged at 15:29 vanished at 15:31 because the market closed and the rule read "not checked";
the open record was dropped from the shown results. u312 (M-11): the carry reminder "day.beforeWeekend.1500.0"
reached the user as the raw id (ADR-267 amendment: a day rule names itself in a sentence). No database.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.timeutil import IST
from ofo_app import adjustment_check as chk_app
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


# ---- round 2: no path shows a raw id; every schedule kind has its pinned sentence ------------------------------------
GENERIC = "A scheduled check for this trade"
SHOW = "Show reduce / partial profit / exit"
CARRY_WORDS = "Run the carry check (overnight margin, gap loss)"


@pytest.mark.parametrize("rule_id", ["day.zzz.1500.0", "day.beforeWeekend.1500.9", "day.invalid", "day:after:1500:exit",
                                     "day.beforeWeekend.15x0.0"])
def test_u312_an_unreadable_day_rule_id_is_one_plain_sentence_never_raw(rule_id, caplog):
    rec = store.Suggestion(1, 144, "day." + rule_id, "day.x", None, None, None, AT, "open", None,
                           [{"cmp": None, "label": None}])
    rec = dataclasses.replace(rec, rule_id=rule_id)
    text = str(opp.condition_text(rec))
    assert text.startswith(GENERIC), text
    assert rule_id not in text
    assert rule_id in caplog.text  # the raw id goes to the server log only


@pytest.mark.parametrize(("rule_id", "sentence"), [
    ("day.beforeWeekend.1500.0", f"The last session before a weekend, 15:00: {CARRY_WORDS}"),
    ("day.beforeHoliday.1500.0", f"The day before a market holiday, 15:00: {CARRY_WORDS}"),
    ("day.expiry.1430.5", "Expiry day, 14:30: Prepare an exit for review"),
    ("day.weekday.0930.1", f"{GENERIC}, 09:30: {SHOW}"),
    ("day.dom.0930.1", f"{GENERIC}, 09:30: {SHOW}"),
    ("day.date.0930.1", f"{GENERIC}, 09:30: {SHOW}"),
    ("day.event.1430.1", f"{GENERIC}, 14:30: {SHOW}"),
    ("day.away.1430.1", f"{GENERIC}, 14:30: {SHOW}"),
])
def test_u312_each_schedule_kind_has_its_pinned_sentence(rule_id, sentence):
    assert chk_app.day_rule_words(rule_id) == sentence


# ---- round 2: a stop read on a later day names its date (the server decides "today", IST)
def _held_stop():
    return chk.HeldFlag("T-06", sl.TRIGGER_MAX_LOSS, "Entry", D("5.8600"), D("1.0000"), "ge")


def test_stop_fired_today_shows_the_time_only():
    at = datetime.datetime(2026, 11, 13, 9, 59, tzinfo=datetime.UTC)  # 15:29 IST
    text = str(chk.stop_text(_held_stop(), (), None, {"T-06": at}, datetime.date(2026, 11, 13)))
    assert text.endswith("; reached at 15:29 IST"), text


def test_stop_fired_on_an_earlier_day_shows_date_and_time():
    at = datetime.datetime(2026, 11, 13, 9, 59, tzinfo=datetime.UTC)
    text = str(chk.stop_text(_held_stop(), (), None, {"T-06": at}, datetime.date(2026, 11, 16)))
    assert text.endswith("; reached on 13 Nov 2026 at 15:29 IST"), text


def test_stop_fired_late_evening_utc_is_the_next_ist_day():
    at = datetime.datetime(2026, 11, 13, 19, 0, tzinfo=datetime.UTC)  # 00:30 IST on the 14th
    text = str(chk.stop_text(_held_stop(), (), None, {"T-06": at}, datetime.date(2026, 11, 14)))
    assert text.endswith("; reached at 00:30 IST"), text
