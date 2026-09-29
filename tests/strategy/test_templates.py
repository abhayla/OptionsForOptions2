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

from ofo.engine.legs import Instrument
from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.strategy.loader import DEFAULT_CATALOGUE_PATH, load_templates
from ofo.strategy.matching import match
from ofo.strategy.model import TemplateError, resolve_template
from ofo.strategy.wording import find_banned_phrases, find_position_words

CATALOGUE = load_templates()
BY_ID = {t.id: t for t in CATALOGUE}
NEAR = datetime.date(2026, 10, 30)
NEXT = datetime.date(2026, 11, 27)

NAKED_CALL = """
  - id: naked_call
    name: "Naked Call"
    description: "Sell a call."
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


def test_catalogue_has_21_templates_adapted_from_algochanakya():
    """AC-3: the catalogue loads as data: 21 templates (legacy 22 minus wheel_strategy, which needs share
    delivery that cash-settled index options never make)."""
    assert len(CATALOGUE) == 21
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
            assert template.id in {"calendar_spread", "diagonal_spread"}
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
     "banned wording ['recommend*'] in name/description"),  # W-046: one combined report, shared-checker labels
    ("underscore-joined advice", NAKED_CALL.replace('"Sell a call."', '"you_should_buy a call."'),
     "banned wording"),
    # W-046: only check_platform_text catches these (the word scans never see a look-alike letter).
    ("Cyrillic look-alike in description", NAKED_CALL.replace('"Sell a call."', '"Sell a cаll."'),
     "non-Latin/confusable"),
    ("zero-width-only description", NAKED_CALL.replace('"Sell a call."', '"​"'), "blank"),
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


NEEDLES = {_normalise(t.id) for t in CATALOGUE} | {_normalise(t.name) for t in CATALOGUE}


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
    }
    assert all(leg.instrument is not Instrument.FUT or leg.strike is None for t in CATALOGUE for leg in t.legs)
