"""GC-IC1 step 10 fixes (W-205 AC-2, W-211 AC-4), pure, no DB.

1. ``adjustment_check.resolve``: ``draft`` is a property of SYSTEM playbooks only (REQ-158 AC-2).
2. The carry check's gap figure is read from the settings registry (``other.carry_gap_percent``), never typed
   in code (REQ-167 AC-1/AC-4, ADR-222 (1)); a missing value fails closed with a named reason, never a default."""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.adjustment import carry
from ofo.settings import calc as settings_calc
from ofo.settings import defaults, registry
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app import playbook_store

NOW = datetime.datetime(2026, 10, 30, 15, 0, tzinfo=IST)


def _resolve(monkeypatch, *, plan):
    async def plan_for(*_a):
        return plan

    async def active_for(*_a):  # ADR-330 (11): never consulted any more
        raise AssertionError("the active playbook must not be read")

    async def saved_before(*_a):
        return False
    monkeypatch.setattr(playbook_store, "plan_for", plan_for)
    monkeypatch.setattr(playbook_store, "active_for", active_for)
    monkeypatch.setattr(check, "plan_saved_before_adr247", saved_before)
    return asyncio.run(check.resolve(None, "u", 1, "iron_condor"))


def test_a_plan_is_never_a_draft_and_has_no_system_status(monkeypatch):
    """REQ-158 AC-2 under ADR-330 (11): ``draft`` / ``status`` belong to system playbooks, which are no longer a
    source of watching; the strategy's own plan resolves as source ``plan``, draft False, status None."""
    got = _resolve(monkeypatch, plan=SimpleNamespace(body={"x": 1}, playbook_id=7))
    assert (got.source, got.draft, got.status, got.is_system, got.playbook_id) == ("plan", False, None, False, 7)


def test_no_plan_resolves_to_none_whatever_playbook_is_active(monkeypatch):
    got = _resolve(monkeypatch, plan=None)
    assert (got.source, got.body, got.playbook_id, got.draft, got.status) == ("none", None, None, False, None)


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
