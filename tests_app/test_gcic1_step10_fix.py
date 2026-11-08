"""GC-IC1 step 10 fixes (W-205 AC-2, W-211 AC-4), pure, no DB.

1. ``adjustment_check.resolve``: ``draft`` is a property of SYSTEM playbooks only (REQ-158 AC-2).
2. The carry check's gap figure is read from the settings registry (``other.carry_gap_percent``), never typed
   in code (REQ-167 AC-1/AC-4, ADR-222 (1)); a missing value fails closed with a named reason, never a default."""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import carry
from ofo.settings import calc as settings_calc
from ofo.settings import defaults, registry
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app import playbook_store

NOW = datetime.datetime(2026, 10, 30, 15, 0, tzinfo=IST)


def _resolve(monkeypatch, *, is_system: bool, status: str):
    async def plan_for(*_a):
        return None

    async def active_for(*_a):
        return SimpleNamespace(is_system=is_system, status=status, body={"x": 1}, id=7)
    monkeypatch.setattr(playbook_store, "plan_for", plan_for)
    monkeypatch.setattr(playbook_store, "active_for", active_for)
    return asyncio.run(check.resolve(None, "u", 1, "iron_condor"))


@pytest.mark.parametrize(("is_system", "status", "draft"), [
    (False, "draft", False),     # the user's OWN copy: the column defaults to 'draft', it is not a draft
    (False, "approved", False),
    (True, "draft", True),
    (True, "approved", False),
])
def test_draft_is_a_property_of_system_playbooks_only(monkeypatch, is_system, status, draft):
    got = _resolve(monkeypatch, is_system=is_system, status=status)
    assert got.draft is draft
    assert got.status == (status if is_system else None)


def test_carry_gap_follows_a_changed_setting_with_no_restart():
    assert "other.carry_gap_percent" in registry()
    values = defaults()
    assert settings_calc.carry_gap_percent(values) == D("2")
    spot = D("24000")
    assert carry.gap_levels(spot, D("2")) == (D("24480.00"), D("23520.00"))
    three = settings_calc.carry_gap_percent({**values, "other.carry_gap_percent": D("3")})
    assert carry.gap_levels(spot, three) == (D("24720.00"), D("23280.00"))


def test_carry_gap_missing_fails_closed_with_a_named_reason():
    figs = carry.carry_figures(None, D("0"), D("1"), NOW, gap_pct=None)
    assert figs.up is None and figs.down is None and figs.gap_reason == carry.CARRY_GAP_UNKNOWN
    assert figs.gap_pct is None
    assert check.carry_record(figs)["gap_pct"] is None


def test_no_typed_gap_figure_remains():
    assert not hasattr(carry, "CARRY_GAP_PCT") and not hasattr(check, "CARRY_GAP_PCT_TEXT")
