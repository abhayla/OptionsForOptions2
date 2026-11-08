"""Structural rule (contract "Your adjustment settings" step 3; the class "a caller bypasses the resolver" recurred in
steps 1 and 2): no route reads a covered setting's value except through ``ofo_app.settings_in_force`` (or the
resolver functions step 1 / 2 already route through, ``adjustment_check.basis_in_force``).

The scan fails when a route module under ``backend/ofo_app/routes/`` contains:
- a covered key's text as a string literal (``"other.carry_gap_percent"``, ``"orders.default_lots"``, ...), or a
  ``layers.<KEY constant>`` index;
- a call into the resolver's internals (``layers.resolve(``, ``user_layer(``, ``admin_of(``, ``carry_gap_of(``,
  ``roll_basis_of(``), or a read of the user store's layers (``.own[`` / ``.own.get(`` / ``.admin[`` /
  ``.admin.get(``).
Allowed: ``adjustment_preferences.py`` writes and lists the user's own values (the user layer's store route).
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest
from ofo_app import settings_in_force as sif

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTES = ROOT / "backend" / "ofo_app" / "routes"
ALLOWED = {"adjustment_preferences.py"}
_CALLS = re.compile(r"\b(layers\.resolve|user_layer|admin_of|carry_gap_of|roll_basis_of)\s*\(|"
                    r"\.(own|admin)\s*(\[|\.get\s*\()|\blayers\.(CARRY_GAP_PERCENT|ROLL_BASIS)\b")


def violations(source: str, keys: tuple[str, ...]) -> list[str]:
    """Every bypass in one module's source (the scanner, also run on seeded sources below)."""
    found = [m.group(0) for m in _CALLS.finditer(source)]
    covered = set(keys)
    found.extend(repr(node.value) for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in covered)
    return found


def test_no_route_reads_a_covered_setting_outside_the_one_read():
    keys = sif.covered_keys()
    bad = {p.name: v for p in sorted(ROUTES.glob("*.py")) if p.name not in ALLOWED
           and (v := violations(p.read_text(encoding="utf-8"), keys))}
    assert bad == {}, f"read these settings through ofo_app.settings_in_force.in_force: {bad}"


def test_the_plan_route_reads_the_one_function():
    assert "in_force_mod.in_force(" in (ROUTES / "adjustment_plan.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("seeded", [
    'x = values["other.carry_gap_percent"]',
    "x = layers.resolve(KEY, a, b, c)",
    "x = check.admin_of(v, k)",
    "x = user_values.own.get(k)",
    "x = user_values.admin[k]",
    "x = v[layers.CARRY_GAP_PERCENT]",
])
def test_the_scanner_sees_each_bypass_shape(seeded):
    assert violations(seeded, sif.covered_keys())


def test_the_scanner_passes_the_one_read():
    assert violations("found = in_force_mod.in_force(user_values, resolved, money)", sif.covered_keys()) == []
