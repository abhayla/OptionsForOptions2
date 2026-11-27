"""ADR-330 (12): each condition is a stand-alone pure check; a new trigger cannot bypass them. AST scan.

Rule 1, backend/ofo/checks/: no import of a store (``*_store``, ``ofo_app``, ``sqlalchemy``, ``asyncpg``, ``redis``,
``fastapi``, a ``routes`` module), no clock (``datetime.now`` / ``utcnow`` / ``today``, ``time.time`` / ``monotonic``,
``import time``), no function with a ``conn`` / ``db`` / ``session`` parameter.

Rule 2, backend/ofo_app/: a trigger-level comparison (``<`` ``<=`` ``>`` ``>=`` with a ``.level`` attribute on one side,
the ``Trigger.level`` pattern) is a problem anywhere; a call of ``crossed`` (the monitor's judgement, which calls
``index_level`` / ``leg_price``) is allowed only in ``paper_monitor.py`` and ``routes/paper.py`` (``_judge_levels``,
the check_trigger_levels path).

Known bypasses (written, not caught): a level held under another attribute or local name (``lvl = t.level`` then
``price >= lvl`` is caught only through the ``.level`` read when compared directly); arithmetic that hides a
comparison (``(price - level).is_signed()``, ``max`` / ``min``, ``Decimal.compare``); a call through ``getattr`` or an
alias of ``crossed`` made by assignment; a clock reached through an alias (``from datetime import datetime as d``,
``d.now()``) or a passed-in callable; a comparison written in SQL; plan-level comparisons in backend/ofo/adjustment
(alert-only, they go through ``actionable_alerts``, ADR-330 (5)(b)); files outside backend/.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKS = "backend/ofo/checks/"
APP = "backend/ofo_app/"
CROSSED_HOMES = frozenset({APP + "paper_monitor.py", APP + "routes/paper.py"})
BAD_IMPORT_PARTS = ("_store", "ofo_app", "sqlalchemy", "asyncpg", "redis", "fastapi", "routes")
CLOCK_ATTRS = {("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("date", "today"),
               ("time", "time"), ("time", "monotonic"), ("time", "time_ns"), ("time", "perf_counter")}
MIN_CHECK_FILES = 7
CONN_PARAMS = {"conn", "db", "session"}
ORDER_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _imported(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [(node.module or "")] + [(node.module or "") + "." + a.name for a in node.names]
    return []


def check_problems(name: str, source: str) -> list[str]:
    """Rule 1 for one file under backend/ofo/checks/."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        out.extend(f"{name}:{node.lineno}: a check imports {mod}: it must stay pure (no store, clock, route)"
                   for mod in _imported(node)
                   if mod == "time" or any(p in mod.split(".")[-1] or p in mod.split(".") for p in BAD_IMPORT_PARTS))
        if isinstance(node, ast.Attribute):
            owner = node.value.id if isinstance(node.value, ast.Name) else \
                node.value.attr if isinstance(node.value, ast.Attribute) else None
            if (owner, node.attr) in CLOCK_ATTRS:
                out.append(f"{name}:{node.lineno}: a check reads the clock ({owner}.{node.attr})")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = node.args
            out.extend(f"{name}:{node.lineno}: {node.name} takes {a.arg}: a check never touches a store"
                       for a in [*args.posonlyargs, *args.args, *args.kwonlyargs] if a.arg in CONN_PARAMS)
    return out


def app_problems(name: str, source: str) -> list[str]:
    """Rule 2 for one file under backend/ofo_app/."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(isinstance(o, ORDER_OPS) for o in node.ops) \
                and any(isinstance(x, ast.Attribute) and x.attr == "level" for x in [node.left, *node.comparators]):
            out.append(f"{name}:{node.lineno}: a trigger level is compared: use ofo.checks.index_level / leg_price")
        if isinstance(node, ast.Call) and name not in CROSSED_HOMES:
            f = node.func
            called = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if called == "crossed":
                out.append(f"{name}:{node.lineno}: crossed() called outside the monitor and check_trigger_levels")
    return out


def _tree(top: str, rel: str) -> dict[str, str]:
    return {str(p.relative_to(ROOT)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in (ROOT / top).rglob("*.py") if rel in str(p.relative_to(ROOT)).replace("\\", "/")}


def test_checks_are_pure_no_store_clock_route_or_conn_parameter():
    files = _tree("backend/ofo/checks", CHECKS)
    assert len(files) >= MIN_CHECK_FILES, sorted(files)  # the scan really saw the checks
    assert [p for n, s in files.items() for p in check_problems(n, s)] == []


def test_no_trigger_level_comparison_or_stray_crossed_call_in_ofo_app():
    files = _tree("backend/ofo_app", APP)
    assert APP + "paper_monitor.py" in files and APP + "routes/paper.py" in files
    assert [p for n, s in files.items() for p in app_problems(n, s)] == []


def test_the_monitor_and_check_trigger_levels_really_call_crossed():
    """Counter: the allowed homes still use the judgement (a vacuous rule 2 would pass with no caller at all)."""
    for home in CROSSED_HOMES:
        assert "crossed(" in (ROOT / home).read_text(encoding="utf-8"), home


@pytest.mark.parametrize("src", [
    "from ofo_app import paper_trigger_store\n",
    "from ofo_app.paper_trigger_store import load\n",
    "import sqlalchemy\n",
    "import time\n",
    "from ofo_app.routes import paper\n",
])
def test_mutation_a_check_importing_a_store_or_clock_fails(src):
    assert check_problems(CHECKS + "sample.py", src)


@pytest.mark.parametrize("src", [
    "import datetime\ndef f():\n    return datetime.datetime.now()\n",
    "from datetime import datetime\ndef f():\n    return datetime.now()\n",
    "def f(conn, x):\n    return x\n",
    "async def f(x, *, session):\n    return x\n",
])
def test_mutation_a_check_reading_a_clock_or_taking_a_connection_fails(src):
    assert check_problems(CHECKS + "sample.py", src)


def test_a_pure_check_is_clean():
    src = "from decimal import Decimal\ndef f(level: Decimal, price: Decimal):\n    return price >= level\n"
    assert check_problems(CHECKS + "sample.py", src) == []


@pytest.mark.parametrize("src", [
    "def f(t, price):\n    return price >= t.level\n",
    "def f(trigger, p):\n    return trigger.level < p.price\n",
    "def f(n, p):\n    return p <= n.level\n",
])
def test_mutation_a_level_comparison_in_ofo_app_fails(src):
    assert app_problems(APP + "new_trigger.py", src)


def test_mutation_a_crossed_call_outside_the_homes_fails_and_inside_is_allowed():
    src = "from ofo.tracking import stops\ndef f(t, p):\n    return stops.crossed(t, p)\n"
    assert app_problems(APP + "new_trigger.py", src)
    assert app_problems(APP + "paper_monitor.py", src) == []
    assert app_problems(APP + "routes/paper.py", src) == []
