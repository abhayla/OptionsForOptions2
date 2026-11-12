"""Guard for the `full_chain` marker (CI speed review F1, 2026-11-13).

Class: pull requests skip every test marked `full_chain` (they run nightly), so a marked test that replays no LATER
migration (its migration is head, so `later_than` is empty) moved a PR's own checks to the nightly for no saving
(0052's only "refusing to downgrade" assertion did). The marker must mean exactly: replays at least one later migration.

This reads the test files' source (no database): for every test function carrying the marker it resolves the migration
file the test targets from its `round_trip_sql(...)` / `later_than(...)` call and requires a non-empty `later_than`.
A marked test whose target cannot be resolved fails too (fail closed).
"""
from __future__ import annotations

import ast
from pathlib import Path

from _migration_replay import later_than

HERE = Path(__file__).resolve().parent
MIN_MARKED = 10  # a parser that finds none would pass the main test for nothing
_CALLS = {"round_trip_sql", "later_than"}


def _is_marker(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "full_chain"


def _module_strings(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            out[node.targets[0].id] = node.value.value
    return out


def _marked_tests() -> list[tuple[str, list[str]]]:
    """(test id, targeted migration file names) for every function marked full_chain, or whose module is."""
    found: list[tuple[str, list[str]]] = []
    for path in sorted(HERE.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        strings = _module_strings(tree)
        module_marked = any(
            isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
            and any(_is_marker(x) for x in ast.walk(n.value)) for n in tree.body)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
                continue
            if not (module_marked or any(_is_marker(x) for d in node.decorator_list for x in ast.walk(d))):
                continue
            targets: list[str] = []
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in _CALLS):
                    continue
                arg = call.args[0] if call.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    targets.append(arg.value)
                elif isinstance(arg, ast.Name) and arg.id in strings:
                    targets.append(strings[arg.id])
            found.append((f"{path.name}::{node.name}", targets))
    return found


def test_there_are_marked_tests_to_check():
    assert len(_marked_tests()) >= MIN_MARKED


def test_every_full_chain_test_replays_at_least_one_later_migration():
    bad = []
    for test_id, targets in _marked_tests():
        if not targets:
            bad.append(f"{test_id}: no round_trip_sql/later_than call with a resolvable migration name")
        bad.extend(f"{test_id}: {name} has no later migration, so it replays no chain; remove the marker"
                   for name in targets if not later_than(name))
    assert not bad, "full_chain must mean 'replays a later migration':\n" + "\n".join(bad)
