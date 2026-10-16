"""ADR-099: Zerodha's margin on the outcome answer, from the REAL recorded 2026-10-16 basket reply (NIFTY long strangle,
Zerodha final 6409, required 7065.50 after the ADR-094 top-up) through a fake transport. No network, no database.

The reviewer's checklist, one test each: Decimal end to end and a 2-decimal string out; the cache key is the plan (a
tick or a re-captured time never refetches, a changed quantity / price / side refetches exactly once), per user,
bounded; no session = the login text and no Kite call; a Kite failure or timeout = the could-not-read text with the
outcome still COMPUTED; the read runs off the event-loop thread; catalogue wording only.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import sys
import threading
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo.errors.explanations import render_explanation  # noqa: E402
from ofo.instruments.parser import zerodha_listed  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.outcome.service import MARGIN  # noqa: E402
from ofo.outcome.snapshot import contract_id  # noqa: E402
from ofo_app import outcome_margin  # noqa: E402
from ofo_app.kite_margin import BasketOrder, KiteMargin  # noqa: E402
from ofo_app.outcome_margin import OutcomeMargin, PlannedOrderIn, margin_answer  # noqa: E402

STRANGLE = json.loads((ROOT / "tests/fixtures/kite_margins/basket-2026-10-16-long-strangle-bump5.json")
                      .read_text(encoding="utf-8"))
BASKET_TEXT = json.dumps(STRANGLE["reply"])
#: equity.net in the recorded SHAPE (tests_app/test_kite_margin_client.py funds_text); 671.50 is ADR-099's real case
FUNDS_TEXT = '{"status": "success", "data": {"equity": {"enabled": true, "net": 671.5}}}'
CHECKED_AT = datetime.datetime(2026, 10, 16, 6, 38, 52, tzinfo=datetime.timezone.utc)  # 12:08:52 IST
OWNER = "owner"
VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")


def _listed(symbol: str, token: int, strike: str, kind: str):
    return zerodha_listed(instrument_token=token * 10, exchange_token=token, tradingsymbol=symbol, name="NIFTY",
                          expiry=datetime.date(2026, 10, 19), strike=Decimal(strike), tick_size=Decimal("0.05"),
                          lot_size=65, instrument_type=kind, segment="NFO-OPT", exchange="NFO")


CE = _listed("NIFTY26O1923250CE", 61001, "23250", "CE")
PE = _listed("NIFTY26O1922950PE", 61002, "22950", "PE")
CE_ID, PE_ID = contract_id(CE), contract_id(PE)
PROVIDER = SimpleNamespace(instrument_master=lambda: [CE, PE])
CTX = SimpleNamespace(provider=PROVIDER)


def plan(ce_lots=1, ce_price="45.55", ce_side="BUY") -> list[PlannedOrderIn]:
    """The recorded request: BUY 65 CE @ 45.55 + BUY 65 PE @ 63.15 (one lot of 65 each)."""
    return [PlannedOrderIn(CE_ID, ce_side, ce_lots, Decimal(ce_price)), PlannedOrderIn(PE_ID, "BUY", 1, Decimal("63.15"))]


class Transport:
    """Replays the recorded replies by path; counts every call and the thread it ran on."""

    def __init__(self, status: int = 200, delay: float = 0.0) -> None:
        self.status, self.delay, self.calls, self.threads = status, delay, [], []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        self.threads.append(threading.get_ident())
        if self.delay:
            time.sleep(self.delay)
        if self.status != 200:
            return self.status, '{"status": "error", "error_type": "NetworkException"}'
        return 200, (FUNDS_TEXT if url.endswith("/user/margins") else BASKET_TEXT)

    def baskets(self) -> int:
        return sum(1 for _m, url, _b in self.calls if "/margins/basket" in url)


class Mono:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def source(transport, session=b"s1", **kw) -> OutcomeMargin:
    async def open_client():
        return KiteMargin(api_key="key", access_token="tok-SECRET", transport=transport)

    return OutcomeMargin(lambda: session, open_client, clock=lambda: CHECKED_AT, **kw)


# ---- the core proof -----------------------------------------------------------------------------------------------

async def test_core_needed_is_the_recorded_required_total_and_available_the_funds() -> None:
    t = Transport()
    m = await margin_answer(source(t), CTX, OWNER, plan())
    assert m.state == "CHECKED"
    assert m.needed == Decimal("7065.50") and type(m.needed) is Decimal
    assert m.available == Decimal("671.50") and type(m.available) is Decimal
    assert m.checked_at == CHECKED_AT
    assert str(m.reason) == ("Margin from Zerodha for these planned orders: ₹7,065.50 needed, ₹671.50 available. "
                             "Checked at 12:08:52 PM.")
    sent = json.loads(next(b for _m, url, b in t.calls if "/margins/basket" in url))
    assert sent == json.loads(json.dumps(STRANGLE["request"]))  # exactly the recorded request, built from the plan


async def test_same_plan_again_makes_no_new_margin_request() -> None:
    t = Transport()
    s = source(t)
    first = await margin_answer(s, CTX, OWNER, plan())
    for _ in range(5):  # five ticks of the live push: the plan has not changed
        assert await margin_answer(s, CTX, OWNER, plan()) == first
    assert t.baskets() == 1 and len(t.calls) == 2 and s.reads == 1


@pytest.mark.parametrize("changed", [dict(ce_lots=2), dict(ce_price="46.00"), dict(ce_side="SELL")])
async def test_one_plan_change_makes_exactly_one_new_request(changed) -> None:
    t = Transport()
    s = source(t)
    await margin_answer(s, CTX, OWNER, plan())
    await margin_answer(s, CTX, OWNER, plan(**changed))
    await margin_answer(s, CTX, OWNER, plan(**changed))
    assert t.baskets() == 2


async def test_cache_is_per_user_and_per_session_and_bounded() -> None:
    t = Transport()
    s = source(t, size=2)
    await margin_answer(s, CTX, OWNER, plan())
    await margin_answer(s, CTX, "another-user", plan())
    assert t.baskets() == 2
    await margin_answer(s, CTX, OWNER, plan(ce_lots=2))  # a third plan: the oldest (owner, 1 lot) is dropped
    await margin_answer(s, CTX, OWNER, plan())
    assert t.baskets() == 4
    assert len(s._cache) == 2


# ---- no session / failures -------------------------------------------------------------------------------------------

async def test_no_session_is_the_login_text_and_no_kite_call() -> None:
    t = Transport()
    for m in (await margin_answer(source(t, session=None), CTX, OWNER, plan()),
              await margin_answer(source(t), None, OWNER, plan()),
              await margin_answer(None, CTX, OWNER, plan())):
        assert m == MARGIN and str(m.reason) == "Margin from Zerodha is not shown yet; it needs your Kite login."
    assert t.calls == []


async def test_no_stored_token_is_the_login_text() -> None:
    async def none():
        return None

    m = await margin_answer(OutcomeMargin(lambda: b"s", none, clock=lambda: CHECKED_AT), CTX, OWNER, plan())
    assert m == MARGIN


async def test_a_leg_outside_the_listed_contracts_makes_no_call() -> None:
    t = Transport()
    m = await margin_answer(source(t), CTX, OWNER, [PlannedOrderIn("NSE_FO:1", "BUY", 1, Decimal("1"))])
    assert m.state == "NO_BASKET" and m.needed is None and t.calls == []
    assert str(m.reason) == str(render_explanation("outcome_margin_no_basket"))


@pytest.mark.parametrize("status", [500, 429, 400])
async def test_kite_unreadable_is_the_could_not_read_text_and_retried_only_after_the_wait(status) -> None:
    t, mono = Transport(status=status), Mono()
    s = source(t, monotonic=mono)
    m = await margin_answer(s, CTX, OWNER, plan())
    assert m.state == "UNREADABLE" and m.needed is None and m.available is None
    assert str(m.reason) == "Margin from Zerodha could not be read just now, so no margin figure is shown."
    calls = len(t.calls)
    await margin_answer(s, CTX, OWNER, plan())  # a push one second later: no new read
    assert len(t.calls) == calls
    mono.now += outcome_margin.RETRY_SECONDS
    await margin_answer(s, CTX, OWNER, plan())
    assert len(t.calls) == calls + 1  # the funds read fails first, so one call per retry


async def test_a_403_says_the_login_is_needed() -> None:
    m = await margin_answer(source(Transport(status=403)), CTX, OWNER, plan())
    assert m == MARGIN


async def test_a_slow_kite_times_out_off_the_event_loop_thread() -> None:
    t = Transport(delay=0.3)
    m = await margin_answer(source(t, timeout=0.05), CTX, OWNER, plan())
    assert m.state == "UNREADABLE"
    assert t.threads and threading.get_ident() not in t.threads  # the network read never ran on the loop's thread
    await asyncio.sleep(0.4)  # let the worker thread finish before the loop closes


async def test_the_token_never_reaches_the_log(caplog) -> None:
    await margin_answer(source(Transport(status=500)), CTX, OWNER, plan())
    assert "tok-SECRET" not in caplog.text


# ---- the REST route: the margin block on the computed answer ------------------------------------------------------

@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


CONDOR = (("NSE_FO:44624", "SELL"), ("NSE_FO:44632", "BUY"), ("NSE_FO:44604", "SELL"), ("NSE_FO:44595", "BUY"))


def _body(provider):
    return {"underlying": "NIFTY", "legs": [
        {"instrument_id": iid, "action": action, "lots": 1,
         "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
        for iid, action in CONDOR]}


async def _post(body, provider, src, n=1):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import MarketContext, get_margin_source, get_market_context

    app = create_app()
    if provider is not None:
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    app.dependency_overrides[get_margin_source] = lambda: src
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return [await ac.post("/api/strategies/outcome", json=body) for _ in range(n)]


def _recorded_orders(_provider, legs):
    """The recorded strangle request as the basket (the replay's condor contracts have no recorded basket reply); the
    first order's quantity follows the first leg's lots, so a plan change is still a different basket."""
    return tuple(BasketOrder(r["exchange"], r["tradingsymbol"], r["transaction_type"], r["product"], r["order_type"],
                             r["quantity"] * (legs[0].lots if i == 0 else 1), Decimal(str(r["price"])), r["variety"])
                 for i, r in enumerate(STRANGLE["request"]))


async def test_route_carries_the_checked_margin_as_strings_once_per_plan(replayed, monkeypatch) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    t = Transport()
    responses = await _post(_body(replayed), replayed, source(t), n=3)
    raw = responses[0].text
    out = json.loads(raw)
    assert out["state"] == "COMPUTED" and out["summary"] is not None
    assert out["margin"]["state"] == "CHECKED"
    assert out["margin"]["needed"] == "7065.50" and out["margin"]["available"] == "671.50"  # strings, 2 decimals
    assert '"needed":"7065.50"' in raw.replace(" ", "")  # a JSON string, never a JSON number
    assert datetime.datetime.fromisoformat(out["margin"]["checked_at"]) == CHECKED_AT
    assert all(json.loads(r.text)["margin"] == out["margin"] for r in responses)
    assert t.baskets() == 1  # three answers, one Zerodha read


async def test_route_unreadable_margin_keeps_the_outcome_computed(replayed, monkeypatch) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(Transport(status=503)))
    out = resp.json()
    assert out["state"] == "COMPUTED" and out["summary"]["max_loss"] is not None
    assert out["margin"]["state"] == "UNREADABLE" and out["margin"]["needed"] is None


async def test_route_without_a_provider_is_the_login_text_and_no_call(replayed) -> None:
    t = Transport()
    [resp] = await _post(_body(replayed), None, source(t))
    out = resp.json()
    assert out["margin"]["state"] == "NOT_AVAILABLE_YET" and t.calls == []


# ---- the live push: a tick re-push reads no margin --------------------------------------------------------------

async def test_live_push_ticks_reuse_the_margin_and_a_plan_change_reads_once(replayed, monkeypatch) -> None:
    from ofo.marketdata.fanout import FanOut
    from ofo_app.live_push import ChannelClosed, LiveFeed, StrategyPush
    from ofo_app.routes.outcome import MarketContext

    sys.path.insert(0, str(ROOT / "tests_app"))
    from test_strategy_live_push import FakeChannel, held_replay, settle, tick

    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    provider, clock, items = new_provider()
    held_replay(provider, clock, items)
    feed = LiveFeed(MarketContext(provider, lambda: VALUATION, RATE), FanOut(provider))
    channel, mono, t = FakeChannel(), Mono(), Transport()
    push = StrategyPush(channel, feed, monotonic=mono, poll=0.005, margin_source=source(t))
    task = asyncio.create_task(push.run())
    body = _body(provider)
    await channel.inbound.put(body)
    await settle()
    for n in range(3):  # three price ticks, each pushed a second apart
        tick(provider, "NSE_FO:44624", f"{100 + n}.05")
        mono.now += 1.0
        await settle()
    assert len(channel.sent) == 4 and all(s["margin"]["state"] == "CHECKED" for s in channel.sent)
    assert t.baskets() == 1
    changed = {**body, "legs": [{**body["legs"][0], "lots": 2}, *body["legs"][1:]]}
    await channel.inbound.put(changed)
    mono.now += 1.0
    await settle()
    assert len(channel.sent) == 5 and t.baskets() == 2
    await channel.inbound.put(ChannelClosed)
    await task
