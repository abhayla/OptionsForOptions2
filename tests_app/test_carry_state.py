"""GC-IC1 1b screen / worker parity (pure, no DB): ``adjustment_check.with_carry`` is the ONE function that fills the
carry inputs, called by ``state_of`` for the screen and for the worker (``background_state`` -> ``state_of``). It sets
today's carry day kinds always and the gap figures only when a carry rule is due, from ``carry_model`` (the market
read's forward and leg IVs) through ``ofo.adjustment.carry.carry_figures``."""
from __future__ import annotations

import dataclasses
import datetime
import inspect
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.adjustment import carry
from ofo.adjustment import playbook_eval as pe
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app import background

BODY = {"day_rules": [{"on": True, "when": "beforeWeekend", "at": "15:00", "action": 0}]}


def _market(now: datetime.datetime) -> SimpleNamespace:
    return SimpleNamespace(now=now, forward_model=None, leg_ivs={}, chain=())


def _tracked() -> SimpleNamespace:
    return SimpleNamespace(position=SimpleNamespace(legs=()), booked=D("0"))


def _state(hhmm: str, margin: D | None = None) -> pe.StrategyState:
    return pe.StrategyState(expiry_kind="weekly", days_left=4, hhmm=hhmm, margin=margin)


def test_state_of_and_the_worker_both_go_through_with_carry():
    assert "with_carry(" in inspect.getsource(check.state_of)
    assert "check.state_of(" in inspect.getsource(background.background_state)


def test_friday_1500_fills_days_and_figures_through_carry_figures():
    now = datetime.datetime(2026, 10, 30, 15, 0, tzinfo=IST)
    got = check.with_carry(_state("15:00", D("98000")), BODY, _tracked(), _market(now))
    assert got.carry_days == frozenset({"beforeWeekend"})
    assert got.carry == carry.carry_figures(None, D("0"), D("98000"), now)  # no forward: figures not known
    assert got.carry.gap_reason == carry.CARRY_GAP_UNKNOWN and got.carry.margin == D("98000")


def test_before_the_time_or_another_day_computes_no_figures():
    fri = datetime.datetime(2026, 10, 30, 14, 59, tzinfo=IST)
    assert check.with_carry(_state("14:59"), BODY, _tracked(), _market(fri)).carry is None
    wed = datetime.datetime(2026, 10, 28, 15, 0, tzinfo=IST)
    got = check.with_carry(_state("15:00"), BODY, _tracked(), _market(wed))
    assert got.carry is None and got.carry_days == frozenset()


def test_carry_record_money_as_strings_and_reasons():
    figs = pe.CarryFigures(D("-1234.50"), D("-2345.60"), None, None, carry.MISSING_MARGIN,
                           datetime.datetime(2026, 11, 2, 9, 15, tzinfo=IST))
    assert check.carry_record(figs) == {"gap_pct": "2", "gap_up": "-1234.50", "gap_down": "-2345.60",
                                        "gap_reason": None, "margin": None, "margin_reason": carry.MISSING_MARGIN,
                                        "next_open": "2026-11-02T09:15:00+05:30"}
    assert check.CARRY_GAP_PCT_TEXT == carry.CARRY_GAP_PCT
    assert dataclasses.is_dataclass(figs)
