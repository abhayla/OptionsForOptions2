"""Reader sweep for the server's outcome answer state (finding new-answer-state-without-reader-sweep).

Row 21d added FROM_ENTRIES to OutcomeResponse.state; three frontend readers knew only COMPUTED / NOT_CONNECTED /
REFUSED and only the Playwright CI job noticed, after the push. This test reads the state values from the backend
model source (ast, the app is never imported) and asserts every value appears, as a quoted string, in each named
reader. Add a value to the Literal and this goes red until every reader below names it.

Covered: OutcomeResponse.state in backend/ofo_app/routes/outcome.py.
Parser answer states: Literal found, Enum class found, alias of a Literal (module-level `X = Literal[...]`),
not found / unparseable -> fail closed, reader file or function missing -> fail closed.
Not covered (same Literal/Enum shape in reply models, readers not swept): outcome.py kind and the 4-value
"NOT_AVAILABLE_YET" state model, leg_picker.py state (3 models), tracking.py state and kind, broker_status.py
Level and Fix, execution_return.py strategy_state, strategies.py state, chain_push.py and index_push.py state,
ready_made.py kind, health.py status.
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
    return text[m.start() : end if end != -1 else len(text)]


def missing_values(values: list[str], text: str) -> list[str]:
    return [v for v in values if not re.search(rf"""['"`]{re.escape(v)}['"`]""", text)]


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
    for bad in ("class Other: pass\n", "class R:\n    other: int\n", "class R:\n    state: str\n"):
        with pytest.raises(pytest.fail.Exception):
            state_values(bad, "R")


def test_missing_reader_function_fails_closed():
    with pytest.raises(pytest.fail.Exception):
        _scope("function other() {}\n", "isOutcome", "x")
    assert missing_values(["A", "B"], "x = ['A']") == ["B"]
