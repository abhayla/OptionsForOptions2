"""REQ-081 (W-154) wiring: the money figures on the REST outcome and the live push, from the recorded Zerodha funds.

Core: a CHECKED margin (the recorded funds 671.50) puts the funds share on the summary as strings, one door for the REST
answer and the live push; every other margin state leaves it null while the rupee figures stay.
Proof: test_route_carries_the_money_figures_as_strings (expected percentages are hand divisions of the replay's
before-charges maximums 4754.75 and 8245.25 by 671.50).
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.outcome.serialize import outcome_to_dict  # noqa: E402
from ofo.outcome.service import MARGIN, Outcome, OutcomeState  # noqa: E402
from ofo_app import outcome_margin  # noqa: E402
from ofo_app.live_push import ChannelClosed, LiveFeed, StrategyPush  # noqa: E402
from ofo_app.routes.outcome import MarketContext  # noqa: E402
from test_outcome_margin import (  # noqa: E402
    CHECKED_AT,
    RATE,
    VALUATION,
    Mono,
    Transport,
    _body,
    _post,
    _recorded_orders,
    source,
)
from test_strategy_live_push import FakeChannel, held_replay, settle  # noqa: E402

PROFIT_TEXT, LOSS_TEXT = "708% of funds", "1228% of funds"  # 4754.75 / 671.50 = 708.1 ; 8245.25 / 671.50 = 1227.9
MONEY_KEYS = ("net_premium", "funds_share", "reward_risk", "risk_reward", "time_value", "intrinsic_value")


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _no_float(node) -> None:
    assert not isinstance(node, float)
    if isinstance(node, dict):
        for v in node.values():
            _no_float(v)
    elif isinstance(node, list):
        for v in node:
            _no_float(v)


async def test_route_carries_the_money_figures_as_strings(replayed, monkeypatch) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(Transport()))
    out = json.loads(resp.text, parse_float=lambda text: pytest.fail(f"float in the JSON: {text}"))
    s = out["summary"]
    share = s["funds_share"]
    assert (share["funds"], share["max_profit_percent"], share["max_loss_percent"]) == ("671.50", "708", "1228")
    assert (share["max_profit_text"], share["max_loss_text"]) == (PROFIT_TEXT, LOSS_TEXT)
    assert share["read_at"] is not None and CHECKED_AT.isoformat().replace("+00:00", "") in share["read_at"]
    assert (s["reward_risk"], s["risk_reward"]) == ("0.58", "1.73")
    net = s["net_premium"]
    assert isinstance(net["amount"], str) and net["side"] in ("get", "pay") and net["reason"] is None
    assert all(isinstance(s[k], str) for k in ("time_value", "intrinsic_value", "reward_risk", "risk_reward"))
    assert out["charges_breakdown"] is None or isinstance(out["charges_breakdown"]["total"], str)
    _no_float(out)


@pytest.mark.parametrize("status", [HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.TOO_MANY_REQUESTS])
async def test_unreadable_margin_leaves_the_share_null_and_the_rupee_figures(replayed, monkeypatch, status) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(Transport(status=status)))
    s = resp.json()["summary"]
    assert s["funds_share"] is None and s["max_loss"] == "8245.25" and s["max_profit"] == "4754.75"


async def test_no_session_and_no_provider_carry_no_funds_share(replayed) -> None:
    [resp] = await _post(_body(replayed), None, source(Transport()))
    out = resp.json()
    assert out["margin"]["state"] == "NOT_AVAILABLE_YET"
    assert out["summary"] is None or out["summary"]["funds_share"] is None


async def test_a_failed_read_is_never_replaced_by_an_older_one_before_the_retry_bound(replayed, monkeypatch) -> None:
    """AC-10: after a failed read no percentage is shown until the retry bound passes and Zerodha is read again."""
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    t, mono = Transport(status=HTTPStatus.SERVICE_UNAVAILABLE), Mono()
    src = source(t, monotonic=mono)
    [first] = await _post(_body(replayed), replayed, src)
    assert first.json()["summary"]["funds_share"] is None
    t.status = HTTPStatus.OK  # Zerodha recovers, but the bound has not passed: no new read, still no share
    calls = len(t.calls)
    [again] = await _post(_body(replayed), replayed, src)
    assert again.json()["summary"]["funds_share"] is None and len(t.calls) == calls
    mono.now += outcome_margin.RETRY_SECONDS  # the bound passed: Zerodha is read again, the share is that fresh read
    [fresh] = await _post(_body(replayed), replayed, src)
    share = fresh.json()["summary"]["funds_share"]
    assert len(t.calls) > calls and share["funds"] == "671.50"


async def test_live_push_and_rest_carry_identical_money_fields(monkeypatch) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    provider, clock, items = new_provider()
    held_replay(provider, clock, items)
    feed = LiveFeed(MarketContext(provider, lambda: VALUATION, RATE), FanOut(provider))
    channel, t = FakeChannel(), Transport()
    push = StrategyPush(channel, feed, monotonic=Mono(), poll=0.005, margin_source=source(t))
    task = asyncio.create_task(push.run())
    body = _body(provider)
    await channel.inbound.put(body)
    await settle()
    [rest] = await _post(body, provider, source(Transport()))
    pushed = channel.sent[0]["summary"]
    answered = rest.json()["summary"]
    assert pushed["funds_share"] is not None
    assert {k: pushed[k] for k in MONEY_KEYS} == {k: answered[k] for k in MONEY_KEYS}
    assert channel.sent[0].get("charges_breakdown") == rest.json().get("charges_breakdown")
    await channel.inbound.put(ChannelClosed)
    await task


def test_refused_and_not_connected_answers_carry_no_money_block() -> None:
    out = Outcome(OutcomeState.NOT_CONNECTED, "NIFTY", None, None, (), MARGIN)
    body = outcome_to_dict(out)
    assert body["summary"] is None and body["charges_breakdown"] is None
