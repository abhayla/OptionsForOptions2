"""#633 round 2: the Compare route reads guards for the SAME strategy type T-19 resolves its playbook from.

Class: callers of ``adjustment_check.strategy_type`` that pass ``listed=None`` while a market context exists read no
strike gap, so the type is None and ``resolve`` finds only the strategy's own plan, never the active playbook of its
type. Population: read_guards (was None), routes/adjustment_check, adjustment_history, adjustment_plan, playbooks x2,
background: all others already pass the instrument listing.
"""
from __future__ import annotations

import datetime
import sys
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_adjustment_approaches_route as rt
from ofo.settings import calc
from ofo.settings import defaults as settings_defaults
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app import scenario_mode
from ofo_app.routes import adjustment as route
from ofo_app.routes import outcome


class _Session:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def _capture(monkeypatch) -> list:
    seen: list = []

    async def fake_resolve(_conn, _user, _sid, stype):
        seen.append(stype)
        return check.Resolved("active", {"guards": {"hide_oi_below": 1}}, 1, "active", False)

    monkeypatch.setattr(readers, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(readers, "current_user_ref", lambda: "u")
    monkeypatch.setattr(check, "resolve", fake_resolve)
    return seen


def _position_and_listing(sid: str = "ADJ-50"):
    sc = rt.load(sid)
    scn = scenario_mode.load(sid)
    return rt.tracked_of(sc).position, D(sc["market"]["spot"]), scn.provider.instrument_master()


@pytest.mark.asyncio
async def test_read_guards_resolves_the_type_of_the_strategy_from_the_listing(monkeypatch):
    seen = _capture(monkeypatch)
    position, spot, listed = _position_and_listing()
    guards = await readers.read_guards(72, position, spot, listed)
    assert seen == ["ic"] and guards == {"hide_oi_below": 1}  # ADJ-50 is the "ic" type


@pytest.mark.asyncio
async def test_without_the_listing_the_type_is_unknown_the_old_behaviour(monkeypatch):
    """Discrimination: this is what the route got before (listed=None): type None, so no active playbook."""
    seen = _capture(monkeypatch)
    position, spot, _ = _position_and_listing()
    await readers.read_guards(72, position, spot, None)
    assert seen == [None]


def test_the_route_hands_the_guards_reader_the_market_context_listing():
    sc = rt.load("ADJ-50")
    listing = scenario_mode.load("ADJ-50").provider.instrument_master()
    got: list = []

    async def guards(_sid, _position, _spot, listed):
        got.append(listed)

    client = rt.client_for(sc)
    client.app.dependency_overrides[route.get_guards_reader] = lambda: guards
    ctx = SimpleNamespace(provider=SimpleNamespace(instrument_master=lambda: listing),
                          clock=lambda: datetime.datetime.fromisoformat(sc["clock"]["ist"]),
                          feed_windows=calc.feed_windows(settings_defaults()))
    client.app.dependency_overrides[outcome.get_market_context] = lambda: ctx
    rt.post(client)
    assert got and got[0] is listing  # not None while a context exists


def test_listed_of_is_none_without_a_context():
    assert check.listed_of(None) is None

