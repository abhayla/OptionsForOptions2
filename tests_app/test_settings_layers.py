"""ADR-245 three-layer resolver (``ofo.settings.layers``), every answer state of every layer read (pure).

Spec basis: ADR-245 "The value in force is the strategy's, else the user's, else the admin default, and every flag,
alert line and Compare cell names the value it used." Contract "Your adjustment settings" step 1 (carry gap) and its
threat model: a layer that exists but cannot be read fails closed with a named reason, never the next layer.
"""
from __future__ import annotations

import datetime
import pathlib
import re
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import carry
from ofo.adjustment import playbook_eval as pe
from ofo.settings import layers
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app.user_preferences_store import Answer, UserValues

# Two tests walk the source tree (rglob), so the whole module carries the mark (tests/test_repo_scan_marked.py).
pytestmark = pytest.mark.repo_scan

KEY = layers.CARRY_GAP_PERCENT
ADMIN = {KEY: D("2")}
USER = {KEY: D("3")}
PLAN = {KEY: "1.5"}


def test_precedence_strategy_then_user_then_default():
    assert layers.resolve(KEY, ADMIN, USER, PLAN) == layers.InForce(KEY, D("1.5"), "strategy")
    assert layers.resolve(KEY, ADMIN, USER, {}) == layers.InForce(KEY, D("3"), "user")
    assert layers.resolve(KEY, ADMIN, None, None) == layers.InForce(KEY, D("2"), "default")


@pytest.mark.parametrize(("strategy", "expected"), [
    (None, (D("3"), "user")),  # no plan: the user's
    ({}, (D("3"), "user")),  # a plan with no settings / an empty container: the user's
    ({"other.something_else": "9"}, (D("3"), "user")),  # the key absent: the user's
    ({KEY: "1.5"}, (D("1.5"), "strategy")),  # present and valid
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
    assert check.Resolved("plan", body, 1, None, False, saved_before_adr247=False).strategy_layer == {KEY: "1.5"}
    for source in ("active", "system", "none"):  # a playbook the user follows is not this strategy's own value
        assert check.Resolved(source, body, 1, None, source == "system",
                              saved_before_adr247=False).strategy_layer is None


def _values(source: str) -> UserValues:
    return UserValues({KEY: Answer(KEY, D("3") if source == "yours" else D("2"), source, D("2"), None)})  # type: ignore[arg-type]


def test_user_layer_is_the_users_own_values_only():
    assert check.user_layer(_values("yours")) == {KEY: D("3")}
    assert check.user_layer(_values("default")) == {}  # a merged default is never "user"
    assert check.user_layer(None) is None  # no user read path: no user layer (the next layer)


class _OwnNotMapping(dict):
    own = ("3",)  # a sequence, not a mapping


@pytest.mark.parametrize("bad", [{KEY: D("3")}, _OwnNotMapping({KEY: D("3")}), "3", 3, [KEY]])
def test_user_values_of_the_wrong_type_fail_closed_never_the_default(bad):
    """Answer states: present (own record) / absent (None) above; wrong type (a merged plain mapping, an ``.own`` that
    is not a mapping, a scalar) -> the named user reason and NO value, never the admin default."""
    assert check.user_layer(bad) == layers.Unreadable(check.USER_VALUES_WITHOUT_OWN)
    assert check.carry_gap_of(D("2"), bad, None) == check.GapInForce(None, None, layers.USER_UNREADABLE)


def test_carry_gap_of_names_value_source_and_reason():
    assert check.carry_gap_of(D("2"), _values("yours"), {KEY: "1.5"}) == check.GapInForce(D("1.5"), "strategy",
                                                                                         None)
    assert check.carry_gap_of(D("2"), _values("yours"), None) == check.GapInForce(D("3"), "user", None)
    assert check.carry_gap_of(D("2"), _values("default"), None) == check.GapInForce(D("2"), "default", None)
    assert check.carry_gap_of(D("2"), _values("yours"), {KEY: "999"}) == check.GapInForce(
        None, None, layers.STRATEGY_UNREADABLE)
    assert check.carry_gap_of(None, None, None) == check.GapInForce(None, None, layers.DEFAULT_UNREADABLE)


def test_carry_figures_and_record_name_the_source_and_the_reason():
    now = datetime.datetime(2026, 10, 30, 15, 0, tzinfo=IST)
    figs = carry.carry_figures(None, D("0"), None, now, gap_pct=D("1.5"), gap_source="strategy")
    assert (figs.gap_pct, figs.gap_source, figs.gap_setting_reason) == (D("1.5"), "strategy", None)
    record = check.carry_record(figs)
    assert (record["gap_pct"], record["gap_source"], record["gap_setting_reason"]) == ("1.5", "strategy", None)
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


@pytest.mark.parametrize(("user", "strategy", "expected"), [
    ("yours", {KEY: "1.5"}, (D("1.5"), "strategy", None)),
    ("yours", None, (D("3"), "user", None)),
    ("default", None, (D("2"), "default", None)),
    ("yours", layers.Unreadable("x"), (None, None, layers.STRATEGY_UNREADABLE)),
])
def test_with_carry_values_the_figures_at_the_gap_in_force_never_the_markets_admin_value(monkeypatch, user,
                                                                                          strategy, expected):
    """The market always holds the ADMIN value (2); the figures follow the gap ``carry_gap_of`` resolved."""
    monkeypatch.setattr(check, "carry_model", lambda tracked, market: None)
    body = {"day_rules": [{"on": True, "when": "beforeWeekend", "at": "15:00", "action": 0}]}
    market = _market(D("2"))  # Friday 2026-10-30 15:00: the carry rule is due
    tracked = SimpleNamespace(position=SimpleNamespace(legs=()), booked=D("0"))
    gap = check.carry_gap_of(market.carry_gap_pct, _values(user), strategy)
    got = check.with_carry(pe.StrategyState(stops=None, expiry_kind="weekly", days_left=4, hhmm="15:00"), body,
                           tracked, market,
                           gap).carry
    assert (got.gap_pct, got.gap_source, got.gap_setting_reason) == expected


def test_state_of_resolves_the_gap_itself_from_two_required_arguments():
    """The choke point: ``state_of`` takes the user values and the strategy layer as REQUIRED keyword arguments (no
    default) and resolves the gap itself; ``with_carry`` takes the resolved gap, never reads the market's value."""
    import inspect  # noqa: PLC0415
    sig = inspect.signature(check.state_of)
    for name in ("user_values", "strategy_layer"):
        assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters[name].default is inspect.Parameter.empty
    assert inspect.signature(check.with_carry).parameters["gap"].default is inspect.Parameter.empty
    src = inspect.getsource(check.state_of)
    assert "carry_gap_of(market.carry_gap_pct, user_values, strategy_layer)" in src
    assert "body, tracked, market, gap)" in src
    assert "carry_gap_pct" not in inspect.getsource(check.with_carry)


def test_watched_strategy_layer_is_required():
    import dataclasses  # noqa: PLC0415

    from ofo_app import background  # noqa: PLC0415
    (field,) = [f for f in dataclasses.fields(background.Watched) if f.name == "strategy_layer"]
    assert field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
    import inspect  # noqa: PLC0415
    assert "resolved.strategy_layer" in inspect.getsource(background.owner_lister)


# ---- every production caller, enumerated by grep (a new call site fails here until it is listed) ------------------
BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
_CALL = re.compile(r"(?<![\w.])(?:check\.)?(state_of|background_state|state_from_market)\(")
#: (file, function called) -> how many calls; each passes the user values and (state_of) the strategy layer
CALL_SITES = {
    ("ofo_app/routes/adjustment_check.py", "state_of"): 1,  # the screen check
    ("ofo_app/routes/playbooks.py", "state_of"): 1,  # POST /api/playbooks/test (missed in round 0)
    ("ofo_app/background.py", "state_of"): 1,  # state_from_market -> the screen's builder
    ("ofo_app/background.py", "state_from_market"): 2,  # background_state and the worker's check
}
_NEEDS = {"state_of": ("user_values=", "strategy_layer="), "state_from_market": ("user_values=",),
          "background_state": ("user_values=",)}


def _call_text(src: str, start: int) -> str:
    depth, i = 0, src.index("(", start)
    for j in range(i, len(src)):
        depth += {"(": 1, ")": -1}.get(src[j], 0)
        if depth == 0:
            return src[start:j + 1]
    raise AssertionError("unbalanced call")


def test_every_production_caller_of_state_of_passes_both_layers():
    found: dict[tuple[str, str], int] = {}
    missing = []
    for path in sorted(BACKEND.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(BACKEND).as_posix()
        for m in _CALL.finditer(src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            if src[line_start:m.start()].strip().startswith("def"):
                continue  # the definition, not a call
            name = m.group(1)
            found[(rel, name)] = found.get((rel, name), 0) + 1
            text = _call_text(src, m.start())
            missing += [(rel, name, arg) for arg in _NEEDS[name] if arg not in text]
    assert found == CALL_SITES  # a new caller: list it here once it passes both layers
    assert missing == []


def test_only_state_of_reads_the_admin_gap_from_the_market():
    """No production code reads ``market.carry_gap_pct`` (the admin layer) except ``state_of``'s one resolution."""
    reads = [(p.relative_to(BACKEND).as_posix(), n) for p in sorted(BACKEND.rglob("*.py"))
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"\bmarket\.carry_gap_pct\b", line) and not line.lstrip().startswith(("#", "else"))]
    assert [r[0] for r in reads] == ["ofo_app/adjustment_check.py"]


def test_check_plan_settings_accepts():
    assert layers.check_plan_settings({KEY: "1.5"}) == {KEY: "1.5"}
    assert layers.check_plan_settings({}) == {}
