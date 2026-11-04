"""GC-IC1 step 9 repo scan (finding freshness-judged-on-request-start-clock): every ``resolve_spot`` call in the routes
(and the window reader) passes ``now=spot_judging_now(...)``, a clock read after the awaited reads, never
``market.now`` or a ``now`` read before them. The ONE exception: a feed-only call (second argument the literal
``None``) has no awaited reader to wait for. Fails closed on shapes it cannot read: ``*args`` / ``**kwargs``, a missing
``now``, an alias import of ``resolve_spot``, a call through an attribute other than ``resolve_spot`` is not seen, so
any alias is refused."""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan  # reads backend source text

BACKEND = Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
HELPER = "spot_judging_now"


def _files():
    return [*sorted((BACKEND / "routes").glob("*.py")), BACKEND / "adjustment_readers.py"]


def problems(source: str, name: str = "<src>") -> list[str]:
    out: list[str] = []
    tree = ast.parse(source)
    skip_args = 2  # resolve_spot(feed, rest, ...): the second positional is the REST reading
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out += [f"{name}:{node.lineno} resolve_spot imported under another name" for a in node.names
                    if a.name == "resolve_spot" and a.asname not in (None, "resolve_spot")]
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
        if called != "resolve_spot":
            continue
        where = f"{name}:{node.lineno}"
        if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
            out.append(f"{where} *args / **kwargs: cannot be read")
            continue
        if len(node.args) >= skip_args and isinstance(node.args[1], ast.Constant) and node.args[1].value is None:
            continue  # feed-only: no awaited reader before it
        now = next((k.value for k in node.keywords if k.arg == "now"), None)
        ok = (isinstance(now, ast.Call) and isinstance(now.func, (ast.Name, ast.Attribute))
              and (now.func.id if isinstance(now.func, ast.Name) else now.func.attr) == HELPER)
        if not ok:
            out.append(f"{where} now= is not {HELPER}(...)")
    return out


def test_every_resolve_spot_call_in_the_routes_uses_the_judging_clock_helper():
    found = {p.name: problems(p.read_text(encoding="utf-8"), p.name) for p in _files()}
    assert [x for v in found.values() for x in v] == []


def test_the_scan_sees_the_known_callers():
    calls = {p.name: p.read_text(encoding="utf-8").count("resolve_spot(") for p in _files()}
    named = {k: v for k, v in calls.items() if v}
    assert {"adjustment.py", "adjustment_check.py", "adjustment_plan.py", "playbooks.py",
            "adjustment_readers.py"} <= set(named)


@pytest.mark.parametrize("src", [
    "resolve_spot(f, r, c, now=market.now, windows=w)",
    "resolve_spot(f, r, c, windows=w)",
    "resolve_spot(f, r, c, now=now, windows=w)",
    "resolve_spot(\n f, r, c,\n now=market.now,\n windows=w)",
    "resolve_spot(*a)",
    "resolve_spot(f, r, c, **kw)",
    "from x import resolve_spot as rs",
    "m.resolve_spot(f, r, c, now=when, windows=w)",
])
def test_the_detector_flags_each_bad_shape(src):
    assert problems(src)


@pytest.mark.parametrize("src", [
    "resolve_spot(f, r, c, now=spot_judging_now(ctx), windows=w)",
    "resolve_spot(\n f, r, c,\n now=outcome.spot_judging_now(ctx),\n windows=w)",
    "resolve_spot(f, None, None, now=now, windows=w)",
])
def test_the_detector_passes_the_good_shapes(src):
    assert problems(src) == []
