"""REQ-118 AC-3 (W-138): a user action refused because Zerodha is busy shows "Zerodha is busy - try again in a moment"
(its one home: ``ofo.errors.templates.ZERODHA_BUSY_TEXT``), never the generic "could not confirm your connection"
text and never a figure. One test per caller group; the limiter's own answer states (slot / busy wait / 429 after
retries / timeout / write refused) are proven at the door in ``test_rate_limit_door.py``."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from ofo.errors import render
from ofo.errors.templates import ZERODHA_BUSY_TEXT
from ofo.execution.basket import _decide_margin
from ofo_app.kite_margin import KiteMarginError, margin_verdict
from ofo_app.kite_reads import KiteReadError
from ofo_app.routes import execute as execute_route
from ofo_app.routes import execution_return as return_route
from ofo_app.routes.strategies import StrategyRefused

BUSY_READ = KiteReadError("kite_read_busy")


class _BusyReads:
    def fetch_orders(self):
        raise BUSY_READ

    fetch_trades = fetch_positions = fetch_orders


def _text(refused: StrategyRefused) -> str:
    return refused.message.what_happened


def test_the_busy_text_is_the_requirements_words_and_has_a_gate_template() -> None:
    assert ZERODHA_BUSY_TEXT == "Zerodha is busy - try again in a moment"
    message = render("gate_zerodha_busy")
    assert message.what_happened == ZERODHA_BUSY_TEXT
    assert message.what_happened != render("gate_broker_unconfirmed").what_happened


async def test_execute_route_busy_orders_read_is_the_busy_text_not_a_broken_connection() -> None:
    req = SimpleNamespace(session=SimpleNamespace(reads=_BusyReads()), strategy_id=1, db=None, user_ref="u")
    with pytest.raises(StrategyRefused) as refused:
        await execute_route._reserve_number(req)
    assert _text(refused.value) == ZERODHA_BUSY_TEXT


async def test_execute_route_a_failed_but_not_busy_read_stays_the_connection_text() -> None:
    class Down(_BusyReads):
        def fetch_orders(self):
            raise KiteReadError("kite_read_unavailable")

    req = SimpleNamespace(session=SimpleNamespace(reads=Down()), strategy_id=1, db=None, user_ref="u")
    with pytest.raises(StrategyRefused) as refused:
        await execute_route._reserve_number(req)
    assert _text(refused.value) == render("gate_broker_unconfirmed").what_happened


def test_return_route_busy_read_is_the_busy_text() -> None:
    req = SimpleNamespace(session=SimpleNamespace(reads=_BusyReads()))
    with pytest.raises(StrategyRefused) as refused:
        return_route._read_zerodha(req, catalogue=None)
    assert _text(refused.value) == ZERODHA_BUSY_TEXT


class _BusyMargin:
    def fetch_available_funds(self):
        raise KiteMarginError("kite_margin_busy")

    def fetch_basket_margin(self, orders):
        raise KiteMarginError("kite_margin_busy")

    available_funds = fetch_available_funds

    def zerodha_required(self, orders):
        raise KiteMarginError("kite_margin_busy")


def test_busy_margin_read_blocks_the_gate_with_the_busy_text_and_no_figure() -> None:
    verdict = margin_verdict(_BusyMargin(), [])
    assert verdict.allowed is False and verdict.available is None and verdict.required is None
    assert verdict.message is not None and verdict.message.what_happened == ZERODHA_BUSY_TEXT


def test_busy_margin_read_while_building_the_basket_blocks_with_the_busy_text() -> None:
    verdict = _decide_margin(_BusyMargin(), ())
    assert verdict.allowed is False and verdict.message.what_happened == ZERODHA_BUSY_TEXT


def test_an_unreadable_margin_that_is_not_busy_keeps_the_could_not_confirm_text() -> None:
    class Down(_BusyMargin):
        def fetch_available_funds(self):
            raise KiteMarginError("kite_margin_unavailable")

    verdict = margin_verdict(Down(), [])
    assert verdict.message.what_happened == render("gate_margin_unconfirmed").what_happened
    assert verdict.required is None
