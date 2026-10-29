"""REQ-081 (W-154) wiring: the money figures on the REST outcome and the live push, from the recorded Zerodha funds.

Core: a CHECKED margin (the recorded margin needed 7065.50; ADR-207 (8): never the funds 671.50) puts the share on the
summary as strings, one door for the REST
answer and the live push; every other margin state leaves it null while the rupee figures stay.
Proof: test_route_carries_the_money_figures_as_strings (expected percentages are hand divisions of the replay's
before-charges maximums 4754.75 and 8245.25 by the margin needed 7065.50).
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from decimal import ROUND_HALF_UP, Decimal
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

# REQ-081 AC-9 (ADR-207 (8)): 4754.75 / 7065.50 = 67.30% ; 8245.25 / 7065.50 = 116.70% (of the 671.50 funds: 708 / 1228)
PROFIT_TEXT, LOSS_TEXT = "67.3% of margin needed", "116.7% of margin needed"
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
    assert (share["margin_needed"], share["max_profit_percent"], share["max_loss_percent"]) == ("7065.50", "67.3", "116.7")
    assert (share["max_profit_text"], share["max_loss_text"]) == (PROFIT_TEXT, LOSS_TEXT)
    assert share["read_at"] is not None and CHECKED_AT.isoformat().replace("+00:00", "") in share["read_at"]
    # no rate table on this route: the charges cannot be priced, so there is no ratio (REQ-081 AC-4), never 0.58/1.73
    assert (s["reward_risk"], s["risk_reward"]) == (None, None)
    assert s["reward_risk_reason"] == "the charges could not be priced, so the ratio is not shown"
    net = s["net_premium"]
    assert isinstance(net["amount"], str) and net["side"] in ("get", "pay") and net["reason"] is None
    assert all(isinstance(s[k], str) for k in ("time_value", "intrinsic_value"))
    assert out["charges_breakdown"] is None or isinstance(out["charges_breakdown"]["total"], str)
    _no_float(out)


async def test_route_carries_the_whole_rupee_display_texts(replayed, monkeypatch) -> None:
    """REQ-152 AC-1/AC-3 and REQ-153 AC-1 on the real route: the same recorded replay, the display text beside every
    exact value (4754.75 -> +4,755; 8245.25 -> U+2212 8,245; the margin figures to whole rupees, Indian grouping)."""
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(Transport()))
    out = resp.json()
    s, m = out["summary"], out["margin"]
    minus = chr(0x2212)
    assert (s["max_profit"], s["max_profit_display"]) == ("4754.75", "+4,755")
    assert (s["max_loss"], s["max_loss_display"]) == ("8245.25", f"{minus}8,245")
    assert s["net_premium"]["amount_display"] is not None and "." not in s["net_premium"]["amount_display"]
    assert s["time_value_display"].lstrip(f"+{minus}").replace(",", "").isdigit()
    assert len(s["breakevens_display"]) == len(s["breakevens"])
    for exact, shown in zip(s["breakevens"], s["breakevens_display"], strict=True):
        assert shown.split(" (")[0].replace(",", "") == str(Decimal(exact).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        assert shown.endswith("%)")
    assert (m["needed"], m["needed_display"]) == ("7065.50", "7,066")  # recorded basket + top-up; .50 rounds half-up
    assert m["available"] == "671.50" and m["available_display"] == "672"
    assert m["broker_needed_display"] == "6,409"


@pytest.mark.parametrize("status", [HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.TOO_MANY_REQUESTS])
async def test_unreadable_margin_leaves_the_share_null_and_the_rupee_figures(replayed, monkeypatch, status) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(Transport(status=status)))
    s = resp.json()["summary"]
    assert s["funds_share"] is None and s["max_loss"] == "8245.25" and s["max_profit"] == "4754.75"
    assert s["max_profit_display"] == "+4,755"  # the rupee display does not depend on the margin read
    m = resp.json()["margin"]
    assert (m["needed_display"], m["available_display"], m["broker_needed_display"]) == (None, None, None)


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
    assert len(t.calls) > calls and share["margin_needed"] == "7065.50"


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
