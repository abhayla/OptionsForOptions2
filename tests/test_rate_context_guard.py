"""GC-SET round 2, finding 1: every priced read of the risk-free rate under ``backend/ofo_app/routes/`` gets its context
through the one per-request dependency (``outcome.get_market_context``, which applies ``with_rate_in_force``).

Spec basis: REQ-167 AC-1 (the value in force now), ADR-222 (1), (9) (a change applies at the next request, no restart).
Defect class: the leg picker priced strikes and futures with ``feed.ctx.rate`` (the registry default) while ``/outcome``
used the stored rate. Before: 2 such reads (``leg_picker.py`` strikes Greeks and futures forward). After: 0.

The rule, by AST, per file (a violation names ``file:line``):

R1  an attribute read ``<x>.rate`` must have a plain name as ``<x>`` (``feed.ctx.rate``, ``get().rate`` and every other
    shape the scan cannot resolve are refused: fail closed);
R2  that name is never assigned in the function (``ctx = feed.ctx`` then ``ctx.rate`` is the original bypass);
R3  that name is a parameter of the function or of an enclosing one (never a global or a free name);
R4  in a route handler (decorated with ``router.<verb>(...)``) the parameter is declared
    ``Depends(get_market_context)``: the request's context, not whatever the caller supplies;
R5  a call to a function of the SAME file that takes a ``rate`` parameter passes it as ``rate=...`` (a route cannot
    silently fall back to the helper's default).

Known bypasses (not covered, by design): a helper in another module receives a context and reads its rate (the caller
is not traced across files: only the route files are scanned); ``getattr(ctx, "rate")`` and ``vars(ctx)["rate"]``;
a ``rate=`` keyword value that is itself wrong (R5 requires the keyword, not its value; the value must come from a
``.rate`` read, which R1-R4 govern, or a module constant); code outside ``routes/`` (the paper monitor and sockets read
the feed's own context on purpose, a later step). Mutation self-tests below show the scan goes red on the original
bypass, on an unresolvable shape and on a dropped ``rate=`` keyword.
"""

from __future__ import annotations

import ast
import pathlib
import shutil

import pytest

pytestmark = pytest.mark.repo_scan

ROUTES = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo_app" / "routes"
DEPENDENCY = "Depends(get_market_context)"


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, ast.arg]:
    a = fn.args
    return {x.arg: x for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, *([a.vararg] if a.vararg else []),
                               *([a.kwarg] if a.kwarg else []))}


def _defaults(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, ast.expr]:
    a = fn.args
    positional = [*a.posonlyargs, *a.args]
    out = {x.arg: d for x, d in zip(positional[len(positional) - len(a.defaults):], a.defaults, strict=True)}
    out.update({x.arg: d for x, d in zip(a.kwonlyargs, a.kw_defaults, strict=True) if d is not None})
    return out


def _is_route(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)
               and d.func.value.id == "router" for d in fn.decorator_list)


def _assigned(fn: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            names.add(node.id)
    return names


def _declared_dependency(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    arg = _params(fn)[name]
    annotated = arg.annotation is not None and DEPENDENCY in ast.unparse(arg.annotation)
    default = _defaults(fn).get(name)
    return annotated or (default is not None and DEPENDENCY in ast.unparse(default))


def scan_source(source: str, filename: str) -> list[str]:  # noqa: C901 - R1-R5 side by side in one AST pass
    """Violations (``file:line: why``) of R1-R5 in one source text."""
    tree = ast.parse(source, filename)
    found: list[str] = []
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    rate_takers = {f.name for f in functions if "rate" in _params(f)}
    owner: dict[int, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}

    def visit(node: ast.AST, chain: list) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            chain = [*chain, node]
        owner[id(node)] = chain
        for child in ast.iter_child_nodes(node):
            visit(child, chain)

    visit(tree, [])
    for node in ast.walk(tree):
        where = f"{filename}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Attribute) and node.attr == "rate" and isinstance(node.ctx, ast.Load):
            if not isinstance(node.value, ast.Name):
                found.append(f"{where}: R1 unresolvable shape {ast.unparse(node)} (read the rate of a plain parameter)")
                continue
            name, chain = node.value.id, owner[id(node)]
            if not chain:
                found.append(f"{where}: R3 {name}.rate read outside any function")
                continue
            if any(name in _assigned(f) for f in chain):
                found.append(f"{where}: R2 {name} is assigned in the function, so {name}.rate is not the dependency's")
                continue
            holder = next((f for f in reversed(chain) if name in _params(f)), None)
            if holder is None:
                found.append(f"{where}: R3 {name} is not a parameter, {name}.rate has no declared source")
            elif _is_route(holder) and not _declared_dependency(holder, name):
                found.append(f"{where}: R4 route parameter {name} is not {DEPENDENCY}")
        elif isinstance(node, ast.Call):
            callee = node.func.id if isinstance(node.func, ast.Name) else None
            if callee in rate_takers and not any(k.arg == "rate" for k in node.keywords):
                found.append(f"{where}: R5 call to {callee} does not pass rate=")
    return found


def scan_dir(directory: pathlib.Path) -> list[str]:
    out: list[str] = []
    for path in sorted(directory.glob("*.py")):
        out.extend(scan_source(path.read_text(encoding="utf-8"), path.name))
    return out


def test_no_route_reads_a_rate_that_did_not_come_from_the_dependency():
    """After: 0 violations in every routes/*.py (before the fix: leg_picker.py read ``feed.ctx.rate`` twice)."""
    assert scan_dir(ROUTES) == []


def test_the_scan_finds_the_priced_routes_it_is_meant_to_guard():
    """Not vacuous: the scan sees `.rate` reads in the files that price (outcome, paper, planned entry, tracking)
    and the leg picker's rate parameter."""
    hits = {p.name for p in ROUTES.glob("*.py") if ".rate" in p.read_text(encoding="utf-8")}
    assert {"outcome.py", "paper.py", "planned_entry.py", "tracking.py"} <= hits
    leg = (ROUTES / "leg_picker.py").read_text(encoding="utf-8")
    assert "rate=DEFAULT_RATE if ctx is None else ctx.rate" in leg


def _mutated(tmp_path: pathlib.Path, old: str, new: str) -> pathlib.Path:
    """A scratch copy of routes/ with leg_picker.py changed once."""
    copy = tmp_path / "routes"
    shutil.copytree(ROUTES, copy, ignore=shutil.ignore_patterns("__pycache__"))
    target = copy / "leg_picker.py"
    text = target.read_text(encoding="utf-8")
    assert text.count(old) >= 1, f"mutation anchor not found: {old!r}"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return copy


def test_mutation_the_original_leg_picker_bypass_is_red(tmp_path):
    """Re-introduce the bypass as it was: Greeks priced with the feed context's rate through a local ``ctx``."""
    copy = _mutated(tmp_path, "answered_at, rate)\n    cell_of", "answered_at, ctx.rate)\n    cell_of")
    problems = scan_dir(copy)
    assert any(p.startswith("leg_picker.py") and "ctx.rate" in p and "R3" in p for p in problems) or any(
        p.startswith("leg_picker.py") and "R2" in p for p in problems), problems


def test_mutation_a_feed_chain_read_is_red(tmp_path):
    copy = _mutated(tmp_path, "rate=DEFAULT_RATE if ctx is None else ctx.rate)\n\n\n@router.get(FUTURES_PATH",
                    "rate=feed.ctx.rate)\n\n\n@router.get(FUTURES_PATH")
    assert any("R1" in p and "feed.ctx.rate" in p for p in scan_dir(copy))


def test_mutation_a_dropped_rate_keyword_is_red(tmp_path):
    copy = _mutated(tmp_path, "viewer,\n                          rate=DEFAULT_RATE if ctx is None else ctx.rate)",
                    "viewer)")
    assert any("R5" in p and "strikes_answer" in p for p in scan_dir(copy)), scan_dir(copy)


def test_mutation_a_route_parameter_that_is_not_the_dependency_is_red(tmp_path):
    copy = _mutated(tmp_path, "ctx: Annotated[MarketContext | None, Depends(get_market_context)],\n        width",
                    "ctx: Annotated[MarketContext | None, Depends(get_feed_ctx)],\n        width")
    assert any("R4" in p for p in scan_dir(copy)), scan_dir(copy)


@pytest.mark.parametrize("source", [
    "def f(feed):\n    ctx = feed.ctx\n    return ctx.rate\n",
    "def f():\n    return get().rate\n",
    "X = ctx.rate\n",
    "def f():\n    return ctx.rate\n",
])
def test_unresolvable_or_unsourced_shapes_fail_closed(source):
    assert scan_source(source, "x.py") != []


def test_a_plain_parameter_and_a_dependency_route_pass():
    ok = ("def helper(ctx):\n    return ctx.rate\n\n"
          "@router.get('/x')\nasync def route(ctx: Annotated[Ctx | None, Depends(get_market_context)]):\n"
          "    return ctx.rate\n")
    assert scan_source(ok, "x.py") == []
