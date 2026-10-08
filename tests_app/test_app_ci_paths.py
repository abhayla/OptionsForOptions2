"""The app CI workflow runs whenever a backend package the app tests import changes.

Class: a CI workflow path-filtered to one layer never runs when only a layer it imports changes (finding
ci-path-filter-misses-dependency-change). W-060 changed backend/ofo/ only, and the app suite did not run.
"""
from __future__ import annotations

import ast
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "app-tests.yml"
BACKEND = ROOT / "backend"


def _backend_packages() -> set[str]:
    return {p.name for p in BACKEND.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def _imported_backend_packages() -> set[str]:
    """Top-level backend packages imported by any module under tests_app/ or backend/ofo_app/."""
    known = _backend_packages()
    found: set[str] = set()
    for base in (ROOT / "tests_app", BACKEND / "ofo_app"):
        for path in base.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    found |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
    return found & known


def _paths(event: str) -> list[str]:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = doc.get(True, doc.get("on"))  # PyYAML reads the bare key `on` as boolean True
    return triggers[event]["paths"]


def test_the_app_tests_import_both_backend_layers() -> None:
    assert _imported_backend_packages() >= {"ofo", "ofo_app"}


def test_every_imported_backend_package_is_covered_by_the_push_and_pull_request_paths() -> None:
    for event in ("push", "pull_request"):
        paths = _paths(event)
        for package in sorted(_imported_backend_packages()):
            assert f"backend/{package}/**" in paths, f"{event} paths of app-tests.yml miss backend/{package}/**"
