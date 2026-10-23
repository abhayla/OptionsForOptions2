"""REQ-001 AC-4 (W-129): adding an index to the one home (`SUPPORTED_UNDERLYINGS`) turns a test red until every
per-underlying table is filled. Every module-level dict, set, list or tuple in backend/ and frontend/src
that is keyed by underlying names must hold EXACTLY the home's names. Files are discovered from the tree;
a file this scan cannot parse fails the test (fail closed)."""
from __future__ import annotations

import ast
import pathlib
import re

import pytest
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

pytestmark = pytest.mark.repo_scan
ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = frozenset(SUPPORTED_UNDERLYINGS)
#: Index names that are NOT supported yet: a table naming one is as wrong as a table missing a supported one.
UNIVERSE = HOME | {"BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
#: Files that legitimately name several underlyings without being a per-underlying table.
SKIP_PARTS = {"alembic", "__pycache__", "node_modules"}
SKIP_FILES = {"underlying.py"}  # builds the type from the home


def _names_in(node: ast.AST) -> set[str]:
    """The underlying names a table literal is KEYED by: dict keys, or the string elements of a set/list/tuple, or the
    first string argument of each call element (ScenarioConfig("NIFTY", ...))."""
    found: set[str] = set()
    elements: list[ast.AST] = []
    if isinstance(node, ast.Dict):
        elements = [k for k in node.keys if k is not None]
    elif isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        elements = list(node.elts)
    elif isinstance(node, ast.Call) and node.args and isinstance(node.func, ast.Name) and node.func.id in {
            "frozenset", "set", "tuple", "list"}:
        return _names_in(node.args[0])
    for element in elements:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            found.add(element.value)
        elif isinstance(element, ast.Call) and element.args and isinstance(element.args[0], ast.Constant) \
                and isinstance(element.args[0].value, str):
            found.add(element.args[0].value)
    return found & UNIVERSE


def python_tables(source: str, filename: str) -> list[tuple[str, int, set[str]]]:
    tree = ast.parse(source, filename=filename)  # a SyntaxError fails the test
    out = []
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if value is None:
            continue
        names = _names_in(value)
        if names:
            out.append((filename, node.lineno, names))
    return out


_JS_START = re.compile(r"^(?:export\s+)?const\s+([A-Za-z_]\w*)\s*(?::[^=]+)?=\s*", re.MULTILINE)
_JS_KEY = re.compile(r"""(?:^|[{,\s])['"]?([A-Z][A-Z0-9]{2,19})['"]?\s*:""")
_JS_STR = re.compile(r"""['"]([A-Z][A-Z0-9]{2,19})['"]""")


def _balanced(text: str, start: int) -> str:
    """The text of the literal starting at `start` (a bracket, or `Object.freeze(` then a bracket) to its close."""
    opens = {"{": "}", "[": "]", "(": ")"}
    stack: list[str] = []
    in_string = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if ch == in_string and text[i - 1] != "\\":
                in_string = ""
            continue
        if ch in "'\"`":
            in_string = ch
        elif ch in opens:
            stack.append(opens[ch])
        elif ch in opens.values():
            if not stack or stack.pop() != ch:
                raise ValueError("unbalanced brackets")
            if not stack:
                return text[start:i + 1]
    raise ValueError("the literal never closes")


def js_tables(text: str, filename: str) -> list[tuple[str, int, set[str]]]:
    out = []
    for match in _JS_START.finditer(text):
        rest = text[match.end():]
        lead = re.match(r"(?:Object\.freeze\(\s*)?", rest).end()
        if lead >= len(rest) or rest[lead] not in "{[":
            continue  # a function, a string, a number: not a table
        literal = _balanced(rest, lead)  # raises (fails the test) on a literal this scan cannot close
        names = set(_JS_KEY.findall(literal)) if literal.startswith("{") else set(_JS_STR.findall(literal))
        names &= UNIVERSE
        if names:
            out.append((filename, text[:match.start()].count("\n") + 1, names))
    return out


def _vue_script(text: str) -> str:
    match = re.search(r"<script[^>]*>(.*?)</script>", text, re.DOTALL)
    return match.group(1) if match else ""


def all_tables() -> list[tuple[str, int, set[str]]]:
    tables = []
    for path in sorted((ROOT / "backend").rglob("*.py")):
        if SKIP_PARTS & set(path.parts) or path.name in SKIP_FILES:
            continue
        tables += python_tables(path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix())
    for path in sorted((ROOT / "frontend" / "src").rglob("*")):
        if path.suffix not in {".js", ".vue", ".ts"} or SKIP_PARTS & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        text = _vue_script(text) if path.suffix == ".vue" else text
        tables += js_tables(text, path.relative_to(ROOT).as_posix())
    return tables


def test_every_per_underlying_table_has_exactly_the_homes_names() -> None:
    wrong = [f"{f}:{line} has {sorted(names)}" for f, line, names in all_tables() if names != HOME]
    assert not wrong, f"tables keyed by underlying that differ from the home {sorted(HOME)}: {wrong}"


def test_the_scan_finds_the_known_tables() -> None:
    """Guards the scan itself: if it stops seeing the tables it was written for, it proves nothing."""
    seen = {f for f, _, _ in all_tables()}
    for expected in ("backend/ofo/instruments/catalogue.py", "backend/ofo/strategy/placement.py",
                     "backend/ofo/range/pick_lists.py", "backend/ofo/scenario/config.py",
                     "frontend/src/lib/guided.js", "frontend/src/lib/readyMade.js",
                     "frontend/src/composables/useIndexLive.js", "frontend/src/lib/underlyings.js"):
        assert expected in seen, expected


def test_the_scan_goes_red_when_the_home_gains_an_index() -> None:
    grown = {"NIFTY", "SENSEX", "BANKNIFTY"}
    assert any(names != grown for _, _, names in all_tables())  # every real table lacks the new index


def test_the_scan_sees_a_missing_name_and_a_bad_file() -> None:
    assert python_tables('T = {"NIFTY": 1}', "x.py")[0][2] == {"NIFTY"}
    assert js_tables("export const T = { NIFTY: 1 }", "x.js")[0][2] == {"NIFTY"}
    with pytest.raises(SyntaxError):
        python_tables("def (", "bad.py")
    with pytest.raises(ValueError):
        js_tables("export const T = { NIFTY: [1 }", "bad.js")


def test_the_frontend_list_is_the_homes_names_in_order() -> None:
    text = (ROOT / "frontend" / "src" / "lib" / "underlyings.js").read_text(encoding="utf-8")
    match = re.search(r"export const UNDERLYINGS\s*=\s*\[([^\]]*)\]", text)
    assert match, "frontend/src/lib/underlyings.js must export UNDERLYINGS as a plain list"
    assert re.findall(r"""['"]([^'"]+)['"]""", match.group(1)) == list(SUPPORTED_UNDERLYINGS)
