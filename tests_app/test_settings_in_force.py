"""Contract "Your adjustment settings" step 3, part 1: the ONE settings-in-force read (``ofo_app.settings_in_force``).

Spec basis: ADR-245 (strategy, else user, else admin default, each named); ADR-247 (stop: 50 % of max loss or 2x the
credit received, whichever comes first; % of margin OFF by default); ADR-008 (the engine owns every rupee figure).
No database: the layers are handed in as the store and the plan store hand them over (``UserValues`` with ``.own`` and
``.admin``; ``Resolved`` with the plan body). The route's own reply is proven on a fresh DB in
``test_adjustment_plan_settings.py``.
"""
from __future__ import annotations

import datetime
import json
import pathlib
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.engine.metrics import UNLIMITED
from ofo.settings import layers
from ofo_app import adjustment_check as check
from ofo_app import settings_in_force as sif
from ofo_app.routes import adjustment_plan as ap
from ofo_app.user_preferences_store import Answer, UserValues

CARRY = layers.CARRY_GAP_PERCENT
NOW = datetime.datetime(2026, 11, 5, 9, 0, tzinfo=datetime.UTC)


def _user(carry_user: D | None, admin: D = D(2)) -> UserValues:
    src = "default" if carry_user is None else "yours"
    return UserValues({CARRY: Answer(CARRY, carry_user if carry_user is not None else admin, src, admin,
                                     None if carry_user is None else NOW)})


def _plan(body: dict) -> check.Resolved:
    return check.Resolved("plan", body, 7, None, False, saved_before_adr247=False)


def _value(found: sif.InForce, key: str) -> tuple:
    row = next(x for x in found.settings if x.key == key)
    return row.value, row.source, row.reason


# ---- settings: the three layers -------------------------------------------------------------------------------------

def test_core_plan_then_user_then_default_with_sources():
    body = {"settings": {CARRY: "1.5"}, "triggers": {}, "guards": {}}
    assert _value(sif.in_force(_user(D(3)), _plan(body), None), CARRY) == (D("1.5"), "strategy", None)
    assert _value(sif.in_force(_user(D(3)), _plan({"guards": {}}), None), CARRY) == (D(3), "user", None)
    assert _value(sif.in_force(_user(None), _plan({"guards": {}}), None), CARRY) == (D(2), "default", None)


def test_a_strategy_following_its_playbook_has_no_strategy_layer():
    """Only the PLAN copy is the strategy layer: the same ``settings`` in the user's active playbook is not."""
    active = check.Resolved("active", {"settings": {CARRY: "1.5"}}, 3, None, False, saved_before_adr247=False)
    assert _value(sif.in_force(_user(D(3)), active, None), CARRY) == (D(3), "user", None)


@pytest.mark.parametrize(("user", "body", "code"), [
    ({CARRY: D(3)}, {"guards": {}}, layers.USER_UNREADABLE),  # a merged mapping, not the store's own values
    (_user(D(3)), {"settings": ["not an object"]}, layers.STRATEGY_UNREADABLE),
    (_user(D(3)), {"settings": {CARRY: "99"}}, layers.STRATEGY_UNREADABLE),  # refused by the registry
])
def test_an_unreadable_layer_fails_closed_with_its_code(user, body, code):
    assert _value(sif.in_force(user, _plan(body), None), CARRY) == (None, None, code)


def test_every_covered_key_is_answered_and_admin_only_keys_are_not():
    keys = sif.covered_keys()
    assert CARRY in keys and layers.ROLL_BASIS in keys
    assert "adjustments.short_delta_weekly" in keys and "alerts.weekly.cooldown_minutes" in keys
    assert not [k for k in keys if k.startswith(("speeds.", "pricing.", "limits.", "facts.", "detection."))]
    found = sif.in_force(None, check.Resolved("none", None, None, None, False, saved_before_adr247=False), None)
    assert [x.key for x in found.settings] == list(keys)
    assert all(x.source == "default" and x.value is not None for x in found.settings)  # no user path: the defaults


# ---- triggers (gap 3) -----------------------------------------------------------------------------------------------

TRIGGERS = {"T-01": {"label": "Spot within this % of a short strike", "unit": "%", "on": True,
                     "weekly": ["0.75", "0.5", "0.3"], "monthly": ["1.5", "1.0", "0.5"]},
            "T-02": {"label": "Spot crosses a breakeven", "unit": "", "on": True, "weekly": None, "monthly": None}}


@pytest.mark.parametrize(("source", "code"), [("plan", "strategy"), ("active", "user"), ("system", "default")])
def test_trigger_values_carry_the_source_of_the_playbook_in_force(source, code):
    found = sif.in_force(None, check.Resolved(source, {"triggers": TRIGGERS}, 1, None, source == "system",
                                              saved_before_adr247=False), None)
    t1 = found.triggers[0]
    assert (t1.id, t1.weekly, t1.monthly, t1.source, t1.reason) == (
        "T-01", (D("0.75"), D("0.5"), D("0.3")), (D("1.5"), D("1.0"), D("0.5")), code, None)
    assert (found.triggers[1].weekly, found.triggers[1].unit, found.triggers_reason) == (None, None, None)


def test_trigger_answer_states():
    none = sif.in_force(None, check.Resolved("none", None, None, None, False, saved_before_adr247=False), None)
    assert (none.triggers, none.triggers_reason) == ((), sif.NO_PLAYBOOK)
    bad = sif.in_force(None, _plan({"triggers": ["x"]}), None)
    assert (bad.triggers, bad.triggers_reason) == ((), sif.TRIGGERS_UNREADABLE)
    one = sif.in_force(None, _plan({"triggers": {"T-01": {"weekly": [0.75, "0.5", "0.3"]}, "T-03": "x"}}), None)
    assert [(t.id, t.weekly, t.source, t.reason) for t in one.triggers] == [
        ("T-01", None, None, sif.TRIGGER_UNREADABLE), ("T-03", None, None, sif.TRIGGER_UNREADABLE)]


# ---- stops (gap 2), strategy 82's figures (ADR-247) ------------------------------------------------------------------

S82 = sif.MoneyInputs(max_loss=D("23897.04"), credit=D("8918"))
SYSTEM_GUARDS = {"stop_line_pct_of_max_loss": "50"}


def _stops(guards, money=S82, source="system") -> sif.StopsInForce:
    return sif.in_force(None, check.Resolved(source, {"guards": guards}, 1, None, True, saved_before_adr247=False),
                        money).stops


def test_default_stops_on_strategy_82_fire_at_the_smaller_amount_first():
    found = _stops(SYSTEM_GUARDS)
    assert [(x.kind, x.active, x.figure, x.amount, x.source, x.reason) for x in found.lines] == [
        ("max_loss_pct", True, D(50), D("11948.52"), "default", None),
        ("credit_multiple", True, D(2), D("17836.00"), "default", None),
        ("margin_pct", False, None, None, "default", None)]
    assert (found.first, found.reason) == ("max_loss_pct", None)


def test_a_plan_credit_multiple_wins_and_can_fire_first():
    found = _stops({**SYSTEM_GUARDS, "stop_line_x_credit": "1"}, source="plan")
    assert found.lines[1].amount == D("8918.00") and found.lines[1].source == "strategy"
    assert found.first == "credit_multiple"


@pytest.mark.parametrize(("guards", "money", "kind", "reason"), [
    (SYSTEM_GUARDS, sif.MoneyInputs(None, D(8918)), "max_loss_pct", sif.MAX_LOSS_UNKNOWN),
    (SYSTEM_GUARDS, sif.MoneyInputs(UNLIMITED, D(8918)), "max_loss_pct", sif.MAX_LOSS_UNLIMITED),
    (SYSTEM_GUARDS, sif.MoneyInputs(D("23897.04"), D(-100)), "credit_multiple", sif.NO_CREDIT),
    (SYSTEM_GUARDS, sif.MoneyInputs(D("23897.04"), None), "credit_multiple", sif.CREDIT_UNKNOWN),
    ({**SYSTEM_GUARDS, "stop_line_pct_of_margin": "4"}, S82, "margin_pct", sif.MARGIN_NOT_READ),
    ({"stop_line_pct_of_max_loss": 50}, S82, "max_loss_pct", sif.STOP_VALUE_UNREADABLE),
])
def test_a_missing_stop_input_names_its_reason_and_first_is_not_guessed(guards, money, kind, reason):
    found = _stops(guards, money)
    line = next(x for x in found.lines if x.kind == kind)
    assert (line.active, line.amount, line.reason) == (True, None, reason)
    assert (found.first, found.reason) == (None, sif.FIRST_UNKNOWN)


def test_stop_answer_states_without_a_playbook_or_guards():
    assert _stops(None, source="none") == sif.StopsInForce((), None, sif.NO_PLAYBOOK)
    assert sif.stops_of(_plan({"guards": ["x"]}), S82) == sif.StopsInForce((), None, sif.GUARDS_UNREADABLE)


def test_money_inputs_credit_is_the_engine_entry_credit_and_no_market_prices_no_max_loss():
    leg = lambda side, entry: SimpleNamespace(side=side, entry=D(entry), lots=1)  # noqa: E731
    tracked = SimpleNamespace(position=SimpleNamespace(lot=65, legs=[
        leg("BUY", "10"), leg("SELL", "60"), leg("SELL", "70"), leg("BUY", "12")]), booked=D(0), paid_charges=D(0))
    assert sif.money_inputs(tracked, None, None) == sif.MoneyInputs(None, D(108) * 65)


# ---- order defaults (gap 4): two layers, admin default -> user ------------------------------------------------------

ORDER_KEYS = ("orders.default_lots", "orders.start_price", "orders.validity")


def test_order_defaults_are_user_settings_with_sources_and_a_plan_never_sets_them():
    assert set(ORDER_KEYS) <= set(sif.covered_keys())
    user = UserValues({"orders.default_lots": Answer("orders.default_lots", D(3), "yours", D(1), NOW),
                       "orders.validity": Answer("orders.validity", D(1), "default", D(1), None)})
    body = {"settings": {"orders.default_lots": "5", "orders.validity": "2"}}  # never written; never read either
    found = sif.in_force(user, _plan(body), None)
    assert _value(found, "orders.default_lots") == (D(3), "user", None)
    assert _value(found, "orders.validity") == (D(1), "default", None)
    assert _value(found, "orders.start_price") == (D(1), "default", None)  # mid of bid and ask
    with pytest.raises(ValueError, match="not a setting a strategy can change"):
        layers.check_plan_settings({"orders.default_lots": "5"})


def test_an_order_default_out_of_range_from_the_user_layer_fails_closed():
    user = UserValues({"orders.default_lots": Answer("orders.default_lots", D(500), "yours", D(1), NOW)})
    assert _value(sif.in_force(user, _plan({}), None), "orders.default_lots") == (None, None, layers.USER_UNREADABLE)


# ---- fix round 1: the max-loss stop default and the reply's text fields ---------------------------------------------

def test_guards_without_the_max_loss_pct_still_stop_at_50_pct_of_max_loss_first_on_strategy_82():
    """ADR-247: 50 % of max loss is ALWAYS active; a body that does not state it follows the default (source
    "default"), exactly like the credit multiple. Strategy 82: 11,948.52 fires before 17,836."""
    for guards in ({}, {"stop_line_x_credit": "2"}):
        found = _stops(guards, source="plan")
        assert found.lines[0] == sif.StopInForce("max_loss_pct", True, D(50), D("11948.52"), "default", None)
        assert found.lines[1].amount == D("17836.00")
        assert (found.first, found.reason) == ("max_loss_pct", None)
    stated = _stops({"stop_line_pct_of_max_loss": "30"}, source="plan").lines[0]
    assert (stated.figure, stated.amount, stated.source) == (D(30), D("7169.11"), "strategy")


def _system_bodies() -> list[dict]:
    path = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
    return [p["body"] for p in json.loads(path.read_text(encoding="utf-8"))["playbooks"]]


@pytest.mark.parametrize("source", ["plan", "active", "system"])
def test_every_text_field_of_the_in_force_reply_validates_for_every_system_playbook(source):
    """Class: every text field the settings-in-force reply carries (settings[], triggers[], stops) passes its reply
    type for every shipped playbook body: the trigger label through the playbook-trigger-label slot (never the
    settings-registry slot), the unit as a closed code. Before the fix the label raised TypeError (a 500)."""
    for body in _system_bodies():
        reply = ap._in_force_reply(sif.in_force(None, check.Resolved(source, body, 1, None, False,
                                                                     saved_before_adr247=False), S82))
        for row in reply["settings"]:
            ap.SettingInForceOut.model_validate(row)
        for row in reply["triggers"]:
            out = ap.TriggerInForceOut.model_validate(row)
            assert out.unit is None or out.unit in sif.UNIT_CODES.values()
        ap.StopsOut.model_validate(reply["stops"])
    ic = next(b for b in _system_bodies() if "T-01" in b.get("triggers", {}))
    reply = ap._in_force_reply(sif.in_force(None, check.Resolved(source, ic, 1, None, False,
                                                                 saved_before_adr247=False), S82))
    t01 = next(t for t in reply["triggers"] if t["id"] == "T-01")
    assert (str(t01["label"]), t01["unit"]) == (ic["triggers"]["T-01"]["label"], "pct")


@pytest.mark.parametrize(("label", "unit", "want_label", "want_unit"), [
    ('a "quoted" label', "%", None, "pct"),  # the slot refuses it -> None (the id names it), never a 500
    ("", "", None, None),  # empty label / no unit
    ("Delta per lot", "delta/lot", "Delta per lot", "delta_per_lot"),
    ("Odd unit", "furlongs", "Odd unit", None),  # a unit outside the closed set -> None, never free text
])
def test_trigger_label_and_unit_answer_states(label, unit, want_label, want_unit):
    body = {"triggers": {"T-01": {"label": label, "unit": unit, "on": True, "weekly": None, "monthly": None}}}
    row = ap._in_force_reply(sif.in_force(None, _plan(body), None))["triggers"][0]
    out = ap.TriggerInForceOut.model_validate(row)
    assert (None if out.label is None else str(out.label), out.unit) == (want_label, want_unit)
