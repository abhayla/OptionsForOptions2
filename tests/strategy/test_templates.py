"""AC-3: named strategies are data templates; adding one needs no code change; the loader fails closed.
AC-5: no separate hard-coded engine per named strategy.

Spec: REQ-028 AC-3, AC-5; ADR-003 (wording); ADR-042 (strike gaps). L1-L9 are the independent reviewer's
loader reproductions (round-2 review, 2026-09-29).
"""
from __future__ import annotations

import ast
import datetime
import re
import textwrap
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.strategy.loader import DEFAULT_CATALOGUE_PATH, load_templates
from ofo.strategy.matching import Custom, MatchResult, match, match_shape, protective_keys, template_shape
from ofo.strategy.model import (
    EqualConstraint,
    OrderConstraint,
    SignConstraint,
    TemplateError,
    resolve_template,
)
from ofo.strategy.wording import find_banned_phrases, find_position_words

pytestmark = pytest.mark.repo_scan

CATALOGUE = load_templates()
BY_ID = {t.id: t for t in CATALOGUE}
NEAR = datetime.date(2026, 10, 30)
NEXT = datetime.date(2026, 11, 27)

NAKED_CALL = """
  - id: naked_call
    name: "Naked Call"
    description: "Sell a call."
    level: Advanced
    views: [bearish]
    objectives: [directional]
    params:
      - {name: c, unit: steps, default: 2, min: -20, max: 20, must_be_positive: false}
    constraints: []
    legs:
      - {name: short_call, action: SELL, instrument: CE, strike: "c", expiry_slot: near, quantity_multiplier: 1}
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "catalogue.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_catalogue_has_41_templates_adapted_from_algochanakya():
    """AC-3: the catalogue loads as data: 41 templates (legacy 22 minus wheel_strategy, which needs share
    delivery that cash-settled index options never make, plus the 20 reference shapes of RD-090)."""
    assert len(CATALOGUE) == 41
    assert "wheel_strategy" not in BY_ID
    assert DEFAULT_CATALOGUE_PATH.name == "catalogue.yaml"


def test_iron_condor_core_proof_at_nifty():
    """AC-3 core: Iron Condor at defaults, NIFTY spot 23,200, gap 50, prices through the one engine."""
    strategy = resolve_template(
        BY_ID["iron_condor"], spot=Decimal("23200"), strike_gap=Decimal("50"), expiries={"near": NEAR},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")], base_quantity=75,
    )
    assert [leg.strike for leg in strategy.legs] == [Decimal(s) for s in ("23000", "23100", "23300", "23400")]
    metrics = strategy_metrics(strategy)
    assert metrics.max_profit == Decimal("3000")
    assert metrics.max_loss == Decimal("4500")
    assert metrics.breakevens == (Decimal("23060"), Decimal("23340"))


@pytest.mark.parametrize("spot,gap", [(Decimal("23200"), Decimal("50")), (Decimal("79800"), Decimal("100"))])
def test_every_template_resolves_and_prices_through_the_engine(spot, gap):
    """AC-3: every template resolves at a real index gap and prices through the one engine; multi-expiry
    templates raise MultiExpiryError on exact metrics."""
    for template in CATALOGUE:
        strategy = resolve_template(
            template, spot=spot, strike_gap=gap, expiries={"near": NEAR, "next": NEXT},
            prices=[Decimal("10")] * len(template.legs), base_quantity=75,
        )
        assert isinstance(strategy.expiry_pnl_at(spot), Decimal)
        if strategy.is_single_expiry:
            assert strategy_metrics(strategy).max_loss is not None
        else:
            assert template.id in {"calendar_spread", "diagonal_spread", "long_calendar_puts"}
            with pytest.raises(MultiExpiryError):
                strategy_metrics(strategy)


def test_adding_a_template_file_needs_zero_code_changes(tmp_path):
    """AC-3: a new template written only as data loads, resolves at a non-default parameter, prices, and
    matches back to itself with its parameter."""
    (loaded,) = load_templates(_write(tmp_path, "templates:" + NAKED_CALL))
    strategy = resolve_template(
        loaded, spot=Decimal("23200"), strike_gap=Decimal("50"), expiries={"near": NEAR},
        prices=[Decimal("15")], base_quantity=75, overrides={"c": 5},
    )
    assert strategy.legs[0].strike == Decimal("23450")
    assert strategy_metrics(strategy).max_profit == Decimal("1125")
    result = match(strategy, spot=Decimal("23200"), strike_gap=Decimal("50"), templates=(loaded,))
    assert result.template.id == "naked_call" and dict(result.params) == {"c": 5}


# L1-L9 (reviewer) plus further red cases: each file must be REFUSED with the stated reason.
BAD_FILES = [
    ("L1 duplicate key in a leg", NAKED_CALL.replace('strike: "c",', 'strike: "c", strike: "c + 1",'),
     "duplicate key 'strike'"),
    ("L2 unknown top-level key", "version: 1\ntemplates:" + NAKED_CALL, "Additional properties"),
    ("L3 second templates block", NAKED_CALL + "\ntemplates:" + NAKED_CALL.replace("naked_call", "other"),
     "duplicate key 'templates'"),
    ("L4 parameter bound 999", NAKED_CALL.replace("max: 20", "max: 999"), "999 is greater than the maximum"),
    ("L4b strike constant 999", NAKED_CALL.replace('strike: "c"', 'strike: "c + 999"'), "beyond +/-50"),
    ("L5 id with spaces and punctuation", NAKED_CALL.replace("id: naked_call", "id: 'Iron Condor!'"),
     "does not match"),
    ("L6 two templates with one name",
     NAKED_CALL + NAKED_CALL.replace("naked_call", "naked_put").replace("CE", "PE"), "duplicate template name"),
    ("L7 two templates with one shape",
     NAKED_CALL + NAKED_CALL.replace("naked_call", "call_sale").replace("Naked Call", "Call Sale"), "share a shape"),
    ("L8 position word without its constraint",
     NAKED_CALL.replace('"Sell a call."', '"Sell an out-of-the-money call."'), "position word class 'otm'"),
    ("L9 duplicate id", NAKED_CALL + NAKED_CALL.replace("Naked Call", "Other Name"), "duplicate template id"),
    ("unknown param in a strike", NAKED_CALL.replace('strike: "c"', 'strike: "c + z"'), "unknown parameter 'z'"),
    ("param used by no leg",
     NAKED_CALL.replace("    constraints", "      - {name: z, unit: steps, default: 0, min: 0, max: 1, "
                        "must_be_positive: false}\n    constraints"), "appear in no leg strike"),
    ("boolean where an int belongs", NAKED_CALL.replace("default: 2", "default: true"), "is not of type 'integer'"),
    ("default outside bounds", NAKED_CALL.replace("default: 2", "default: 30"), "min <= default <= max"),
    ("futures leg with a strike", NAKED_CALL.replace("instrument: CE", "instrument: FUT"), "should not be valid"),
    ("banned advice wording", NAKED_CALL.replace('"Sell a call."', '"The best way to sell a call."'),
     "banned wording"),
    # W-024 / Q226: wording only the shared tokenised checker catches (a stem, and `_`-joined words).
    ("Q226 stem wording", NAKED_CALL.replace('"Sell a call."', '"Our recommendation: sell a call."'),
     "banned wording"),
    ("underscore-joined advice", NAKED_CALL.replace('"Sell a call."', '"you_should_buy a call."'),
     "banned wording"),
    ("misspelled leg key", NAKED_CALL.replace("quantity_multiplier", "qty_multiplier"), "qty_multiplier"),
    ("YAML merge key", NAKED_CALL.replace("    constraints: []", "    constraints: []\n    <<: {x: 1}"),
     "merge keys"),
]


@pytest.mark.parametrize("label,body,reason", BAD_FILES, ids=[b[0] for b in BAD_FILES])
def test_loader_refuses_bad_catalogue(tmp_path, label, body, reason):
    """AC-3: the loader fails closed on every malformed catalogue (reviewer L1-L9 and further red cases)."""
    text = body if body.lstrip().startswith(("templates", "version")) else "templates:" + body
    with pytest.raises(TemplateError, match=re.escape(reason)):
        load_templates(_write(tmp_path, text))


def test_wording_banned_and_position_words():
    """AC-3 (ADR-003): no catalogue text carries banned advice wording; the position-word scan finds each class."""
    for template in CATALOGUE:
        assert find_banned_phrases(f"{template.name} {template.description}") == [], template.id
    assert find_position_words("Sell an at-the-money call and an OTM put with protective wings") == {
        "atm", "otm", "protective"}
    assert find_position_words("Sell a call at a higher strike") == set()


# --- AC-5: no template id or name in backend code; no branch on a template's id or name. ------------------

def _normalise(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _offenders(source: str, needles: set[str]) -> list[str]:
    """Identifiers, attribute names, arguments and non-docstring string literals whose letters-only lowercase
    form contains a template id or name; plus any comparison or ``match`` of ``.id``/``.name`` to a string.
    Docstrings are documentation (like comments) and are skipped."""
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }
    found: list[str] = []
    for node in ast.walk(tree):
        texts: list[str] = []
        if isinstance(node, ast.Name):
            texts.append(node.id)
        elif isinstance(node, ast.Attribute):
            texts.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            texts.append(node.name)
        elif isinstance(node, ast.arg):
            texts.append(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            texts.append(node.value)
        for text in texts:
            normal = _normalise(text)
            found += [f"{text!r} contains {n!r}" for n in needles if n in normal]
            if needles is NEEDLES:
                found += _word_hits(text)
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(isinstance(s, ast.Attribute) and s.attr in {"id", "name"} for s in sides) and any(
                isinstance(c, ast.Constant) and isinstance(c.value, str)
                for s in sides for c in ast.walk(s)
            ):
                found.append(f"comparison of .id/.name to a string at line {node.lineno}")
        if isinstance(node, ast.Match) and isinstance(node.subject, ast.Attribute) and node.subject.attr in {"id", "name"}:
            found.append(f"match on .{node.subject.attr} at line {node.lineno}")
    return found


# The 21 templates of the first catalogue (ids, current names and the names they had before RD-095) are matched as
# substrings, as before. The 20 reference shapes of RD-090 have short everyday words as ids ("strip" is `str.strip`,
# "strap", "batman"), so a substring scan would flag ordinary code: those are matched as whole word sequences
# (`buy_call`, `Sell Put (ATM)`), and the single-word ones are covered by the `.id`/`.name` comparison rule only.
_FIRST_IDS = {
    "bull_call_spread", "bull_put_spread", "synthetic_long", "bear_put_spread", "bear_call_spread", "synthetic_short",
    "iron_condor", "iron_butterfly", "short_straddle", "short_strangle", "jade_lizard", "long_straddle",
    "long_strangle",
    "reverse_iron_condor", "covered_call", "cash_secured_put", "calendar_spread", "diagonal_spread", "butterfly_spread",
    "ratio_backspread_call", "ratio_backspread_put",
}
_OLD_NAMES = {"Straddle (Short)", "Strangle (Short)", "Straddle (Long)", "Strangle (Long)", "Iron Condor",
              "Reverse Iron Condor", "Calendar Spread", "Butterfly Spread", "Synthetic Long", "Synthetic Short"}
NEEDLES = ({_normalise(i) for i in _FIRST_IDS} | {_normalise(t.name) for t in CATALOGUE if t.id in _FIRST_IDS}
           | {_normalise(n) for n in _OLD_NAMES})
_NEW = [t for t in CATALOGUE if t.id not in _FIRST_IDS]
WORD_NEEDLES = {tuple(re.findall(r"[a-z]+", w.lower())) for t in _NEW for w in (t.id.replace("_", " "), t.name)}
_MIN_WORDS = 2
WORD_NEEDLES = {n for n in WORD_NEEDLES if len(n) >= _MIN_WORDS}


def _word_hits(text: str) -> list[str]:
    """Whole-word runs of a new template's id or name inside an identifier or string (camelCase and `_` split)."""
    words = re.findall(r"[a-z]+", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).lower())
    return [f"{text!r} contains the words {' '.join(n)!r}" for n in WORD_NEEDLES
            if any(tuple(words[i:i + len(n)]) == n for i in range(len(words)))]


def test_ac5_scanner_catches_every_disguise():
    """AC-5 red cases (review F4): each disguise of a per-template engine is flagged."""
    for snippet in (
        "def iron_condor(): pass",
        "class IronCondorEngine: pass",
        "def price_iron_condor(x): return x",
        "LABEL = 'iron condor'",
        "IRON_CONDOR = 1",
        "def f(t):\n    if t.id == 'anything':\n        return 1",
        "def f(t):\n    if t.name in ('x', 'y'):\n        return 1",
        "def f(t):\n    match t.id:\n        case 'x':\n            return 1",
    ):
        assert _offenders(snippet, NEEDLES), snippet
    assert _offenders('def f():\n    """An Iron Condor example."""\n    return 1', NEEDLES) == []


def test_no_template_id_or_name_in_backend_code():
    """AC-5: no backend module names a template in code or branches on a template's id or name."""
    backend = Path(__file__).resolve().parents[2] / "backend"
    scanned = sorted(backend.rglob("*.py"))
    assert len(scanned) >= 15 and backend / "ofo" / "strategy" / "matching.py" in scanned  # not vacuous
    offenders = [
        f"{path.relative_to(backend)}: {problem}"
        for path in sorted(backend.rglob("*.py"))
        for problem in _offenders(path.read_text(encoding="utf-8"), NEEDLES)
    ]
    assert offenders == []


def test_catalogue_descriptions_hold_for_every_parameter_value():
    """AC-3 (review F6): only templates whose constraints make a position word always true use one."""
    uses = {t.id: find_position_words(f"{t.name} {t.description}") for t in CATALOGUE}
    assert {tid for tid, kinds in uses.items() if kinds} == {
        "iron_butterfly", "short_straddle", "long_straddle", "short_strangle", "long_strangle",
        "jade_lizard", "covered_call", "cash_secured_put",
        # RD-090: each is true for every allowed value by a sign constraint or a constant zero strike
        "range_forward", "risk_reversal", "reverse_jade_lizard", "sell_put_atm", "strap", "strip",
        "long_iron_butterfly",
    }
    assert all(leg.instrument is not Instrument.FUT or leg.strike is None for t in CATALOGUE for leg in t.legs)


# --- REQ-078 AC-2 (W-158): the Width and Hedge controls are catalogue DATA, not per-template code. --------------------

WIDTH_ADJUSTABLE = {"short_straddle", "short_strangle", "long_straddle", "long_strangle", "iron_condor",
                    "reverse_iron_condor", "iron_butterfly", "long_iron_butterfly"}  # Sensibull's 8 Width codes
HEDGE_SHAPES = {"bull_call_spread", "bull_put_spread", "bear_put_spread", "bear_call_spread", "iron_condor",
                "iron_butterfly"}  # the templates that carry a Hedge (protective) leg today


def test_req_078_width_adjustable_is_exactly_the_eight_shapes_of_ac_2():
    assert {t.id for t in CATALOGUE if t.width_adjustable} == WIDTH_ADJUSTABLE
    assert all(type(t.width_adjustable) is bool for t in CATALOGUE)


def test_req_078_hedge_applies_only_to_the_templates_with_protective_legs():
    assert {t.id for t in CATALOGUE if any(leg.protective for leg in t.legs)} == HEDGE_SHAPES


# --- ADR-186 (4): unequal wings keep the shape name; a NEW strategy still starts with equal wings. ----------------

UNEQUAL_SPOT, UNEQUAL_GAP = Decimal("23000"), Decimal("50")
EQUAL_WING_TEMPLATES = {"iron_condor", "iron_butterfly", "reverse_iron_condor", "long_iron_butterfly"}


def _legs(rows):
    return [Leg(Action(a), Instrument(i), Decimal(k), NEAR, 65, Decimal("10")) for a, i, k in rows]


def test_core_unequal_wing_condor_on_real_listed_strikes_is_an_iron_condor_with_both_hedge_marks():
    """ADR-186 (4) core: the ADR's example, SELL 22800 PE / BUY 22500 PE (put wing 300), SELL 23200 CE / BUY 23400 CE
    (call wing 200), all listed on the fixture's 2026-10-06 NIFTY expiry, is named Iron Condor, both BUY legs Hedge."""
    legs = _legs([("SELL", "PE", "22800"), ("BUY", "PE", "22500"), ("SELL", "CE", "23200"), ("BUY", "CE", "23400")])
    result = match(legs, spot=UNEQUAL_SPOT, strike_gap=UNEQUAL_GAP, templates=CATALOGUE)
    assert isinstance(result, MatchResult) and result.template.id == "iron_condor"
    assert (result.params["w_put"], result.params["w_call"]) == (6, 4)
    marks = protective_keys(result)
    kinds = {(a, i) for a, i, _, _ in marks}
    assert kinds == {(Action.BUY, Instrument.PE), (Action.BUY, Instrument.CE)} and len(marks) == len(kinds)


def test_an_unequal_wing_iron_butterfly_is_named_with_its_hedge_marks():
    legs = _legs([("SELL", "PE", "23000"), ("BUY", "PE", "22800"), ("SELL", "CE", "23000"), ("BUY", "CE", "23300")])
    result = match(legs, spot=UNEQUAL_SPOT, strike_gap=UNEQUAL_GAP, templates=CATALOGUE)
    assert isinstance(result, MatchResult) and result.template.id == "iron_butterfly"
    assert {i for _, i, _, _ in protective_keys(result)} == {Instrument.PE, Instrument.CE}


def test_the_long_twins_with_unequal_wings_keep_their_names():
    for template_id in ("long_iron_butterfly", "reverse_iron_condor"):
        template = BY_ID[template_id]
        equal = next(c for c in template.constraints if isinstance(c, EqualConstraint))
        point = {**template.defaults(), equal.params[0]: 3, equal.params[1]: 2}
        assert template.violations(point) and not template.violations(point, matching=True), template_id
        shape = template_shape(template, point)
        result = match_shape(shape, CATALOGUE)
        assert isinstance(result, MatchResult) and result.template.id == template_id, template_id


def test_a_new_strategy_built_from_the_catalogue_still_has_equal_wings():
    """Building keeps the equal-wings default: an unequal override is refused by resolve, for every template that has
    an equal constraint."""
    equal_templates = [t for t in CATALOGUE if any(isinstance(c, EqualConstraint) for c in t.constraints)]
    assert {t.id for t in equal_templates} == EQUAL_WING_TEMPLATES
    for template in equal_templates:
        equal = next(c for c in template.constraints if isinstance(c, EqualConstraint))
        defaults = template.defaults()
        assert defaults[equal.params[0]] == defaults[equal.params[1]], template.id
        with pytest.raises(TemplateError):
            resolve_template(template, spot=UNEQUAL_SPOT, strike_gap=UNEQUAL_GAP, expiries={"near": NEAR},
                             prices=[Decimal("10")] * len(template.legs), base_quantity=65,
                             overrides={equal.params[0]: 3, equal.params[1]: 2})


def test_every_equal_constraint_is_build_only_and_an_unknown_constraint_kind_must_be_classified():
    """Standing item (c): fails closed. Every EqualConstraint in the catalogue is build_only; the matcher-skipped set
    is exactly the build_only equal constraints, so a new constraint kind is not silently skipped or silently kept."""
    seen = 0
    for template in CATALOGUE:
        for constraint in template.constraints:
            assert isinstance(constraint, (EqualConstraint, SignConstraint, OrderConstraint)), (template.id, constraint)
            if isinstance(constraint, EqualConstraint):
                assert constraint.build_only is True, template.id
                seen += 1
    assert seen == len(EQUAL_WING_TEMPLATES)


def test_two_puts_and_one_call_is_still_a_custom_strategy():
    legs = _legs([("BUY", "PE", "22800"), ("SELL", "PE", "22500"), ("SELL", "CE", "23200")])  # a put pair + ONE call
    assert isinstance(match(legs, spot=UNEQUAL_SPOT, strike_gap=UNEQUAL_GAP, templates=CATALOGUE), Custom)
    # a put pair + call pair whose order is wrong (short put above short call) stays Custom as well
    wrong = _legs([("SELL", "PE", "23400"), ("BUY", "PE", "23100"), ("SELL", "CE", "23200"), ("BUY", "CE", "23400")])
    assert isinstance(match(wrong, spot=UNEQUAL_SPOT, strike_gap=UNEQUAL_GAP, templates=CATALOGUE), Custom)


def test_the_families_in_the_not_applicable_texts_follow_the_catalogue_data_not_a_typed_list(monkeypatch):
    """REQ-078 AC-2: change a label in the data and the control's families change with it; a control with a template
    that has no label is refused (fail closed)."""
    from dataclasses import replace

    from ofo.strategy import shape_families

    assert shape_families.control_families("width") == ("straddles", "strangles", "iron butterflies", "iron condors")
    assert shape_families.control_families("hedge") == ("vertical spreads", "iron butterflies", "iron condors")
    relabelled = tuple(replace(t, family_plural="odd fish") if t.id == "iron_condor" else t for t in CATALOGUE)
    monkeypatch.setattr(shape_families, "load_templates", lambda: relabelled)
    assert "odd fish" in shape_families.control_families("width")
    unlabelled = tuple(replace(t, family_plural=None) if t.id == "iron_condor" else t for t in CATALOGUE)
    monkeypatch.setattr(shape_families, "load_templates", lambda: unlabelled)
    with pytest.raises(ValueError):
        shape_families.control_families("width")
    with pytest.raises(ValueError):
        shape_families.control_families("shift")


def test_the_catalogue_names_the_shape_family_for_the_not_applicable_texts():
    """REQ-078 AC-2: the plural family label is DATA on the templates, never typed in backend code."""
    labels = {t.id: t.family_plural for t in CATALOGUE if t.family_plural}
    assert labels["iron_condor"] == "iron condors" and labels["iron_butterfly"] == "iron butterflies"
    assert labels["short_straddle"] == labels["long_straddle"] == "straddles"
    assert labels["short_strangle"] == labels["long_strangle"] == "strangles"
    assert {t.id for t in CATALOGUE if t.width_adjustable} <= set(labels)
    assert {t.id for t in CATALOGUE if any(leg.protective for leg in t.legs)} <= set(labels)
