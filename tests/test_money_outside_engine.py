"""AC-3 (REQ-063, ADR-008): no money or P&L figure is computed outside the calculation engine.

Widens the guard that used to cover only backend/ofo/rules/ (finding money-value-computed-outside-engine) to every
Python module under backend/ and every .vue/.js/.ts file under frontend/src. It is an allow-list: the engine homes
below may do money arithmetic; every other file is scanned and any arithmetic touching a money-named value fails.

Threat model: in scope - arithmetic (+ - * / // % and augmented forms) on a value named premium, price, pnl, charge(s),
margin, ltp, mtm, funds, brokerage, including through a one-step alias, getattr with a literal name, a dict key and an
aliased import; in the browser also Number()/parseFloat()/toFixed() outside the chart files and arithmetic on a
money-named identifier. Out of scope - code built at run time, generated files, test files.
"""
from __future__ import annotations

import ast
import pathlib
import re
from collections.abc import Callable

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND_SRC = ROOT / "frontend" / "src"

# Allowed homes (repo-relative, posix). Everything else is scanned.
PY_ALLOWED_DIRS = ("backend/ofo/engine/", "backend/ofo/scenario/", "backend/ofo/charges/")
PY_ALLOWED_FILES = ("backend/ofo/money.py",)
# Chart drawing and colour-intensity files that the vue rule permits to call Number() (vue-frontend.md).
JS_ALLOWED_FILES = (
    "frontend/src/components/strategy/PayoffChart.vue",
    "frontend/src/components/strategy/PnLCell.vue",
)

MONEY_TOKENS = {"premium", "premiums", "price", "prices", "pnl", "charge", "charges", "margin", "margins", "ltp",
                "mtm", "funds", "brokerage"}
# Money arithmetic that already sits outside the engine on main (GC-1 audit gap). A BASELINE, not an allowance: the
# test fails on any line not listed here, and fails when a listed line is fixed or gone (delete the entry then). Each
# entry is a deferred finding (see the W-110 report); do not add to this table.
KNOWN_ON_MAIN: dict[str, tuple[str, ...]] = {
    "backend/ofo/execution/cost.py": (
        'return _SIGN[order.side] * order.price * order.quantity',
        'net = sum((signed_premium(o) for o in orders), Decimal(0))',
    ),
    "backend/ofo/execution/margin_gate.py": (
        'required += max(Decimal(0), quantity * price - _premium(row.get("option_premium")))',
    ),
    "backend/ofo/execution/sequence.py": (
        'impact[ref] = base - plan_margin(Strategy(others), planner).total',
    ),
    "backend/ofo/marketdata/forward.py": (
        'atm = min(strikes, key=lambda k: abs(k - spot.ltp))',
    ),
    "backend/ofo/orders/model.py": (
        'cash -= f.price * signed',
    ),
    "backend/ofo/outcome/service.py": (
        'max_loss = metrics.max_loss if loss_unl or charges is None else metrics.max_loss + charges  # ADR-082 (2)',
        'max_profit = metrics.max_profit if profit_unl or charges is None else metrics.max_profit - charges',
    ),
    "backend/ofo/rules/inputs.py": (
        'values[InputName.PNL_PCT_OF_MAX_PROFIT] = pnl * 100 / metrics.max_profit',
        'values[InputName.PNL_PCT_OF_MAX_LOSS] = -pnl * 100 / metrics.max_loss',
    ),
    "backend/ofo/table/model.py": (
        'entry_value = core.entry_price * core.quantity',
        'current_value = core.ltp * core.quantity if core.ltp is not None else None',
        'net_entry = None if has_futures else sum(',
        '((leg.premium if leg.action is Action.SELL else -leg.premium) * leg.quantity for leg in legs), Decimal(0))',
        'net_current = None if has_futures else sum(',
        '((leg.ltp if leg.action is Action.SELL else -leg.ltp) * leg.quantity for leg in legs), Decimal(0))',
        'unrealized = sum((live_pnl(leg.leg) for leg in legs), Decimal(0))',
    ),
}

MIN_PY_FILES = 100  # sanity floors: the scan really reads the trees
MIN_FRONTEND_FILES = 30
ARITH_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)


def is_money_name(name: str) -> bool:
    """True when a snake_case or camelCase identifier has a money word as one of its parts.

    An UPPER_CASE name is a constant or enum member (a label, not a value) and an is_/has_ name is a flag."""
    if name.isupper() or name.lstrip("_").startswith(("is_", "has_")):
        return False
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return any(part in MONEY_TOKENS for part in spaced.lower().split("_"))


def _literal_name(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _own_money_ref(node: ast.AST) -> bool:
    """A single node that reads a money-named value (name, attribute, dict key, getattr/attrgetter literal)."""
    if isinstance(node, ast.Name):
        return is_money_name(node.id)
    if isinstance(node, ast.Attribute):
        return is_money_name(node.attr)
    if isinstance(node, ast.Subscript):
        key = _literal_name(node.slice)
        return key is not None and is_money_name(key)
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name in ("getattr", "attrgetter"):
            args = node.args[1:2] if name == "getattr" else node.args
            return any((lit := _literal_name(a)) is not None and is_money_name(lit.split(".")[-1]) for a in args)
        if name == "get":
            return any((lit := _literal_name(a)) is not None and is_money_name(lit) for a in node.args[:1])
    return False


def _money_aliases(tree: ast.AST) -> set[str]:
    """Names that stand for a money value: aliased imports of money-named objects and ``other = <money value>``."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):  # a rename must not hide the name (fail closed)
            aliases.update(a.asname for a in node.names if a.asname and is_money_name(a.name.split(".")[-1]))
        if isinstance(node, ast.Assign) and _own_money_ref(node.value):
            aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    for node in ast.walk(tree):  # once more, so a chain a = price; b = a; c = b * 2 is still caught
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return aliases


def _is_money_arithmetic(node: ast.AST, reads_money: Callable[[ast.AST], bool]) -> bool:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ARITH_OPS):
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            return False  # "%s" % x / string building is not arithmetic
        return reads_money(node)
    if isinstance(node, ast.AugAssign) and isinstance(node.op, ARITH_OPS):
        return reads_money(node.target) or reads_money(node.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sum":
        return bool(node.args) and reads_money(node.args[0])
    return False


def money_arithmetic(source: str) -> list[int]:
    """Line numbers of arithmetic whose operands (at any depth) read a money-named value, an alias of one included."""
    tree = ast.parse(source)
    aliases = _money_aliases(tree)

    def reads_money(sub: ast.AST) -> bool:
        return any(_own_money_ref(n) or (isinstance(n, ast.Name) and n.id in aliases) for n in ast.walk(sub))

    return sorted({n.lineno for n in ast.walk(tree) if _is_money_arithmetic(n, reads_money)})


# ---- the browser side -----------------------------------------------------------------------------------------------

_JS_IDENT = r"[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*"
_JS_OP = r"(?:\*\*|[*/%+\-])=?"
_JS_COERCE = re.compile(r"\b(?:Number|parseFloat|parseInt)\s*\(|\.toFixed\s*\(|\bMath\.(?:round|floor|ceil|trunc)\s*\(")
_JS_ARITH = re.compile(rf"({_JS_IDENT})\s*({_JS_OP})\s*({_JS_IDENT}|\d)|(\d)\s*({_JS_OP})\s*({_JS_IDENT})")
_JS_STRINGS = re.compile(r"""'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""")
_JS_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/|<!--.*?-->", re.S)


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def js_money_arithmetic(source: str) -> list[int]:
    """Line numbers where browser code coerces a number or does arithmetic on a money-named identifier.

    Comments and string literals are blanked first, keeping line numbers. Template markup (`<div class="a-b">`) is not
    code, so for .vue files only the <script> block and mustache/bound expressions are scanned by the caller."""
    text = _JS_COMMENTS.sub(_blank, source)
    text = _JS_STRINGS.sub(_blank, text)
    bad: set[int] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _JS_COERCE.search(line):
            bad.add(lineno)
        for m in _JS_ARITH.finditer(line):
            names = [g for g in (m.group(1), m.group(3), m.group(4), m.group(6)) if g and not g[0].isdigit()]
            if any(is_money_name(part) for n in names for part in re.split(r"\??\.", n)):
                bad.add(lineno)
    return sorted(bad)


def _vue_code(source: str) -> str:
    """Keep <script> bodies and template expressions ({{ }} and :bound / @event attribute values); blank the rest."""
    out = [" " if c != "\n" else "\n" for c in source]

    def keep(start: int, end: int) -> None:
        for i in range(start, end):
            out[i] = source[i]

    for m in re.finditer(r"<script[^>]*>(.*?)</script>", source, re.S):
        keep(m.start(1), m.end(1))
    for m in re.finditer(r"\{\{(.*?)\}\}", source, re.S):
        keep(m.start(1), m.end(1))
    for m in re.finditer(r"""\s(?::|v-bind:|v-if=|v-show=|@|v-on:)[\w.:\-\[\]]*=("[^"]*"|'[^']*')""", source):
        keep(m.start(1) + 1, m.end(1) - 1)
    return "".join(out)


def _rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def python_files() -> list[pathlib.Path]:
    files = [p for p in BACKEND.rglob("*.py") if "alembic" not in p.parts and "__pycache__" not in p.parts]
    return sorted(p for p in files
                  if not _rel(p).startswith(PY_ALLOWED_DIRS) and _rel(p) not in PY_ALLOWED_FILES)


def frontend_files() -> list[pathlib.Path]:
    files = [p for p in FRONTEND_SRC.rglob("*") if p.suffix in (".vue", ".js", ".ts")]
    return sorted(p for p in files if _rel(p) not in JS_ALLOWED_FILES)


def scan_frontend(path: pathlib.Path) -> list[int]:
    source = path.read_text(encoding="utf-8")
    return js_money_arithmetic(_vue_code(source) if path.suffix == ".vue" else source)


# ---- AC-3 -----------------------------------------------------------------------------------------------------------


def test_guard_flags_planted_money_arithmetic_python():
    """AC-3: mutation - a planted premium times quantity (and its disguised forms) is flagged; plain reads are not."""
    assert money_arithmetic("total = premium * quantity") == [1]
    assert money_arithmetic("total = leg.ltp * leg.quantity") == [1]
    assert money_arithmetic("x = row['premium'] * 2") == [1]
    assert money_arithmetic("x = getattr(leg, 'entry_price') - 1") == [1]
    assert money_arithmetic("net += leg.premium") == [1]
    assert money_arithmetic("net = sum(-leg.premium for leg in legs)") == [1]
    assert money_arithmetic("from engine import net_premium as np_\nx = np_ + 1") == [2]
    assert money_arithmetic("p = leg.ltp\nq = p\nx = q * 2") == [3]
    # Plain reads, comparisons, string building and non-money arithmetic are not money arithmetic.
    assert money_arithmetic("x = leg.ltp is None") == []
    assert money_arithmetic("x = premium > limit") == []
    assert money_arithmetic("x = quantity * lot_size") == []
    assert money_arithmetic("x = 'premium: %s' % value") == []
    assert money_arithmetic("x = f'{premium}'") == []


def test_guard_flags_planted_money_arithmetic_browser():
    """AC-3: mutation - a planted premium * quantity in a .js and a .vue file is flagged; shown-as-given is not."""
    assert js_money_arithmetic("const total = premium * quantity") == [1]
    assert js_money_arithmetic("const t = leg.ltp - 2") == [1]
    assert js_money_arithmetic("const n = Number(row.pnl)") == [1]
    assert js_money_arithmetic("const s = spot.toFixed(2)") == [1]
    assert js_money_arithmetic("const ok = premium // premium * 2\nconst x = 1") == []  # comment blanked after //
    assert js_money_arithmetic("const label = 'premium * quantity'") == []
    assert js_money_arithmetic("const i = a + b") == []
    assert js_money_arithmetic("const shown = leg.premium") == []
    script = "<script setup>\nconst k = 1\n</script>"
    vue = '<template><div class="a-b">{{ leg.premium * leg.quantity }}</div></template>\n' + script
    assert js_money_arithmetic(_vue_code(vue)) == [1]
    clean = '<template><div class="text-gray-50 mt-2">{{ leg.premium }}</div></template>\n' + script
    assert js_money_arithmetic(_vue_code(clean)) == []


def test_money_arithmetic_only_in_allowed_homes():
    """AC-3: every file outside the engine's allowed homes is scanned; none computes money beyond the baseline."""
    py = python_files()
    fe = frontend_files()
    assert len(py) > MIN_PY_FILES and len(fe) > MIN_FRONTEND_FILES  # the scan really reads the trees
    assert not any(_rel(p).startswith(PY_ALLOWED_DIRS) for p in py)
    found: dict[str, tuple[str, ...]] = {}
    for p in py:
        text = p.read_text(encoding="utf-8")
        lines = money_arithmetic(text)
        if lines:
            source = text.splitlines()
            found[_rel(p)] = tuple(source[n - 1].strip() for n in lines)
    assert found == KNOWN_ON_MAIN  # exact: a new line fails, and so does a listed line that no longer exists
    assert {_rel(p): scan_frontend(p) for p in fe if scan_frontend(p)} == {}


def test_allow_list_entries_exist():
    """AC-3: a renamed or deleted allowed home must be edited out of the list, never left as a silent hole."""
    for d in PY_ALLOWED_DIRS:
        assert (ROOT / d).is_dir(), d
    for f in PY_ALLOWED_FILES + JS_ALLOWED_FILES:
        assert (ROOT / f).is_file(), f
