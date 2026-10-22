"""W-133 / REQ-053 AC-5: every Zerodha rule the code encodes is in the registry with a source and a date (repo scan).

Spec basis (quoted): REQ-053 AC-5 "Any Zerodha rule encoded in code (market-order limits, SL-M limits on index options,
freak-trade protection, OI and strike restrictions, basket execution) cites a current Zerodha source and date; 'options
are limit-only' is never hard-coded." Finding guard-as-forbidden-list: the scan is an ALLOW-LIST. It discovers the files
under the scoped trees by path, reads each by AST and FAILS CLOSED on a file it cannot parse; a constant or an
order-type call site that is not listed is red until it is listed with a reason.
"""

from __future__ import annotations

import ast
import datetime
from collections import Counter
from pathlib import Path

import pytest
from ofo_app.order_limits_registry import NOT_A_ZERODHA_RULE, RULES, ZerodhaRule

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend"
#: The scoped trees, by path (relative to backend/).
SCOPE_GLOBS = ("ofo/execution/**/*.py", "ofo/broker/**/*.py", "ofo_app/kite_*.py")
_ORDER_TYPES = frozenset({"LIMIT", "MARKET", "SL", "SL-M"})

#: Every place in backend/ that writes an order type as a string literal: (path, literal) -> (count, reason). A new
#: site is red until it is listed here with a reason. "Options are limit-only" is not a rule in any of them: each site
#: either carries the type through (a schema/validator) or is the product's own choice, labelled below.
ORDER_TYPE_SITES: dict[tuple[str, str], tuple[int, str]] = {
    ("backend/ofo/execution/basket.py", "LIMIT"): (1, (
        "the basket order's field default; the order type is carried on the order, and the module is "
        "where a Zerodha basket line is formed"
    )),
    ("backend/ofo_app/basket_post.py", "LIMIT"): (2, (
        "builds and re-checks the checked basket's lines: this product places LIMIT orders only "
        "(ADR-094: the user pays up to the planned price) - a product choice, not a Zerodha rule"
    )),
    ("backend/ofo_app/checked_basket.py", "LIMIT"): (1, (
        "the checked basket's line: LIMIT per ADR-094, a product choice"
    )),
    ("backend/ofo_app/kite_margin.py", "LIMIT"): (1, (
        "the order types the margin call accepts (registry entry ofo_app.kite_margin:_ORDER_TYPES)"
    )),
    ("backend/ofo_app/kite_margin.py", "MARKET"): (1, (
        "the order types the margin call accepts (registry entry ofo_app.kite_margin:_ORDER_TYPES)"
    )),
    ("backend/ofo_app/outcome_margin.py", "LIMIT"): (1, (
        "margin preview of a planned price: LIMIT per ADR-094, a product choice"
    )),
    ("backend/ofo_app/routes/execute.py", "LIMIT"): (2, (
        "the Execute request schema (Literal) and the review lines: LIMIT per ADR-094, a product choice"
    )),
}


class ScanError(AssertionError):
    """A scoped file could not be read or parsed: the scan fails closed instead of skipping it."""


def _parse(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        raise ScanError(f"cannot parse {path}: {type(exc).__name__}") from exc


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def scoped_files(root: Path) -> list[Path]:
    found = sorted({p for pattern in SCOPE_GLOBS for p in root.glob(pattern)})
    if not found:
        raise ScanError(f"no scoped file found under {root}: the scan would be empty")
    return found


def _strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (tuple, list, set, frozenset)):
        return {s for item in value for s in _strings(item)}
    return set()


def _carries_a_literal(value: ast.expr) -> bool:
    """True when the value's source holds a number or a string anywhere in it (a bare literal, a tuple/frozenset of
    strings, an f-string, ``_BASE ** 3 - 1``, ``compute(900)``). The scan reads the SOURCE, so a value it cannot
    evaluate still counts: it fails closed. A value with no literal in it (``object()``, ``tuple(SomeEnum)``) is built
    at runtime, which is out of scope. True/False/None carry no limit and do not count."""
    return any(isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes, int, float, complex))
               and not isinstance(n.value, bool) for n in ast.walk(value))


def module_constants(root: Path) -> set[str]:
    """``<module>:<NAME>`` of EVERY module-level UPPER_CASE constant in the scoped trees whose value carries a literal
    number or string. Allow-list scope: there is no name or value pattern to miss (``MAX_TAG_LENGTH`` has no ``LIMIT``
    in it); each hit must be in ``RULES`` or ``NOT_A_ZERODHA_RULE``."""
    hits = set()
    for path in scoped_files(root):
        for node in _parse(path).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                name, value = node.target.id, node.value
            else:
                continue
            if name.lstrip("_").isupper() and _carries_a_literal(value):
                hits.add(f"{_module_name(root, path)}:{name}")
    return hits


def order_type_sites(root: Path) -> Counter:
    """(path relative to the repo, literal) -> count, for every string literal equal to an order type in backend/
    outside docstrings and migrations."""
    sites: Counter = Counter()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("ofo_app/alembic/"):
            continue
        tree = _parse(path)
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in _ORDER_TYPES \
                    and id(node) not in docstrings:
                sites[(f"backend/{rel}", node.value)] += 1
    return sites


def _defined(root: Path, constant: str) -> bool:
    module, _, name = constant.partition(":")
    path = root / (module.replace(".", "/") + ".py")
    if not path.is_file():
        return False
    for node in _parse(path).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return True
    return False


def registry_problems(root: Path, rules=RULES, other=NOT_A_ZERODHA_RULE) -> list[str]:
    problems = []
    for rule in rules:
        if not rule.source.strip():
            problems.append(f"{rule.constant}: no source")
        try:
            datetime.date.fromisoformat(rule.recorded_on)
        except ValueError:
            problems.append(f"{rule.constant}: no ISO date")
        if not _defined(root, rule.constant):
            problems.append(f"{rule.constant}: names a constant that no longer exists (stale)")
    for constant, reason in other.items():
        if not reason.strip():
            problems.append(f"{constant}: no reason")
        if not _defined(root, constant):
            problems.append(f"{constant}: names a constant that no longer exists (stale)")
    listed = {r.constant for r in rules} | set(other)
    problems += [f"{c}: a module-level constant that is not in the registry"
                 for c in sorted(module_constants(root) - listed)]
    return problems


def site_problems(root: Path, allowed=ORDER_TYPE_SITES) -> list[str]:
    problems = []
    for key, count in sorted(order_type_sites(root).items()):
        if key not in allowed:
            problems.append(f"{key[0]}: an order type {key[1]!r} written here is not on the call-site allow-list")
        elif allowed[key][0] != count:
            problems.append(f"{key[0]}: {count} sites of {key[1]!r}, the allow-list says {allowed[key][0]}")
    for key, (_count, reason) in allowed.items():
        if not reason.strip():
            problems.append(f"{key}: allow-list entry without a reason")
    return problems


# ---- the real tree is green ---------------------------------------------------------------------------------------

def test_the_real_tree_has_every_rule_cited_and_every_order_type_site_listed():
    assert registry_problems(BACKEND) == []
    assert site_problems(BACKEND) == []


def test_the_scan_is_not_empty_and_finds_the_known_constants():
    found = module_constants(BACKEND)
    assert {"ofo.execution.sequence:DEFAULT_FREEZE_UNITS", "ofo_app.kite_ws:MAX_TOKENS_PER_CONNECTION",
            "ofo.execution.basket:MAX_TAG_LENGTH", "ofo.execution.basket:_LEGACY_TAG_MAX_LENGTH"} <= found
    listed = {r.constant for r in RULES}
    assert {"ofo.execution.basket:MAX_TAG_LENGTH", "ofo.execution.basket:_LEGACY_TAG_MAX_LENGTH"} <= listed
    assert order_type_sites(BACKEND)  # the order-type scan reads the whole of backend/


def test_every_registry_entry_says_whether_it_was_verified_against_its_source():
    """Visible, not hidden: the entries not yet compared with Zerodha's documentation (REQ-056 AC-10)."""
    assert all(isinstance(rule.verified, bool) for rule in RULES)


# ---- mutations on a scratch copy: each guard dies without its check ----------------------------------------------

def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_rule_constant_planted_without_a_registry_entry_is_red(tmp_path):
    root = _tree(tmp_path, {"ofo/execution/planted.py": "SL_M_LIMIT_UNITS = 500\n"})
    assert "ofo.execution.planted:SL_M_LIMIT_UNITS: a module-level constant that is not in the registry" in \
        registry_problems(root, rules=(), other={})
    root = _tree(tmp_path, {"ofo_app/kite_planted.py": 'SEGMENT = "NFO"\n'})
    assert any("kite_planted:SEGMENT" in p for p in registry_problems(root, rules=(), other={}))


def test_a_registry_entry_without_a_source_or_date_or_naming_a_removed_constant_is_red(tmp_path):
    root = _tree(tmp_path, {"ofo/execution/planted.py": "FREEZE_UNITS = 900\n"})
    ok = ZerodhaRule("ofo.execution.planted:FREEZE_UNITS", "freeze", "https://kite.trade/docs", "2026-10-22", False)
    assert registry_problems(root, rules=(ok,), other={}) == []
    no_source = ZerodhaRule(ok.constant, "r", " ", "2026-10-22", False)
    assert any("no source" in p for p in registry_problems(root, rules=(no_source,), other={}))
    no_date = ZerodhaRule(ok.constant, "r", "s", "", False)
    assert any("no ISO date" in p for p in registry_problems(root, rules=(no_date,), other={}))
    gone = ZerodhaRule("ofo.execution.planted:REMOVED", "freeze", "s", "2026-10-22", False)
    assert any("stale" in p for p in registry_problems(root, rules=(ok, gone), other={}))
    blank = {"ofo.execution.planted:FREEZE_UNITS": " "}
    assert any("no reason" in p for p in registry_problems(root, rules=(ok,), other=blank))


def test_a_new_order_type_call_site_is_red_until_listed(tmp_path):
    root = _tree(tmp_path, {"ofo_app/new_route.py": 'def f():\n    return {"order_type": "MARKET"}\n'})
    assert site_problems(root, allowed={}) != []
    key = ("backend/ofo_app/new_route.py", "MARKET")
    assert site_problems(root, allowed={key: (1, "a reason")}) == []
    assert site_problems(root, allowed={key: (2, "a reason")}) != []  # a second site in a listed file is red too


def test_a_scoped_file_that_cannot_be_parsed_fails_closed(tmp_path):
    root = _tree(tmp_path, {"ofo/execution/broken.py": "def (:\n"})
    with pytest.raises(ScanError):
        module_constants(root)
    with pytest.raises(ScanError):
        order_type_sites(root)
    with pytest.raises(ScanError):
        module_constants(tmp_path / "empty")  # no scoped file at all


def test_a_constant_with_no_rule_shaped_name_is_found_and_red_until_listed(tmp_path):
    """Attack 3: ``MAX_FOO_LENGTH = 9`` (a name no pattern knew), a string and an annotated cap are all red."""
    root = _tree(tmp_path, {"ofo/execution/planted.py": "MAX_FOO_LENGTH = 9\nTHE_SIDE = 'BUY'\n_HIDDEN_CAP: int = 3\n"})
    problems = registry_problems(root, rules=(), other={})
    for name in ("MAX_FOO_LENGTH", "THE_SIDE", "_HIDDEN_CAP"):
        assert any(f"planted:{name}" in p for p in problems), problems
    listed = {f"ofo.execution.planted:{n}": "a reason" for n in ("MAX_FOO_LENGTH", "THE_SIDE", "_HIDDEN_CAP")}
    assert registry_problems(root, rules=(), other=listed) == []


@pytest.mark.parametrize("source", [
    "CAP = compute(900)\n",                      # a call the scan cannot evaluate
    "CAP = _BASE ** 3 - 1\n",                    # arithmetic
    "CAP = f'https://{HOST}/orders'\n",          # an f-string
    "CAP = {'NIFTY': 1800}\n",                   # a dict
    "CAP = frozenset({'LIMIT', *OTHERS})\n",     # a set with a star the scan cannot resolve
])
def test_a_value_the_scan_cannot_evaluate_fails_closed(tmp_path, source):
    root = _tree(tmp_path, {"ofo/execution/planted.py": source})
    assert module_constants(root) == {"ofo.execution.planted:CAP"}


def test_a_value_built_at_runtime_with_no_literal_is_out_of_scope(tmp_path):
    root = _tree(tmp_path, {"ofo/execution/planted.py": "A = object()\nB = tuple(SomeEnum)\nC = True\nD = None\n"})
    assert module_constants(root) == set()
