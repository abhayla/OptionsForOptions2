"""ADR-330 (5): a plan's profit target and loss stop typed in rupees or percent; the plan shows both figures. No DB.

Real case (owner example): Rs 1,000 target on a 3,900 max-profit trade shows 25.64 % and Rs 1,000 together, Rs 500
per lot on 2 lots; a percent edit recomputes the rupee figure; both boxes with different values -> refused naming the
field; a stored rupee level that is not a positive decimal is refused on save naming the guard.
Spec basis: ADR-330 (5) and its Q3 answer (whole trade, before charges, per-lot figure beside it).
"""
from __future__ import annotations

import copy
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import stop_lines as sl
from ofo_app import playbook_store
from ofo_app.routes import adjustment_plan as plan

SEED = json.loads((pathlib.Path(__file__).parent.parent / "backend/ofo/adjustment/system_playbooks.json")
                  .read_text(encoding="utf-8"), parse_float=D)
BODY = next(p["body"] for p in SEED["playbooks"] if p["body"]["strategy_type"] == "ic")
BASES = plan.Bases(max_profit=D("3900"), max_loss=D("8000"), lots=2)


def edited(**typed) -> dict:
    return plan.with_overrides(copy.deepcopy(BODY), plan.PlanIn(playbook_id=3, **typed), "weekly", BASES)


def shown(body: dict) -> dict:
    return plan.with_rupee_figures(plan._values(body, False, "weekly"), body, BASES)


def test_rupee_target_shows_percent_and_rupees_together():
    out = shown(edited(target_rupees="1000"))
    assert (out["target"], out["target_rupees"], out["target_per_lot"]) == (D("25.64"), D("1000.00"), D("500.00"))
    assert out["target_rupee_words"] == "Rs 1000.00 for the whole trade (Rs 500.00 per lot), before charges"
    assert out["target_words"] == "25.64 % of max profit"


def test_rupee_target_is_stored_as_text_and_the_percent_target_is_off():
    guards = edited(target_rupees="1000")["guards"]
    assert guards[sl.RUPEE_PROFIT_KEY] == "1000" and guards["profit_target_pct_of_max_profit"] == ""


def test_percent_edit_recomputes_the_rupee_figure_and_drops_the_rupee_level():
    body = edited(target_rupees="1000")
    again = plan.with_overrides(body, plan.PlanIn(playbook_id=3, target="30"), "weekly", BASES)
    assert sl.RUPEE_PROFIT_KEY not in again["guards"]
    out = shown(again)
    assert (out["target"], out["target_rupees"], out["target_per_lot"]) == (D("30"), D("1170.00"), D("585.00"))


def test_rupee_stop_shows_figures_and_keeps_the_percent_stop():
    body = edited(stop_rupees="400")
    out = shown(body)
    assert (out["stop_rupees"], out["stop_per_lot"]) == (D("400.00"), D("200.00"))
    assert body["guards"][sl.RUPEE_LOSS_KEY] == "400"


def test_both_boxes_with_different_values_are_refused_naming_the_field():
    with pytest.raises(playbook_store.PlaybookStoreError) as err:
        edited(target="50", target_rupees="1000")
    assert err.value.slots["field"] == "target_rupees"
    with pytest.raises(playbook_store.PlaybookStoreError) as err:
        edited(stop="50", stop_rupees="1000")
    assert err.value.slots["field"] == "stop_rupees"


def test_both_boxes_with_the_same_level_keep_the_percent_only():
    body = edited(target="25.64", target_rupees="1000")
    assert sl.RUPEE_PROFIT_KEY not in body["guards"] and body["guards"]["profit_target_pct_of_max_profit"] == "25.64"


def test_both_boxes_with_no_base_cannot_be_judged_and_are_refused():
    with pytest.raises(playbook_store.PlaybookStoreError):
        plan.with_overrides(copy.deepcopy(BODY), plan.PlanIn(playbook_id=3, target="25", target_rupees="1000"),
                            "weekly", plan.Bases())


@pytest.mark.parametrize("raw", ["0", "-5", "NaN", "abc", "1,000", "1000.123", "1e3"])
def test_unreadable_rupee_text_is_refused_naming_the_field(raw):
    with pytest.raises(playbook_store.PlaybookStoreError) as err:
        edited(target_rupees=raw)
    assert err.value.slots["field"] == "target_rupees"


def test_empty_rupee_box_clears_the_level():
    body = edited(target_rupees="")
    assert sl.RUPEE_PROFIT_KEY not in body["guards"]


@pytest.mark.parametrize("raw", ["0", "-1", "NaN", 5, "x"])
def test_saved_body_with_a_bad_rupee_guard_is_refused_naming_it(raw):
    body = copy.deepcopy(BODY)
    body["guards"][sl.RUPEE_LOSS_KEY] = raw
    with pytest.raises(playbook_store.PlaybookStoreError) as err:
        playbook_store.check_body(body, "ic")
    assert err.value.slots["field"] == f"guards.{sl.RUPEE_LOSS_KEY}"


def test_saved_body_with_good_rupee_guards_passes():
    body = copy.deepcopy(BODY)
    body["guards"].update({sl.RUPEE_LOSS_KEY: "400", sl.RUPEE_PROFIT_KEY: ""})
    assert playbook_store.check_body(body, "ic") is body


def test_rupee_stop_on_the_s21_base_shows_the_percent_derived_beside_it():
    """S-21 base: max loss 2,600. A Rs 400 stop is 15.38 % of it (shown to the catalogue's two decimals)."""
    body = edited(stop_rupees="400")
    out = plan.with_rupee_figures(plan._values(body, False, "weekly"), body, plan.Bases(max_loss=D("2600"), lots=2))
    assert (out["stop"], out["stop_rupees"]) == (D("15.38"), D("400.00"))
    assert out["stop_words"] == "15.38 % of max loss"
