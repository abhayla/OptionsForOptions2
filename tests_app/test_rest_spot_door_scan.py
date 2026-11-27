"""Lane U hotfix A repo scans (REQ-118; ADR-330 (39)): the worker never reaches the REST index door, and no route
awaits a REST spot reader outside ``rest_spot_if_needed`` (which judges the tick store first)."""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend" / "ofo_app"


def test_the_worker_and_the_monitor_never_reach_the_rest_index_door():
    for name in ("background.py", "paper_monitor.py", "paper_exit.py", "tracking.py"):
        path = BACKEND / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            assert "index_spot" not in text and "read_rest_spot" not in text, name


def test_no_route_awaits_a_rest_spot_reader_before_the_tick_is_judged():
    """Every ``await <x>rest_reader(...)`` / ``read_rest_spot(...)`` / ``index_spot(...)`` in a route is the argument of
    ``rest_spot_if_needed`` (the one door); ``outcome.py`` holds the one real await."""
    found: list[str] = []
    for path in sorted((BACKEND / "routes").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
                f = node.value.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                if name in {"rest_reader", "read_rest_spot", "index_spot"} and path.name != "outcome.py":
                    found.append(f"{path.name}:{node.lineno}")
                if isinstance(f, ast.Call) and isinstance(f.func, ast.Name) and f.func.id == "get_rest_spot_reader":
                    found.append(f"{path.name}:{node.lineno}")
    assert found == []
