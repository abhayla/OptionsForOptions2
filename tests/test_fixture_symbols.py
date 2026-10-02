"""AC-1 (REQ-053, finding fixture-symbol-not-in-catalogue): every tradingsymbol literal under
``tests/`` must resolve in the real catalogue slice (``tests/fixtures/instruments/instruments_slice.csv``)
with the expiry the symbol itself encodes.

**Practical, deterministic rule** (documented here because the guard's rule must be explainable, not
just enforced):

1. A *full* literal -- a prefix (``NIFTY``/``BANKNIFTY``/``FINNIFTY``/``SENSEX``), a 2-digit year, a
   month/day code (``OCT``, ``NOV``, ... or a weekly day code ``O01``..``O31``), then either digits
   followed by ``CE``/``PE`` (an option) or ``FUT`` directly (a future) -- is found ANYWHERE in the
   file's text (so it also catches a symbol embedded inside a longer message string, e.g. an
   assertion's expected error text). It must appear verbatim as a ``tradingsymbol`` in the catalogue
   CSV. This catches the case where the symbol TEXT itself is wrong (``NIFTY26OCT23400CE`` is not a
   real catalogue symbol for any expiry; the real one is ``NIFTY26O0623400CE``).
2. A *dynamic head* -- the same prefix/year/month pattern immediately followed by an f-string ``{``
   (a template whose strike and CE/PE suffix are filled in at runtime, e.g.
   ``f"NIFTY26OCT{strike}{instrument.value}"``) -- is checked differently: the catalogue must contain
   AT LEAST ONE option row (``CE`` or ``PE``) whose tradingsymbol starts with that exact head. This
   catches a template built on a month/day code for which the catalogue holds no options at all (e.g.
   ``NIFTY26OCT`` -- the catalogue's only 2026-10-27 NIFTY row is the future, ``NIFTY26OCTFUT``; it
   holds no NIFTY options at that expiry, so no template built on that head can ever produce a real
   option symbol).
   **Built strikes (rule 2b).** The head check alone passes ``f"NIFTY26O06{strike}CE"`` for ANY strike, so
   the strikes are checked too (issue #61): for every f-string whose head is a real catalogue head, the
   interpolated expression (``strike``, ``int(s)``) is resolved through the file's own assignments and ``for`` targets (list/tuple literals,
   ``range(a, b, c)`` with literal arguments, comprehensions, ``enumerate``, tuple positions) to the integers it
   can take, and every integer must give a symbol that exists in the catalogue (``CE`` or ``PE`` as written).
   A name that cannot be resolved (a function parameter) is left unchecked, never guessed. A test that builds
   its own synthetic catalogue on purpose is excused per FUNCTION in ``SYNTHETIC_CATALOGUE_ALLOWLIST`` with the
   reason, so the exemption is as narrow as the test.
3. **Pairing (AST-based).** A full literal being a real catalogue symbol does NOT by itself prove it is
   paired with the right expiry: a real symbol (``NIFTY26O0623400CE``, catalogue expiry 2026-10-06) can
   still be attached to the WRONG separately-declared expiry (e.g. ``expiry=date(2026, 10, 13)``) --
   exactly the original W-023 defect shape (a symbol string plus a separate expiry value that silently
   drift apart). Every Python file is parsed with ``ast``; two deterministic pairings are checked:

   a. **Same call.** For every ``ast.Call`` (a function/constructor call, e.g. ``Leg(contract=...,
      expiry=...)``), if one keyword argument's value is a full symbol literal AND another keyword
      argument is named ``expiry`` or ``expiry_date`` with a value that is either a ``"YYYY-MM-DD"``
      string or a ``date(y, m, d)``/``datetime.date(y, m, d)`` call with literal integer arguments, the
      two are paired and compared against the catalogue's real expiry for that symbol.
   b. **Module constants.** At module top level only (``ast.Assign`` to a single ``Name``), collect
      every assignment whose value resolves to a date (as above) and every assignment whose value is a
      full symbol literal, or a tuple/list made ENTIRELY of full symbol literals. When a file declares
      **exactly one** such date constant, every symbol constant in that same file is paired with it and
      compared (the ``partial_inputs.py`` style: one shared ``EXPIRY``, several contract constants).
      A file with zero or more than one date constant is left **unpairable** -- reported as nothing,
      never failed -- rather than guess which constant a given symbol belongs to.

   Only keyword-argument calls and simple top-level assignments are parsed; anything else (a symbol or
   expiry built through a function call, an f-string interpolation, a class attribute) is unpairable by
   this rule and is not checked for pairing (it may still be checked as a full literal/dynamic head
   above).

A small, explicit allowlist covers three honest exceptions, each with a one-line reason: (a) a fixture
that is DELIBERATELY not in the catalogue, or deliberately mispaired, to prove some guard refuses it
(an "attack" fixture); (b) a locked spec example (scenario-calculations.md §6) whose expiry has no
matching row in this catalogue SLICE at all -- corrected only by inventing a row, which is worse than
naming the gap; (c) a defect found outside this item's named scope, deferred to a filed issue.

Anything not in the catalogue, not correctly paired, and not allowlisted is a genuine instance of the
finding's class and must be corrected to a real catalogue symbol and/or a matching expiry before this
test is allowed to pass.
"""
from __future__ import annotations

import ast
import csv
import re
from datetime import date
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
CATALOGUE_CSV = TESTS_DIR / "fixtures" / "instruments" / "instruments_slice.csv"
THIS_FILE = Path(__file__).resolve()

MONTH = r"(?:O[0-9]{2}|OCT|NOV|DEC|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP)"
FULL_SYMBOL_RE = re.compile(
    rf"\b(?:NIFTY|BANKNIFTY|FINNIFTY|SENSEX)[0-9]{{2}}{MONTH}(?:[0-9]+(?:CE|PE)|FUT)\b"
)
DYNAMIC_HEAD_RE = re.compile(
    rf"(?:NIFTY|BANKNIFTY|FINNIFTY|SENSEX)[0-9]{{2}}{MONTH}(?=\{{)"
)

# (relative file path, exact matched text) -> one-line reason. Every entry is either a deliberate
# "attack" fixture (a symbol a guard elsewhere must refuse) or a locked spec example with no
# matching row in this catalogue SLICE.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("execution/test_strategy_only.py", "BANKNIFTY26OCT50000CE"):
        "attack fixture: a BANKNIFTY order deliberately not in the strategy/catalogue, proving the "
        "sink refuses a contract that is not the strategy's own catalogue symbol.",
    ("execution/test_sink_backup_checks.py", "FINNIFTY26O0623600CE"):
        "attack fixture: FINNIFTY is out of the catalogue's supported-underlying scope; inserted "
        "directly to prove the sink's underlying-equality filter (M7) refuses a same-strike twin.",
    ("execution/test_complete_slices.py", "NIFTY26O0623625CE"):
        "attack fixture (AC-4 negative): a plan contract the catalogue does not hold, proving "
        "sequence_plan refuses an unknown symbol instead of guessing a lot size.",
    ("engine/conftest.py", "NIFTY26OCT"):
        "locked spec example (scenario-calculations.md section 6, the golden Iron Condor) at the "
        "monthly 2026-10-27 expiry; this catalogue slice holds only the monthly FUTURE for that "
        "expiry (NIFTY26OCTFUT), no options -- there is no real row to correct the option legs to, "
        "and the IV values are computed from the spec, never the catalogue.",
    ("engine/test_inputs.py", "NIFTY26OCT22800PE"):
        "same golden Iron Condor fixture as engine/conftest.py: no NIFTY option row exists at the "
        "2026-10-27 expiry in this catalogue slice.",
    ("scenario/scenario_fixtures.py", "NIFTY26OCT"):
        "same golden Iron Condor fixture (scenario-calculations.md section 6) reused for scenario "
        "tests: no NIFTY option row exists at the 2026-10-27 expiry in this catalogue slice.",
    ("table/conftest.py", "NIFTY26OCT"):
        "same golden Iron Condor fixture (scenario-calculations.md section 6) reused for the table tests: no "
        "NIFTY option row exists at the 2026-10-27 expiry in this catalogue slice.",
    ("scenario/test_modes.py", "NIFTY26OCT22800PE"):
        "same golden Iron Condor fixture: the unavailable-IV message names the same leg used by "
        "engine/conftest.py, for which no catalogue row exists at 2026-10-27.",
    ("audit/test_log.py", "NIFTY24JAN25000CE"):
        "REQ-064: the audit log stores a raw Kite-style broker-response payload EXACTLY as passed, "
        "with no secret filtering and no catalogue lookup; the payload's tradingsymbol is "
        "illustrative content the log must not alter, not a contract this test resolves.",
}
HEAD_ONLY_RE = re.compile(rf"(?:NIFTY|BANKNIFTY|FINNIFTY|SENSEX)[0-9]{{2}}{MONTH}")

#: (relative file path, function name) -> reason. Functions that build their OWN in-memory Catalogue with strikes
#: chosen for the scenario (a current level far beyond every strike), so the strikes
#: are deliberately not the real slice's. Their assertions read the synthetic Catalogue, never the CSV.
SYNTHETIC_CATALOGUE_ALLOWLIST: dict[tuple[str, str], str] = {
    ("range/test_pick_lists.py", "test_reviewer_repro_synthetic_upper_list_never_appends_the_wrong_side_strike"):
        "exact verifier reproduction: synthetic Catalogue with strikes 20000..21000 and current 100,000; the "
        "meaning (every listed strike far below the current level) does not exist in the real slice.",
    ("range/test_pick_lists.py", "test_mutation_side_check_must_reject_a_wrong_side_bound"):
        "same verifier reproduction (strikes 20000..21000, current 100,000) used as a mutation probe of the "
        "side check; synthetic Catalogue by design.",
}


def _load_catalogue_symbols() -> set[str]:
    with CATALOGUE_CSV.open(encoding="utf-8") as fh:
        return {row["tradingsymbol"] for row in csv.DictReader(fh)}


def _load_catalogue_expiries() -> dict[str, date]:
    """Only F&O rows carry a real expiry (equity/cash rows leave the column blank); those are simply
    not candidates for pairing and are skipped rather than raising."""
    with CATALOGUE_CSV.open(encoding="utf-8") as fh:
        out: dict[str, date] = {}
        for row in csv.DictReader(fh):
            m = _ISO_DATE_RE.match(row.get("expiry", "") or "")
            if not m:
                continue
            out[row["tradingsymbol"]] = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return out


_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
EXPIRY_KEYWORDS = {"expiry", "expiry_date"}


def _date_from_node(node: ast.AST) -> date | None:
    """A "YYYY-MM-DD" string constant, or a date(y, m, d)/datetime.date(y, m, d) call with three
    literal integer arguments. Anything else (a Name, an f-string, a call with non-literal args)
    returns None -- unpairable by design, never guessed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        m = _ISO_DATE_RE.match(node.value)
        if not m:
            return None
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name != "date" or len(node.args) < 3:
            return None
        vals = []
        for arg in node.args[:3]:
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, int) and not isinstance(arg.value, bool)):
                return None
            vals.append(arg.value)
        try:
            return date(*vals)
        except ValueError:
            return None
    return None


def _symbol_from_node(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and FULL_SYMBOL_RE.fullmatch(node.value):
        return node.value
    return None


def _pairing_violations(rel: str, text: str, cat_expiries: dict[str, date],
                         allowlist: dict[tuple[str, str], str]) -> list[tuple[str, int, str, str]]:
    """AST-based pairing checks (rule 3 in the module docstring): a real catalogue symbol paired,
    in the same call or via a single module-level expiry constant, with an expiry that does not
    match the catalogue's own expiry for that symbol."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    violations: list[tuple[str, int, str, str]] = []

    # 3a: same-call pairing.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        sym_val: str | None = None
        exp_node: ast.AST | None = None
        for kw in node.keywords:
            if kw.arg is None:
                continue
            sym = _symbol_from_node(kw.value)
            if sym is not None:
                sym_val = sym
            if kw.arg in EXPIRY_KEYWORDS:
                exp_node = kw.value
        if sym_val is None or exp_node is None:
            continue
        real = cat_expiries.get(sym_val)
        if real is None:
            continue  # already reported (or allowlisted) as a full-symbol violation
        claimed = _date_from_node(exp_node)
        if claimed is None or claimed == real:
            continue
        if (rel, sym_val) in allowlist:
            continue
        violations.append((rel, node.lineno, sym_val,
                            f"paired with expiry {claimed.isoformat()} but the catalogue lists "
                            f"{real.isoformat()} for this symbol"))

    # 3b: module-level constant pairing.
    date_constants: list[date] = []
    symbol_assignments: list[tuple[int, str]] = []  # (lineno, symbol)
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        val = node.value
        d = _date_from_node(val)
        if d is not None:
            date_constants.append(d)
            continue
        sym = _symbol_from_node(val)
        if sym is not None:
            symbol_assignments.append((node.lineno, sym))
            continue
        if isinstance(val, (ast.Tuple, ast.List)) and val.elts:
            syms = [_symbol_from_node(elt) for elt in val.elts]
            if all(syms):
                symbol_assignments.extend((node.lineno, s) for s in syms if s)
    if len(date_constants) == 1:
        real_by_symbol = date_constants[0]
        for lineno, sym in symbol_assignments:
            real = cat_expiries.get(sym)
            if real is None or real == real_by_symbol:
                continue
            if (rel, sym) in allowlist:
                continue
            violations.append((rel, lineno, sym,
                                f"module constant paired with expiry {real_by_symbol.isoformat()} but "
                                f"the catalogue lists {real.isoformat()} for this symbol"))
    return violations


Defs = dict[str, list[tuple[ast.AST, "int | None"]]]


def _is_int(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool)


def _int_values(node: ast.AST, defs: Defs, seen: frozenset[str]) -> set[int]:
    """Integers an expression can take: literals, ``range(literal, ...)`` expanded, names resolved through
    ``defs`` (assignment values and ``for`` iterables). Unknown pieces contribute nothing (never guessed)."""
    if _is_int(node):
        return {node.value}  # type: ignore[attr-defined]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
        args = [a.value for a in node.args if _is_int(a)]  # type: ignore[attr-defined]
        if len(args) == len(node.args) and 1 <= len(args) <= 3 and (len(args) < 3 or args[2] != 0):
            return set(range(*args))
        return set()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "enumerate" and node.args:
        return _int_values(node.args[0], defs, seen)
    if isinstance(node, ast.Name):
        if node.id in seen:
            return set()
        out: set[int] = set()
        for value, position in defs.get(node.id, []):
            rows = value.elts if isinstance(value, (ast.Tuple, ast.List)) else []
            if position is not None and rows and all(isinstance(r, (ast.Tuple, ast.List)) for r in rows):
                for row in rows:
                    if position < len(row.elts):  # type: ignore[attr-defined]
                        out |= _int_values(row.elts[position], defs, seen | {node.id})  # type: ignore[attr-defined]
            else:
                out |= _int_values(value, defs, seen | {node.id})
        return out
    found: set[int] = set()
    for child in ast.iter_child_nodes(node):
        found |= _int_values(child, defs, seen)
    return found


def _name_definitions(scope: ast.AST) -> Defs:
    """name -> [(value expression, tuple position or None)] from assignments, ``for`` loops and comprehensions."""
    defs: Defs = {}

    def bind(target: ast.AST, value: ast.AST, offset: int = 0) -> None:
        if isinstance(target, ast.Name):
            defs.setdefault(target.id, []).append((value, None))
        elif isinstance(target, (ast.Tuple, ast.List)):
            for i, t in enumerate(target.elts):
                if isinstance(t, ast.Name):
                    defs.setdefault(t.id, []).append((value, i - offset))

    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                bind(t, node.value)
        elif isinstance(node, (ast.For, ast.comprehension)):
            enum = (isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name)
                    and node.iter.func.id == "enumerate")
            bind(node.target, node.iter, 1 if enum else 0)
    return defs


def _fstring_strike_violations(rel: str, tree: ast.AST, catalogue_symbols: set[str],
                                synthetic: dict[tuple[str, str], str]) -> list[tuple[str, int, str, str]]:
    """Rule 2b: the strikes an f-string tradingsymbol can be built from must exist in the catalogue."""
    violations: list[tuple[str, int, str, str]] = []
    module_defs = _name_definitions(tree)
    scope_of: dict[int, ast.AST] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                scope_of[id(n)] = fn  # inner functions are walked later and overwrite: innermost wins
    for node in ast.walk(tree):
        if not (isinstance(node, ast.JoinedStr) and len(node.values) >= 2):
            continue
        first, second = node.values[0], node.values[1]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)
                and HEAD_ONLY_RE.fullmatch(first.value)
                and isinstance(second, ast.FormattedValue)):
            continue
        head = first.value
        if not any(s.startswith(head) and s.endswith(("CE", "PE")) for s in catalogue_symbols):
            continue  # no option at this head at all: reported by the head check
        third = node.values[2] if len(node.values) > 2 else None
        literal = third.value if isinstance(third, ast.Constant) else None
        suffixes = (literal,) if literal in ("CE", "PE") else ("CE", "PE")
        fn = scope_of.get(id(node))
        if fn is not None and (rel, fn.name) in synthetic:  # type: ignore[attr-defined]
            continue
        defs = {**module_defs, **(_name_definitions(fn) if fn is not None else {})}
        missing = sorted(k for k in _int_values(second.value, defs, frozenset())
                         if not any(f"{head}{k}{sfx}" in catalogue_symbols for sfx in suffixes))
        if missing:
            shown = ", ".join(str(k) for k in missing[:6]) + (" ..." if len(missing) > 6 else "")
            violations.append((rel, node.lineno, f"{head}{{{ast.unparse(second.value)}}}",
                               f"{len(missing)} built strike(s) not in the catalogue for this head: {shown}"))
    return violations


def find_violations(paths: list[Path], catalogue_symbols: set[str],
                     allowlist: dict[tuple[str, str], str] | None = None,
                     base: Path = TESTS_DIR,
                     catalogue_expiries: dict[str, date] | None = None,
                     synthetic: dict[tuple[str, str], str] | None = None) -> list[tuple[str, int, str, str]]:
    """Return (relative_path, line_number, matched_text, reason) for every literal that is neither a
    real catalogue symbol/head nor allowlisted, plus every real symbol paired (same call or a single
    module expiry constant) with an expiry the catalogue does not agree with. Pure function of its
    inputs -- used directly by the mutation tests below without touching the real tree."""
    allowlist = allowlist or {}
    if catalogue_expiries is None:
        catalogue_expiries = _load_catalogue_expiries()
    violations: list[tuple[str, int, str, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        rel = str(path.resolve().relative_to(base.resolve())).replace("\\", "/") if path.is_absolute() else str(path)
        for m in FULL_SYMBOL_RE.finditer(text):
            sym = m.group(0)
            if (rel, sym) in allowlist:
                continue
            if sym not in catalogue_symbols:
                line = text.count("\n", 0, m.start()) + 1
                violations.append((rel, line, sym, "full symbol not found in the catalogue"))
        for m in DYNAMIC_HEAD_RE.finditer(text):
            head = m.group(0)
            if (rel, head) in allowlist:
                continue
            if not any(s.startswith(head) and s.endswith(("CE", "PE")) for s in catalogue_symbols):
                line = text.count("\n", 0, m.start()) + 1
                violations.append((rel, line, head, "no catalogue option starts with this head"))
        violations.extend(_pairing_violations(rel, text, catalogue_expiries, allowlist))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        violations.extend(_fstring_strike_violations(rel, tree, catalogue_symbols, synthetic or {}))
    return violations


def _real_test_files() -> list[Path]:
    return sorted(p for p in TESTS_DIR.rglob("*.py") if p.resolve() != THIS_FILE)


def test_every_tradingsymbol_literal_in_tests_resolves_in_the_catalogue() -> None:
    """AC-1: core proof. Scans every ``tests/**/*.py`` file (this guard excluded) for tradingsymbol
    literals and fails, listing file:line, if any is neither a real catalogue symbol/head for its
    paired expiry nor an explicitly-reasoned allowlist entry."""
    catalogue_symbols = _load_catalogue_symbols()
    catalogue_expiries = _load_catalogue_expiries()
    violations = find_violations(_real_test_files(), catalogue_symbols, ALLOWLIST,
                                  catalogue_expiries=catalogue_expiries, synthetic=SYNTHETIC_CATALOGUE_ALLOWLIST)
    assert violations == [], "tradingsymbol literal(s) not in the catalogue (see ALLOWLIST to accept):\n" + "\n".join(
        f"  {path}:{line}: {sym!r} ({reason})" for path, line, sym, reason in violations
    )


def _run_on_scratch(source: str) -> list[tuple[str, int, str, str]]:
    catalogue_symbols = _load_catalogue_symbols()
    catalogue_expiries = _load_catalogue_expiries()
    scratch = TESTS_DIR / "_scratch_mutation_probe.py"
    scratch.write_text(source, encoding="utf-8")
    try:
        return find_violations([scratch], catalogue_symbols, ALLOWLIST, catalogue_expiries=catalogue_expiries)
    finally:
        scratch.unlink()


def test_guard_goes_red_on_the_findings_example_mutation() -> None:
    """Core/Proof mutation: reintroducing NIFTY26OCT23400CE paired with expiry 2026-10-06 (the exact
    finding example) must be caught. Run against a synthetic snippet (never the real tree) so this
    test itself never needs the real files to be broken."""
    mutated_source = (
        "import datetime\n"
        "EXPIRY = datetime.date(2026, 10, 6)\n"
        'CONTRACT = "NIFTY26OCT23400CE"\n'
    )
    violations = _run_on_scratch(mutated_source)
    assert violations, "the guard must go red on NIFTY26OCT23400CE (not a real catalogue symbol)"
    assert any(sym == "NIFTY26OCT23400CE" for _, _, sym, _ in violations)


def test_guard_catches_a_real_symbol_paired_with_the_wrong_expiry_same_call() -> None:
    """Attack 3 (verifier, round 2), same-call form: NIFTY26O0623400CE is a REAL catalogue symbol
    (expiry 2026-10-06), but here it is passed to a call alongside expiry=date(2026, 10, 13). Full-
    literal membership alone would pass this (the symbol IS in the catalogue); only the pairing check
    (rule 3a) catches the mismatch."""
    mutated_source = (
        "import datetime\n"
        "def Leg(contract, expiry):\n"
        "    return (contract, expiry)\n"
        'Leg(contract="NIFTY26O0623400CE", expiry=datetime.date(2026, 10, 13))\n'
    )
    violations = _run_on_scratch(mutated_source)
    assert violations, "the guard must go red on a real symbol paired with the wrong expiry (same call)"
    assert any(sym == "NIFTY26O0623400CE" and "paired with expiry 2026-10-13" in reason
               for _, _, sym, reason in violations)


def test_guard_catches_a_real_symbol_paired_with_the_wrong_expiry_module_constants() -> None:
    """Attack 3, module-constant form (the partial_inputs.py style): a single module-level EXPIRY
    constant and a real symbol constant that does not actually expire on that date."""
    mutated_source = (
        "import datetime\n"
        "EXPIRY = datetime.date(2026, 10, 13)\n"
        'CONTRACT = "NIFTY26O0623400CE"\n'
    )
    violations = _run_on_scratch(mutated_source)
    assert violations, "the guard must go red on a module-constant pairing mismatch"
    assert any(sym == "NIFTY26O0623400CE" and "module constant paired with expiry 2026-10-13" in reason
               for _, _, sym, reason in violations)


def test_guard_does_not_guess_when_a_file_has_no_or_multiple_expiry_constants() -> None:
    """A file with two expiry constants (like scenario_fixtures.py's NIFTY_EXPIRY/SENSEX_EXPIRY) must
    NOT be paired by guesswork -- unpairable, not a violation -- even when a symbol constant next to
    them would mismatch one of the two if guessed wrong."""
    mutated_source = (
        "import datetime\n"
        "A_EXPIRY = datetime.date(2026, 10, 6)\n"
        "B_EXPIRY = datetime.date(2026, 10, 13)\n"
        'CONTRACT = "NIFTY26O0623400CE"\n'
    )
    violations = _run_on_scratch(mutated_source)
    assert violations == [], f"a file with 2 expiry constants must be left unpairable, got: {violations}"


def test_allowlist_entries_are_not_stale() -> None:
    """Every ALLOWLIST entry names a file that still contains the literal it excuses, so a future
    correction that removes the literal is forced to also remove the now-dead allowlist entry."""
    for (rel_path, literal), _reason in ALLOWLIST.items():
        full_path = TESTS_DIR / rel_path
        assert full_path.is_file(), f"allowlisted file missing: {rel_path}"
        assert literal in full_path.read_text(encoding="utf-8"), (
            f"allowlist entry {rel_path!r}/{literal!r} no longer matches the file's contents"
        )


def test_guard_catches_an_fstring_whose_built_strikes_are_not_in_the_catalogue() -> None:
    """AC-1 (issue #61): ``f"NIFTY26O06{s}CE"`` has a real head, but strikes 20000..20200 are in no catalogue
    row at 2026-10-06; the head-only check passed it. Built through a comprehension over ``range``, as the real
    test_pick_lists.py does. A listed strike (23400, real NIFTY26O0623400CE) in the same shape passes."""
    bad = ("def make():\n"
           "    strikes = [v for v in range(20000, 20201, 100)]\n"
           "    return [f'NIFTY26O06{s}CE' for s in strikes]\n")
    good = ("def make():\n"
            "    return [f'NIFTY26O06{s}CE' for s in (23400, 23500)]\n")
    violations = _run_on_scratch(bad)
    assert len(violations) == 1 and "3 built strike(s)" in violations[0][3] and "20000, 20100, 20200" in violations[0][3]
    assert _run_on_scratch(good) == []
    tuple_rows = ("LEGS = ((1, 20000, 5), (2, 23400, 7))\n"
                  "def make():\n"
                  "    return [f'NIFTY26O06{k}PE' for a, k, p in LEGS]\n")
    assert len(_run_on_scratch(tuple_rows)) == 1  # only column 1 (strikes) is read, not the prices 5 and 7


def test_synthetic_catalogue_allowlist_entries_are_not_stale() -> None:
    """AC-1: each excused function still exists in its file and still builds an f-string symbol, so a rename
    or a cleanup forces the entry out."""
    for (rel_path, function), _reason in SYNTHETIC_CATALOGUE_ALLOWLIST.items():
        tree = ast.parse((TESTS_DIR / rel_path).read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
        assert funcs, f"{rel_path}: function {function} no longer exists"
        assert any(isinstance(n, ast.JoinedStr) for n in ast.walk(funcs[0])), f"{rel_path}:{function} has no f-string"
        lines = range(funcs[0].lineno, funcs[0].end_lineno + 1)  # type: ignore[operator]
        own = [v for v in _fstring_strike_violations(rel_path, tree, _load_catalogue_symbols(), {}) if v[1] in lines]
        assert own, f"{rel_path}:{function} no longer builds strikes missing from the catalogue; drop the entry"
