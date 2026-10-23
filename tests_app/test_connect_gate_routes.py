"""REQ-015 AC-2 (W-130 fix round 1): the Execute and return routes answer the AC-2 sentence when there is NO stored
Zerodha session, and keep ``gate_broker_unconfirmed`` only for a session that exists but cannot be read.

No database: the strategy load is stubbed, so the first thing under test is the session branch itself."""
from __future__ import annotations

import datetime

import pytest
from ofo.errors import render
from ofo_app import live_market
from ofo_app.routes import execute as execute_route
from ofo_app.routes import execution_return as return_route
from ofo_app.routes.strategies import StrategyRefused

AC2_SENTENCE = ("Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, "
                "check margin and prepare/execute your strategy.")
NOW = datetime.datetime(2026, 10, 22, 11, 0, tzinfo=datetime.UTC)


class _Db:
    async def rollback(self) -> None:
        pass

    async def commit(self) -> None:
        pass


async def _no_load(*_a, **_k):
    return object()


def _what(exc: StrategyRefused) -> str:
    return exc.message.what_happened


async def test_execute_without_a_stored_session_asks_with_the_ac2_sentence(monkeypatch):
    monkeypatch.setattr(execute_route.store, "load", _no_load)
    with pytest.raises(StrategyRefused) as err:
        await execute_route.execute_strategy(1, execute_route.ExecuteIn(action="ENTRY"), None, None,
                                             lambda: NOW, _Db(), "owner", None)
    assert _what(err.value) == AC2_SENTENCE


async def test_return_without_a_stored_session_asks_with_the_ac2_sentence(monkeypatch):
    monkeypatch.setattr(return_route.store, "load", _no_load)
    with pytest.raises(StrategyRefused) as err:
        await return_route.return_from_kite(1, None, None, _Db(), "owner")
    assert _what(err.value) == AC2_SENTENCE


async def test_a_stored_session_that_cannot_be_read_stays_unconfirmed(monkeypatch):
    async def broken():
        raise RuntimeError("decrypt failed")

    monkeypatch.setattr(live_market, "owner_margin_client", broken)
    with pytest.raises(StrategyRefused) as err:
        await execute_route.get_kite_session()
    assert _what(err.value) == render("gate_broker_unconfirmed").what_happened
    assert "decrypt" not in _what(err.value)


async def test_no_session_at_all_is_none_not_a_refusal(monkeypatch):
    async def none():
        return None

    monkeypatch.setattr(live_market, "owner_margin_client", none)
    monkeypatch.setattr(live_market, "owner_kite_reads", none)
    assert await execute_route.get_kite_session() is None
