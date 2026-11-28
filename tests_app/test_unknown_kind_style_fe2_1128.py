"""Lane FE2 (28 Nov 2026), item 5 (issue #865): the timing style the worker uses when the expiry kind is not known is
pinned by a test. Spec basis: ADR-330 (44), (47); REQ-115 AC-4; Lane J3 item 1 ("Decision recorded: the timing style is
intraday, not a guessed weekly or monthly row").

Behaviour stated: a trade whose expiry kind is not known (no days to expiry) and that has NO pin is gated with the
INTRADAY style (the fastest: candle 1 minute) and stays watched; its rules that need the kind answer "not checked".
A pin is never replaced by that fallback (``test_a_refused_pin_is_never_replaced_by_the_unknown_kind_fallback``).
A trade whose kind IS known keeps its own style.
"""
from __future__ import annotations

import dataclasses

from ofo_app import background
from test_background_cycle import FIRST_ID, Calls, FakeGate, Prov, _watched, _worker, scn  # noqa: F401 - fixture
from test_worker_j3 import _state_without_kind

INTRADAY = "intraday"


async def test_an_unknown_expiry_kind_without_a_pin_is_gated_with_the_intraday_style(scn, monkeypatch):  # noqa: F811
    _state_without_kind(monkeypatch)
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, [dataclasses.replace(x) for x in _watched(scn)], now, calls, gate_store=FakeGate())
    await w.cycle()
    print("STYLE", w._style.get(FIRST_ID), "STATUS", w.status.get(FIRST_ID))
    assert background.UNKNOWN_KIND_TIMING_STYLE == INTRADAY
    assert w._style[FIRST_ID] == INTRADAY
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE


async def test_a_known_expiry_kind_keeps_its_own_style_not_the_fallback(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls, gate_store=FakeGate())
    await w.cycle()
    print("STYLE", w._style.get(FIRST_ID))
    assert calls.states[0][1].days_left is not None
    assert w._style[FIRST_ID] == "weekly"  # the scenario trade expires in a weekly row: its own style
