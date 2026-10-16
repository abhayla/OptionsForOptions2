"""One home per real-world constant (owner 2026-10-16: "saving all the constant at one places").

Every `.py` under `backend/` is parsed with the AST and each constant below may be written only in its home module:

- the IST offset (a `timedelta` whose constant arguments total 5 h 30 min) and the zone name "Asia/Kolkata" (in any
  string that is not a docstring, so SQL text counts) -> `ofo/timeutil.py`
- the named market times (09:15, 15:30, 15:39, 15:59 as a `time(...)` call) -> `ofo/timeutil.py`
- the paise step (`Decimal` of a constant equal to 0.01, however it is spelled) -> `ofo/money.py`
- the segment codes "NSE_FO" / "BSE_FO" as string values -> `ofo/instruments/models.py` (an `__all__` entry is a
  name, not the value, and is allowed)
- lot alignment (`x % <something named lot>`) -> `is_lot_aligned` in `ofo/instruments/models.py`

Fails closed: a file that cannot be read or parsed is a violation, an empty scan is a failure, and an allow-list entry
that no longer matches anything is a failure (so the phase-2 list can only shrink).

Migration files (`ofo_app/alembic/versions/`) are not scanned: a migration is frozen history and must not import
application modules that can change after it was written (Alembic practice); each one carries its own literal.
"""
from __future__ import annotations

import ast
import pathlib
from decimal import Decimal, InvalidOperation

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"

IST_SECONDS = 5 * 3600 + 30 * 60
MARKET_TIMES = {(9, 15), (15, 30), (15, 39), (15, 59)}
SEGMENT_CODES = {"NSE_FO", "BSE_FO"}
ZONE_NAME = "Asia/Kolkata"

#: rule -> the only module(s) allowed to write it (paths relative to backend/).
HOMES: dict[str, frozenset[str]] = {
    "ist_offset": frozenset({"ofo/timeutil.py"}),
    "zone_name": frozenset({"ofo/timeutil.py"}),
    "market_time": frozenset({"ofo/timeutil.py"}),
    "paise": frozenset({"ofo/money.py"}),
    "segment_code": frozenset({"ofo/instruments/models.py"}),
    "lot_modulo": frozenset({"ofo/instruments/models.py"}),
}

#: Temporary exceptions: ONLY files another branch owns today. Each entry: (rule, file).
PHASE_2: frozenset[tuple[str, str]] = frozenset({
    ("ist_offset", "ofo/errors/explanations.py"),  # phase 2: ofo/errors/explanations.py owned by W-080/W-075 today
})

EXCLUDED_DIRS = ("ofo_app/alembic/versions/",)

_TIMEDELTA_UNITS = {"weeks": 604800, "days": 86400, "hours": 3600, "minutes": 60, "seconds": 1,
                    "milliseconds": 0.001, "microseconds": 0.000001}
_TIMEDELTA_POSITIONAL = ("days", "seconds", "microseconds", "milliseconds", "minutes", "hours", "weeks")


def _const_number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _const_number(node.operand)
        return None if inner is None else -inner
    return None


def _callee(node: ast.Call, aliases: dict[str, str]) -> str | None:
    """The real name of what is called: `timedelta`, `datetime.timedelta`, `dt.timedelta` and `td` (imported as an
    alias of timedelta) all resolve to "timedelta"."""
    if isinstance(node.func, ast.Name):
        return aliases.get(node.func.id, node.func.id)
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _timedelta_seconds(node: ast.Call) -> float | None:
    total = 0.0
    for i, arg in enumerate(node.args):
        value = _const_number(arg)
        if value is None or i >= len(_TIMEDELTA_POSITIONAL):
            return None
        total += value * _TIMEDELTA_UNITS[_TIMEDELTA_POSITIONAL[i]]
    for kw in node.keywords:
        value = None if kw.arg is None else _const_number(kw.value)
        if value is None or kw.arg not in _TIMEDELTA_UNITS:
            return None
        total += value * _TIMEDELTA_UNITS[kw.arg]
    return total


def _is_paise(node: ast.Call) -> bool:
    if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Constant):
        return False
    raw = node.args[0].value
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        return False
    try:
        return Decimal(str(raw).strip()) == Decimal("0.01")
    except InvalidOperation:
        return False


def _time_args(node: ast.Call) -> tuple[int, int] | None:
    if len(node.args) < 2:
        return None
    hour, minute = _const_number(node.args[0]), _const_number(node.args[1])
    if hour is None or minute is None:
        return None
    return int(hour), int(minute)


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            for stmt in body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    ids.add(id(stmt.value))
    return ids


def _all_entry_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AugAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            ids.update(id(c) for c in ast.walk(node.value) if isinstance(c, ast.Constant))
    return ids


def _names_lot(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return "lot" in node.id.lower()
    if isinstance(node, ast.Attribute):
        return "lot" in node.attr.lower()
    if isinstance(node, ast.Subscript):
        return _names_lot(node.value)
    if isinstance(node, ast.Call):
        return _names_lot(node.func)
    return False


def scan_source(source: str, filename: str = "<src>") -> list[tuple[str, int]]:
    """Every (rule, line) found in ``source``. Raises SyntaxError when it cannot be parsed (the caller fails closed)."""
    tree = ast.parse(source, filename=filename)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
    docstrings, all_entries = _docstring_ids(tree), _all_entry_ids(tree)
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _callee(node, aliases)
            if name == "timedelta" and _timedelta_seconds(node) == IST_SECONDS:
                hits.append(("ist_offset", node.lineno))
            elif name == "Decimal" and _is_paise(node):
                hits.append(("paise", node.lineno))
            elif name == "time" and _time_args(node) in MARKET_TIMES:
                hits.append(("market_time", node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if ZONE_NAME in node.value:
                hits.append(("zone_name", node.lineno))
            if node.value in SEGMENT_CODES and id(node) not in all_entries:
                hits.append(("segment_code", node.lineno))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and _names_lot(node.right):
            if not (isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)):  # "%s" % lot is text
                hits.append(("lot_modulo", node.lineno))
    return sorted(hits, key=lambda h: (h[1], h[0]))


def scan_tree(root: pathlib.Path) -> tuple[list[str], set[tuple[str, str]], int]:
    """(violations, (rule, file) pairs used from the phase-2 list, files scanned)."""
    violations, used = [], set()
    files = 0
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(d) for d in EXCLUDED_DIRS):
            continue
        files += 1
        try:
            hits = scan_source(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, OSError, ValueError) as exc:
            violations.append(f"{rel}: cannot be parsed, so it cannot be checked ({type(exc).__name__}: {exc})")
            continue
        for rule, line in hits:
            if rel in HOMES[rule]:
                continue
            if (rule, rel) in PHASE_2:
                used.add((rule, rel))
                continue
            violations.append(f"{rel}:{line}: {rule} belongs only in {sorted(HOMES[rule])}")
    return violations, used, files


def test_every_constant_lives_in_its_one_home():
    violations, used, files = scan_tree(BACKEND)
    assert files > 50, f"scanned only {files} files under {BACKEND}: the scan is not looking where the code is"
    assert violations == [], "constants outside their home:\n" + "\n".join(violations)
    assert used == set(PHASE_2), f"stale phase-2 entries (remove them): {sorted(set(PHASE_2) - used)}"


def test_the_homes_exist():
    for homes in HOMES.values():
        for rel in homes:
            assert (BACKEND / rel).is_file(), f"home module {rel} is missing"


def test_each_rule_catches_every_spelling():
    src = (
        "import datetime\nfrom datetime import timedelta as td\nfrom decimal import Decimal\n"
        "A = datetime.timedelta(hours=5, minutes=30)\n"
        "B = td(minutes=330)\n"
        "C = datetime.timedelta(seconds=19800)\n"
        "D = Decimal('0.01')\n"
        "E = Decimal('.010')\n"
        "F = \"SELECT now() AT TIME ZONE 'Asia/Kolkata'\"\n"
        "G = ('NSE_FO', 'BSE_FO')\n"
        "H = datetime.time(15, 30)\n"
        "I = qty % lot_size\n"
        "J = q % lots[ref]\n"
    )
    rules = [rule for rule, _ in scan_source(src)]
    assert rules == ["ist_offset", "ist_offset", "ist_offset", "paise", "paise", "zone_name",
                     "segment_code", "segment_code", "market_time", "lot_modulo", "lot_modulo"]


def test_it_ignores_what_is_not_the_constant():
    src = (
        '"""Docstring mentioning Asia/Kolkata and NSE_FO."""\n'
        "from decimal import Decimal\nimport datetime\n"
        "__all__ = ['NSE_FO', 'BSE_FO']\n"
        "A = datetime.timedelta(hours=5)\n"
        "B = datetime.timedelta(hours=n, minutes=30)\n"
        "C = Decimal('0.1')\n"
        "D = 'transaction_rate_nse_fo'\n"
        "E = datetime.time(10, 0)\n"
        "F = units % step\n"
        "G = 'lot %s' % lot\n"
    )
    assert scan_source(src) == []


def test_it_fails_closed_on_a_file_it_cannot_parse(tmp_path):
    (tmp_path / "ofo").mkdir()
    (tmp_path / "ofo" / "broken.py").write_text("def f(:\n", encoding="utf-8")
    violations, _, files = scan_tree(tmp_path)
    assert files == 1 and len(violations) == 1 and "cannot be parsed" in violations[0]


def test_a_planted_copy_in_a_domain_module_fails(tmp_path):
    target = tmp_path / "ofo" / "history" / "bars.py"
    target.parent.mkdir(parents=True)
    original = (BACKEND / "ofo" / "history" / "bars.py").read_text(encoding="utf-8")
    target.write_text(original + "\n_PLANTED = __import__('datetime').timedelta(hours=5, minutes=30)\n", encoding="utf-8")
    violations, _, _ = scan_tree(tmp_path)
    assert len(violations) == 1 and "ofo/history/bars.py" in violations[0] and "ist_offset" in violations[0]
