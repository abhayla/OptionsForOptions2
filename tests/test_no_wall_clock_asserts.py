"""W-033: no test asserts elapsed wall-clock time against a number.

Finding wall-clock-assertion-flakes-under-load: a threshold such as ``time.perf_counter() - start < 1.0`` measures how
busy the machine is, not what the code costs, so it fails under parallel load and passes on re-run. A test proves cost
by COUNTING work (see ``tests/work_count.py``). This guard reads every test file with ``ast`` and fails, listing
file:line, on any comparison that involves a clock reading (directly or through a variable) and a number.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent

#: Explicit exceptions as "relative/path.py:line" with the reason. Empty: no test needs a wall-clock threshold.
ALLOWLIST: dict[str, str] = {}

CLOCK_FUNCTIONS = {"perf_counter", "perf_counter_ns", "monotonic", "monotonic_ns", "process_time", "process_time_ns",
                   "time", "time_ns"}
#: Bare names imported from the time module (``from time import perf_counter``); bare ``time`` is left out because
#: ``from datetime import time`` makes it a clock-time constructor, not a clock.
BARE_CLOCK_NAMES = CLOCK_FUNCTIONS - {"time"}
#: timeit measures wall-clock time too: ``timeit.timeit(...) < 1`` is the same flake as a perf_counter difference.
TIMEIT_FUNCTIONS = {"timeit", "repeat", "default_timer"}
DATETIME_NOW = {"now", "utcnow", "today"}


class _Clocks:
    """Which names in one file refer to a clock: ``import time as t`` and ``from time import perf_counter as pc``."""

    def __init__(self, tree: ast.AST) -> None:
        self.time_modules = {"time"}
        self.timeit_modules = {"timeit"}
        self.bare: set[str] = set(BARE_CLOCK_NAMES)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "time":
                        self.time_modules.add(a.asname or a.name)
                    if a.name == "timeit":
                        self.timeit_modules.add(a.asname or a.name)
            elif isinstance(node, ast.ImportFrom) and node.module in ("time", "timeit"):
                allowed = CLOCK_FUNCTIONS - {"time"} if node.module == "time" else TIMEIT_FUNCTIONS
                self.bare.update(a.asname or a.name for a in node.names if a.name in allowed)

    def is_clock_call(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            return ((func.attr in CLOCK_FUNCTIONS and func.value.id in self.time_modules)
                    or (func.attr in TIMEIT_FUNCTIONS and func.value.id in self.timeit_modules))
        return isinstance(func, ast.Name) and func.id in self.bare

    @staticmethod
    def is_datetime_now(node: ast.AST) -> bool:
        """``datetime.now()`` / ``datetime.datetime.now()`` / ``utcnow()`` / ``today()``."""
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in DATETIME_NOW):
            return False
        base = node.func.value
        return (isinstance(base, ast.Name) and base.id == "datetime") or (
            isinstance(base, ast.Attribute) and base.attr == "datetime")


def _is_clock_call(node: ast.AST) -> bool:
    """Compatibility helper for the plain ``time`` module names (no aliases)."""
    return _Clocks(ast.Module(body=[], type_ignores=[])).is_clock_call(node)


def _numeric_constants(tree: ast.Module) -> set[str]:
    """Module-level names bound to a number (``LIMIT = 0.5``): a threshold held in a constant is still a threshold."""
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v = node.value
            if isinstance(v, ast.UnaryOp):
                v = v.operand
            if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) and not isinstance(v.value, bool):
                out.add(node.targets[0].id)
    return out


def wall_clock_asserts(source: str) -> list[int]:
    """Line numbers of comparisons between a clock reading (or a value computed from one) and a number."""
    tree = ast.parse(source)
    clocks = _Clocks(tree)
    constants = _numeric_constants(tree) if isinstance(tree, ast.Module) else set()
    tainted: set[str] = set()
    datetimes: set[str] = set()  # names bound directly to datetime.now(): only their DIFFERENCE is a duration

    def datetime_diff(node: ast.AST) -> bool:
        return any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Sub)
                   and any(clocks.is_datetime_now(m) or (isinstance(m, ast.Name) and m.id in datetimes)
                           for m in ast.walk(n))
                   for n in ast.walk(node))

    def clock_tainted(node: ast.AST) -> bool:
        return datetime_diff(node) or any(
            clocks.is_clock_call(n) or (isinstance(n, ast.Name) and n.id in tainted) for n in ast.walk(node))

    def has_number(node: ast.AST) -> bool:
        return any((isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool))
                   or (isinstance(n, ast.Name) and n.id in constants) for n in ast.walk(node))

    assignments = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))]
    for node in assignments:  # datetime names first so a later difference can use them
        value = getattr(node, "value", None)
        if clocks.is_datetime_now(value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            datetimes.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
    for node in assignments:
        value = getattr(node, "value", None)
        if value is not None and clock_tainted(value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            tainted.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(clock_tainted(s) for s in sides) and any(has_number(s) for s in sides):
                hits.append(node.lineno)
    return sorted(hits)


def test_guard_no_test_compares_elapsed_wall_clock_time_to_a_number() -> None:
    """Guard (finding wall-clock-assertion-flakes-under-load): no file under tests/ asserts a clock reading against a number (outside the explicit ALLOWLIST)."""
    found = []
    for path in sorted(TESTS.rglob("*.py")):
        relative = path.relative_to(TESTS).as_posix()
        for line in wall_clock_asserts(path.read_text(encoding="utf-8")):
            if f"{relative}:{line}" not in ALLOWLIST:
                found.append(f"{relative}:{line}")
    assert not found, "wall-clock threshold assertions (count work instead, see tests/work_count.py): " + ", ".join(found)


SHAPE_TIMEIT = "import timeit\nassert timeit.timeit(run, number=1) < 1\n"
SHAPE_DATETIME = "from datetime import datetime\ns = datetime.now()\nassert (datetime.now() - s).total_seconds() < 1\n"
SHAPE_ALIAS = "import time as t\ns = t.perf_counter()\nassert t.perf_counter() - s < 1\n"
SHAPE_CONSTANT = ("import time\nLIMIT = 0.5\ns = time.perf_counter()\nelapsed = time.perf_counter() - s\n"
                  "assert elapsed < LIMIT\n")
SHAPE_ALIASED_BARE = "from time import perf_counter as pc\ns = pc()\nassert pc() - s < 1\n"


def test_guard_flags_every_clock_threshold_shape_and_passes_clean_code() -> None:
    """Guard self-test on sample snippets: each real-world shape is flagged, look-alikes are not."""
    direct = "import time\nstart = time.perf_counter()\nrun()\nassert time.perf_counter() - start < 0.05\n"
    via_variable = "import time\ns = time.monotonic()\nrun()\nelapsed = time.monotonic() - s\nassert elapsed < 2.0, 'slow'\n"
    bare = "from time import perf_counter\nt = perf_counter()\nassert perf_counter() - t < 5\n"
    wall = "import time\nassert time.time() < 1e12\n"
    assert wall_clock_asserts(direct) == [4]
    assert wall_clock_asserts(via_variable) == [5]
    assert wall_clock_asserts(bare) == [3]
    assert wall_clock_asserts(wall) == [2]
    clock_time_constructor = "import datetime\nassert datetime.time(9, 30) < datetime.time(11, 0)\n"
    unrelated_number = "import time\nstart = time.perf_counter()\nassert len(items) < 5\n"
    assert wall_clock_asserts(clock_time_constructor) == []
    assert wall_clock_asserts(SHAPE_TIMEIT) == [2]
    assert wall_clock_asserts(SHAPE_DATETIME) == [3]
    assert wall_clock_asserts(SHAPE_ALIAS) == [3]
    assert wall_clock_asserts(SHAPE_CONSTANT) == [5]
    assert wall_clock_asserts(SHAPE_ALIASED_BARE) == [3]
    look_alikes = ("import datetime\nassert datetime.datetime.now().year < 3000\n"
                   "import timeit\nassert timeit.default_timer is not None\nLIMIT = 5\nassert len(x) < LIMIT\n")
    assert wall_clock_asserts(look_alikes) == []
    assert wall_clock_asserts(unrelated_number) == []
