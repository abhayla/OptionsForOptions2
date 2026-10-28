"""AC-3 (REQ-063, ADR-008): no money or P&L figure is computed outside the calculation engine.

Widens the guard that used to cover only backend/ofo/rules/ (finding money-value-computed-outside-engine) to every
Python module under backend/ and every .vue/.js/.ts file under frontend/src. It is an allow-list: the engine homes
below may do money arithmetic; every other file is scanned and any arithmetic touching a money-named value fails.

Threat model: in scope - arithmetic (+ - * / // % ** and augmented forms) and sum() on a value whose name has a money
part (premium, price, pnl, charge, margin, ltp, mtm, funds, brokerage, value, loss, profit, unrealized, realized;
camelCase and PnL split), through a literal getattr/dict key/bracket key, an aliased import, an alias made by plain,
annotated or tuple-unpack assignment, or a list/set/generator comprehension over money. In the browser also
Number()/parseFloat()/parseInt()/toFixed()/Math rounding, unary +, bracket keys, a parenthesised operand and an operator
on the next line, outside the chart files.
Out of scope (documented limits, not claims): helpers such as mul/operator.mul/fsum/reduce, for-loop variables and
function parameters that are not money-named, amounts named amount/cost/net/total, a ratio of generically named values
(table/model.py _percent), JS decimal libraries, code built at run time, generated files, test files.
Existing hits on main are pinned in KNOWN_ON_MAIN (money, deferred findings) and
NOT_MONEY_ON_MAIN (not money, each file with a reason).
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
                "mtm", "funds", "brokerage", "value", "values", "loss", "profit", "unrealized", "realized"}
# Money arithmetic that already sits outside the engine on main (GC-1 audit gap). A BASELINE, not an allowance: the
# test fails on any line not listed here, and fails when a listed line is fixed or gone (delete the entry then). Each
# entry is a deferred finding (see the W-110 report); do not add to this table.
KNOWN_ON_MAIN: dict[str, tuple[str, ...]] = {
    "backend/ofo/execution/cost.py": (
        'return _SIGN[order.side] * order.price * order.quantity',
        'net = sum((signed_premium(o) for o in orders), Decimal(0))',
    ),
    "backend/ofo/execution/margin_gate.py": (
        'top_up += max(Decimal(0), quantity * price - _premium(row.get("option_premium")))',  # GC-UI D-A47
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
        'times += list(snapshot.ended_times.values())  # ADR-077: times kept after the subscription ended',
        'max_loss = metrics.max_loss if loss_unl or charges is None else metrics.max_loss + charges  # ADR-082 (2)',
        'max_profit = metrics.max_profit if profit_unl or charges is None else metrics.max_profit - charges',
    ),
    "backend/ofo/rules/inputs.py": (
        'values[InputName.PNL_PCT_OF_MAX_PROFIT] = pnl * 100 / metrics.max_profit',
        'values[InputName.PNL_PCT_OF_MAX_LOSS] = -pnl * 100 / metrics.max_loss',
    ),
    "backend/ofo/table/model.py": (
        'return value * sign * quantity',
        'entry_value = core.entry_price * core.quantity',
        'current_value = core.ltp * core.quantity if core.ltp is not None else None',
        'ratio = (unrealized / max_loss) * 100',
        'net_entry = None if has_futures else sum(',
        '((leg.premium if leg.action is Action.SELL else -leg.premium) * leg.quantity for leg in legs), Decimal(0))',
        'net_current = None if has_futures else sum(',
        '((leg.ltp if leg.action is Action.SELL else -leg.ltp) * leg.quantity for leg in legs), Decimal(0))',
        'unrealized = sum((live_pnl(leg.leg) for leg in legs), Decimal(0))',
    ),
    "backend/ofo_app/routes/execute.py": (
        'return None if value is None else value.quantize(PAISE, rounding=ROUND_HALF_UP) + 0',
    ),
}
# Lines that match a money token but are not money (generic `value` parameters, counters). Pinned like the
# baseline, one reason per file; a file listed here is still scanned and a NEW line in it fails.
NOT_MONEY_ON_MAIN_WHY: dict[str, str] = {
    "backend/ofo/errors/explanations.py": 'len(value) - 1: an index into a string, not money',
    "backend/ofo/history/store.py": 'counts bars (sum of 1s over self._bars.values()), not money',
    "backend/ofo/range/pick_lists.py": 'snaps a strike or index level to a step; points, not rupees',
    "backend/ofo/reconciliation/compare.py": 'adds a contract quantity (units), not money',
    "backend/ofo/strategy/guard.py": 'sign of a number (-1/0/1)',
    "backend/ofo/strategy/leg_edit.py": 'strike width and index-to-strike distance (REQ-078 AC-4); points, not rupees',
    "backend/ofo/strategy/linear.py": 'exact linear algebra over generic coefficients/values',
    "backend/ofo_app/errors.py": 'encodes an HTTP header value, not money',
    "backend/ofo_app/reconcile_attribution.py": (
        'net units minus units held by open plans (contract quantity), not money'
    ),
}
NOT_MONEY_ON_MAIN: dict[str, tuple[str, ...]] = {
    "backend/ofo/errors/explanations.py": (
        'last = len(value) - 1',
    ),
    "backend/ofo/history/store.py": (
        'kept = sum(1 for b in self._bars.values() if b.minute.date() == day and b.source is BarSource.LIVE)',
    ),
    "backend/ofo/range/pick_lists.py": (
        'return (value // STEP) * STEP',
        'value -= STEP',
        'value += STEP',
    ),
    "backend/ofo/reconciliation/compare.py": (
        'expected[contract] = expected.get(contract, 0) + value',
    ),
    "backend/ofo/strategy/guard.py": (
        'return (value > 0) - (value < 0)',
    ),
    "backend/ofo/strategy/leg_edit.py": (
        'now = min(calls.values()) - max(puts.values())',
        'put_nearer = spot is not None and abs(spot - max(puts.values())) < abs(spot - min(calls.values()))',
    ),
    "backend/ofo/strategy/linear.py": (
        'return self.const + sum(coefficient * values[name] for name, coefficient in self.coefficients)',
        'rows[rank] = [value / lead for value in rows[rank]]',
        '[Fraction(dict(e.coefficients).get(p, 0)) for p in params] + [Fraction(value - e.const)]',
    ),
    "backend/ofo_app/errors.py": (
        'headers += [(name.lower().encode("ascii"), value.encode("ascii")) for name, value in NO_LEAK_HEADERS.items()]',
    ),
    "backend/ofo_app/reconcile_attribution.py": (
        'left = (raw_net.get(contract, 0) - sum(units.get(contract, 0) for units in held.values())',
    ),
}

# Browser lines the scan flags that are not money (W-119 guided flow): index/strike levels read as numbers for
# selection and comparison (points, not rupees), and the wizard step counter. Exact stripped line text per file, so a
# new or changed line in these files fails; a file listed here is still scanned.
NOT_MONEY_FRONTEND_WHY: dict[str, str] = {
    "frontend/src/lib/guided.js": 'index levels and listed strikes (points) parsed for selection; no rupee value',
    "frontend/src/pages/CreateStrategyPage.vue": 'the wizard step counter (`step.value`), a page number',
    "frontend/src/lib/oiBars.js": 'open-interest COUNTS (contracts, not rupees) scaled to a CSS bar width',
}
NOT_MONEY_FRONTEND: dict[str, tuple[str, ...]] = {
    "frontend/src/lib/guided.js": (
        "return [...new Set(contracts.filter((c) => c.strike !== null && c.instrument_type !== 'FUT')"
        ".map((c) => Number(c.strike)))]",
        'const current = Number(currentText)',
        'const c = Number(currentText)',
        'const down = c - Number(lowerText)',
        'const up = Number(upperText) - c',
        'const current = Number(currentText)',
        "const c = contracts.find((x) => x.instrument_type === leg.instrument && x.strike !== null "
        "&& Number(x.strike) === strike)",
    ),
    "frontend/src/pages/CreateStrategyPage.vue": (
        'step.value = step.value === 3 && isKnow.value ? 1 : step.value - 1',
    ),
    "frontend/src/lib/oiBars.js": (
        "const oiCount = (v) => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null "
        ": Number(v))",
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
    spaced = name.replace("PnL", "Pnl")  # PnL / unrealizedPnL tokenise as pnl, not Pn + L
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", spaced)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced)
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


def _is_money_value(value: ast.AST, aliases: set[str]) -> bool:
    """A value that IS a money value or a collection of them: a money read, an alias, or a comprehension over money."""
    if isinstance(value, ast.Name):
        return value.id in aliases
    if isinstance(value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return any(_own_money_ref(n) or (isinstance(n, ast.Name) and n.id in aliases) for n in ast.walk(value.elt))
    return _own_money_ref(value)


def _alias_targets(node: ast.AST, aliases: set[str]) -> set[str]:
    """Names bound to a money value by ``a = v``, ``a: T = v`` and the pairs of ``a, b = v1, v2``."""
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        pairs = [(node.target, node.value)]
    elif isinstance(node, ast.Assign):
        pairs = []
        for target in node.targets:
            both_tuples = isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple)
            if both_tuples and len(target.elts) == len(node.value.elts):
                pairs.extend(zip(target.elts, node.value.elts, strict=True))
            else:
                pairs.append((target, node.value))
    else:
        return set()
    return {t.id for t, v in pairs if isinstance(t, ast.Name) and _is_money_value(v, aliases)}


def _money_aliases(tree: ast.AST) -> set[str]:
    """Names that stand for a money value: aliased imports of money-named objects and the assignments above."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):  # a rename must not hide the name (fail closed)
            aliases.update(a.asname for a in node.names if a.asname and is_money_name(a.name.split(".")[-1]))
    for _ in range(3):  # repeat so a chain a = price; b = a; c = b * 2 is still caught
        for node in ast.walk(tree):
            aliases |= _alias_targets(node, aliases)
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
_JS_ARITH = re.compile(
    rf"({_JS_IDENT})\s*\)?\s*({_JS_OP})\s*\(?\s*({_JS_IDENT}|\d)|(\d)\s*({_JS_OP})\s*\(?\s*({_JS_IDENT})")
_JS_UNARY_PLUS = re.compile(rf"(?<![\w$)\]+])\+\s*\(?\s*({_JS_IDENT})")  # +leg.premium coerces to a number
_JS_BRACKET_KEY = re.compile(r"""\[\s*['"]([\w$]+)['"]\s*\]""")  # leg['premium'] reads like leg.premium
_JS_STRINGS = re.compile(r"""'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""")
_JS_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/|<!--.*?-->", re.S)


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _line_of(text: str, match: re.Match[str]) -> int:
    return text.count(chr(10), 0, match.start()) + 1


def js_money_arithmetic(source: str) -> list[int]:
    """Line numbers where browser code coerces a number or does arithmetic on a money-named identifier.

    Comments and string literals are blanked first, keeping line numbers. Template markup (`<div class="a-b">`) is not
    code, so for .vue files only the <script> block and mustache/bound expressions are scanned by the caller."""
    text = _JS_COMMENTS.sub(_blank, source)
    text = _JS_BRACKET_KEY.sub(lambda m: "." + m.group(1), text)
    text = _JS_STRINGS.sub(_blank, text)
    bad: set[int] = set()

    def money(*idents: str | None) -> bool:
        return any(is_money_name(part) for n in idents if n and not n[0].isdigit() for part in re.split(r"\??\.", n))

    for m in _JS_COERCE.finditer(text):
        bad.add(_line_of(text, m))
    for m in _JS_ARITH.finditer(text):  # whole text: an operator may sit on the next line
        if money(m.group(1), m.group(3), m.group(4), m.group(6)):
            bad.add(_line_of(text, m))
    for m in _JS_UNARY_PLUS.finditer(text):
        if money(m.group(1)):
            bad.add(_line_of(text, m))
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


def _frontend_scanned_text(path: pathlib.Path) -> str:
    source = path.read_text(encoding="utf-8")
    return _vue_code(source) if path.suffix == ".vue" else source


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
    # Fix round 1: new tokens, camelCase, and the alias shapes.
    assert money_arithmetic("x = entry_value * 2") == [1]
    assert money_arithmetic("x = loss + 1") == [1]
    assert money_arithmetic("x = profit - 1") == [1]
    assert money_arithmetic("x = unrealized / 2") == [1]
    assert money_arithmetic("x = realized * 2") == [1]
    assert money_arithmetic("x = livePnL * 2") == [1]
    assert money_arithmetic("x = unrealizedPnl * 2") == [1]
    assert money_arithmetic("x = quantity * 2") == []
    assert money_arithmetic("from decimal import Decimal\np: Decimal = leg.premium\nx = p * 2") == [3]
    assert money_arithmetic("p, q = leg.premium, 5\nx = p * 2") == [2]
    assert money_arithmetic("q, p = 5, leg.premium\nx = q * 2") == []
    assert money_arithmetic("ps = [l.premium for l in legs]\nx = sum(ps)") == [2]
    assert money_arithmetic("ps = (l.ltp for l in legs)\nx = sum(ps)") == [2]
    assert money_arithmetic("ps = [l.quantity for l in legs]\nx = sum(ps)") == []


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
    assert js_money_arithmetic("const a = +leg.premium") == [1]  # unary plus coerces to a number
    assert js_money_arithmetic("const a = x + +y") == []
    assert js_money_arithmetic("const a = leg['premium'] * q") == [1]
    assert js_money_arithmetic("const a = leg.premium\n  * q") == [1]  # operator on the next line
    assert js_money_arithmetic("const a = (leg.premium) * qty") == [1]
    assert js_money_arithmetic("const a = leg['quantity']") == []
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
    assert found == {**KNOWN_ON_MAIN, **NOT_MONEY_ON_MAIN}  # exact: new or vanished lines fail
    flagged: dict[str, tuple[str, ...]] = {}
    for p in fe:
        hits = scan_frontend(p)
        if hits:
            source = _frontend_scanned_text(p).splitlines()
            flagged[_rel(p)] = tuple(source[n - 1].strip() for n in hits)
    assert flagged == NOT_MONEY_FRONTEND  # exact: a new, changed or vanished line fails
    assert set(NOT_MONEY_FRONTEND) == set(NOT_MONEY_FRONTEND_WHY)


def test_allow_list_entries_exist():
    """AC-3: a renamed or deleted allowed home must be edited out of the list, never left as a silent hole."""
    for d in PY_ALLOWED_DIRS:
        assert (ROOT / d).is_dir(), d
    for f in PY_ALLOWED_FILES + JS_ALLOWED_FILES:
        assert (ROOT / f).is_file(), f
