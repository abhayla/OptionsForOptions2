"""ADR-330 (36), issue #752 (amends ADR-200 (2)): "Freeze at 15:30". After the close the figure is the last price
received up to the calendar close; later frames are ignored for the figure, so the label "Prices are from 15:30:00"
and the number agree. The ONE place is the quote book (``QuoteBook``), the single store every price read goes through.

Real sequence of the after-close check (26 Nov 2026, trade 185's 25750 PE): 99.75, then 99.60, then 100.10 under one
label. Rebuilt here with 15:29:59 -> 99.75, 15:31:10 -> 99.60, 15:33:48 -> 100.10 on Tue 1 Dec 2026, as REAL packets
decoded by the real ``parse_frame`` in the real ``KiteProvider``; the clock is injected.

Answer states: in session (latest, unchanged); after close with a pre-close quote (the at-close one); after close with
only post-close quotes (nothing at close is held: the latest frame, its OWN time, LR-Q17);
holiday (the previous session's close quote); no exchange time (the frame's arrival time is its time, so it is
cut by when it arrived)."""
from __future__ import annotations

import datetime
import struct
from decimal import Decimal

from _kite_fixture import Clock, all_instrument_ids, listed
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.rules.inputs import DataHealth

OPTION_TOKEN = 11421186  # NSE_FO:44614, NIFTY 22550 CE in the catalogue fixture
OPTION_ID = "NSE_FO:44614"
TUE = datetime.date(2026, 12, 1)
HOLIDAY = datetime.date(2026, 10, 20)  # Dussehra, a Tuesday NSE F&O holiday


def _at(day: datetime.date, hh: int, mm: int, ss: int) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=IST)


def _packet(ltp: str, exchange_ts: datetime.datetime | None) -> bytes:
    """A 184-byte full packet of the option; ``exchange_ts`` None writes time 0 (no exchange time)."""
    paise = int(Decimal(ltp) * 100)
    head = struct.pack(">11i", OPTION_TOKEN, paise, 65, paise, 0, 0, 0, 0, 0, 0, 0)
    rest = struct.pack(">5i", 0, 1000, 0, 0, 0 if exchange_ts is None else int(exchange_ts.timestamp()))
    level = struct.pack(">iihh", 65, paise - 5, 1, 0)
    ask = struct.pack(">iihh", 65, paise + 5, 1, 0)
    empty = b"\x00" * 12
    body = head + rest + level + empty * 4 + ask + empty * 4
    return (1).to_bytes(2, "big") + len(body).to_bytes(2, "big") + body


def _feed(*frames: tuple[str, datetime.datetime | None, datetime.datetime]) -> tuple[KiteProvider, Clock]:
    """(ltp, exchange time, arrival time) per frame, in order; the clock ends at the last arrival."""
    start = frames[0][2]
    clock = Clock(start)
    provider = KiteProvider(listed(), clock=clock)
    provider.subscribe(all_instrument_ids(listed()))
    provider.on_connected(start)
    for ltp, exchange_ts, arrived in frames:
        clock.now = arrived
        provider.on_frame(_packet(ltp, exchange_ts), arrived)
    return provider, clock


def _served(provider: KiteProvider, clock: Clock, at: datetime.datetime):
    clock.now = at
    quote = provider.book.get(OPTION_ID, at)
    assert quote is not None
    return quote


def _real_sequence() -> tuple[KiteProvider, Clock]:
    return _feed(("99.75", _at(TUE, 15, 29, 59), _at(TUE, 15, 29, 59)),
                 ("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                 ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))


def test_after_the_close_the_figure_is_the_last_price_up_to_the_close_not_a_later_frame():
    provider, clock = _real_sequence()
    quote = _served(provider, clock, _at(TUE, 15, 34, 0))
    made = _at(TUE, 15, 29, 59)
    assert (quote.ltp, quote.timestamp, quote.price_at) == (Decimal("99.75"), made, made)
    assert quote.health is DataHealth.STALE  # closed: never live, as before
    listed_now = provider.book.quotes(_at(TUE, 15, 34, 0))
    assert [q.ltp for q in listed_now if q.instrument_id == OPTION_ID] == [Decimal("99.75")]


def test_in_session_the_latest_frame_is_served_unchanged():
    provider, clock = _feed(("99.50", _at(TUE, 15, 29, 0), _at(TUE, 15, 29, 0)),
                            ("99.75", _at(TUE, 15, 29, 59), _at(TUE, 15, 29, 59)))
    quote = _served(provider, clock, _at(TUE, 15, 29, 59))
    assert (quote.ltp, quote.health) == (Decimal("99.75"), DataHealth.AVAILABLE)


def test_a_frame_stamped_exactly_at_the_close_is_the_close_price():
    provider, clock = _feed(("99.75", _at(TUE, 15, 29, 59), _at(TUE, 15, 29, 59)),
                            ("99.80", _at(TUE, 15, 30, 0), _at(TUE, 15, 30, 1)),
                            ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    assert _served(provider, clock, _at(TUE, 15, 40, 0)).ltp == Decimal("99.80")


def test_only_post_close_quotes_held_serves_the_latest_with_its_own_time():
    """ADR-330 (36) path (b), LR-Q17: a contract first priced after the close (an API restart after 15:30, a strike
    first subscribed after hours) has no at-close quote. The latest frame is served and labelled with ITS OWN time
    (15:33:48), never clamped to "15:30:00"."""
    provider, clock = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                            ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    quote = _served(provider, clock, _at(TUE, 15, 34, 0))
    assert (quote.ltp, quote.price_at) == (Decimal("100.10"), _at(TUE, 15, 33, 48))
    assert quote.price_at != _at(TUE, 15, 30, 0)


def test_path_a_label_is_the_last_price_made_by_the_close_path_b_label_is_its_own():
    """Both paths side by side on the real sequence: (a) a process that ran through the close serves 99.75 made at
    15:29:59; (b) a fresh provider fed only the two post-close frames serves 100.10 made at 15:33:48."""
    ran, clock_a = _real_sequence()
    a = _served(ran, clock_a, _at(TUE, 15, 40, 0))
    fresh, clock_b = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                           ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    b = _served(fresh, clock_b, _at(TUE, 15, 40, 0))
    assert (a.ltp, a.price_at) == (Decimal("99.75"), _at(TUE, 15, 29, 59))
    assert (b.ltp, b.price_at) == (Decimal("100.10"), _at(TUE, 15, 33, 48))


def _held_overnight() -> tuple[KiteProvider, Clock]:
    """Monday 30 Nov: 99.75 at 15:29:59 (the at-close quote), then 99.60 at 15:31:10 (after the close, the latest)."""
    prev = datetime.date(2026, 11, 30)  # Monday, a trading day
    return _feed(("99.75", _at(prev, 15, 29, 59), _at(prev, 15, 29, 59)),
                 ("99.60", _at(prev, 15, 31, 10), _at(prev, 15, 31, 10)))


def test_during_the_session_the_book_serves_the_latest_quote_not_the_held_close_quote():
    """Guard for the in-hours check in ``_served``: at 10:00 IST on a trading day the book holds an at-close quote
    (99.75) and a later, different latest quote (99.60); the LATEST is served. A ``_served`` that always returns
    close_quote fails this (scratch-copy mutation check recorded in the handover)."""
    provider, clock = _held_overnight()
    assert _served(provider, clock, _at(TUE, 10, 0, 0)).ltp == Decimal("99.60")


def test_exactly_at_the_reopen_the_book_serves_the_latest_quote():
    provider, clock = _held_overnight()
    assert _served(provider, clock, _at(TUE, 9, 15, 0)).ltp == Decimal("99.60")
    assert _served(provider, clock, _at(TUE, 9, 14, 59)).ltp == Decimal("99.75")  # one second before: still closed


def test_a_fresh_process_at_pre_open_labels_the_frame_with_the_previous_close_never_its_arrival():
    """F-19, kept by ADR-330 (36): a provider that starts at 09:10 IST with no overnight close quote serves the pre-open
    frame (exchange stamp 09:08:30, arrived 09:10:05). Before the open a frame's stamp is not a price time, so the label
    is the previous session's close (Mon 30 Nov 15:30), never the 09:10:05 arrival (and the figure is the frame's)."""
    provider, clock = _feed(("100.10", _at(TUE, 9, 8, 30), _at(TUE, 9, 10, 5)))
    quote = _served(provider, clock, _at(TUE, 9, 10, 6))
    prev_close = _at(datetime.date(2026, 11, 30), 15, 30, 0)
    assert (quote.ltp, quote.timestamp, quote.price_at) == (Decimal("100.10"), _at(TUE, 9, 8, 30), prev_close)
    assert quote.price_at != _at(TUE, 9, 10, 5)


def test_a_holiday_serves_the_previous_sessions_close_quote():
    prev = datetime.date(2026, 10, 19)  # Monday, a trading day
    provider, clock = _feed(("99.75", _at(prev, 15, 29, 59), _at(prev, 15, 29, 59)),
                            ("100.10", _at(HOLIDAY, 11, 0, 0), _at(HOLIDAY, 11, 0, 0)))  # frame on the holiday
    quote = _served(provider, clock, _at(HOLIDAY, 11, 1, 0))
    assert (quote.ltp, quote.price_at) == (Decimal("99.75"), _at(prev, 15, 29, 59))


def test_overnight_and_pre_open_frames_do_not_replace_the_close_quote():
    nxt = datetime.date(2026, 12, 2)
    provider, clock = _feed(("99.75", _at(TUE, 15, 29, 59), _at(TUE, 15, 29, 59)),
                            ("100.10", _at(nxt, 9, 8, 0), _at(nxt, 9, 8, 0)))  # pre-open auction frame
    assert _served(provider, clock, _at(nxt, 9, 10, 0)).ltp == Decimal("99.75")


def test_a_frame_with_no_exchange_time_is_cut_by_when_it_arrived():
    provider, clock = _feed(("99.75", None, _at(TUE, 15, 29, 59)),  # no exchange time, arrived in session
                            ("100.10", None, _at(TUE, 15, 33, 48)))  # no exchange time, arrived after the close
    quote = _served(provider, clock, _at(TUE, 15, 34, 0))
    assert (quote.ltp, quote.timestamp) == (Decimal("99.75"), _at(TUE, 15, 29, 59))


def test_a_removed_quote_still_keeps_no_price():
    """The existing rule is untouched: an unsubscribed contract holds no price (ADR-077)."""
    provider, _clock = _real_sequence()
    provider.book.remove(OPTION_ID)
    assert provider.book.get(OPTION_ID, _at(TUE, 15, 34, 0)) is None
