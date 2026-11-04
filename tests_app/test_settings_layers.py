"""ADR-245 three-layer resolver (``ofo.settings.layers``), every answer state of every layer read (pure).

Spec basis: ADR-245 "The value in force is the strategy's, else the user's, else the admin default, and every flag,
alert line and Compare cell names the value it used." Contract "Your adjustment settings" step 1 (carry gap) and its
threat model: a layer that exists but cannot be read fails closed with a named reason, never the next layer.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment import carry
from ofo.adjustment import playbook_eval as pe
from ofo.settings import layers
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app.user_preferences_store import Answer, UserValues

KEY = layers.CARRY_GAP_PERCENT
ADMIN = {KEY: D("2")}
USER = {KEY: D("3")}
PLAN = {KEY: "1.5"}


def test_precedence_strategy_then_user_then_default():
    assert layers.resolve(KEY, ADMIN, USER, PLAN) == layers.InForce(KEY, D("1.5"), "this strategy")
    assert layers.resolve(KEY, ADMIN, USER, {}) == layers.InForce(KEY, D("3"), "your setting")
    assert layers.resolve(KEY, ADMIN, None, None) == layers.InForce(KEY, D("2"), "default")


@pytest.mark.parametrize(("strategy", "expected"), [
    (None, (D("3"), "your setting")),  # no plan: the user's
    ({}, (D("3"), "your setting")),  # a plan with no settings / an empty container: the user's
    ({"other.something_else": "9"}, (D("3"), "your setting")),  # the key absent: the user's
    ({KEY: "1.5"}, (D("1.5"), "this strategy")),  # present and valid
])
def test_strategy_layer_present_absent_empty(strategy, expected):
    got = layers.resolve(KEY, ADMIN, USER, strategy)
    assert (got.value, got.source) == expected


@pytest.mark.parametrize("bad", ["999", "", "  ", "abc", "NaN", 1.5, True, 2, None, ["1.5"]])
def test_strategy_value_refused_fails_closed_never_the_user_or_default(bad):
    with pytest.raises(layers.LayerUnreadable) as refused:
        layers.resolve(KEY, ADMIN, USER, {KEY: bad})
    assert refused.value.code == layers.STRATEGY_UNREADABLE


@pytest.mark.parametrize(("admin", "user", "strategy", "code"), [
    (ADMIN, USER, layers.Unreadable("read failed"), layers.STRATEGY_UNREADABLE),
    (ADMIN, layers.Unreadable("read failed"), None, layers.USER_UNREADABLE),
    (ADMIN, {KEY: D("999")}, None, layers.USER_UNREADABLE),
    (ADMIN, {KEY: "3"}, None, None),  # a decimal string is the same value
    (layers.Unreadable("not read"), None, None, layers.DEFAULT_UNREADABLE),
    ({}, None, None, layers.DEFAULT_UNREADABLE),  # the admin value missing is a defect, never a typed one
    ({KEY: D("999")}, None, None, layers.DEFAULT_UNREADABLE),
    (ADMIN, ["not a mapping"], None, layers.USER_UNREADABLE),
])
def test_each_unreadable_layer_names_itself(admin, user, strategy, code):
    if code is None:
        assert layers.resolve(KEY, admin, user, strategy).value == D("3")
        return
    with pytest.raises(layers.LayerUnreadable) as refused:
        layers.resolve(KEY, admin, user, strategy)
    assert refused.value.code == code


def test_admin_only_keys_are_not_three_layer():
    for key in ("speeds.open_strategy_seconds", "pricing.risk_free_rate", "limits.max_lots"):
        with pytest.raises(KeyError):
            layers.resolve(key, {key: D("1")}, None, None)


@pytest.mark.parametrize(("body", "expected"), [
    (None, None),
    ({"schema": 1}, {}),
    ({"settings": {KEY: "1.5"}}, {KEY: "1.5"}),
])
def test_strategy_layer_of_a_plan_body(body, expected):
    assert layers.strategy_layer(body) == expected


@pytest.mark.parametrize("body", [{"settings": ["1.5"]}, {"settings": "1.5"}, ["not", "an object"]])
def test_strategy_layer_of_an_unreadable_plan_body(body):
    assert isinstance(layers.strategy_layer(body), layers.Unreadable)


def test_only_a_plan_is_a_strategy_layer():
    body = {"settings": {KEY: "1.5"}}
    assert check.Resolved("plan", body, 1, None, False).strategy_layer == {KEY: "1.5"}
    for source in ("active", "system", "none"):  # a playbook the user follows is not this strategy's own value
        assert check.Resolved(source, body, 1, None, source == "system").strategy_layer is None


def _values(source: str) -> UserValues:
    return UserValues({KEY: Answer(KEY, D("3") if source == "yours" else D("2"), source, D("2"), None)})  # type: ignore[arg-type]


def test_user_layer_is_the_users_own_values_only():
    assert check.user_layer(_values("yours")) == {KEY: D("3")}
    assert check.user_layer(_values("default")) == {}  # a merged default is never "your setting"
    assert check.user_layer({KEY: D("3")}) is None  # a plain mapping (a test seam) has no user layer


def test_carry_gap_of_names_value_source_and_reason():
    assert check.carry_gap_of(D("2"), _values("yours"), {KEY: "1.5"}) == check.GapInForce(D("1.5"), "this strategy",
                                                                                         None)
    assert check.carry_gap_of(D("2"), _values("yours"), None) == check.GapInForce(D("3"), "your setting", None)
    assert check.carry_gap_of(D("2"), _values("default"), None) == check.GapInForce(D("2"), "default", None)
    assert check.carry_gap_of(D("2"), _values("yours"), {KEY: "999"}) == check.GapInForce(
        None, None, layers.STRATEGY_UNREADABLE)
    assert check.carry_gap_of(None, None, None) == check.GapInForce(None, None, layers.DEFAULT_UNREADABLE)


def test_carry_figures_and_record_name_the_source_and_the_reason():
    now = datetime.datetime(2026, 10, 30, 15, 0, tzinfo=IST)
    figs = carry.carry_figures(None, D("0"), None, now, gap_pct=D("1.5"), gap_source="this strategy")
    assert (figs.gap_pct, figs.gap_source, figs.gap_setting_reason) == (D("1.5"), "this strategy", None)
    record = check.carry_record(figs)
    assert (record["gap_pct"], record["gap_source"], record["gap_setting_reason"]) == ("1.5", "this strategy", None)
    closed = carry.carry_figures(None, D("0"), None, now, gap_pct=None, gap_source="default",
                                 gap_setting_reason=layers.USER_UNREADABLE)
    assert (closed.gap_pct, closed.gap_source, closed.gap_reason, closed.gap_setting_reason) == (
        None, None, carry.CARRY_GAP_UNKNOWN, layers.USER_UNREADABLE)
    assert isinstance(closed, pe.CarryFigures)


@pytest.mark.parametrize("bad", [{KEY: "999"}, {KEY: ""}, {KEY: 1.5}, {"speeds.open_strategy_seconds": "5"}, []])
def test_check_plan_settings_refuses(bad):
    with pytest.raises(ValueError):
        layers.check_plan_settings(bad)


def _market(admin: D | None):
    from ofo_app.routes.adjustment import MarketInputs  # noqa: PLC0415
    return MarketInputs((), {}, None, None, None, None, None, datetime.datetime(2026, 10, 30, 15, 0, tzinfo=IST),
                        carry_gap_pct=admin)


def test_carry_gap_in_force_replaces_the_admin_value_with_the_strategys():
    got = check.carry_gap_in_force(_market(D("2")), _values("yours"), {KEY: "1.5"})
    assert (got.carry_gap_pct, got.carry_gap_source, got.carry_gap_reason) == (D("1.5"), "this strategy", None)
    closed = check.carry_gap_in_force(_market(D("2")), _values("yours"), layers.Unreadable("x"))
    assert (closed.carry_gap_pct, closed.carry_gap_source, closed.carry_gap_reason) == (
        None, None, layers.STRATEGY_UNREADABLE)


def test_the_worker_and_the_screen_check_both_resolve_through_carry_gap_in_force_before_state_of():
    import inspect  # noqa: PLC0415

    from ofo_app import background  # noqa: PLC0415
    from ofo_app.routes import adjustment_check as route  # noqa: PLC0415
    worker = inspect.getsource(background.Worker._check_unpaused)
    assert worker.index("check.carry_gap_in_force(") < worker.index("state_from_market(")
    screen = inspect.getsource(route.adjustment_check)
    assert screen.index("check.carry_gap_in_force(") < screen.index("check.state_of(")
    assert "resolved.strategy_layer" in inspect.getsource(background.owner_lister)


def test_check_plan_settings_accepts():
    assert layers.check_plan_settings({KEY: "1.5"}) == {KEY: "1.5"}
    assert layers.check_plan_settings({}) == {}
