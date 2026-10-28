"""GC-UI step 4 server round 3, item 1 (REQ-083 AC-5 / AC-6; D-B16, D-B17): an outcome call that asks for it
(``open_interest``) carries each plotted strike's call OI and put OI for the strategy's expiry, with the time they were
read, from the same feed the strike drawer reads, so the chart draws OI bars behind the curve; and says why when OI is
not available, never a zero-height bar as if OI were zero. Today's OI change (D-B18) is Later and not built here.

Real rows: strategy 54's legs (BUY 22600 CE / SELL 22800 CE, 13-Oct) and the calendar on the recorded 2026-10-08 NIFTY
replay (tests/outcome/_both_curves_cases.py). Every expected OI is read from the replay's own chain, never typed.

Answer states: flag off (no key; tests/outcome/test_both_curves.py holds the byte baseline), OI streaming, not
streaming (AC-6 reason, no rows), stale in hours (AC-6 reason, no rows), a real OI of 0 ("0"), calendar (nearest leg
expiry, named), after hours (the last OI with its own time), no live data (AC-6 reason), and the live push's lease:
held while the socket asks for OI, released when it stops asking and when the socket ends.
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider_with_futures, replay  # noqa: E402
from ofo.engine.display import format_oi_compact  # noqa: E402
from ofo.errors.explanations import render_explanation  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.outcome.snapshot import contract_id  # noqa: E402
from ofo_app.live_push import ChannelClosed, LiveFeed, StrategyPush  # noqa: E402
from ofo_app.routes.outcome import MarketContext, OutcomeRequest, outcome_response  # noqa: E402
from outcome._both_curves_cases import CALENDAR, S54  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
EXPIRY = datetime.date(2026, 10, 13)
AFTER_CLOSE = datetime.datetime(2026, 10, 8, 18, 0, tzinfo=IST)
MANY_STRIKES = 10  # the default NIFTY range spans tens of strikes
IN_HOURS_LATE = datetime.datetime(2026, 10, 8, 11, 0, tzinfo=IST)  # in hours, the frames 1.7 h old: stale


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _market(at=VALUATION):
    provider, clock, items, _futures = new_provider_with_futures("NIFTY")
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    clock.now = at
    return provider


def _req(provider, legs, **extra) -> OutcomeRequest:
    return OutcomeRequest.model_validate({"underlying": "NIFTY", "legs": [
        {"instrument_id": i, "action": a.value, "lots": 1,
         "planned_entry": f"{provider.book.get(i, VALUATION).ltp:.2f}", "captured_at": VALUATION.isoformat()}
        for i, a in legs], **extra})


def _body(provider, legs, at=VALUATION, streaming=None, **extra) -> dict:
    ctx = MarketContext(provider, _Clock(at), RATE)
    if streaming is not None:
        streaming.ctx = ctx
    return outcome_response(_req(provider, legs, **extra), ctx, streaming).model_dump(mode="json", exclude_unset=True)


def _chain_oi(provider, expiry=EXPIRY) -> dict[tuple[Decimal, str], int | None]:
    return {(q.strike, q.instrument_type.value): q.oi for q in provider.option_chain_snapshot("NIFTY", expiry)}


def _listed_strikes(provider, expiry, start, end) -> list[Decimal]:
    return sorted({lc.contract.strike for lc in provider.instrument_master()
                   if lc.contract.name == "NIFTY" and lc.contract.expiry == expiry
                   and lc.contract.instrument_type in ("CE", "PE") and start <= lc.contract.strike <= end})


@pytest.fixture(scope="module")
def provider():
    return _market()


def test_core_s54_reply_carries_each_plotted_strikes_call_and_put_oi_for_its_expiry(provider):
    body = _body(provider, S54, open_interest=True)
    oi = body["open_interest"]
    assert oi["available"] is True and oi["unavailable_reason"] is None
    assert oi["expiry"] == EXPIRY.isoformat() and oi["expiry_note"] is None  # one expiry: nothing to name
    start, end = Decimal(body["scenario"]["start"]), Decimal(body["scenario"]["end"])
    strikes = _listed_strikes(provider, EXPIRY, start, end)
    assert [Decimal(r["strike"]) for r in oi["rows"]] == strikes and len(strikes) > MANY_STRIKES
    chain = _chain_oi(provider)
    for row in oi["rows"]:
        k = Decimal(row["strike"])
        assert row["call_oi"] == chain[(k, "CE")] and row["put_oi"] == chain[(k, "PE")], k
        assert row["call_oi"] is not None and row["put_oi"] is not None
    assert oi["contracts"] == 2 * len(strikes)
    times = [q.timestamp for q in provider.option_chain_snapshot("NIFTY", EXPIRY)
             if start <= q.strike <= end]
    assert datetime.datetime.fromisoformat(oi["read_at"]) == min(times)  # the oldest used quote: never overstated
    assert oi["read_at_display"] == render_explanation("outcome_oi_read_at", time=min(times))
    assert oi["read_at_display"].startswith("OI data at ")


def test_display_text_is_the_drawers_compact_form(provider):
    rows = _body(provider, S54, open_interest=True)["open_interest"]["rows"]
    for row in rows:
        for side in ("call", "put"):
            assert row[f"{side}_oi_display"] == render_explanation("outcome_oi_count", count=row[f"{side}_oi"])
    assert [format_oi_compact(n) for n in (0, 999, 62075, 99999, 100000, 7490000, 9994999, 9995000, 12345678)] == [
        "0", "999", "62,075", "99,999", "1.0L", "74.9L", "99.9L", "1.00Cr", "1.23Cr"]


def test_flag_off_has_no_open_interest_key(provider):
    assert "open_interest" not in _body(provider, S54)


def test_one_strike_without_a_usable_quote_is_null_with_a_dash_never_0(monkeypatch):
    """REQ-083 AC-6 ("never draws zero-height bars as if OI were zero"), round 3's surviving mutant M2: inside the range,
    22700 CE has NO quote and 22700 PE has a STALE one while every other strike is quoted. Those two sides are null
    with the dash; the neighbours keep their own real OI; the block stays available."""
    import dataclasses as _dc  # noqa: PLC0415

    from ofo.rules.inputs import DataHealth  # noqa: PLC0415
    from ofo_app.outcome_oi import oi_of  # noqa: PLC0415

    market = _market()
    real = market.option_chain_snapshot
    hole = Decimal("22700")

    def with_a_hole(underlying, expiry):
        out = []
        for q in real(underlying, expiry):
            if q.strike == hole and q.instrument_type.value == "CE":
                continue  # no quote at all
            out.append(_dc.replace(q, health=DataHealth.STALE) if q.strike == hole else q)
        return out

    monkeypatch.setattr(market, "option_chain_snapshot", with_a_hole)
    oi = _body(market, S54, open_interest=True)["open_interest"]
    assert oi["available"] is True
    rows = {Decimal(r["strike"]): r for r in oi["rows"]}
    gap = rows[hole]
    dash = render_explanation("cell_dash")
    assert (gap["call_oi"], gap["call_oi_display"]) == (None, dash)  # missing quote: null, never 0
    assert (gap["put_oi"], gap["put_oi_display"]) == (None, dash)  # unusable quote: null, never 0
    chain = _chain_oi(market)
    for k in (Decimal("22650"), Decimal("22750")):
        assert rows[k]["call_oi"] == chain[(k, "CE")] is not None and rows[k]["put_oi"] == chain[(k, "PE")]
    assert oi_of(None) is None and oi_of(None, closed=True) is None  # the shared rule itself


def test_a_real_oi_of_zero_shows_0_not_a_dash(provider):
    """A real 0 (20200 CE on 13-Oct carries oi 0 in the replay) is a count: "0", never dropped or dashed."""
    body = _body(provider, S54, open_interest=True, range_start="20000", range_end="21500")
    row = next(r for r in body["open_interest"]["rows"] if Decimal(r["strike"]) == Decimal("20200"))
    assert _chain_oi(provider)[(Decimal("20200"), "CE")] == 0
    assert row["call_oi"] == 0 and row["call_oi_display"] == "0"


def test_calendar_uses_the_nearest_leg_expiry_and_says_which(provider):
    oi = _body(provider, CALENDAR, open_interest=True, view="estimated_now")["open_interest"]
    assert oi["available"] is True and oi["expiry"] == EXPIRY.isoformat()
    assert oi["expiry_note"] == render_explanation("outcome_oi_nearest_expiry", expiry=EXPIRY)
    chain = _chain_oi(provider)
    assert all(r["call_oi"] == chain[(Decimal(r["strike"]), "CE")] for r in oi["rows"])  # never the 19-Oct chain


class _Streaming:
    """The REST route's streaming predicate: only ``held`` ids stream (the owner context is set by ``_body``)."""

    def __init__(self, held):
        self.held, self.ctx = set(held), None

    def __call__(self, instrument_id):
        return instrument_id in self.held


def test_not_streaming_says_why_and_draws_no_bar(provider):
    legs_and_index = [i for i, _a in S54] + [provider.index_id("NIFTY")]
    body = _body(provider, S54, streaming=_Streaming(legs_and_index), open_interest=True)
    assert body["state"] == "COMPUTED"  # the strategy itself streams; only its OI strikes do not
    oi = body["open_interest"]
    assert oi["available"] is False and oi["rows"] == [] and oi["read_at"] is None
    assert oi["unavailable_reason"] == render_explanation("outcome_oi_not_streaming")
    assert oi["unavailable_reason"].startswith("OI not available for this expiry")


def test_stale_in_hours_says_why_and_draws_no_bar():
    late = _market(IN_HOURS_LATE)
    oi = _body(late, S54, at=IN_HOURS_LATE, open_interest=True)["open_interest"]
    assert oi["available"] is False and oi["rows"] == []
    assert oi["unavailable_reason"] == render_explanation("outcome_oi_stale")


def test_after_hours_shows_the_last_oi_with_its_own_time():
    closed = _market(AFTER_CLOSE)
    body = _body(closed, S54, at=AFTER_CLOSE, open_interest=True)
    oi = body["open_interest"]
    assert body["market_closed"] is True and oi["available"] is True and oi["rows"]
    assert datetime.datetime.fromisoformat(oi["read_at"]) < AFTER_CLOSE  # the quotes' time, not the answer time
    chain = _chain_oi(closed)
    assert all(r["put_oi"] == chain[(Decimal(r["strike"]), "PE")] for r in oi["rows"])


def test_no_live_data_says_why():
    req = OutcomeRequest.model_validate({"underlying": "NIFTY", "open_interest": True, "legs": [
        {"instrument_id": "NSE_FO:44616", "action": "BUY", "lots": 1, "planned_entry": "101.55",
         "captured_at": VALUATION.isoformat()}]})
    oi = outcome_response(req, None).model_dump(mode="json", exclude_unset=True)["open_interest"]
    assert oi["available"] is False and oi["rows"] == []
    assert oi["unavailable_reason"] == render_explanation("outcome_oi_not_connected")


def test_open_interest_must_be_a_real_boolean():
    with pytest.raises(ValueError):
        OutcomeRequest.model_validate({"underlying": "NIFTY", "open_interest": "yes", "legs": [
            {"instrument_id": "NSE_FO:44616", "action": "BUY", "lots": 1, "planned_entry": "1",
             "captured_at": VALUATION.isoformat()}]})


# ---- the live push's lease (threat: a lease that is never released) ---------------------------------------------

class _Channel:
    def __init__(self):
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.sent: list = []

    async def receive(self):
        item = await self.inbound.get()
        if item is ChannelClosed:
            raise ChannelClosed()
        return item

    async def send(self, source):
        self.sent.append(source)


class _Mono:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


async def _until(cond, n=200):
    for _ in range(n):
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


def _payload(provider, legs, **extra) -> dict:
    return _req(provider, legs, **extra).model_dump(mode="json", exclude_defaults=True)


async def test_push_holds_the_oi_strikes_and_releases_them_when_asked_and_when_the_socket_ends():
    provider = _market()
    feed = LiveFeed(MarketContext(provider, _Clock(VALUATION), RATE), FanOut(provider))
    channel, mono = _Channel(), _Mono()
    push = StrategyPush(channel, feed, monotonic=mono, poll=0.005)
    task = asyncio.create_task(push.run())
    far = next(contract_id(lc) for lc in provider.instrument_master()
               if lc.contract.name == "NIFTY" and lc.contract.expiry == EXPIRY
               and lc.contract.strike == Decimal("21500") and lc.contract.instrument_type == "PE")
    try:
        await channel.inbound.put(_payload(provider, S54, open_interest=True))
        assert await _until(lambda: feed.fanout.subscriber_count(far) > 0)  # an OI strike far from the money: held
        assert channel.sent and channel.sent[-1].open_interest.available is True
        mono.now += 2
        await channel.inbound.put(_payload(provider, S54))  # the chart stops asking for OI
        assert await _until(lambda: feed.fanout.subscriber_count(far) == 0)
        mono.now += 2
        await channel.inbound.put(_payload(provider, S54, open_interest=True))
        assert await _until(lambda: feed.fanout.subscriber_count(far) > 0)
        await channel.inbound.put(ChannelClosed)
        await asyncio.wait_for(task, 5)
        assert feed.fanout.subscriber_count(far) == 0  # the socket ended: nothing it held for OI is left
        assert all(feed.fanout.subscriber_count(i) == 0 for i, _a in S54)
    finally:
        if not task.done():
            task.cancel()
