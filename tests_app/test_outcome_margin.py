"""ADR-099: Zerodha's margin on the outcome answer, from the REAL recorded 2026-10-16 basket reply (NIFTY long strangle,
Zerodha final 6409, required 7065.50 after the ADR-094 top-up; REQ-055 AC-3: the two are named apart) through a fake
transport. No network, no database.

The reviewer's checklist, one test each: Decimal end to end and a 2-decimal string out; the cache key is the plan (a
tick or a re-captured time never refetches, a changed quantity / price / side refetches exactly once), per user and
session, bounded; no session = the login text and no Kite call; a Kite failure or timeout = the could-not-read text with
the outcome still COMPUTED; the read runs off the event-loop thread; catalogue wording only.
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
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.errors.explanations import render_explanation  # noqa: E402
from ofo.instruments.parser import zerodha_listed  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.outcome.service import MARGIN  # noqa: E402
from ofo.outcome.snapshot import contract_id  # noqa: E402
from ofo_app import live_market, outcome_margin  # noqa: E402
from ofo_app.kite_margin import BasketOrder, KiteMargin, KiteMarginError  # noqa: E402
from ofo_app.live_push import ChannelClosed, LiveFeed, StrategyPush  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.outcome_margin import MarginLimits, OutcomeMargin, PlannedOrderIn, margin_answer  # noqa: E402
from ofo_app.routes.outcome import MarketContext, get_margin_source, get_market_context  # noqa: E402
from test_strategy_live_push import FakeChannel, held_replay, settle, tick  # noqa: E402

STRANGLE = json.loads((ROOT / "tests/fixtures/kite_margins/basket-2026-10-16-long-strangle-bump5.json")
                      .read_text(encoding="utf-8"))
BASKET_TEXT = json.dumps(STRANGLE["reply"])
#: equity.net in the recorded SHAPE (tests_app/test_kite_margin_client.py funds_text); 671.50 is ADR-099's real case
FUNDS_TEXT = '{"status": "success", "data": {"equity": {"enabled": true, "net": 671.5}}}'
CHECKED_AT = datetime.datetime(2026, 10, 16, 6, 38, 52, tzinfo=datetime.UTC)  # 12:08:52 IST
OWNER_SESSION = ("owner", b"s1")
VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
FAKE_ACCESS = "tok-NOT-REAL-123"
LOGIN_TEXT = "Margin from Zerodha is not shown yet; it needs your Kite login."


def _listed(symbol: str, token: int, strike: str, kind: str):
    return zerodha_listed(instrument_token=token * 10, exchange_token=token, tradingsymbol=symbol, name="NIFTY",
                          expiry=datetime.date(2026, 10, 19), strike=Decimal(strike), tick_size=Decimal("0.05"),
                          lot_size=65, instrument_type=kind, segment="NFO-OPT", exchange="NFO")


CE = _listed("NIFTY26O1923250CE", 61001, "23250", "CE")
PE = _listed("NIFTY26O1922950PE", 61002, "22950", "PE")
CE_ID, PE_ID = contract_id(CE), contract_id(PE)
CTX = SimpleNamespace(provider=SimpleNamespace(instrument_master=lambda: [CE, PE]))


def plan(ce_lots=1, ce_price="45.55", ce_side="BUY") -> list[PlannedOrderIn]:
    """The recorded request: BUY 65 CE @ 45.55 + BUY 65 PE @ 63.15 (one lot of 65 each)."""
    return [PlannedOrderIn(CE_ID, ce_side, ce_lots, Decimal(ce_price)),
            PlannedOrderIn(PE_ID, "BUY", 1, Decimal("63.15"))]


class Transport:
    """Replays the recorded replies by path; counts every call and the thread it ran on."""

    def __init__(self, status: int = HTTPStatus.OK, delay: float = 0.0, slow_when: str | None = None) -> None:
        self.status, self.delay, self.calls, self.threads = status, delay, [], []
        self.slow_when = slow_when  # only a request body holding this text is delayed

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        self.threads.append(threading.get_ident())
        if self.delay and (self.slow_when is None or (body is not None and self.slow_when in body)):
            time.sleep(self.delay)
        if self.status != HTTPStatus.OK:
            return self.status, '{"status": "error", "error_type": "NetworkException"}'
        return HTTPStatus.OK, (FUNDS_TEXT if url.endswith("/user/margins") else BASKET_TEXT)

    def baskets(self) -> int:
        return sum(1 for _m, url, _b in self.calls if "/margins/basket" in url)


class Mono:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def source(transport, session=OWNER_SESSION, **kw) -> OutcomeMargin:
    async def open_client():
        return KiteMargin(api_key="key", access_token=FAKE_ACCESS, transport=transport)

    holder = session if callable(session) else (lambda: session)
    return OutcomeMargin(holder, open_client, clock=lambda: CHECKED_AT, **kw)


def _own_line(theirs: str, ours: str, have: str, where: str = "your Zerodha account", added: str = "₹656.50") -> str:
    """The catalogue sentence with an ADR-094 top-up (GC-UI D-A47): Zerodha's own figure as Zerodha's, the top-up
    named, ours as an estimate (REQ-055 AC-3). The recorded strangle's top-up is 7,065.50 - 6,409 = 656.50."""
    return (f"Zerodha's own margin figure is {theirs}; your planned entry prices are above Zerodha's, which adds about "
            f"{added}, so about {ours} is needed (an estimate); {have} is available in {where}.")


def _short_line(theirs: str, ours: str, have: str, added: str = "₹656.50") -> str:
    return _own_line(theirs, ours, have, "your account", added) + " " + SHORT_WAYS


# ---- the core proof -----------------------------------------------------------------------------------------------

async def test_core_needed_is_the_recorded_required_total_and_available_the_funds() -> None:
    t = Transport()
    m = await margin_answer(source(t), CTX, plan())
    assert m.state == "CHECKED"
    assert m.needed == Decimal("7065.50") and type(m.needed) is Decimal and str(m.needed) == "7065.50"
    assert m.available == Decimal("671.50") and type(m.available) is Decimal and str(m.available) == "671.50"
    assert m.checked_at == CHECKED_AT and m.shortfall is True  # 671.50 < 7065.50
    assert (str(m.broker_needed), str(m.reason)) == ("6409.00", _own_line("₹6,409.00", "₹7,065.50", "₹671.50"))
    sent = json.loads(next(b for _m, url, b in t.calls if "/margins/basket" in url))
    assert sent == json.loads(json.dumps(STRANGLE["request"]))  # exactly the recorded request, built from the plan


async def test_same_plan_again_makes_no_new_margin_request() -> None:
    t = Transport()
    s = source(t)
    first = await margin_answer(s, CTX, plan())
    for _ in range(5):  # five ticks of the live push: the plan has not changed
        assert await margin_answer(s, CTX, plan()) == first
    funds_and_basket = 2
    assert t.baskets() == 1 and len(t.calls) == funds_and_basket and s.reads == 1


@pytest.mark.parametrize("changed", [{"ce_lots": 2}, {"ce_price": "46.00"}, {"ce_side": "SELL"}])
async def test_one_plan_change_makes_exactly_one_new_request(changed) -> None:
    t = Transport()
    s = source(t)
    await margin_answer(s, CTX, plan())
    await margin_answer(s, CTX, plan(**changed))
    await margin_answer(s, CTX, plan(**changed))
    two_plans = 2
    assert t.baskets() == two_plans


async def test_cache_is_per_user_and_per_session_and_bounded() -> None:
    t, current = Transport(), [OWNER_SESSION]
    s = source(t, session=lambda: current[0], limits=MarginLimits(size=2))
    await margin_answer(s, CTX, plan())
    current[0] = ("another-user", b"s9")
    await margin_answer(s, CTX, plan())
    current[0] = ("owner", b"s2")  # a new login of the same user: never the old session's figures
    await margin_answer(s, CTX, plan())
    three_sessions = 3
    assert t.baskets() == three_sessions
    current[0] = OWNER_SESSION  # the oldest entry was dropped (size 2): read again
    await margin_answer(s, CTX, plan())
    assert t.baskets() == three_sessions + 1
    assert len(s._cache) == MarginLimits(size=2).size


# ---- no session / failures -------------------------------------------------------------------------------------------

async def test_no_session_is_the_login_text_and_no_kite_call() -> None:
    t = Transport()
    for m in (await margin_answer(source(t, session=None), CTX, plan()),
              await margin_answer(source(t), None, plan()),
              await margin_answer(None, CTX, plan())):
        assert m == MARGIN and str(m.reason) == LOGIN_TEXT
    assert t.calls == []


async def test_a_cached_plan_never_waits_behind_another_plans_slow_read() -> None:
    """Tier A review (MAJOR): plan A's basket read sleeps 3 s; cached plan B must answer in under 100 ms meanwhile."""
    t = Transport(delay=3.0, slow_when='"quantity": 130')  # only plan A's basket (2 lots = 130) is slow
    s = source(t)
    cached = await margin_answer(s, CTX, plan())  # plan B, read once and cached
    slow = asyncio.create_task(margin_answer(s, CTX, plan(ce_lots=2)))
    await asyncio.sleep(0.05)  # plan A is now inside its 3 s read
    started = time.perf_counter()
    assert await margin_answer(s, CTX, plan()) == cached
    elapsed = time.perf_counter() - started
    hundred_ms = 0.1
    assert elapsed < hundred_ms, elapsed
    assert not slow.done()
    assert (await slow).state == "CHECKED"


async def test_two_concurrent_requests_for_one_uncached_plan_make_one_read() -> None:
    t = Transport(delay=0.2)
    s = source(t)
    first, second = await asyncio.gather(margin_answer(s, CTX, plan()), margin_answer(s, CTX, plan()))
    assert first == second and first.state == "CHECKED"
    assert s.reads == 1 and t.baskets() == 1


async def test_an_unknown_session_is_read_but_never_cached() -> None:
    t = Transport()
    s = source(t, session=("owner", None))
    await margin_answer(s, CTX, plan())
    await margin_answer(s, CTX, plan())
    two_reads = 2
    assert t.baskets() == two_reads and len(s._cache) == 0


@pytest.mark.parametrize(("needed", "available", "shown", "short"), [
    ("100.004", "100.00", ("100.01", "100.00"), True),  # never "100.00 needed, 100.00 available" with a red line
    ("100.00", "100.009", ("100.00", "100.00"), False),
    ("100.001", "100.005", ("100.01", "100.00"), True),  # the shown figures decide, not the unrounded ones
    ("68498.85000000001", "68498.85", ("68498.86", "68498.85"), True),  # Kite's float noise errs on the safe side
])
def test_shortfall_compares_the_figures_shown(needed, available, shown, short) -> None:
    m = outcome_margin.margin_checked(Decimal(needed), Decimal(available), CHECKED_AT, Decimal(needed),
                                      Decimal(0))
    assert (str(m.needed), str(m.available)) == shown and m.shortfall is short


async def test_the_owner_client_bounds_each_call_below_the_read_timeout(monkeypatch) -> None:
    async def stored(_config):
        return FAKE_ACCESS

    monkeypatch.setattr(live_market, "_current", SimpleNamespace(_config=SimpleNamespace(api_key="key"),
                                                                 _stored_token=stored))
    client = await live_market.owner_margin_client()
    timeout = client._call.keywords["timeout"]
    assert timeout * 2 <= outcome_margin.READ_TIMEOUT_SECONDS  # funds + basket together never outlive the read
    seen = {}

    def door(_url, *, method="GET", data=None, headers=None, timeout=None):  # W-080: every send goes via the door
        seen["timeout"] = timeout
        raise OSError("no network in tests")

    monkeypatch.setattr("ofo_app.kite_margin.kite_open_url", door)
    with pytest.raises(KiteMarginError):  # the transport's own failure; only the timeout is asserted
        client._call("GET", "https://api.kite.trade/user/margins", {}, None)
    assert seen["timeout"] == timeout


async def test_099_kites_float_noise_is_not_a_shortfall_on_the_screen() -> None:
    """ADR-099 (issue 297): Zerodha final.total 67842.35000000001 + the 656.50 BUY top-up, funds 68498.84999999999:
    both read 68498.85, so the screen shows equal figures and NO shortfall."""
    funds = '{"status": "success", "data": {"equity": {"enabled": true, "net": 68498.84999999999}}}'
    reply = json.loads(BASKET_TEXT)
    reply["data"]["final"]["total"] = "@@"  # swapped for the float-tail text below, which json.dumps cannot print
    basket = json.dumps(reply).replace('"@@"', "67842.35000000001")
    assert "67842.35000000001" in basket

    def transport(_method, url, _headers, _body):
        return HTTPStatus.OK, (funds if url.endswith("/user/margins") else basket)

    m = await margin_answer(source(transport), CTX, plan())
    assert m.state == "CHECKED" and (str(m.needed), str(m.available)) == ("68498.85", "68498.85")
    assert m.shortfall is False


def test_enough_funds_is_no_shortfall() -> None:
    m = outcome_margin.margin_checked(Decimal("7065.50"), Decimal("7065.50"), CHECKED_AT, Decimal("6409"),
        Decimal("656.50"))
    assert m.shortfall is False and str(m.available) == "7065.50"
    short = outcome_margin.margin_checked(Decimal("7065.50"), Decimal("7065.49"), CHECKED_AT, Decimal("6409"),
        Decimal("656.50"))
    assert short.shortfall is True


async def test_no_stored_token_is_the_login_text() -> None:
    async def none():
        return None

    m = await margin_answer(OutcomeMargin(lambda: OWNER_SESSION, none, clock=lambda: CHECKED_AT), CTX, plan())
    assert m == MARGIN


async def test_a_leg_outside_the_listed_contracts_makes_no_call() -> None:
    t = Transport()
    m = await margin_answer(source(t), CTX, [PlannedOrderIn("NSE_FO:1", "BUY", 1, Decimal("1"))])
    assert m.state == "NO_BASKET" and m.needed is None and t.calls == []
    assert str(m.reason) == str(render_explanation("outcome_margin_no_basket"))


@pytest.mark.parametrize("status", [500, 429, 400])
async def test_kite_unreadable_is_the_could_not_read_text_and_retried_only_after_the_wait(status) -> None:
    t, mono = Transport(status=status), Mono()
    s = source(t, monotonic=mono)
    m = await margin_answer(s, CTX, plan())
    assert m.state == "UNREADABLE" and m.needed is None and m.available is None
    if status == HTTPStatus.TOO_MANY_REQUESTS:  # REQ-118 AC-3: busy (the limiter's refusal arrives as 429)
        assert str(m.reason) == "Zerodha is busy - try again in a moment"
    else:
        assert str(m.reason) == "Margin from Zerodha could not be read just now, so no margin figure is shown."
    calls = len(t.calls)
    await margin_answer(s, CTX, plan())  # a push one second later: no new read
    assert len(t.calls) == calls
    mono.now += outcome_margin.RETRY_SECONDS
    await margin_answer(s, CTX, plan())
    assert len(t.calls) == calls + 1  # the funds read fails first, so one call per retry


async def test_a_403_says_the_login_is_needed() -> None:
    m = await margin_answer(source(Transport(status=403)), CTX, plan())
    assert m == MARGIN


async def test_a_slow_kite_times_out_off_the_event_loop_thread() -> None:
    t = Transport(delay=0.3)
    m = await margin_answer(source(t, limits=MarginLimits(timeout=0.05)), CTX, plan())
    assert m.state == "UNREADABLE"
    assert t.threads and threading.get_ident() not in t.threads  # the network read never ran on the loop's thread
    await asyncio.sleep(0.4)  # let the worker thread finish before the loop closes


async def test_the_token_never_reaches_the_log(caplog) -> None:
    await margin_answer(source(Transport(status=500)), CTX, plan())
    assert FAKE_ACCESS not in caplog.text


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
    answers = 3
    responses = await _post(_body(replayed), replayed, source(t), n=answers)
    raw = responses[0].text
    out = json.loads(raw)
    assert out["state"] == "COMPUTED" and out["summary"] is not None
    assert out["margin"]["state"] == "CHECKED" and out["margin"]["shortfall"] is True
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
    assert out["margin"]["state"] == "NOT_AVAILABLE_YET" and out["margin"]["reason"] == LOGIN_TEXT
    assert t.calls == []


# ---- the live push: a tick re-push reads no margin --------------------------------------------------------------

async def test_live_push_ticks_reuse_the_margin_and_a_plan_change_reads_once(monkeypatch) -> None:
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
    ticks = 3
    for n in range(ticks):  # three price ticks, each pushed a second apart
        tick(provider, "NSE_FO:44624", f"{100 + n}.05")
        mono.now += 1.0
        await settle()
    assert len(channel.sent) == ticks + 1 and all(s["margin"]["state"] == "CHECKED" for s in channel.sent)
    assert t.baskets() == 1
    changed = {**body, "legs": [{**body["legs"][0], "lots": 2}, *body["legs"][1:]]}
    await channel.inbound.put(changed)
    mono.now += 1.0
    await settle()
    two_plans = 2
    assert len(channel.sent) == ticks + two_plans and t.baskets() == two_plans
    await channel.inbound.put(ChannelClosed)
    await task


async def test_route_busy_margin_read_shows_the_zerodha_busy_text_and_no_figure(replayed, monkeypatch) -> None:
    """REQ-118 AC-3: Kite answers 429 (the limiter's busy refusal reaches the client as 429): UNREADABLE, no figure, and
    the reason is the busy text from its one home, not the generic could-not-be-read text."""
    from ofo.errors.templates import ZERODHA_BUSY_TEXT  # noqa: PLC0415

    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(Transport(status=429)))
    out = resp.json()
    assert out["state"] == "COMPUTED" and out["margin"]["state"] == "UNREADABLE" and out["margin"]["needed"] is None
    assert out["margin"]["reason"] == ZERODHA_BUSY_TEXT


# ---- REQ-055 AC-4: the shortfall line from the server, and every answer state of the two Zerodha reads ----

SHORT_WAYS = "Reduce the quantity, review the strategy, or add funds in Zerodha, then check again."
NO_FIGURE_BLOCK = {"needed": None, "broker_needed": None, "available": None, "checked_at": None, "shortfall": False,
                   "shortfall_reason": None}


def _funds(net) -> str:
    return json.dumps({"status": "success", "data": {"equity": {"enabled": True, "net": net}}})


def _basket(mutate=None) -> str:
    reply = json.loads(BASKET_TEXT)
    if mutate is not None:
        mutate(reply["data"])
    return json.dumps(reply)


def replies(funds_text: str | None = None, basket_text: str | None = None):
    """A transport answering the two reads with the given texts (default: the recorded ones)."""
    def transport(_method, url, _headers, _body):
        return HTTPStatus.OK, ((funds_text or FUNDS_TEXT) if url.endswith("/user/margins")
                               else (basket_text or BASKET_TEXT))
    return transport


def test_shortfall_reason_carries_both_figures_to_the_paisa_only_when_short() -> None:
    equal = outcome_margin.margin_checked(Decimal("100.00"), Decimal("100.00"), CHECKED_AT, Decimal("90"),
        Decimal("10.00"))
    assert equal.shortfall is False and equal.shortfall_reason is None
    paisa = outcome_margin.margin_checked(Decimal("100.00"), Decimal("99.99"), CHECKED_AT, Decimal("90"),
        Decimal("10.00"))
    assert paisa.shortfall is True
    assert str(paisa.shortfall_reason) == _short_line("₹90.00", "₹100.00", "₹99.99", "₹10.00")


async def test_the_execute_gate_and_the_builder_line_share_one_ways_forward_sentence() -> None:
    from ofo.errors import CATALOGUE  # noqa: PLC0415

    assert CATALOGUE["margin_basket_insufficient"].next_action == SHORT_WAYS
    m = await margin_answer(source(Transport()), CTX, plan())
    assert str(m.shortfall_reason).endswith(SHORT_WAYS)


async def test_enough_funds_has_no_shortfall_reason() -> None:
    m = await margin_answer(source(replies(funds_text=_funds(12500.0))), CTX, plan())
    assert m.state == "CHECKED" and m.shortfall is False and m.shortfall_reason is None


async def test_funds_one_paisa_short_of_the_recorded_total_is_a_shortfall_with_the_line() -> None:
    m = await margin_answer(source(replies(funds_text=_funds(7065.49))), CTX, plan())
    assert (str(m.needed), str(m.available), m.shortfall) == ("7065.50", "7065.49", True)
    assert str(m.shortfall_reason) == _short_line("₹6,409.00", "₹7,065.50", "₹7,065.49")


async def test_negative_funds_are_checked_and_short() -> None:
    m = await margin_answer(source(replies(funds_text=_funds(-120.5))), CTX, plan())
    assert m.state == "CHECKED" and str(m.available) == "-120.50" and m.shortfall is True
    assert m.shortfall_reason is not None


async def test_closing_basket_needs_nothing_and_is_not_short() -> None:
    def closing(data):
        data["final"]["total"] = -214.5
        for row in data["orders"]:
            row["total"] = 0
    both_sell = [PlannedOrderIn(CE_ID, "SELL", 1, Decimal("45.55")), PlannedOrderIn(PE_ID, "SELL", 1, Decimal("63.15"))]
    m = await margin_answer(source(replies(basket_text=_basket(closing))), CTX, both_sell)
    assert m.state == "CHECKED" and str(m.needed) == "0.00" and m.shortfall is False and m.shortfall_reason is None


def _shorter(d):
    d["orders"] = d["orders"][:1]


def _longer(d):
    d["orders"] = [*d["orders"], d["orders"][0]]


def _reordered(d):
    d["orders"] = list(reversed(d["orders"]))


def _no_orders(d):
    d.pop("orders")


def _no_total(d):
    d["final"].pop("total")


@pytest.mark.parametrize("mutate", [_shorter, _longer, _reordered], ids=["shorter", "longer", "reordered"])
async def test_ambiguous_basket_reply_shows_could_not_be_read_and_not_zerodhas_total(mutate) -> None:
    m = await margin_answer(source(replies(basket_text=_basket(mutate))), CTX, plan())
    assert m.state == "UNREADABLE" and m.needed is None and m.available is None and m.shortfall_reason is None
    assert str(m.reason) == "Margin from Zerodha could not be read just now, so no margin figure is shown."


@pytest.mark.parametrize(("funds", "basket"), [
    (json.dumps({"status": "success", "data": {"commodity": {"net": 1}}}), None),  # no equity block
    (None, _basket(_no_orders)),  # no orders list
    (None, _basket(_no_total)),  # no final.total
], ids=["no-equity", "no-orders", "no-total"])
async def test_empty_reads_are_unreadable_with_no_figure(funds, basket) -> None:
    m = await margin_answer(source(replies(funds, basket)), CTX, plan())
    assert m.state == "UNREADABLE" and m.needed is None and m.available is None


# the route body, per Zerodha failure: needed, available and shortfall_reason are all null, never a made-up figure
ROUTE_STATES = [
    ("kite_margin_token", lambda: Transport(status=403), "NOT_AVAILABLE_YET"),
    ("kite_margin_busy", lambda: Transport(status=429), "UNREADABLE"),
    ("kite_margin_refused", lambda: Transport(status=400), "UNREADABLE"),
    ("kite_margin_unavailable", lambda: Transport(status=500), "UNREADABLE"),
    ("kite_margin_no_figure", lambda: replies(funds_text='{"status": "success", "data": {}}'), "UNREADABLE"),
    ("ambiguous", lambda: replies(basket_text=_basket(_shorter)), "UNREADABLE"),
]


@pytest.mark.parametrize(("code", "make", "state"), ROUTE_STATES, ids=[r[0] for r in ROUTE_STATES])
async def test_route_every_failed_read_has_null_figures_and_no_shortfall_reason(replayed, monkeypatch, code, make,
                                                                                state) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [resp] = await _post(_body(replayed), replayed, source(make()))
    out = resp.json()
    assert out["state"] == "COMPUTED" and out["margin"]["state"] == state, code
    assert {k: out["margin"][k] for k in NO_FIGURE_BLOCK} == NO_FIGURE_BLOCK, code


async def test_route_timeout_and_unreadable_token_store_have_null_figures(replayed, monkeypatch) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    slow = source(Transport(delay=0.3), limits=MarginLimits(timeout=0.05))

    async def broken_store():
        raise OSError("token store unreadable")

    broken = OutcomeMargin(lambda: OWNER_SESSION, broken_store, clock=lambda: CHECKED_AT)
    for src in (slow, broken):
        [resp] = await _post(_body(replayed), replayed, src)
        margin = resp.json()["margin"]
        assert margin["state"] == "UNREADABLE"
        assert {k: margin[k] for k in NO_FIGURE_BLOCK} == NO_FIGURE_BLOCK
    await asyncio.sleep(0.4)


async def test_route_no_basket_has_null_figures_and_makes_no_kite_call(replayed) -> None:
    t = Transport()
    ctx = SimpleNamespace(provider=SimpleNamespace(instrument_master=lambda: [CE, PE]))
    src = source(t)
    m = await margin_answer(src, ctx, [PlannedOrderIn("NSE_FO:1", "BUY", 1, Decimal("1"))])
    assert m.state == "NO_BASKET" and t.calls == []
    assert (m.needed, m.available, m.checked_at, m.shortfall, m.shortfall_reason) == (None, None, None, False, None)


async def test_route_shortfall_reason_is_the_catalogue_line_only_when_short(replayed, monkeypatch) -> None:
    monkeypatch.setattr(outcome_margin, "basket_orders", _recorded_orders)
    [short] = await _post(_body(replayed), replayed, source(Transport()))
    margin = short.json()["margin"]
    assert margin["shortfall"] is True
    assert margin["shortfall_reason"] == _short_line("₹6,409.00", "₹7,065.50", "₹671.50")
    assert margin["broker_needed"] == "6409.00" and margin["needed"] == "7065.50"  # money strings, never numbers
    [enough] = await _post(_body(replayed), replayed, source(replies(funds_text=_funds(12500.0))))
    assert enough.json()["margin"]["shortfall"] is False and enough.json()["margin"]["shortfall_reason"] is None


# ---- REQ-055 AC-3: Zerodha's own figure and the ADR-094 figure are named apart --------------------------------------

def _no_premium_in_the_reply(data) -> None:
    """The recorded reply with the buy legs' premium taken out of Zerodha's figure, so the ADR-094 top-up is large:
    Zerodha's final.total stays 6409, the figure the check needs becomes 13474.50 (the Opus checker's case)."""
    for row in data["orders"]:
        if row.get("transaction_type") == "BUY" or "option_premium" in row:
            row["option_premium"] = 0


ZERODHA_OWN = "Zerodha's own margin figure is ₹6,409.00"


async def test_core_zerodhas_own_figure_and_ours_are_labelled_apart() -> None:
    m = await margin_answer(source(replies(basket_text=_basket(_no_premium_in_the_reply))), CTX, plan())
    assert (str(m.broker_needed), str(m.needed), m.shortfall) == ("6409.00", "13474.50", True)
    for text in (str(m.reason), str(m.shortfall_reason)):
        assert "Zerodha says these planned orders need" not in text
        assert ZERODHA_OWN in text  # Zerodha's figure, named as Zerodha's
        assert "₹13,474.50" in text and "estimate" in text
        # the only place Zerodha's name sits next to a figure is its own 6,409.00
        assert text.replace(ZERODHA_OWN, "").count("Zerodha says") == 0
        assert "Zerodha needs ₹13,474.50" not in text


def test_execute_refusal_does_not_call_our_figure_zerodhas_and_decides_as_before() -> None:
    from ofo.execution.margin_gate import check_margin  # noqa: PLC0415

    blocked = check_margin(Decimal("671.50"), Decimal("13474.50"))
    assert blocked.allowed is False  # the decision: ours versus available, unchanged
    assert check_margin(Decimal("13474.50"), Decimal("13474.50")).allowed is True
    said = str(blocked.message.what_happened)
    assert "₹13,474.50" in said and "₹671.50" in said and "Zerodha says" not in said


@pytest.mark.parametrize("mutate", [None, _no_premium_in_the_reply])
async def test_zerodha_figure_is_carried_only_when_checked(mutate) -> None:
    ok = await margin_answer(source(replies(basket_text=_basket(mutate))), CTX, plan())
    assert ok.state == "CHECKED" and str(ok.broker_needed) == "6409.00"
    for gone in (await margin_answer(source(Transport(), session=None), CTX, plan()),
                 await margin_answer(source(Transport()), CTX, [PlannedOrderIn("no-such-id", "BUY", 1, Decimal(1))]),
                 await margin_answer(source(Transport(status=HTTPStatus.INTERNAL_SERVER_ERROR)), CTX, plan())):
        assert gone.broker_needed is None


async def test_closing_basket_shows_zerodha_zero() -> None:
    def closing(data):
        data["final"]["total"] = -214.5
        for row in data["orders"]:
            row["total"] = 0
    both_sell = [PlannedOrderIn(CE_ID, "SELL", 1, Decimal("45.55")), PlannedOrderIn(PE_ID, "SELL", 1, Decimal("63.15"))]
    m = await margin_answer(source(replies(basket_text=_basket(closing))), CTX, both_sell)
    assert (str(m.broker_needed), str(m.needed)) == ("0.00", "0.00")
    assert "Zerodha's own margin figure is ₹0.00" in str(m.reason)
