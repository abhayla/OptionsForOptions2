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


def _is_clock_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in CLOCK_FUNCTIONS and isinstance(func.value, ast.Name) and func.value.id == "time"
    return isinstance(func, ast.Name) and func.id in BARE_CLOCK_NAMES


def _clock_tainted(node: ast.AST, tainted: set[str]) -> bool:
    return any(_is_clock_call(n) or (isinstance(n, ast.Name) and n.id in tainted) for n in ast.walk(node))


def _has_number(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
               for n in ast.walk(node))


def wall_clock_asserts(source: str) -> list[int]:
    """Line numbers of comparisons between a clock reading (or a value computed from one) and a number."""
    tree = ast.parse(source)
    tainted: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value is not None:
            targets, value = [node.target], node.value
        if value is not None and _clock_tainted(value, tainted):
            tainted.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(_clock_tainted(s, tainted) for s in sides) and any(_has_number(s) for s in sides):
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
    assert wall_clock_asserts(unrelated_number) == []
