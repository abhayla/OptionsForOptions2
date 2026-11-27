"""Lane K2 item 3 (ADR-330 (52), (58)): the REAL order door's review step calls the same lots check as the paper door
(``order_lots.check_lots``). Unit tests with fakes: nothing is ordered, no database."""
from __future__ import annotations

import datetime
import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.engine import Action
from ofo.instruments.models import InstrumentId
from ofo.settings import calc
from ofo_app import order_lots, paper_limit
from ofo_app.execute_plan import LegToPrice
from ofo_app.order_lots import LegLots
from ofo_app.routes import execute
from ofo_app.strategy_refused import StrategyRefused

IID = InstrumentId("NSE_FO", 44595)
KEY = "NSE_FO:44595"
LOT = 75


def _catalogue():
    ref = SimpleNamespace(broker_symbol="NIFTY26DEC24200CE", lot_size=LOT)
    contract = SimpleNamespace(instrument_type="CE", strike=Decimal("24200"), expiry=datetime.date(2026, 12, 1))
    return SimpleNamespace(get=lambda _i: SimpleNamespace(ref=lambda _b: ref, contract=contract))


async def _check(monkeypatch, action, lots, held_lots=0, top=100):
    async def reader(_db):
        return {calc.MAX_LOTS: Decimal(top)}
    monkeypatch.setattr(execute, "get_settings_reader", lambda: reader)
    held = {KEY: held_lots * LOT} if held_lots else {}
    await execute._refuse_lots_over_limit(SimpleNamespace(db=None), [LegToPrice(IID, action, lots * LOT, None)], held,
                                          _catalogue(), "NIFTY")


async def test_101_lots_on_an_empty_leg_is_refused_at_the_default_of_100(monkeypatch):
    with pytest.raises(StrategyRefused) as e:
        await _check(monkeypatch, Action.SELL, 101)
    assert e.value.args[0] == "paper_leg_total_over_limit"
    assert "NIFTY 1 Dec 24200 CE" in e.value.message.what_happened
    assert "101 lots" in e.value.message.what_happened


async def test_100_lots_is_accepted(monkeypatch):
    await _check(monkeypatch, Action.BUY, 100)


async def test_60_held_plus_50_more_on_the_same_leg_is_refused(monkeypatch):
    with pytest.raises(StrategyRefused) as e:
        await _check(monkeypatch, Action.BUY, 50, held_lots=60)
    assert "110 lots" in e.value.message.what_happened


async def test_an_exit_of_a_leg_held_over_a_lowered_limit_is_not_refused(monkeypatch):
    await _check(monkeypatch, Action.SELL, 150, held_lots=150, top=100)


def test_both_doors_call_the_one_function():
    assert paper_limit.check_lots is order_lots.check_lots
    assert execute.check_lots is order_lots.check_lots


def test_a_flip_long_to_short_past_the_limit_is_refused_and_a_cut_back_is_not():
    leg = LegLots("NIFTY 1 Dec 24200 CE", LOT, 60 * LOT, [-170 * LOT])  # 60 long -> 110 short
    with pytest.raises(StrategyRefused):
        order_lots.check_lots(100, [leg])
    order_lots.check_lots(100, [LegLots("NIFTY 1 Dec 24200 CE", LOT, 150 * LOT, [-50 * LOT])])


def test_the_real_door_runs_the_lots_check_in_its_review_before_the_gate():
    src = inspect.getsource(execute._execute)
    assert src.index("_refuse_lots_over_limit(") < src.index("_gate(req")


async def test_two_wanted_entries_on_one_instrument_add_up_and_a_leading_zero_held_key_still_matches(monkeypatch):
    async def reader(_db):
        return {calc.MAX_LOTS: Decimal(100)}
    monkeypatch.setattr(execute, "get_settings_reader", lambda: reader)
    two = [LegToPrice(IID, Action.BUY, 60 * LOT, None), LegToPrice(IID, Action.BUY, 50 * LOT, None)]
    with pytest.raises(StrategyRefused):
        await execute._refuse_lots_over_limit(SimpleNamespace(db=None), two, {}, _catalogue(), "NIFTY")
    exit_leg = [LegToPrice(IID, Action.SELL, 150 * LOT, None)]
    await execute._refuse_lots_over_limit(SimpleNamespace(db=None), exit_leg, {"NSE_FO:044595": 150 * LOT},
                                          _catalogue(), "NIFTY")


async def test_a_lot_size_of_zero_is_a_refusal_not_a_crash(monkeypatch):
    async def reader(_db):
        return {calc.MAX_LOTS: Decimal(100)}
    monkeypatch.setattr(execute, "get_settings_reader", lambda: reader)
    ref = SimpleNamespace(broker_symbol="X", lot_size=0)
    cat = SimpleNamespace(get=lambda _i: SimpleNamespace(ref=lambda _b: ref))
    with pytest.raises(StrategyRefused) as e:
        await execute._refuse_lots_over_limit(SimpleNamespace(db=None), [LegToPrice(IID, Action.BUY, 75, None)], {},
                                              cat, "NIFTY")
    assert e.value.args[0] == "strategy_contract_not_in_catalogue"
