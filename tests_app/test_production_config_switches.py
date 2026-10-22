"""W-125 (REQ-079 AC-11, REQ-082 AC-7; serves lanes B5 / B6): production configuration never turns a held feature on.

An allow-list guard (finding guard-as-forbidden-list): the closed switch list is pinned here, the committed example
configuration is loaded as a production configuration, and every use of a held switch in backend code must name a
switch of the list through the ``ofo_app.held_switches`` module (import source, not identifier text); a name that
cannot be resolved fails.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from ofo_app import held_switches as hs

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PINNED_NAMES = ("platform_strikes", "probability_of_profit", "delayed_prices", "history_charts", "events_calendar",
                "fii_dii", "market_event_warning", "strategy_price_history")
SWITCH_MODULE = "ofo_app.held_switches"
SWITCH_FILE = "backend/ofo_app/held_switches.py"
USERS = {"held_on", "features_on"}


def _example_environment() -> dict[str, str]:
    """The committed example configuration read as KEY=VALUE lines, forced to production."""
    out: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    out["APP_ENV"] = "production"
    return out


def _imports_switch_module(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(local names bound to the module, local names bound to its held_on / features_on) by IMPORT SOURCE."""
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ofo_app":
            modules |= {a.asname or a.name for a in node.names if a.name == "held_switches"}
        elif isinstance(node, ast.ImportFrom) and node.module == SWITCH_MODULE:
            functions |= {a.asname or a.name for a in node.names if a.name in USERS}
        elif isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name == SWITCH_MODULE}
    return modules, functions


def _problems(rel: str, source: str) -> list[str]:
    """The allow-list rules for one module: a listed switch name by import source; no other module reads OFO_HELD_*."""
    found: list[str] = []
    tree = ast.parse(source)
    if rel != SWITCH_FILE:
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "OFO_HELD" in node.value:
                found.append(f"{rel}:{node.lineno} reads a held-switch variable outside the one function")
    modules, functions = _imports_switch_module(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        via_module = (isinstance(f, ast.Attribute) and f.attr in USERS and isinstance(f.value, ast.Name)
                      and f.value.id in modules)
        if not (via_module or (isinstance(f, ast.Name) and f.id in functions)):
            continue
        name = f.attr if isinstance(f, ast.Attribute) else f.id
        if name == "features_on":
            continue
        arg = node.args[0] if node.args else None
        ok = (isinstance(arg, ast.Constant) and arg.value in PINNED_NAMES) or (
            isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id in modules
            and getattr(hs, arg.attr, None) in PINNED_NAMES)
        if not ok:
            found.append(f"{rel}:{node.lineno} held_on() argument is not a listed switch")
    return found


def test_ac11_the_closed_list_is_exactly_the_pinned_list():
    """REQ-079 AC-11 / REQ-082 AC-7: a new switch name must be added here too (this test fails on any other)."""
    assert hs.SWITCH_NAMES == PINNED_NAMES


def test_ac11_the_production_configuration_has_every_held_feature_off():
    """AC-11 / AC-7: the committed example configuration, as production, turns no held feature on without a reference."""
    env = _example_environment()
    hs.require_valid_configuration(env)
    assert hs.features_on(env) == ()


@pytest.mark.repo_scan
def test_ac11_every_use_of_a_held_switch_names_a_listed_switch_by_import_source():
    """Allow-list scan over backend/: every held_on() names a listed switch; only held_switches.py reads OFO_HELD_*."""
    problems: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        problems += _problems(path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf8"))
    assert problems == []


def test_ac11_the_scan_rejects_an_unlisted_name_an_unresolved_argument_and_a_foreign_read():
    """Mutation: the scan's rules go red for an unlisted name, an unresolved argument and a foreign OFO_HELD_ read."""
    base = "from ofo_app import held_switches\n"
    assert _problems("backend/x.py", base + "held_switches.held_on('platform_strike')\n")
    assert _problems("backend/x.py", base + "held_switches.held_on(name)\n")
    assert _problems("backend/x.py", base + "import os\nos.environ.get('OFO_HELD_X')\n")
    assert _problems("backend/x.py", base + "held_switches.held_on(held_switches.PLATFORM_STRIKES)\n") == []
    assert _problems(SWITCH_FILE, "import os\nos.environ.get('OFO_HELD_X')\n") == []
