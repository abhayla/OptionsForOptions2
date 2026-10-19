"""W-116 (REQ-029 AC-1/AC-2/AC-4/AC-6/AC-8; REQ-049 AC-2; ADR-077): the Option Chain push and its REST read.

The push-class and REST-function tests run on a fake provider behind the REAL shared ``FanOut``, a fake stored
catalogue and a fake channel minted by the door's ``socket_body``: no database, no server, no Kite. The app-route tests
at the end override every seam of the REST read (context, streaming, clock, catalogue reader), so no database either.

Expected values come from the inputs the tests write, by hand: the catalogue grid is 25000..25400 in steps of 50; a spot
of 25162.30 is 12.30 from 25150 and 37.70 from 25200, so ATM = 25150 and two strikes each side are 25050, 25100, 25150,
25200, 25250. A pushed ``ltp`` is the fake quote's price as a 2-decimal string, ``at`` its time, ``health`` its health.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import re
from decimal import Decimal

import pytest
from ofo.engine.legs import Instrument
from ofo.errors import render
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app import chain_push
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import ChainCatalogue, ChainOut, ChainPush, ChainRequest, atm_strike, strike_window
from ofo_app.errors import socket_body
from ofo_app.live_push import ChannelClosed, LiveFeed
from ofo_app.routes.chain import chain_read
from ofo_app.routes.outcome import MarketContext

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 19, 9, 20, 0, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
NEXT_EXPIRY = datetime.date(2026, 11, 3)
NIFTY_ID = "NSE_INDEX:256265"
GRID = [Decimal(25000 + 50 * i) for i in range(9)]  # 25000 .. 25400
WINDOW_2 = [Decimal(s) for s in ("25050", "25100", "25150", "25200", "25250")]
ERROR = render("user_input_request_invalid").as_dict()
ONE, TWO = 1, 2


def contracts_for(expiry: datetime.date, token_base: int) -> tuple[PickableContract, ...]:
    out = []
    for i, strike in enumerate(GRID):
        for j, side in enumerate(("CE", "PE")):
            token = token_base + 2 * i + j
            out.append(PickableContract(contract_id=token, instrument_id=f"NSE_FO:{token}", exchange_segment="NSE_FO",
                                        exchange_token=token, instrument_type=side, expiry=expiry, strike=strike,
                                        lot_size=75, symbol=f"NIFTY{expiry:%y%b}{strike}{side}".upper()))
    return tuple(out)


CONTRACTS = contracts_for(EXPIRY, 40000)
NEXT_CONTRACTS = contracts_for(NEXT_EXPIRY, 50000)


def cid(strike: str, side: str, contracts=CONTRACTS) -> str:
    return next(c.instrument_id for c in contracts if c.strike == Decimal(strike) and c.instrument_type == side)


def index_quote(ltp: str, at: datetime.datetime = T0, health: DataHealth = DataHealth.AVAILABLE) -> NormalizedQuote:
    return NormalizedQuote(NIFTY_ID, "NIFTY", "NSE", "INDICES", None, None, None, Decimal(ltp), None, None, None, None,
                           None, None, None, None, None, None, at, SourceMetadata("fake", "fake-feed"), health)


def option_quote(instrument_id: str, ltp: str, *, at: datetime.datetime = T0, oi: int = 1000, volume: int = 500,
                 health: DataHealth = DataHealth.AVAILABLE, contracts=CONTRACTS) -> NormalizedQuote:
    c = next(c for c in contracts if c.instrument_id == instrument_id)
    return NormalizedQuote(instrument_id, "NIFTY", "NSE", "NSE_FO", Instrument(c.instrument_type), c.expiry, c.strike,
                           Decimal(ltp), None, None, volume, oi, None, None, None, None, None, None, at,
                           SourceMetadata("fake", "fake-feed"), health)


class FakeProvider:
    """The provider methods the fan-out and the push use; records every vendor subscribe / unsubscribe call."""

    def __init__(self) -> None:
        self.quotes: dict[str, NormalizedQuote] = {}
        self.vendor_subscribed: set[str] = set()
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []
        self.unknown: set[str] = set()
        self._listener = None

    def live_quote_stream(self, listener) -> None:
        self._listener = listener

    def subscribe(self, ids) -> None:
        if any(i in self.unknown for i in ids):
            raise KeyError("unknown")
        self.subscribe_calls.append(list(ids))
        self.vendor_subscribed.update(ids)

    def unsubscribe(self, ids) -> None:
        self.unsubscribe_calls.append(list(ids))
        self.vendor_subscribed.difference_update(ids)

    def index_id(self, underlying: str) -> str | None:
        return NIFTY_ID if underlying == "NIFTY" else None

    def underlying_quote(self, underlying: str) -> NormalizedQuote | None:
        return self.quotes.get(NIFTY_ID) if underlying == "NIFTY" else None

    def option_chain_snapshot(self, underlying: str, expiry: datetime.date) -> list[NormalizedQuote]:
        return [q for q in self.quotes.values() if q.underlying == underlying and q.expiry == expiry]

    def tick(self, q: NormalizedQuote) -> None:
        self.quotes[q.instrument_id] = q
        if self._listener is not None:
            self._listener(q)


class FakeChannel:
    def __init__(self) -> None:
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []

    async def receive(self):
        item = await self.inbound.get()
        if item is ChannelClosed:
            raise ChannelClosed()
        return item

    async def send(self, source) -> None:
        """Minted exactly as the app's door socket mints it, then read back as JSON."""
        self.sent.append(json.loads(bytes(socket_body(source, (ChainOut,)))))


class Clock:
    def __init__(self, start) -> None:
        self.now = start

    def __call__(self):
        return self.now


class Reader:
    def __init__(self, by_expiry: dict | None = None, *, unreadable: bool = False) -> None:
        self.by_expiry = {EXPIRY: CONTRACTS, NEXT_EXPIRY: NEXT_CONTRACTS} if by_expiry is None else by_expiry
        self.unreadable = unreadable
        self.calls: list[tuple[str, datetime.date]] = []

    async def __call__(self, underlying: str, expiry: datetime.date) -> ChainCatalogue:
        self.calls.append((underlying, expiry))
        if self.unreadable:
            return ChainCatalogue((), (), unreadable=True)
        return ChainCatalogue(tuple(sorted(self.by_expiry)), self.by_expiry.get(expiry, ()))


def make_rig(reader: Reader | None = None, provider: FakeProvider | None = None, fanout: FanOut | None = None):
    provider = provider or FakeProvider()
    wall = Clock(T0)
    feed = LiveFeed(MarketContext(provider, wall, Decimal("0.065")), fanout or FanOut(provider))
    channel, mono = FakeChannel(), Clock(1000.0)
    push = ChainPush(channel, feed, monotonic=mono, now=wall, reader=reader or Reader(), poll=0.005)
    return provider, feed, channel, mono, push


def request(each_side=2, expiry: datetime.date = EXPIRY) -> dict:
    return {"underlying": "NIFTY", "expiry": expiry.isoformat(), "strikes_each_side": each_side}


async def settle(n: int = 6) -> None:
    for _ in range(n):
        await asyncio.sleep(0.01)


async def start(push, channel, req: dict | None = None):
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request() if req is None else req)
    await settle()
    return task


async def close(channel, task) -> None:
    await channel.inbound.put(ChannelClosed)
    await task


def tick_window(provider, ltp_offset: int = 0, health: DataHealth = DataHealth.AVAILABLE, at=T0) -> None:
    for k, strike in enumerate(WINDOW_2):
        provider.tick(option_quote(cid(str(strike), "CE"), f"{100 + k + ltp_offset}.50", at=at, health=health))
        provider.tick(option_quote(cid(str(strike), "PE"), f"{200 + k + ltp_offset}.25", at=at, health=health))


async def test_ac1_core_two_pushes_for_a_five_strike_chain_with_changing_ltps_and_per_cell_health():
    """AC-1 (core proof): a 5-strike chain around ATM reaches the channel as two pushes one second apart, rows by strike
    with the CE and PE cells of each strike, each cell with its quote's own price and health, state LIVE."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    provider.tick(option_quote(cid("25150", "CE"), "131.00", health=DataHealth.STALE))
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(channel.sent) == TWO
    first, second = channel.sent
    assert first["state"] == second["state"] == "LIVE"
    assert [r["strike"] for r in first["rows"]] == ["25050.00", "25100.00", "25150.00", "25200.00", "25250.00"]
    for k, row in enumerate(first["rows"]):
        assert row["ce"]["instrument_id"] == cid(row["strike"], "CE") and row["ce"]["ltp"] == f"{100 + k}.50"
        assert row["pe"]["instrument_id"] == cid(row["strike"], "PE") and row["pe"]["ltp"] == f"{200 + k}.25"
        assert row["ce"]["health"] == row["pe"]["health"] == "available"
    atm_row = second["rows"][2]
    assert atm_row["ce"] == {"instrument_id": cid("25150", "CE"), "ltp": "131.00", "change": None, "oi": 1000,
                             "volume": 500, "health": "stale", "at": T0.isoformat()}
    assert second["rows"][2]["pe"]["health"] == "available"


async def test_ac2_default_columns_present_and_change_null_without_a_previous_close():
    """AC-2: each cell carries exactly LTP, Change, OI, Volume (plus id, health, time), no IV or Greeks; the feed has no
    previous close, so change is null on every cell, never computed from anything else."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    await close(channel, task)
    cells = [row[s] for row in channel.sent[0]["rows"] for s in ("ce", "pe")]
    assert {frozenset(c) for c in cells} == {frozenset({"instrument_id", "ltp", "change", "oi", "volume", "health",
                                                        "at"})}
    assert [c["change"] for c in cells] == [None] * 10
    assert set(channel.sent[0]) == {"state", "underlying", "expiry", "spot", "spot_at", "spot_health", "atm_strike",
                                    "rows_missing", "rows", "answered_at"}


async def test_ac4_at_most_one_push_a_second_and_none_without_a_change():
    """AC-4: LTPs change every 0.2 s for 2 s: at most one push per second; then 2 s with no change: no push."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    for step in range(10):
        tick_window(provider, ltp_offset=step + 1)
        mono.now += 0.2
        await settle(2)
    pushed = len(channel.sent)
    for _ in range(10):
        mono.now += 0.2
        await settle(2)
    await close(channel, task)
    assert pushed == 3  # t=0 (first), t=1.0, t=2.0: hand count of 1 s gates over 2 s
    assert len(channel.sent) == pushed + 1  # the last tick's change is pushed once at the next gate, then nothing


async def test_ac4_requests_are_applied_at_most_once_a_second_latest_wins():
    """AC-4 / threat model (push storm): three different requests inside one second read the catalogue once at once,
    then once for the latest a second later; the middle one is never read or subscribed."""
    reader = Reader()
    provider, _feed, channel, mono, push = make_rig(reader)
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel, request(2))
    await channel.inbound.put(request(3))
    await channel.inbound.put(request(4))
    await settle()
    assert reader.calls == [("NIFTY", EXPIRY)]
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(reader.calls) == TWO
    assert len(provider.subscribe_calls) == TWO  # 5 strikes, then 9 (4 each side): never 7
    assert len(channel.sent[-1]["rows"]) == 9


@pytest.mark.parametrize(("spot", "atm"), [("25162.30", "25150.00"), ("25175", "25150.00"), ("25175.01", "25200.00"),
                                           ("24000", "25000.00"), ("26000", "25400.00")])
async def test_ac8_atm_is_the_catalogue_strike_nearest_the_spot(spot, atm):
    """AC-8: the ATM strike is the grid strike nearest the live spot (a tie at 25175 takes the lower, 25150), the spot
    is shown, and the rows are centred on it (fewer at the grid's ends)."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote(spot))
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert body["atm_strike"] == atm and body["spot"] == f"{Decimal(spot):.2f}"
    assert body["spot_health"] == "available" and body["spot_at"] == T0.isoformat()
    strikes = [Decimal(r["strike"]) for r in body["rows"]]
    i = GRID.index(Decimal(atm))
    assert strikes == GRID[max(0, i - 2): i + 3]


def test_ac8_pure_atm_and_window_on_the_grid():
    """AC-8: the helpers on the grid itself; a window outside 1..15 is refused."""
    assert atm_strike(GRID, Decimal("25124.99")) == Decimal("25100")
    assert atm_strike(GRID, Decimal("25125")) == Decimal("25100")
    assert list(strike_window(GRID, Decimal("25000"), 1)) == [Decimal("25000"), Decimal("25050")]
    for bad in (0, 16):
        with pytest.raises(ValueError):
            strike_window(GRID, Decimal("25000"), bad)


@pytest.mark.parametrize("health", list(DataHealth))
async def test_ac2_each_cell_carries_its_quotes_own_health(health):
    """REQ-049 AC-2: each of the five health states reaches its cell as the quote gave it, never upgraded."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider, health=health)
    task = await start(push, channel)
    await close(channel, task)
    assert {row[s]["health"] for row in channel.sent[0]["rows"] for s in ("ce", "pe")} == {health.value}


async def test_ac2_a_held_contract_without_a_quote_reads_unavailable():
    """REQ-049 AC-2: a subscribed contract with no quote yet is shown unavailable with no number."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    await close(channel, task)
    assert channel.sent[0]["rows"][0]["ce"] == {"instrument_id": cid("25050", "CE"), "ltp": None, "change": None,
                                                "oi": None, "volume": None, "health": "unavailable", "at": None}


@pytest.mark.parametrize("bad", [0, 16, -1, "x", "5", True, 2.0, None])
async def test_strikes_each_side_out_of_range_is_refused(bad):
    """Threat model (unbounded strike range): 0, 16, -1, 'x', a numeric string, a bool, a float and null are refused
    with the one input message, and nothing is subscribed or read."""
    reader = Reader()
    provider, _feed, channel, _mono, push = make_rig(reader)
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel, request(bad))
    await close(channel, task)
    assert channel.sent == [ERROR]
    assert reader.calls == [] and provider.subscribe_calls == []


@pytest.mark.parametrize("raw", [{**request(), "fallback": True}, {**request(), "extra": 1}, {"underlying": "BANKNIFTY",
                                 "expiry": EXPIRY.isoformat()}, "text"])
async def test_unreadable_requests_are_refused(raw):
    """Threat model: the REST fallback flag, an unknown key, an unknown underlying or a non-object are refused."""
    provider, _feed, channel, _mono, push = make_rig()
    task = await start(push, channel, raw)
    await close(channel, task)
    assert channel.sent == [ERROR] and provider.subscribe_calls == []


async def test_expiry_change_releases_the_old_contracts_and_keeps_the_index_held():
    """Threat model (leaked subscription on an expiry change): the new expiry's contracts are taken BEFORE the old are
    released; afterwards every old contract has 0 subscribers, the index 1, and the index was never unsubscribed."""
    provider, feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    old_ids = [cid(str(s), side) for s in WINDOW_2 for side in ("CE", "PE")]
    assert all(feed.fanout.subscriber_count(i) == ONE for i in old_ids)
    mono.now += 1.0
    await channel.inbound.put(request(expiry=NEXT_EXPIRY))
    await settle()
    new_ids = [cid(str(s), side, NEXT_CONTRACTS) for s in WINDOW_2 for side in ("CE", "PE")]
    assert [feed.fanout.subscriber_count(i) for i in old_ids] == [0] * 10
    assert [feed.fanout.subscriber_count(i) for i in new_ids] == [1] * 10
    assert feed.fanout.subscriber_count(NIFTY_ID) == ONE
    assert all(NIFTY_ID not in call for call in provider.unsubscribe_calls)
    assert provider.unsubscribe_calls == [old_ids]
    await close(channel, task)
    assert channel.sent[-1]["expiry"] == NEXT_EXPIRY.isoformat()


async def test_close_releases_everything():
    """Threat model (leaked subscription after disconnect): on close every contract and the index has 0 subscribers
    and the vendor holds nothing."""
    provider, feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    assert provider.vendor_subscribed
    await close(channel, task)
    assert provider.vendor_subscribed == set()
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0


async def test_an_unknown_contract_subscribes_nothing_and_keeps_the_old_subscription():
    """A contract the provider does not know: the input message, nothing new subscribed, the old window still held."""
    provider, feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    provider.unknown = {cid("25150", "CE", NEXT_CONTRACTS)}
    mono.now += 1.0
    await channel.inbound.put(request(expiry=NEXT_EXPIRY))
    await settle()
    assert feed.fanout.subscriber_count(cid("25150", "CE")) == ONE
    await close(channel, task)
    assert ERROR in channel.sent


async def test_spot_missing_shows_no_rows_and_no_guessed_atm_then_rows_when_the_spot_arrives():
    """Answer state 'spot missing': LIVE with rows empty and rows_missing SPOT_MISSING, atm null, only the index held;
    once the spot arrives the window is picked and subscribed."""
    provider, feed, channel, mono, push = make_rig()
    task = await start(push, channel)
    first = channel.sent[0]
    assert (first["state"], first["rows"], first["rows_missing"], first["atm_strike"], first["spot"]) == (
        "LIVE", [], "SPOT_MISSING", None, None)
    assert first["spot_health"] == "unavailable" and provider.vendor_subscribed == {NIFTY_ID}
    provider.tick(index_quote("25162.30"))
    mono.now += 1.0
    await settle()
    await close(channel, task)
    last = channel.sent[-1]
    assert last["atm_strike"] == "25150.00" and len(last["rows"]) == 5 and last["rows_missing"] is None
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0


@pytest.mark.parametrize(("reader", "missing"), [(Reader({NEXT_EXPIRY: NEXT_CONTRACTS}), "EXPIRY_UNKNOWN"),
                                                 (Reader({}), "CATALOGUE_EMPTY"),
                                                 (Reader({EXPIRY: ()}), "CATALOGUE_EMPTY"),
                                                 (Reader(unreadable=True), "CATALOGUE_UNREADABLE")])
async def test_catalogue_answer_states(reader, missing):
    """Answer states: expiry unknown, catalogue empty, catalogue unreadable: no rows, the reason named, no ATM."""
    provider, _feed, channel, _mono, push = make_rig(reader)
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert (body["rows"], body["rows_missing"], body["atm_strike"]) == ([], missing, None)


async def test_no_feed_answers_not_connected_with_no_number():
    """Answer state NOT_CONNECTED (no feed): no rows, no spot, no ATM."""
    channel = FakeChannel()
    push = ChainPush(channel, None, monotonic=Clock(1000.0), now=Clock(T0), reader=Reader(), poll=0.005)
    task = await start(push, channel)
    await close(channel, task)
    assert len(channel.sent) == ONE
    body = channel.sent[0]
    assert (body["state"], body["rows"], body["spot"], body["atm_strike"]) == ("NOT_CONNECTED", [], None, None)


def _catalogue() -> ChainCatalogue:
    return ChainCatalogue((EXPIRY, NEXT_EXPIRY), CONTRACTS)


async def test_two_holders_and_fallback_answer_not_connected():
    """Finding liveness-from-shared-subscribers: another socket holds every contract and the index, yet the REST read
    with fallback=1 (this screen's own socket is down) answers NOT_CONNECTED with no number; without the flag LIVE."""
    provider = FakeProvider()
    fanout = FanOut(provider)
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    _p, feed, channel_a, _m, push_a = make_rig(provider=provider, fanout=fanout)
    _p2, _f2, channel_b, _m2, push_b = make_rig(provider=provider, fanout=fanout)
    task_a, task_b = await start(push_a, channel_a), await start(push_b, channel_b)
    assert fanout.subscriber_count(cid("25150", "CE")) == TWO
    streaming = lambda i: fanout.subscriber_count(i) > 0  # noqa: E731 - outcome.get_streaming's predicate
    streaming.ctx = feed.ctx
    req = ChainRequest.model_validate(request())
    down = chain_read(feed.ctx, streaming, req, _catalogue(), fallback=True, now=Clock(T0))
    up = chain_read(feed.ctx, streaming, req, _catalogue(), fallback=False, now=Clock(T0))
    await close(channel_a, task_a)
    await close(channel_b, task_b)
    assert (down.state, down.rows, down.spot, down.atm_strike) == ("NOT_CONNECTED", [], None, None)
    assert down.spot_at == T0
    assert up.state == "LIVE" and up.atm_strike == Decimal("25150") and len(up.rows) == 5


def test_rest_read_without_a_holder_is_not_live():
    """Issue #206's rule: no socket holds the contracts, so the REST read is NOT_CONNECTED."""
    provider = FakeProvider()
    fanout = FanOut(provider)
    provider.tick(index_quote("25162.30"))
    ctx = MarketContext(provider, Clock(T0), Decimal("0.065"))
    streaming = lambda i: fanout.subscriber_count(i) > 0  # noqa: E731
    streaming.ctx = ctx
    body = chain_read(ctx, streaming, ChainRequest.model_validate(request()), _catalogue(), fallback=False,
                      now=Clock(T0))
    assert body.state == "NOT_CONNECTED"


def test_ac6_no_order_basket_margin_or_execute_reachable_from_the_chain_code():
    """AC-6: the chain modules import nothing that places, builds, checks or sends an order."""
    root = pathlib.Path(chain_push.__file__).parent
    for path in (root / "chain_push.py", root / "routes" / "chain.py"):
        imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        assert imports, path
        allowed = {"__future__", "asyncio", "contextlib", "datetime", "logging", "time", "collections.abc",
                   "dataclasses", "decimal", "typing", "pydantic", "sqlalchemy.exc", "fastapi", "ofo.errors",
                   "ofo.marketdata.quote", "ofo.money", "ofo_app.api_models", "ofo_app.catalogue_picker",
                   "ofo_app.live_push", "ofo_app.routes.outcome", "ofo_app", "ofo_app.db", "ofo_app.chain_push",
                   "ofo_app.errors", "ofo_app.routes"}
        assert set(imports) <= allowed, (path.name, set(imports) - allowed)
