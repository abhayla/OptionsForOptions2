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

ALLOW-LIST (fix round 1, finding guard-as-forbidden-list): the comparison rules above name shapes, and a language has
more ways to name a broker than any list of shapes (``b.startswith('zerodha')``, an import alias, SQL text). So ANY
broker word in feature code is a finding unless its file and exact line text are on the reasoned allow-list
``broker_name_allowlist.py``. Python is resolved by AST (string constants except docstrings; every name, attribute,
import and alias holding a broker word; names the tree binds to a broker string); JS/Vue is a token scan with comments
stripped. An allow-list entry whose line no longer exists is a finding (stale). Known limit: a name built from
strings at runtime (``getattr(m, 'Ki' + 'te')``) is not seen. The scratch cases below prove each red and that the same
text in a data-layer module stays green.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import pytest
from broker_name_allowlist import ALLOW

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


#: Found anywhere inside a word: ZerodhaKite, KiteBrokerReader, connect_zerodha.
SUBSTRING_WORDS: Final = ("zerodha", "kite")
CAMEL: Final = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _has_broker_word(value: str) -> bool:
    """A broker word in any casing or joining: a substring word, or a whole word of ``BROKER_WORDS`` (split on
    non-letters and camel-case humps)."""
    lower = value.lower()
    if any(w in lower for w in SUBSTRING_WORDS):
        return True
    return any(t.lower() in BROKER_WORDS for t in (*TOKEN.findall(lower), *CAMEL.findall(value)))


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _named_words(node: ast.AST, bound: frozenset[str]) -> list[str]:
    """Every identifier this node introduces or uses (name, attribute, import, alias, def, argument, keyword)."""
    if isinstance(node, ast.Name):
        names = [node.id]
    elif isinstance(node, ast.Attribute):
        names = [node.attr]
    elif isinstance(node, ast.alias):
        names = [node.name, node.asname or ""]
    elif isinstance(node, ast.ImportFrom):
        names = [node.module or ""]
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names = [node.name]
    elif isinstance(node, ast.arg):
        names = [node.arg]
    elif isinstance(node, ast.keyword):
        names = [node.arg or ""]
    else:
        return []
    return [n for n in names if n and (_has_broker_word(n) or n in bound)]


def scan_python_words(source: str, bound: frozenset[str]) -> list[int]:
    """Lines holding ANY broker word as code (a string constant that is not a docstring, or an identifier);
    comments never reach the AST. Raises SyntaxError if unparsable."""
    tree = ast.parse(source)
    docs = _docstring_ids(tree)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                and _has_broker_word(node.value):
            hits.append(node.lineno)
        elif _named_words(node, bound):
            hits.append(getattr(node, "lineno", 0))
    return sorted(set(hits))


def scan_python(source: str, bound: frozenset[str]) -> list[int]:
    """Lines of broker-name use: a broker word anywhere in code, or a comparison / match / dispatch key on a
    ``broker`` identifier; raises SyntaxError if unparsable."""
    hits = list(scan_python_words(source, bound))
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
JS_COMPARE: Final = re.compile(rf"(?:===|!==|==|!=)\s*{_JS_OPERAND}|{_JS_OPERAND}\s*(?:===|!==|==|!=)", re.I)
JS_CALL: Final = re.compile(rf"\.(?:includes|indexOf|startsWith|endsWith|has|get|some|find|test)\(\s*{_JS_OPERAND}|"
                            rf"Object\.is\([^)]*{_JS_OPERAND}|"
                            rf"{_QUOTED}[^;\n]*\.(?:includes|indexOf)\(|\bcase\s+{_QUOTED}", re.I)
JS_BLOCK_COMMENT: Final = re.compile(r"/\*.*?\*/|<!--.*?-->", re.S)
JS_LINE_COMMENT: Final = re.compile(r"(?:(?<=\s)|^)//[^\n]*")


def strip_js_comments(source: str) -> str:
    """Blank out comments, keeping the line count so hit line numbers stay true."""
    blank = JS_BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    return "\n".join(JS_LINE_COMMENT.sub("", line) for line in blank.split("\n"))


def scan_js(source: str) -> list[int]:
    """Lines holding ANY broker word outside comments (a literal, a name, a regex, a key), plus the comparison and
    lookup shapes on a ``broker`` identifier (``BROKER``, ``brokerId``)."""
    hits = []
    for number, line in enumerate(strip_js_comments(source).splitlines(), start=1):
        if _has_broker_word(line):
            hits.append(number)
            continue
        for pattern in (JS_COMPARE, JS_CALL):
            for match in pattern.finditer(line):
                text = match.group(0)
                bare = re.sub(_QUOTED, "", text)  # a path such as '/broker/status' is text, not an identifier
                if re.search(r"broker(?:_?id|_?name|_?key)?\b", bare, re.I):
                    hits.append(number)
    return sorted(set(hits))


def scan_tree(root: Path, minimums: Mapping[str, int] | None = None,
              allow: Mapping[tuple[str, str], str] | None = None) -> list[str]:
    """Findings (``path:line: reason``) over the feature folders under ``root``; empty means clean. A missing feature
    folder is always a finding; ``minimums`` is how many files a folder must hold (the real tree's floor); ``allow``
    maps (path, stripped line text) to its reason (the real tree uses ``ALLOW``, a scratch tree none)."""
    findings: list[str] = []
    if minimums is None:  # the real tree has a floor; a scratch tree only needs its folders to exist
        minimums = MIN_FEATURE_FILES if root == ROOT else {}
    if allow is None:
        allow = ALLOW if root == ROOT else {}
    for (rel_path, line_text), reason in allow.items():  # a stale or unexplained entry is itself a finding
        target = root / rel_path
        exists = target.is_file() and line_text in {ln.strip() for ln in
                                                    target.read_text(encoding="utf-8").splitlines()}
        if not exists:
            findings.append(f"{rel_path}: allow-list entry is stale (line no longer exists): {line_text!r}")
        if not reason.strip():
            findings.append(f"{rel_path}: allow-list entry has no reason: {line_text!r}")
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
            source_lines = text.splitlines()
            findings.extend(f"{name}:{n}: names a broker (or compares a broker id); ask a capability flag instead, or "
                            "add the line to broker_name_allowlist.py with a reason"
                            for n in lines if (name, source_lines[n - 1].strip() if 0 < n <= len(source_lines)
                                               else "") not in allow)
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


#: Fix round 1: the verifier's unlisted shapes (an allow-list, not a list of shapes: all must be red).
PY_BYPASS_PLANTS = {
    "startswith": "def f(b):\n    return b.startswith('zerodha')\n",
    "dunder eq": "def f(b):\n    return 'zerodha'.__eq__(b)\n",
    "camel literal": "def f(b):\n    return b == 'ZerodhaKite'\n",
    "class name compare": "def f(r):\n    return type(r).__name__ == 'KiteBrokerReader'\n",
    "isinstance": "def f(r):\n    return isinstance(r, KiteBrokerReader)\n",
    "import alias": "from ofo.instruments.models import ZERODHA as Z\ndef f(b):\n    return b == Z\n",
    "local alias": "from ofo.instruments import models\nZ = models.ZERODHA\ndef f(b):\n    return b == Z\n",
    "dict get": "def f(T):\n    return T.get('kite')\n",
    "module set": "BROKERS = {'zerodha', 'x'}\ndef f(b):\n    return b in BROKERS\n",
    "contains": "S = frozenset(['zerodha'])\ndef f(b):\n    return S.__contains__(b)\n",
    "sql text": "Q = \"SELECT 1 FROM public.broker_sessions WHERE broker = 'zerodha'\"\n",
    "match capture": "def f(b):\n    match b:\n        case 'upstox':\n            return 1\n",
    "f-string": "def f(b):\n    return f\"{b}-kite\"\n",
}
JS_BYPASS_PLANTS = {
    "const alias": "const Z = 'zerodha'\nif (b === Z) {}\n",
    "BROKER constant": "if (b === BROKER) {}\n",
    "some": "list.some(x => x === 'zerodha')\n",
    "multi-line includes": "const ok = names.includes(\n  'zerodha'\n)\n",
    "camel literal": "if (b === 'ZerodhaKite') {}\n",
    "map key": "const v = MAP['zerodha']\n",
    "regex": "/zerodha/i.test(b)\n",
    "Object.is": "Object.is(b, 'kite')\n",
}


@pytest.mark.parametrize("label", sorted(PY_BYPASS_PLANTS))
def test_ac3_each_unlisted_python_shape_is_red(tmp_path: Path, label: str) -> None:
    """AC-3 (fix round 1, attack 1): shapes the old forbidden-list missed are red under the allow-list."""
    assert scan_tree(_tree(tmp_path, "backend/ofo_app/routes/planted.py", PY_BYPASS_PLANTS[label])), label


@pytest.mark.parametrize("label", sorted(PY_BYPASS_PLANTS))
def test_ac3_the_same_unlisted_python_shape_in_a_data_layer_module_is_green(tmp_path: Path, label: str) -> None:
    """AC-3 (attack 2): the same text in the session store (data layer) is clean."""
    assert scan_tree(_tree(tmp_path, "backend/ofo_app/broker_token_store.py", PY_BYPASS_PLANTS[label])) == [], label


@pytest.mark.parametrize("label", sorted(JS_BYPASS_PLANTS))
def test_ac3_each_unlisted_js_shape_is_red(tmp_path: Path, label: str) -> None:
    """AC-3 (attack 1): the JS shapes the old scan missed, in .js and .vue (inside a script block)."""
    root = _tree(tmp_path, "frontend/src/lib/planted.js", JS_BYPASS_PLANTS[label])
    assert scan_tree(root), label
    vue = f"<template><p>x</p></template>\n<script>\n{JS_BYPASS_PLANTS[label]}</script>\n"
    assert scan_tree(_tree(tmp_path, "frontend/src/components/Planted.vue", vue)), label


def test_ac3_the_verifier_bypass_startswith_in_a_feature_module_is_red(tmp_path: Path) -> None:
    """AC-3 (the proof): ``b.startswith('zerodha')`` in a feature module was green before this fix, red after."""
    findings = scan_tree(_tree(tmp_path, "backend/ofo/strategy/planted.py", PY_BYPASS_PLANTS["startswith"]))
    assert [f for f in findings if "strategy/planted.py:2" in f]


def test_ac3_allow_listed_line_is_green_and_a_stale_entry_is_red(tmp_path: Path) -> None:
    """AC-3 (attack 3): an allow-listed line passes; an entry whose line is gone is itself a finding."""
    rel = "backend/ofo_app/routes/planted.py"
    root = _tree(tmp_path, rel, "LABEL = 'Margin (Zerodha)'\n")
    assert scan_tree(root, allow={(rel, "LABEL = 'Margin (Zerodha)'"): "a label"}) == []
    stale = scan_tree(root, allow={(rel, "LABEL = 'Margin (Zerodha)'"): "a label",
                                   (rel, "GONE = 'zerodha'"): "no longer there"})
    assert any("stale" in f for f in stale)
    assert any("no reason" in f for f in scan_tree(root, allow={(rel, "LABEL = 'Margin (Zerodha)'"): " "}))
    assert any("stale" in f for f in scan_tree(root, allow={("backend/ofo_app/routes/missing.py", "x"): "r"}))


def test_ac3_a_comment_or_docstring_is_not_a_finding_and_a_second_script_block_is(tmp_path: Path) -> None:
    """AC-3 (attack 4): comments/docstrings are ignored; every ``<script>`` block of a .vue file is scanned."""
    py = '"""Talks about Zerodha."""\n# kite here\ndef f():\n    """Zerodha docstring."""\n    return 1  # zerodha\n'
    assert scan_tree(_tree(tmp_path, "backend/ofo_app/routes/ok.py", py)) == []
    js = "// zerodha\n/* kite\n   zerodha */\nconst x = 1 // kite\n"
    assert scan_tree(_tree(tmp_path, "frontend/src/lib/ok.js", js)) == []
    vue = "<!-- zerodha -->\n<script>\nconst a = 1\n</script>\n<script setup>\nconst b = 'zerodha'\n</script>\n"
    found = scan_tree(_tree(tmp_path, "frontend/src/components/Two.vue", vue))
    assert [f for f in found if "Two.vue:6" in f] and not [f for f in found if "Two.vue:1:" in f]


def test_ac3_every_allow_list_entry_has_a_reason() -> None:
    """AC-3 (attack 7): the real allow-list is explained, entry by entry."""
    assert ALLOW and all(r.strip() for r in ALLOW.values())


@pytest.mark.parametrize("text", [
    'def f(state):\n    return state == "connected"\n',
    'def f(b):\n    return {"broker": b}\n', 'def f(a):\n    return a["state"]\n',
])
def test_ac3_text_and_unrelated_comparisons_are_not_flagged(tmp_path: Path, text: str) -> None:
    """AC-3: an unrelated comparison and a dict VALUE are not findings (no false red)."""
    assert scan_tree(_tree(tmp_path, "backend/ofo_app/routes/ok.py", text)) == []


@pytest.mark.parametrize("text", ["if (state === 'connected') {}\n", "const r = { broker: 'x' }\n"])
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
