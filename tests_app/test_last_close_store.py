"""Lane N A1 / AF-02: the stored last close (ADR-330 (36), ADR-212, ADR-008). Fakes only: no database here.

The sequence is the real one of 26 Nov rebuilt on Tue 1 Dec 2026 (99.75 at 15:29:59, then 99.60 at 15:31:10, then
100.10 at 15:33:48 for NIFTY 22550 CE), as real packets through the real KiteProvider and its QuoteBook. Answer states:
writer before the close / at the close / on a holiday / process started after the close / database dead then back;
reader market open / closed with no stored row / today's close already held / an earlier day's row / first live tick.
"""
from __future__ import annotations

import asyncio
import datetime
import struct
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from marketdata._kite_fixture import Clock, all_instrument_ids, listed
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import last_close_store as lcs

OPTION_TOKEN = 11421186
OPTION_ID = "NSE_FO:44614"
TUE = datetime.date(2026, 12, 1)
MON = datetime.date(2026, 11, 30)
WED = datetime.date(2026, 12, 2)
HOLIDAY = datetime.date(2026, 10, 20)
LAST_TICK = 5
EXCHANGE = {"NSE_FO": "NSE", "BSE_FO": "BSE", "NSE_INDEX": "NSE", "BSE_INDEX": "BSE"}


def at(day: datetime.date, hh: int, mm: int = 0, ss: int = 0) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=IST)


def packet(ltp: str, ts: datetime.datetime) -> bytes:
    paise = int(Decimal(ltp) * 100)
    head = struct.pack(">11i", OPTION_TOKEN, paise, 65, paise, 0, 0, 0, 0, 0, 0, 0)
    rest = struct.pack(">5i", 0, 1000, 0, 0, int(ts.timestamp()))
    bid, ask = struct.pack(">iihh", 65, paise - 5, 1, 0), struct.pack(">iihh", 65, paise + 5, 1, 0)
    empty = b"\x00" * 12
    body = head + rest + bid + empty * 4 + ask + empty * 4
    return (1).to_bytes(2, "big") + len(body).to_bytes(2, "big") + body


def provider_with(*frames: tuple[str, datetime.datetime]) -> KiteProvider:
    """One frame per (ltp, exchange time); each arrives at its own time."""
    start = frames[0][1] if frames else at(TUE, 10)
    provider = KiteProvider(listed(), clock=Clock(start))
    provider.subscribe(all_instrument_ids(listed()))
    provider.on_connected(start)
    for ltp, ts in frames:
        provider.on_frame(packet(ltp, ts), ts)
    return provider


def real_day() -> KiteProvider:
    return provider_with(("99.75", at(TUE, 15, 29, 59)), ("99.60", at(TUE, 15, 31, 10)),
                         ("100.10", at(TUE, 15, 33, 48)))


class FakeStore:
    def __init__(self, latest=None, fail: int = 0) -> None:
        self.written: list[list] = []
        self.latest = latest or {}
        self.reads = 0
        self.fail = fail

    def write_closes(self, rows):
        rows = list(rows)
        if self.fail:
            self.fail -= 1
            raise OSError("database down")
        self.written.append(rows)
        return len(rows)

    def read_latest(self, ids=None):
        self.reads += 1
        return dict(self.latest)


def writer(provider, store, started: datetime.datetime) -> lcs.CloseWriter:
    return lcs.CloseWriter(store, lambda: provider.book, started_at=started)


# ---- the writer ---------------------------------------------------------------------------------------------------
def test_no_write_one_second_before_the_close():
    store = FakeStore()
    assert writer(real_day(), store, at(TUE, 9, 30)).step(at(TUE, 15, 29, 59)) is None
    assert store.written == []


def test_write_once_after_the_close_with_the_frame_made_by_the_close():
    store = FakeStore()
    w = writer(real_day(), store, at(TUE, 9, 30))
    assert w.step(at(TUE, 15, 30, 4)) is None  # inside the grace
    assert w.step(at(TUE, 15, 30, 5)) and len(store.written) == 1
    row = next(r for r in store.written[0] if r[0] == OPTION_ID)
    assert row == (OPTION_ID, TUE, Decimal("99.75"), at(TUE, 15, 29, 59), "feed_book")  # not the 15:31 / 15:33 frames
    assert w.step(at(TUE, 15, 31)) is None and len(store.written) == 1  # once per day


def test_a_holiday_writes_nothing():
    store = FakeStore()
    w = writer(provider_with(("99.75", at(HOLIDAY, 15, 29, 59))), store, at(HOLIDAY, 9))
    assert w.step(at(HOLIDAY, 15, 30, 5)) is None and store.written == []


def test_app_down_at_the_close_leaves_no_row_for_the_day():
    store = FakeStore()
    w = writer(provider_with(("100.10", at(TUE, 15, 50, 1))), store, at(TUE, 15, 50))  # restarted at 15:50
    for now in (at(TUE, 15, 50, 2), at(TUE, 16), at(WED, 8)):
        assert w.step(now) is None
    assert store.written == []
    w2 = writer(provider_with(("99.60", at(TUE, 15, 32))), store, at(TUE, 15, 31))  # started 15:31: still no row
    assert w2.step(at(TUE, 15, 35)) is None and store.written == []


def test_post_close_frames_are_never_written_as_the_close():
    store = FakeStore()
    w = writer(provider_with(("100.10", at(TUE, 15, 33, 48))), store, at(TUE, 9, 30))  # up at the close, no frame by it
    assert w.step(at(TUE, 15, 34)) == 0
    assert all(r[0] != OPTION_ID for rows in store.written for r in rows)


def test_a_dead_database_is_a_logged_error_and_a_retry_never_a_fault():
    store = FakeStore(fail=1)
    w = writer(real_day(), store, at(TUE, 9, 30))
    assert w.step(at(TUE, 15, 30, 6)) is None and w.counters["errors"] == 1
    assert w.step(at(TUE, 15, 31)) and len(store.written) == 1  # back inside the window: written
    assert w.step(at(TUE, 15, 32)) is None  # and not again


def test_no_retry_after_the_window():
    store = FakeStore(fail=99)
    w = writer(real_day(), store, at(TUE, 9, 30))
    assert w.step(at(TUE, 15, 30, 6)) is None
    assert w.step(at(TUE, 15, 41)) is None and store.written == []


# ---- Decimal / paisa refusal --------------------------------------------------------------------------------------
@pytest.mark.parametrize("price", [99.75, Decimal("99.755"), Decimal("NaN"), Decimal("-1.00"), 99, True,
                                   Decimal("1000000000000.00")])
def test_a_float_or_sub_paisa_or_out_of_range_price_is_refused(price):
    with pytest.raises(ValueError):
        lcs.check_row((OPTION_ID, TUE, price, at(TUE, 15, 29, 59), "feed_book"))


@pytest.mark.parametrize("price_at", [at(MON, 15, 29, 59), at(TUE, 15, 30, 1), at(TUE, 20, 0), at(WED, 9, 20)])
def test_m6_a_time_off_the_trade_date_or_after_the_close_is_refused(price_at):
    with pytest.raises(ValueError, match="trade date"):
        lcs.check_row((OPTION_ID, TUE, Decimal("99.75"), price_at, "feed_book"))


@pytest.mark.parametrize("price_at", [at(TUE, 9, 0), at(TUE, 15, 29, 59), at(TUE, 15, 30, 0)])
def test_m6_a_time_on_the_trade_date_up_to_the_close_is_taken(price_at):
    lcs.check_row((OPTION_ID, TUE, Decimal("99.75"), price_at, "feed_book"))


def test_the_store_refuses_before_any_connection_and_writes_nothing():
    store = lcs.PostgresLastCloseStore("postgresql+asyncpg://nobody@127.0.0.1:1/none")
    try:
        good = (OPTION_ID, TUE, Decimal("99.75"), at(TUE, 15, 29, 59), "feed_book")
        with pytest.raises(ValueError):
            store.write_closes([good, (OPTION_ID, MON, 99.75, at(MON, 15, 29), "feed_book")])
        assert store.write_closes([]) == 0
    finally:
        store.close()


# ---- the reader ---------------------------------------------------------------------------------------------------
def test_a_stored_close_is_seeded_only_while_the_market_is_closed():
    provider = provider_with()
    store = FakeStore({OPTION_ID: (Decimal("77.00"), at(MON, 15, 29, 30), MON)})
    assert lcs.seed_book(provider, store, at(TUE, 11)) is None  # open: not asked, NOT READ
    assert store.reads == 0 and provider.book.get(OPTION_ID, at(TUE, 11)) is None
    assert lcs.seed_book(provider, store, at(TUE, 15, 40)) == 1 and store.reads == 1


def test_an_earlier_days_row_is_served_with_its_own_date_and_time():
    provider = provider_with()
    lcs.seed_book(provider, FakeStore({OPTION_ID: (Decimal("77.00"), at(MON, 15, 29, 30), MON)}), at(TUE, 15, 40))
    q = provider.book.get(OPTION_ID, at(TUE, 15, 41))
    assert (q.ltp, q.timestamp, q.price_at) == (Decimal("77.00"), at(MON, 15, 29, 30), at(MON, 15, 29, 30))


def test_seeding_never_overrides_the_close_the_book_already_holds():
    provider = real_day()
    lcs.seed_book(provider, FakeStore({OPTION_ID: (Decimal("88.00"), at(TUE, 15, 29, 0), TUE)}), at(TUE, 15, 40))
    assert provider.book.get(OPTION_ID, at(TUE, 15, 41)).ltp == Decimal("99.75")


def test_a_restart_after_the_close_serves_the_stored_close_not_a_later_frame():
    provider = provider_with(("100.10", at(TUE, 15, 50, 1)))  # restarted: only a post-close snapshot tick
    lcs.seed_book(provider, FakeStore({OPTION_ID: (Decimal("99.75"), at(TUE, 15, 29, 59), TUE)}), at(TUE, 15, 51))
    q = provider.book.get(OPTION_ID, at(TUE, 15, 52))
    assert (q.ltp, q.timestamp) == (Decimal("99.75"), at(TUE, 15, 29, 59))


def test_while_open_the_seeded_figure_is_hidden_and_the_first_live_tick_wins():
    provider = provider_with()
    lcs.seed_book(provider, FakeStore({OPTION_ID: (Decimal("99.75"), at(TUE, 15, 29, 59), TUE)}), at(TUE, 16))
    assert provider.book.get(OPTION_ID, at(TUE, 16)).ltp == Decimal("99.75")
    open_now = at(WED, 9, 20)
    assert provider.book.get(OPTION_ID, open_now) is None
    assert all(q.instrument_id != OPTION_ID for q in provider.book.quotes(open_now))
    provider.on_frame(packet("101.00", open_now), open_now)
    assert provider.book.get(OPTION_ID, open_now).ltp == Decimal("101.00")


def test_a_row_with_no_catalogue_contract_or_a_bad_time_is_skipped():
    provider = provider_with()
    latest = {"NSE_FO:1": (Decimal("1.00"), at(MON, 15, 29), MON),
              OPTION_ID: (Decimal("5.00"), at(MON, 16, 5), MON)}  # after the close: not a close
    assert lcs.seed_book(provider, FakeStore(latest), at(TUE, 16)) == 0
    assert provider.book.get(OPTION_ID, at(TUE, 16)) is None


def test_the_index_is_seeded_too():
    provider = provider_with()
    nifty = provider.index_id("NIFTY")
    lcs.seed_book(provider, FakeStore({nifty: (Decimal("25000.50"), at(MON, 15, 29, 58), MON)}), at(TUE, 16))
    q = provider.book.get(nifty, at(TUE, 16))
    assert q.ltp == Decimal("25000.50") and q.instrument_type is None


# ---- the task -----------------------------------------------------------------------------------------------------
def test_the_task_seeds_once_and_writes_once_then_survives_a_failure():
    provider = real_day()
    store = FakeStore({}, fail=1)
    now = [at(TUE, 15, 29, 56)]
    ctx = type("Ctx", (), {"clock": staticmethod(lambda: now[0]), "provider": provider})()
    market = type("Market", (), {"feed": type("Feed", (), {"ctx": ctx})()})()
    ticks: list[int] = []

    async def sleep(_):
        ticks.append(1)
        now[0] += datetime.timedelta(seconds=5)
        if len(ticks) == LAST_TICK:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(lcs.run_forever(market, store, sleep=sleep))
    assert store.reads == 1 and len(store.written) == 1  # first write failed, the retry wrote


def test_no_market_no_task():
    assert lcs.start(None) is None


def test_the_seeded_quote_has_the_feeds_own_source_and_exchange():
    provider = provider_with(("99.75", at(TUE, 15, 29, 59)))
    live = provider.book.get(OPTION_ID, at(TUE, 15, 40))
    lc = next(x for x in listed() if f"{x.contract.exchange_segment}:{x.contract.exchange_token}" == OPTION_ID)
    seeded = lcs.quote_of(lc, Decimal("99.75"), at(TUE, 15, 29, 59))
    assert (seeded.source, seeded.exchange, seeded.segment) == (live.source, live.exchange, live.segment)
    for lc in listed():  # every catalogue row: the exchange the provider names
        quote = lcs.quote_of(lc, Decimal("1.00"), at(MON, 15, 29))
        if quote is not None:
            assert quote.exchange == EXCHANGE[quote.segment]
