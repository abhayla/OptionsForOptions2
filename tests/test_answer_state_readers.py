"""Reader sweep for the server's outcome answer state (finding new-answer-state-without-reader-sweep).

Row 21d added FROM_ENTRIES to OutcomeResponse.state; three frontend readers knew only COMPUTED / NOT_CONNECTED /
REFUSED and only the Playwright CI job noticed, after the push. This test reads the state values from the backend
model source (ast, the app is never imported) and asserts every value appears, as a quoted string, in each named
reader. Add a value to the Literal and this goes red until every reader below names it.

Covered: OutcomeResponse.state in backend/ofo_app/routes/outcome.py.
Parser answer states: Literal found, Enum class found, alias of a Literal (module-level `X = Literal[...]`),
not found / unparseable -> fail closed, reader file or function missing -> fail closed.
Also covered (added with the step-1 sweep, FIELDS below): ChainOut.state, IndicesOut.state, TrackingOut.state, broker
StatusOut.state and .fix (object-key readers), StrikesOut.centre, TemplateOut.level (display-order lists).
Step-1 measurement (origin/main b7670e10): 47 state/status/kind/level/fix fields in backend/ofo_app models; 30 parse
as a
Literal/alias/Enum, 17 do not (plain `str` or union annotations in store/internal models); 8 are switched on by a reader
(the outcome state above plus the 7 added; ChainOut and IndicesOut count once each).
Not covered, with the reason: a reader that checks ONE value and treats the rest as its default cannot be presence-
checked
(DepthOut.state AVAILABLE, StrikesOut/FuturesOut.state LIVE, outcome MarginOut.state CHECKED, zerodha MarginOut.state
available, HealthOut.status healthy, ContractState live in saveDraft.js); no frontend file names the values at all
(outcome
ScenarioOut.kind, ReturnOut.strategy_state, ReturnPlanOut.state, outcome CellOut/ColumnOut.kind: the server sends the
wording); request models, not replies (ready_made QuickPickIn.kind); stored rows, not replies (StoredPlan.status,
VersionOut.state has no reader); the 17 non-Literal fields (str-typed: PlanAnswer.state, StrategyOut.status, ...).
Known blind spots: a reader that switches through a lookup table built at runtime, a value spelled by a constant
or template string, a mention in a comment or an unrelated branch (the value only has to appear quoted), and a
reader that handles the value wrongly. This is a presence check, not a behaviour test.
"""

import ast
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan  # reads backend and frontend source text

ROOT = Path(os.environ.get("OFO_STATE_CHECK_ROOT") or Path(__file__).resolve().parents[1])
MODEL_FILE = "backend/ofo_app/routes/outcome.py"
MODEL_CLASS = "OutcomeResponse"
FIELD = "state"

# (name, file, function to scope to or None for the whole file, values the reader handles as its final `else`).
# applyOutcome ends in `else state.value = 'refused'`, so REFUSED is its default branch and not spelled; any
# other value missing there would silently draw as refused, which is why only REFUSED is excused.
# Picked by grep of the old value set (COMPUTED / NOT_CONNECTED / REFUSED) over frontend/src;
# execute.js reads only COMPUTED on purpose (live-only gate).
READERS = [
    ("useStrategyLive.isOutcome", "frontend/src/composables/useStrategyLive.js", "isOutcome", ()),
    ("LiveStrategyCard.vue", "frontend/src/components/live/LiveStrategyCard.vue", None, ()),
    ("StrategyBuilderPage.applyOutcome", "frontend/src/pages/StrategyBuilderPage.vue", "applyOutcome", ("REFUSED",)),
]


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        pytest.fail(f"cannot read {rel} (under {ROOT})")
    return p.read_text(encoding="utf-8")


def _literal_values(node: ast.AST) -> list[str] | None:
    """Values of a `Literal[...]` subscript, else None."""
    if isinstance(node, ast.Subscript) and (
        (isinstance(node.value, ast.Name) and node.value.id == "Literal")
        or (isinstance(node.value, ast.Attribute) and node.value.attr == "Literal")
    ):
        sl = node.slice
        elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
        if all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elts):
            return [e.value for e in elts]
    return None


def _unwrap_optional(ann: ast.AST) -> ast.AST:
    """`Optional[X]` and `X | None` -> X (None is not a state value); anything else unchanged."""
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id == "Optional":
        return ann.slice
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        for keep, other in ((ann.left, ann.right), (ann.right, ann.left)):
            if isinstance(other, ast.Constant) and other.value is None:
                return keep
    return ann


def state_values(source: str, cls: str = MODEL_CLASS, field: str = FIELD) -> list[str]:
    """The string values of `cls.field`: a Literal, an alias of a Literal, or an Enum class. Fails closed."""
    tree = ast.parse(source)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    aliases = {
        t.id: n.value for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)
    }
    model = classes.get(cls)
    if model is None:
        pytest.fail(f"class {cls} not found")
    ann = next(
        (n.annotation for n in model.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == field),
        None,
    )
    if ann is None:
        pytest.fail(f"{cls}.{field} not found")
    ann = _unwrap_optional(ann)
    vals = _literal_values(ann)
    if vals is None and isinstance(ann, ast.Name):
        if ann.id in aliases:
            vals = _literal_values(aliases[ann.id])
        elif ann.id in classes:  # Enum: member values
            members = [
                n.value.value
                for n in classes[ann.id].body
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
            ]
            vals = members or None
    if not vals:
        pytest.fail(f"{cls}.{field} is not a Literal / Enum of strings this test can parse")
    return vals


def _scope(text: str, func: str | None, name: str) -> str:
    if func is None:
        return text
    m = re.search(rf"(?:function\s+{re.escape(func)}\b|(?:const|let)\s+{re.escape(func)}\s*=)", text)
    if not m:
        pytest.fail(f"function {func} not found in {name}")
    end = text.find("\n}\n", m.start())
    line_end = text.find("\n", m.start())
    first = text[m.start() : line_end if line_end != -1 else len(text)]
    if sum(first.count(c) for c in "{[(") == sum(first.count(c) for c in "}])"):
        return first  # a one-line statement (const X = new Set([...]), const LABEL = {...})
    return text[m.start() : end if end != -1 else len(text)]


def missing_values(values: list[str], text: str, keys: bool = False) -> list[str]:
    """Values the reader text does not name as a quoted string (keys=True: or as an unquoted object key `value:`)."""
    def named(v: str) -> bool:
        if re.search(rf"""['"`]{re.escape(v)}['"`]""", text):
            return True
        return keys and re.search(rf"(?m)(?:^|[\s,{{]){re.escape(v)}\s*:", text) is not None
    return [v for v in values if not named(v)]


def test_the_state_values_are_read_from_the_model():
    vals = state_values(_read(MODEL_FILE))
    assert {"COMPUTED", "NOT_CONNECTED", "REFUSED", "FROM_ENTRIES"} <= set(vals), vals


@pytest.mark.parametrize("name,rel,func,implicit", READERS, ids=[r[0] for r in READERS])
def test_every_outcome_state_appears_in_the_reader(name, rel, func, implicit):
    vals = state_values(_read(MODEL_FILE))
    gone = [v for v in missing_values(vals, _scope(_read(rel), func, name)) if v not in implicit]
    assert not gone, f"{name} ({rel}) does not name outcome state(s) {gone}; the server sends {vals}"


# parser answer states, on synthetic source
def test_parser_accepts_literal_alias_and_enum_and_fails_closed():
    assert state_values("class R:\n    state: Literal['A','B']\n", "R") == ["A", "B"]
    assert state_values("S = Literal['A','B']\nclass R:\n    state: S\n", "R") == ["A", "B"]
    assert state_values("class E(Enum):\n    A='A'\n    B='B'\nclass R:\n    state: E\n", "R") == ["A", "B"]
    assert state_values("class R:\n    state: Optional[Literal['A','B']]\n", "R") == ["A", "B"]
    assert state_values("S = Literal['A']\nclass R:\n    state: S | None\n", "R") == ["A"]
    for bad in ("class Other: pass\n", "class R:\n    other: int\n", "class R:\n    state: str\n"):
        with pytest.raises(pytest.fail.Exception):
            state_values(bad, "R")


def test_missing_reader_function_fails_closed():
    with pytest.raises(pytest.fail.Exception):
        _scope("function other() {}\n", "isOutcome", "x")
    assert missing_values(["A", "B"], "x = ['A']") == ["B"]


# ---- the other sent state fields that a frontend reader switches on (step-1 measurement, see the docstring) ----
# (id, model file, class, field, [(reader name, file, scope function/const or None, implicit values, keys)])
FIELDS = [
    ("ChainOut.state", "backend/ofo_app/chain_push.py", "ChainOut", "state",
     [("useChainLive.isChainAnswer", "frontend/src/composables/useChainLive.js", "isChainAnswer", (), False)]),
    ("IndicesOut.state", "backend/ofo_app/index_push.py", "IndicesOut", "state",
     [("useIndexLive.isIndicesAnswer", "frontend/src/composables/useIndexLive.js", "isIndicesAnswer", (), False)]),
    ("TrackingOut.state", "backend/ofo_app/routes/tracking.py", "TrackingOut", "state",
     [("lib/tracking.js STATES", "frontend/src/lib/tracking.js", "STATES", (), False)]),
    ("broker StatusOut.state", "backend/ofo_app/routes/broker_status.py", "StatusOut", "state",
     [("BrokerSettingsPage LABEL", "frontend/src/pages/BrokerSettingsPage.vue", "LABEL", (), True)]),
    ("broker StatusOut.fix", "backend/ofo_app/routes/broker_status.py", "StatusOut", "fix",
     [("BrokerSettingsPage FIX", "frontend/src/pages/BrokerSettingsPage.vue", "FIX", (), True)]),
    ("StrikesOut.centre", "backend/ofo_app/routes/leg_picker.py", "StrikesOut", "centre",
     [("lib/legPicker.centreText", "frontend/src/lib/legPicker.js", "centreText", (), False)]),
    ("TemplateOut.level", "backend/ofo_app/routes/strategy_templates.py", "TemplateOut", "level",
     [("lib/guided LEVEL_ORDER", "frontend/src/lib/guided.js", "LEVEL_ORDER", (), False),
      ("LearnPage LEVELS", "frontend/src/pages/LearnPage.vue", "LEVELS", (), False)]),
]
CASES = [(f[0], f[1], f[2], f[3], r) for f in FIELDS for r in f[4]]


@pytest.mark.parametrize("fid,model_file,cls,field,reader", CASES, ids=[f"{c[0]}->{c[4][0]}" for c in CASES])
def test_every_value_of_a_sent_state_field_appears_in_its_reader(fid, model_file, cls, field, reader):
    name, rel, func, implicit, keys = reader
    vals = state_values(_read(model_file), cls, field)
    gone = [v for v in missing_values(vals, _scope(_read(rel), func, name), keys) if v not in implicit]
    assert not gone, f"{name} ({rel}) does not name {fid} value(s) {gone}; the server sends {vals}"


def test_key_style_readers_and_one_line_scope():
    assert missing_values(["a", "b"], "const M = { a: 1,\n  b: 2 }", keys=True) == []
    assert missing_values(["a", "b"], "const M = { a: 1 }", keys=True) == ["b"]
    assert missing_values(["a"], "const M = { a: 1 }") == ["a"]  # unquoted key only counts when keys=True
    text = "const L = { a: 1 }\nconst Z = { b: 2 }\n"
    assert "b" not in _scope(text, "L", "x")
