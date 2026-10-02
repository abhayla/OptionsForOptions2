#!/usr/bin/env python3
# Copied/adapted from abhayla/algochanakya@bf9faf7:.github/scripts/alembic-migration-guard.py (ADR-047)
# Changed: versions directory is backend/ofo_app/alembic/versions; a missing directory fails (fail closed);
# standard library only, so CI may run it before installing dependencies.
"""CI guard: refuse a silently-empty Alembic migration.

An empty migration happens when autogenerate saw no schema delta (usually a model not imported in
backend/ofo_app/alembic/env.py). Each migration's upgrade() must contain at least one `op.*` call, unless its
docstring marks the emptiness as intentional. Merge migrations (2+ down revisions) are skipped.

Exit codes: 0 = all migrations non-empty; 1 = an empty upgrade() or an unreadable file.
Run from the repo root: python scripts/alembic_migration_guard.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = REPO_ROOT / "backend" / "ofo_app" / "alembic" / "versions"

EMPTY_MIGRATION_HINT = (
    "This usually means the new model was not imported in backend/ofo_app/models.py / "
    "backend/ofo_app/alembic/env.py, so autogenerate saw no change."
)

INTENTIONAL_MARKERS = ("not supported", "no-op", "no op", "irreversible", "intentional", "not reversible")


def find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def body_is_effectively_empty(body: list[ast.stmt]) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        return False
    return True


def count_op_calls(body: list[ast.stmt]) -> int:
    count = 0
    for stmt in body:
        for node in ast.walk(stmt):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "op"
            ):
                count += 1
    return count


def is_merge_migration(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "down_revision"
                    and isinstance(node.value, (ast.Tuple, ast.List))
                    and len(node.value.elts) >= 2
                ):
                    return True
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "down_revision"
            and isinstance(node.value, (ast.Tuple, ast.List))
            and len(node.value.elts) >= 2
        ):
            return True
    return False


def has_intentional_empty_marker(body: list[ast.stmt]) -> bool:
    if not body:
        return False
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        doc = first.value.value.lower()
        return any(marker in doc for marker in INTENTIONAL_MARKERS)
    return False


def check_migration(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return [f"could not read file: {exc}"]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    if is_merge_migration(tree):
        return []
    upgrade = find_function(tree, "upgrade")
    if upgrade is None:
        return ["missing upgrade() function"]
    if (body_is_effectively_empty(upgrade.body) or count_op_calls(upgrade.body) == 0) and not (
        has_intentional_empty_marker(upgrade.body)
    ):
        return [
            "upgrade() has no op.* calls (empty migration); add a docstring marker like 'intentional' "
            "if this is deliberate"
        ]
    return []


def main(versions_dir: Path = VERSIONS_DIR) -> int:
    if not versions_dir.is_dir():
        print(f"ERROR: versions directory not found: {versions_dir}", file=sys.stderr)
        return 1
    files = sorted(p for p in versions_dir.glob("*.py") if p.name != "__init__.py")
    if not files:
        print(f"No migrations found in {versions_dir} -- nothing to check.")
        return 0
    problems = [(p, issues) for p in files if (issues := check_migration(p))]
    if not problems:
        print(f"OK: all {len(files)} migrations have non-empty bodies.")
        return 0
    print("FAIL: empty Alembic migration(s) detected.\n")
    for path, issues in problems:
        print(f"  {path.name}")
        for issue in issues:
            print(f"    - {issue}")
    print()
    print(EMPTY_MIGRATION_HINT)
    return 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else VERSIONS_DIR))
