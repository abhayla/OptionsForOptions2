"""Contract "Your adjustment settings" step 3, round 5: saving the plan sheet never loosens or rewrites a stop the user
did not change.

Spec basis: ADR-252 addendum (the sheet shows ONE stop = T-06's early-stage value in the strategy's own stage row; a
save changes T-06 only when the submitted stop differs from it; an edit to V sets early and middle to V and the last
stage to min(V, its current value); switching a plan to another playbook is a new acceptance); ADR-250.

Class: every plan-sheet save that reaches the T-06 write: stop unchanged, changed looser, changed stricter, weekly and
monthly strategies. Before: any non-empty stop rewrote every stage flat (50/50/40 + stop "50" -> 50/50/50).
"""
from __future__ import annotations

import copy
import importlib.util
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.adjustment import stop_lines as sl
from ofo_app import playbook_store as store
from ofo_app import settings_in_force as sif
from ofo_app.routes import adjustment_plan as ap

ROOT = Path(__file__).resolve().parents[1]
_IC = next(r["body"] for r in json.loads(
    (ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text(encoding="utf-8"))["playbooks"]
    if r["strategy_type"] == "ic")


def plan(weekly=("50", "50", "40"), monthly=("50", "50", "40")) -> dict:
    out = copy.deepcopy(_IC)
    out["triggers"][sl.TRIGGER_MAX_LOSS]["weekly"] = list(weekly)
    out["triggers"][sl.TRIGGER_MAX_LOSS]["monthly"] = list(monthly)
    return out


def t06(body: dict) -> tuple[list, list]:
    trig = body["triggers"][sl.TRIGGER_MAX_LOSS]
    return trig["weekly"], trig["monthly"]


def save(body: dict, stop: str, kind: str | None = None) -> dict:
    return ap.with_overrides(body, ap.PlanIn(playbook_id=1, stop=stop, target="60"), kind)


# ---- item 1: the core ------------------------------------------------------------------------------------------------
def test_core_an_untouched_stop_keeps_50_50_40():
    b = plan()
    out = ap.with_overrides(b, ap.PlanIn(playbook_id=1, stop="50", target="60"))
    assert t06(out) == (["50", "50", "40"], ["50", "50", "40"])
    assert out["guards"][ap.TARGET_KEY] == "60"  # the other sheet fields still save


def test_an_untouched_save_with_a_decimal_spelling_of_the_same_number_rewrites_nothing():
    assert t06(save(plan(), "50.0")) == (["50", "50", "40"], ["50", "50", "40"])


def test_a_looser_stop_60_gives_60_60_40():
    assert t06(save(plan(), "60")) == (["60", "60", "40"], ["60", "60", "40"])


def test_a_stricter_stop_30_gives_30_30_30():
    assert t06(save(plan(), "30")) == (["30", "30", "30"], ["30", "30", "30"])


def test_a_stop_between_the_stages_45_gives_45_45_40():
    assert t06(save(plan(), "45")) == (["45", "45", "40"], ["45", "45", "40"])


def test_a_stage_without_a_value_stays_without_one_and_a_switched_off_t06_comes_on():
    b = plan(weekly=("50", "50", ""))
    b["triggers"][sl.TRIGGER_MAX_LOSS]["on"] = False
    out = save(b, "30")
    assert t06(out)[0] == ["30", "30", ""]
    assert out["triggers"][sl.TRIGGER_MAX_LOSS]["on"] is True


def test_the_input_body_is_not_mutated():
    b = plan()
    before = copy.deepcopy(b)
    save(b, "60")
    assert b == before


# ---- item 2: the shown value is the strategy's own stage row ---------------------------------------------------------
def test_a_monthly_strategy_shows_its_own_row_30():
    b = plan(weekly=("50", "50", "40"), monthly=("30", "30", "30"))
    assert sif.sheet_stop(b) == D(50)  # no kind: the weekly row
    assert sif.sheet_stop(b, "monthly") == D(30)
    values = ap._values(b, False, "monthly")
    assert values["stop"] == D(30)
    assert values["stop_words"] is not None


def test_a_monthly_strategy_saving_its_shown_30_rewrites_nothing_and_a_new_value_edits_both_rows():
    b = plan(weekly=("50", "50", "40"), monthly=("30", "30", "30"))
    assert t06(save(b, "30", "monthly")) == (["50", "50", "40"], ["30", "30", "30"])
    assert t06(save(b, "35", "monthly")) == (["35", "35", "35"], ["35", "35", "30"])


def test_the_monthly_stop_words_follow_the_monthly_row():
    b = plan(weekly=("50", "50", "40"), monthly=("30", "30", "30"))
    assert ap._values(b, False, "monthly")["stop_words"] != ap._values(b, False)["stop_words"]


# ---- item 3: a playbook switch is a new acceptance --------------------------------------------------------------------
def _migration():
    path = ROOT / "backend/ofo_app/alembic/versions/0041_plan_switch_is_acceptance.py"
    found = importlib.util.spec_from_file_location("m0041_for_test", path)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


def test_the_plan_guard_stamps_accepted_at_when_the_playbook_changes():
    m = _migration()
    up, down = m.upgrade_sql(), m.downgrade_sql()
    assert m.NEW_TEST in up and m.OLD_TEST not in up
    assert m.OLD_TEST in down and m.NEW_TEST not in down
    assert up.replace(m.NEW_TEST, m.OLD_TEST) == down  # nothing else in the function moved
    assert "NEW.accepted_at := OLD.accepted_at" in up  # an unchanged playbook and body still keep the old time


def test_the_upsert_does_not_write_accepted_at_itself_the_guard_stamps_it():
    sql = str(store._UPSERT_PLAN)
    assert "accepted_at" in sql.split("RETURNING")[1]
    assert "accepted_at =" not in sql.split("DO UPDATE")[1]
    assert "playbook_id = EXCLUDED.playbook_id" in sql  # the switch reaches the guard as a playbook_id change


@pytest.mark.parametrize("raw", ["0", "101", "x", ""])
def test_a_bad_stop_is_still_refused(raw):
    with pytest.raises(Exception):  # noqa: B017, PT011 - the store error type is the route's concern
        save(plan(), raw)
