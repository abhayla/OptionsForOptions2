"""REQ-117 AC-3 (W-132): "A repo test fails if feature code compares a broker name or id (for example "zerodha") instead
of a flag."

FEATURE code is named by path (``FEATURE_PYTHON`` folders under ``backend/`` and ``FEATURE_JS`` under ``frontend/src``);
its files are DISCOVERED from the tree, never listed. Data-layer modules (the catalogue, eligibility and reconciliation
stores, the broker adapter) sit outside by path: per-broker tables keyed by broker are legitimate there.

Fail closed (standing item c): a Python file that does not parse, a JS/Vue file that is not UTF-8, a feature folder that
is missing or nearly empty is a finding, never a skip. The Python scan is an AST walk, so quoting style, spacing and
line breaks do not matter. A broker id is a string that holds a broker's name (``BROKER_WORDS``) or a name the tree
itself binds to one (``ZERODHA = "zerodha"``, found by walking ``backend/``, not typed here), or the attribute/name
``broker``/``broker_id``/``broker_name``. The scan flags:

* a comparison (``==``, ``!=``, ``in``, ``not in``, ``is``) with a broker id on either side, tuple/list/set members too;
* a ``match`` case on a broker string; a broker string used as a subscript key (dispatch by name);
* in JS/Vue: ``===``/``!==``/``==``/``!=``, ``switch``/``case``, ``includes``/``indexOf``/``startsWith``/``endsWith``
  next to a quoted broker string, or a comparison of ``.broker``/``broker_id``/``brokerName``.

Text is not a comparison: a label such as "Margin (Zerodha)" is not flagged. The scratch cases below prove each
red and that the same text in a data-layer module stays green.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parents[1]
FEATURE_PYTHON: Final = ("backend/ofo_app/routes", "backend/ofo/strategy", "backend/ofo/outcome")
FEATURE_JS: Final = ("frontend/src",)
JS_SUFFIXES: Final = frozenset({".js", ".ts", ".vue", ".mjs", ".jsx", ".tsx"})
#: The brokers the platform could meet (REQ-054's scan vocabulary, tests/test_one_broker_only.py BROKERISH).
BROKER_WORDS: Final = frozenset({
    "zerodha", "kite", "upstox", "angel", "angelone", "fyers", "dhan", "groww", "paytm", "icici", "kotak", "motilal",
    "5paisa", "shoonya", "finvasia", "flattrade", "aliceblue", "iifl", "openalgo", "smartapi"})
BROKER_IDENTIFIERS: Final = frozenset({"broker", "broker_id", "brokerid", "broker_name", "brokername", "brokerkey"})
MIN_FEATURE_FILES: Final = {"backend/ofo_app/routes": 10, "backend/ofo/strategy": 3, "backend/ofo/outcome": 3,
                            "frontend/src": 30}
TOKEN: Final = re.compile(r"[a-z0-9]+")


def _is_broker_text(value: object) -> bool:
    return isinstance(value, str) and any(t in BROKER_WORDS for t in TOKEN.findall(value.lower()))


def _identifier(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _bound_broker_names(root: Path) -> frozenset[str]:
    """Names the backend binds to a broker string at module level (``ZERODHA = "zerodha"``): found, not typed."""
    found = set()
    for path in sorted((root / "backend").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue  # an unreadable file is reported by the feature scan if it is feature code
        for node in tree.body:
            if isinstance(node, ast.Assign) and _is_broker_text(getattr(node.value, "value", None)):
                found.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                    and _is_broker_text(getattr(node.value, "value", None)):
                found.add(node.target.id)
    return frozenset(found)


def _broker_operand(node: ast.AST, bound: frozenset[str]) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and _is_broker_text(sub.value):
            return True
        ident = _identifier(sub)
        if ident is not None and (ident in bound or ident.lower() in BROKER_IDENTIFIERS):
            return True
    return False


def scan_python(source: str, bound: frozenset[str]) -> list[int]:
    """Lines of broker-name use as a comparison / match / dispatch key; raises SyntaxError if unparsable."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            if any(_broker_operand(o, bound) for o in (node.left, *node.comparators)):
                hits.append(node.lineno)
        elif isinstance(node, (ast.MatchValue, ast.MatchSingleton)):
            if _broker_operand(getattr(node, "value", node), bound):
                hits.append(node.lineno)
        elif (isinstance(node, ast.Subscript) and _identifier(node.value) != "Literal"  # Literal[...] is a type
              and _broker_operand(node.slice, bound)):
            hits.append(node.lineno)
    return sorted(set(hits))


_QUOTED = r"""(?:'[^'\n]*'|"[^"\n]*"|`[^`\n]*`)"""
_JS_OPERAND = rf"(?:{_QUOTED}|[\w$.\[\]?]*[bB]roker(?:_?[iI]d|_?[nN]ame|[kK]ey)?\b)"
JS_COMPARE: Final = re.compile(rf"(?:===|!==|==|!=)\s*{_JS_OPERAND}|{_JS_OPERAND}\s*(?:===|!==|==|!=)")
JS_CALL: Final = re.compile(rf"\.(?:includes|indexOf|startsWith|endsWith|has|get)\(\s*{_JS_OPERAND}|"
                            rf"{_QUOTED}[^;\n]*\.(?:includes|indexOf)\(|\bcase\s+{_QUOTED}")


def scan_js(source: str) -> list[int]:
    """Lines where a broker word (or a ``broker`` identifier) is compared, switched on or looked up."""
    hits = []
    for number, line in enumerate(source.splitlines(), start=1):
        for pattern in (JS_COMPARE, JS_CALL):
            for match in pattern.finditer(line):
                text = match.group(0)
                quoted = re.findall(_QUOTED, text)
                bare = re.sub(_QUOTED, "", text)  # a path such as '/broker/status' is text, not an identifier
                if any(_is_broker_text(q) for q in quoted) or re.search(
                        r"[bB]roker(?:_?[iI]d|_?[nN]ame|[kK]ey)?\b", bare):
                    hits.append(number)
    return sorted(set(hits))


def scan_tree(root: Path, minimums: Mapping[str, int] | None = None) -> list[str]:
    """Findings (``path:line: reason``) over the feature folders under ``root``; empty means clean. A missing feature
    folder is always a finding; ``minimums`` is how many files a folder must hold (the real tree's floor)."""
    findings: list[str] = []
    if minimums is None:  # the real tree has a floor; a scratch tree only needs its folders to exist
        minimums = MIN_FEATURE_FILES if root == ROOT else {}
    bound =_bound_broker_names(root)
    for rel in (*FEATURE_PYTHON, *FEATURE_JS):
        folder = root / rel
        files = [p for p in sorted(folder.rglob("*")) if p.is_file()] if folder.is_dir() else []
        wanted = (".py",) if rel in FEATURE_PYTHON else tuple(JS_SUFFIXES)
        files = [p for p in files if p.suffix in wanted and "node_modules" not in p.parts]
        minimum = max(minimums.get(rel, 0), 1)
        if not folder.is_dir() or len(files) < minimum:
            findings.append(f"{rel}: only {len(files)} feature files found (expected >= {minimum}): wrong folder?")
        for path in files:
            name = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
                lines = scan_python(text, bound) if path.suffix == ".py" else scan_js(text)
            except (SyntaxError, UnicodeDecodeError, ValueError) as error:
                findings.append(f"{name}: cannot be read ({type(error).__name__}); unreadable cannot be cleared")
                continue
            findings.extend(f"{name}:{n}: compares or switches on a broker name or id; ask a capability flag instead"
                            for n in lines)
    return findings


def test_ac3_feature_code_never_compares_a_broker_name_or_id() -> None:
    """AC-3: the real tree is clean (a feature asks a flag, never the broker's name)."""
    assert scan_tree(ROOT) == []


# --- the scratch cases: each rule goes red; the same text in a data-layer module is green ---------------------

def _tree(tmp_path: Path, rel: str, text: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    consts = tmp_path / "backend/ofo/broker/session.py"  # where the tree binds the broker id
    consts.parent.mkdir(parents=True, exist_ok=True)
    consts.write_text('BROKER_ZERODHA = "zerodha"\n', encoding="utf-8")
    for rel_folder in FEATURE_PYTHON:  # every feature folder exists and holds one harmless file
        (tmp_path / rel_folder).mkdir(parents=True, exist_ok=True)
        (tmp_path / rel_folder / "stub.py").write_text("X = 1\n", encoding="utf-8")
    for rel_folder in FEATURE_JS:
        (tmp_path / rel_folder).mkdir(parents=True, exist_ok=True)
        (tmp_path / rel_folder / "stub.js").write_text("export const x = 1\n", encoding="utf-8")
    return tmp_path


PY_PLANTS = {
    "eq string": 'def f(b):\n    return b == "zerodha"\n',
    "eq string single quote kite": "def f(b):\n    return b != 'kite'\n",
    "uppercase and spaces": 'def f(b):\n    return b == "  ZERODHA "\n',
    "reversed": 'def f(b):\n    return "zerodha" == b\n',
    "in tuple": 'def f(b):\n    return b in ("upstox", "zerodha")\n',
    "in list not in": 'def f(b):\n    return b not in ["fyers"]\n',
    "in set": 'def f(b):\n    return b in {"angel"}\n',
    "constant by name": 'ZERODHA = "zerodha"\ndef f(b):\n    return b == ZERODHA\n',
    "attribute constant": 'def f(b, mod):\n    return b is mod.BROKER_ZERODHA\n',
    "broker attribute": 'def f(ref, x):\n    return ref.broker == x\n',
    "broker_id name": "def f(broker_id, x):\n    return broker_id != x\n",
    "compare in call": 'def f(b):\n    return int(b == "kite")\n',
    "multi-line": 'def f(b):\n    return (\n        b\n        ==\n        "zerodha"\n    )\n',
    "match case": 'def f(b):\n    match b:\n        case "zerodha":\n            return 1\n',
    "subscript key": 'def f(t):\n    return t["kite"]\n',
    "token inside text": 'def f(b):\n    return b == "kite-connect"\n',
}
JS_PLANTS = {
    "===": "if (broker === 'zerodha') {}\n",
    "!==": 'if (b.broker !== "kite") {}\n',
    "reversed": "if ('zerodha' === b) {}\n",
    "loose": "if (b == 'upstox') {}\n",
    "includes": "['zerodha', 'upstox'].includes(b)\n",
    "includes arg": "const ok = names.includes('zerodha')\n",
    "switch case": "switch (b) {\n  case 'zerodha':\n    break\n}\n",
    "template literal": "if (b === `zerodha`) {}\n",
    "broker field": "if (row.broker === other) {}\n",
    "broker_id field": "if (row.broker_id !== other) {}\n",
    "kite": "if (x === 'kite') {}\n",
}


@pytest.mark.parametrize("label", sorted(PY_PLANTS))
def test_ac3_a_planted_python_comparison_in_feature_code_is_red(tmp_path: Path, label: str) -> None:
    """AC-3 (attack 4): each planted shape in a feature folder is a finding."""
    root = _tree(tmp_path, "backend/ofo_app/routes/planted.py", PY_PLANTS[label])
    assert scan_tree(root), label


@pytest.mark.parametrize("label", sorted(PY_PLANTS))
def test_ac3_the_same_python_text_in_a_data_layer_module_is_green(tmp_path: Path, label: str) -> None:
    """AC-3 (attack 4): the same text in a data-layer module (outside the feature folders by path) is clean."""
    root = _tree(tmp_path, "backend/ofo_app/catalogue_store.py", PY_PLANTS[label])
    assert scan_tree(root) == [], label


@pytest.mark.parametrize("label", sorted(JS_PLANTS))
def test_ac3_a_planted_js_comparison_in_feature_code_is_red(tmp_path: Path, label: str) -> None:
    """AC-3 (attack 4): each planted JS shape under frontend/src is a finding, in .js and in .vue."""
    for name in ("src/lib/planted.js", "src/components/Planted.vue"):
        root = _tree(tmp_path, f"frontend/{name}", JS_PLANTS[label])
        assert scan_tree(root), (label, name)


def test_ac3_the_same_js_text_outside_the_feature_folders_is_green(tmp_path: Path) -> None:
    """AC-3: the scan covers frontend/src only; the same text elsewhere (a tools script) is not scanned."""
    root = _tree(tmp_path, "frontend/scripts/planted.js", "".join(JS_PLANTS.values()))
    assert scan_tree(root) == []


@pytest.mark.parametrize("text", [
    'LABEL = "Margin (Zerodha)"\n', 'def f(state):\n    return state == "connected"\n',
    'def f(b):\n    return {"broker": b}\n', 'def f(a):\n    return a["state"]\n',
    'from typing import Literal\nStep = Literal["zerodha_login", "connected"]\n',
])
def test_ac3_text_and_unrelated_comparisons_are_not_flagged(tmp_path: Path, text: str) -> None:
    """AC-3: a label naming the broker, an unrelated comparison and a dict VALUE are not findings (no false red)."""
    assert scan_tree(_tree(tmp_path, "backend/ofo_app/routes/ok.py", text)) == []


@pytest.mark.parametrize("text", ["const label = 'Margin (Zerodha)'\n", "if (state === 'connected') {}\n",
                                  "const r = { broker: 'x' }\n"])
def test_ac3_js_text_and_unrelated_comparisons_are_not_flagged(tmp_path: Path, text: str) -> None:
    """AC-3: no false red on JS text, an unrelated comparison or an object literal."""
    assert scan_tree(_tree(tmp_path, "frontend/src/lib/ok.js", text)) == []


def test_ac3_a_file_that_cannot_be_read_is_a_finding_not_a_skip(tmp_path: Path) -> None:
    """AC-3 / standing item (c): unparsable Python and a non-UTF-8 JS file each fail closed."""
    root = _tree(tmp_path, "backend/ofo_app/routes/broken.py", "def f(:\n")
    assert any("cannot be read" in f for f in scan_tree(root))
    path = tmp_path / "frontend/src/lib/binary.js"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00 if (x === 'zerodha') {}")
    assert any("cannot be read" in f for f in scan_tree(tmp_path))


def test_ac3_a_missing_feature_folder_is_a_finding(tmp_path: Path) -> None:
    """AC-3: a scan pointed at the wrong folder finds nothing to read and says so (never a silent pass)."""
    (tmp_path / "backend").mkdir()
    assert len([f for f in scan_tree(tmp_path) if "feature files found" in f]) == len(FEATURE_PYTHON) + len(FEATURE_JS)


def test_ac3_the_real_feature_folders_are_found_and_large_enough() -> None:
    """AC-3: the real tree really has the folders and enough files in them (the scan is not vacuous)."""
    for rel, minimum in MIN_FEATURE_FILES.items():
        found = [p for p in (ROOT / rel).rglob("*") if p.is_file() and "node_modules" not in p.parts]
        assert len(found) >= minimum, rel
    assert "ZERODHA" in _bound_broker_names(ROOT)  # the constant is discovered from the tree, not typed in the test
