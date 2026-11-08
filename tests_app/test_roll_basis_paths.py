"""ADR-243 fix round 1 (contract "Your adjustment settings" step 2): the roll basis is resolved in ONE place
(``adjustment_check.basis_in_force``) and is a REQUIRED input of the one build path every production caller passes
through (``routes.adjustment.priced_approach`` / ``with_basis``; ``adjustment_check.cheapest_offered``; ``state_of``
with ``entry_facts=``). Before: only the Compare route resolved it, so the adjustment check built every roll on the
target delta for a user whose basis is "Entry distance" (alerts and Compare disagreed).

Core: the same strategy and user give the same roll strikes and basis on Compare and in the adjustment check.
Answer states (through ``state_of``): basis present (user 2) / absent (default) / unreadable (refused); entry facts
present / absent (refused under entry distance) / unreadable (refused). A config with no basis refuses every roll
(``Config.roll_basis`` None = not resolved), never the delta silently. A source scan lists every production caller.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import replace
from decimal import Decimal as D

import pytest
import t19_support as s
from ofo.adjustment.approaches import NO_STRATEGY_BASIS, ROLL_ENTRY_DISTANCE, EntryFacts, build_approach
from ofo.marketdata.spot_source import SpotAnswer
from ofo.settings import layers
from ofo_app import adjustment_check as check
from test_entry_facts import _reply, _values

# One test walks the source tree (rglob), so the whole module carries the mark (tests/test_repo_scan_marked.py).
pytestmark = pytest.mark.repo_scan

SID = "ADJ-02"
FACTS = EntryFacts(D("23000"), D("300"), D("300"))  # as test_entry_facts' reply case: 300 points each side
ROLLS = ("A-01", "A-05")


def _check_builds(monkeypatch, user_values, facts, strategy_layer=None) -> dict:
    """The adjustment check (``state_of``, the ONE function the screen check, the worker and the playbook test pass
    through) on ADJ-02, with a spy on the build path it uses: approach id -> (built approach, call args, kwargs)."""
    seen: dict = {}
    real = check.priced_approach

    def spy(a, *args, **kwargs):
        built, priced = real(a, *args, **kwargs)
        seen[a] = (built, args, kwargs)
        return built, priced

    monkeypatch.setattr(check, "priced_approach", spy)
    sc = s.load(SID)
    tracked, market, spot = s.inputs(sc)
    body = s.body_of(sc)
    body["approaches"]["applicable"] = list(dict.fromkeys([*body["approaches"]["applicable"], *ROLLS]))
    body.pop("guards", None)  # no roll debit limit: the basis decides the strikes, not the playbook's cost cap
    check.state_of(tracked, market, SpotAnswer(spot, "feed", market.now), None, s.RATES, True, body,
                   config=s.PREFS.approach, user_values=user_values, strategy_layer=strategy_layer,
                   entry_facts=facts, resolved=None)  # stops not supplied: this test reads the roll basis only
    assert set(ROLLS) <= set(seen), sorted(seen)  # never a vacuous pass: both rolls were built by the check
    return seen


def test_core_check_builds_entry_distance_rolls_from_the_user_basis(monkeypatch):
    seen = _check_builds(monkeypatch, _values(D(2)), FACTS)
    for a in ROLLS:
        b = seen[a][0]
        assert b.refusal is None, (a, b.refusal)
        assert (b.step_basis, b.step_value, b.basis_source) == (ROLL_ENTRY_DISTANCE, D("300"), layers.SOURCE_USER)


def test_core_compare_and_check_give_the_same_strikes_and_basis(monkeypatch):
    built_by_check = {a: v[0] for a, v in _check_builds(monkeypatch, _values(D(2)), FACTS).items()}
    compare = _reply(monkeypatch, D(2), FACTS)
    for a in ROLLS:
        got, built = compare[a], built_by_check[a]
        assert (got["step_basis"], D(got["step_value"]), got["basis_source"]) == \
            (built.step_basis, built.step_value, built.basis_source), a
        assert sorted((t["type"], D(str(t["strike"])), t["action"]) for t in got["trades"]) == \
            sorted((t.type, t.strike, t.action) for t in built.trades), a


@pytest.mark.parametrize("values", ["none", "changed-nothing"], ids=["no-user-read-path", "changed-nothing"])
def test_user_who_changed_nothing_gets_todays_delta_rolls_byte_identical(monkeypatch, values):
    """Regression: a user who changed nothing (and a caller with no user read path, admin layer not read -> the
    registry default) gets exactly the rolls today's rule builds; only ``basis_source`` names "default"."""
    seen = _check_builds(monkeypatch, _values(None) if values == "changed-nothing" else None, None)
    for a in ROLLS:
        got, args, kwargs = seen[a]
        today, _ = s.priced_approach(a, *args, **{**kwargs, "roll_basis": NO_STRATEGY_BASIS})
        assert got.refusal is None and got.step_basis in ("delta", "points"), (a, got.refusal)
        assert got.basis_source == layers.SOURCE_DEFAULT
        assert replace(got, basis_source=None) == today, a


def test_compare_route_user_who_changed_nothing_is_target_delta_named_default(monkeypatch):
    got = _reply(monkeypatch, None, None)
    built = [a for a in got.values() if a["step_basis"] is not None]
    assert built and {a["basis_source"] for a in built} == {layers.SOURCE_DEFAULT}
    assert {a["step_basis"] for a in built} <= {"delta", "points"}


@pytest.mark.parametrize(("values", "facts", "plan", "refused"), [
    ("entry", FACTS, None, False),  # basis present, facts present: built on entry distance
    ("entry", None, None, True),  # facts absent: refused by name, never the delta
    ("entry", layers.Unreadable("boom"), None, True),  # facts unreadable: refused
    ("plain", FACTS, None, True),  # user layer unreadable (a plain mapping): refused, never a default
    ("entry", FACTS, layers.Unreadable("plan_read_failed"), True),  # plan unreadable: refused
    ("entry", FACTS, {layers.ROLL_BASIS: "1"}, False),  # the plan says target delta: the plan wins
], ids=["basis-facts", "facts-absent", "facts-unreadable", "user-unreadable", "plan-unreadable", "plan-delta"])
def test_answer_states_through_the_check(monkeypatch, values, facts, plan, refused):
    user_values = _values(D(2)) if values == "entry" else {layers.ROLL_BASIS: D(2)}
    seen = _check_builds(monkeypatch, user_values, facts, plan)
    for a in ROLLS:
        b = seen[a][0]
        assert (b.refusal is not None) is refused, (a, b.refusal)
        if refused:
            assert b.trades == () and ("spot at entry is not stored" in b.refusal or "roll basis setting" in b.refusal)
    if plan is not None and not refused:
        assert {seen[a][0].basis_source for a in ROLLS} == {layers.SOURCE_STRATEGY}


def test_a_config_with_no_basis_refuses_every_roll_never_the_delta():
    tracked, market, spot = s.inputs(s.load(SID))
    for a in ROLLS:
        b = build_approach(tracked.position, market.chain, spot, a, replace(s.PREFS.approach, roll_basis=None))
        assert b.refusal is not None and "roll basis setting" in b.refusal and b.trades == (), a


def test_with_basis_refuses_an_unresolved_basis():
    from ofo_app.routes.adjustment import with_basis  # noqa: PLC0415

    with pytest.raises(TypeError):
        with_basis(s.PREFS.approach, None)  # type: ignore[arg-type]


def test_admin_layer_missing_falls_back_to_the_registry_default():
    assert check.admin_of(None, layers.ROLL_BASIS) == D(1)
    no_row = _values(None)
    no_row.admin.pop(layers.ROLL_BASIS)
    assert check.admin_of(no_row, layers.ROLL_BASIS) == D(1)
    bad = _values(None)
    bad.admin[layers.ROLL_BASIS] = "2"  # present but not a Decimal: unreadable, fail closed
    assert check.admin_of(bad, layers.ROLL_BASIS) is None
    assert check.basis_in_force(bad, None, None).reason == layers.DEFAULT_UNREADABLE


# ---- every production caller, enumerated by grep (a new call site fails here until it is listed) ------------------
BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
_CALL = re.compile(r"(?<![\w.])(?:check\.|route\.)?(priced_approach|cheapest_offered|state_of|build_approach|"
                   r"applicable_approaches|with_basis)\(")
#: (file, function) -> calls. priced_approach / cheapest_offered must name ``roll_basis=``; state_of ``entry_facts=``;
#: a direct build_approach call is listed with the config it passes (resolved through ``with_basis``, or a build that
#: never rolls); any config without a basis refuses every roll (``test_a_config_with_no_basis_...``)
CALL_SITES = {
    ("ofo/adjustment/approaches.py", "build_approach"): 1,  # applicable_approaches (a pure caller: config as given)
    ("ofo_app/routes/adjustment.py", "build_approach"): 3,  # priced_approach (with_basis), _available (cfg), NO_CHANGE
    ("ofo_app/routes/adjustment.py", "with_basis"): 2,  # the Compare route's cfg and priced_approach
    ("ofo_app/routes/adjustment.py", "priced_approach"): 1,  # the Compare route
    ("ofo_app/adjustment_check.py", "priced_approach"): 1,  # cheapest_offered (T-19, the check)
    ("ofo_app/adjustment_check.py", "cheapest_offered"): 1,  # state_of
    ("ofo_app/routes/adjustment_check.py", "state_of"): 1,  # the screen check
    ("ofo_app/routes/playbooks.py", "state_of"): 1,  # POST /api/playbooks/test
    ("ofo_app/background.py", "state_of"): 1,  # the worker, through state_from_market
}
_NEEDS = {"priced_approach": ("roll_basis=",), "cheapest_offered": ("roll_basis=",), "state_of": ("entry_facts=",)}


def _call_text(src: str, start: int) -> str:
    depth, i = 0, src.index("(", start)
    for j in range(i, len(src)):
        depth += {"(": 1, ")": -1}.get(src[j], 0)
        if depth == 0:
            return src[start:j + 1]
    raise AssertionError("unbalanced call")


def test_every_production_caller_passes_the_roll_basis():
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
            missing += [(rel, name, arg) for arg in _NEEDS.get(name, ()) if arg not in text]
    assert found == CALL_SITES  # a new caller: list it here once it passes the roll basis
    assert missing == []
