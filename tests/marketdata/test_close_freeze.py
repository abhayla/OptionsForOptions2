"""ADR-330 (36), issue #752 (amends ADR-200 (2)): "Freeze at 15:30". After the close the figure is the last price
received up to the calendar close; later frames are ignored for the figure, so the label "Prices are from 15:30:00"
and the number agree. The ONE place is the quote book (``QuoteBook``), the single store every price read goes through.

Real sequence of the after-close check (26 Nov 2026, trade 185's 25750 PE): 99.75, then 99.60, then 100.10 under one
label. Rebuilt here with 15:29:59 -> 99.75, 15:31:10 -> 99.60, 15:33:48 -> 100.10 on Tue 1 Dec 2026, as REAL packets
decoded by the real ``parse_frame`` in the real ``KiteProvider``; the clock is injected.

Answer states: in session (latest, unchanged); after close with a pre-close quote (the at-close one); after close with
only post-close quotes (nothing at close is held: the FIRST post-close frame is frozen, with its OWN time, LR-Q17;
later frames are ignored, owner PC 27 Nov, Lane N A2);
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


def test_only_post_close_quotes_held_freezes_the_first_frame_with_its_own_time():
    """ADR-330 (36) + ADR-200 (2)(b), owner PC 27 Nov: a contract first priced after the close (an API restart after
    15:30, a strike first subscribed after hours) has no at-close quote. Its FIRST frame (99.60 at 15:31:10) is frozen
    as its close and carries its own time; the later 100.10 at 15:33:48 is ignored for the figure, so the price does
    not keep moving under "Market closed"."""
    provider, clock = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                            ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    quote = _served(provider, clock, _at(TUE, 15, 34, 0))
    assert (quote.ltp, quote.price_at) == (Decimal("99.60"), _at(TUE, 15, 31, 10))
    assert quote.price_at != _at(TUE, 15, 30, 0)  # never clamped to the calendar close
    assert [q.ltp for q in provider.book.quotes(_at(TUE, 15, 34, 0)) if q.instrument_id == OPTION_ID] == [
        Decimal("99.60")]


def test_a_later_frame_never_changes_the_served_price_of_a_frozen_first_frame_contract():
    """Serve, then three more frames arrive, serve again: the figure and its time are unchanged each time."""
    provider, clock = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)))
    first = _served(provider, clock, _at(TUE, 15, 31, 20))
    for ltp, at in (("100.10", _at(TUE, 15, 33, 48)), ("98.00", _at(TUE, 16, 5, 0)), ("101.00", _at(TUE, 18, 0, 0))):
        clock.now = at
        provider.on_frame(_packet(ltp, at), at)
        again = _served(provider, clock, at)
        assert (again.ltp, again.price_at) == (first.ltp, first.price_at) == (Decimal("99.60"), _at(TUE, 15, 31, 10))


def test_path_a_label_is_the_last_price_made_by_the_close_path_b_label_is_its_own():
    """Both paths side by side on the real sequence: (a) a process that ran through the close serves 99.75 made at
    15:29:59; (b) a fresh provider fed only the two post-close frames serves its FIRST, 99.60 made at 15:31:10."""
    ran, clock_a = _real_sequence()
    a = _served(ran, clock_a, _at(TUE, 15, 40, 0))
    fresh, clock_b = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                           ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    b = _served(fresh, clock_b, _at(TUE, 15, 40, 0))
    assert (a.ltp, a.price_at) == (Decimal("99.75"), _at(TUE, 15, 29, 59))
    assert (b.ltp, b.price_at) == (Decimal("99.60"), _at(TUE, 15, 31, 10))


def test_the_market_opening_again_releases_the_frozen_first_frame():
    """Frozen after the close on Tue; Wed 09:15:00 the market is open: the latest frame is served, and a new in-session
    frame becomes the new at-close quote for Wed's close."""
    nxt = datetime.date(2026, 12, 2)
    provider, clock = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                            ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    assert _served(provider, clock, _at(nxt, 9, 14, 59)).ltp == Decimal("99.60")  # one second before: still frozen
    assert _served(provider, clock, _at(nxt, 9, 15, 0)).ltp == Decimal("100.10")  # open: released
    clock.now = _at(nxt, 10, 0, 0)
    provider.on_frame(_packet("103.00", _at(nxt, 10, 0, 0)), _at(nxt, 10, 0, 0))
    assert _served(provider, clock, _at(nxt, 10, 0, 1)).ltp == Decimal("103.00")
    clock.now = _at(nxt, 15, 40, 0)
    provider.on_frame(_packet("104.00", _at(nxt, 15, 40, 0)), _at(nxt, 15, 40, 0))
    assert _served(provider, clock, _at(nxt, 15, 41, 0)).ltp == Decimal("103.00")  # Wed's own close, not Tue's


def test_no_frame_at_all_is_unpriced_with_its_reason_never_a_default():
    from ofo.marketdata.provider import NOT_HELD  # noqa: PLC0415

    provider, _clock = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)))
    other = "NSE_FO:44632"  # a held-by-catalogue contract that never got a frame
    now = _at(TUE, 15, 40, 0)
    assert provider.book.get(other, now) is None
    assert provider.book.depth_after_close(other, now) is None
    answer = provider.book.latest_day_stats(other, now)
    assert (answer.stats, answer.reason) == (None, NOT_HELD)


def test_depth_after_close_comes_from_the_frozen_frame_not_a_later_one():
    """Depth levels carry prices: after the close they must be the frame the served quote came from. Frame 1 (99.60):
    best bid 99.55, best ask 99.65; the later 100.10 frame (bid 100.05) is ignored. ``latest_depth`` (an order
    input, AVAILABLE only) is None while the market is closed: unchanged."""
    provider, _clock = _feed(("99.60", _at(TUE, 15, 31, 10), _at(TUE, 15, 31, 10)),
                             ("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    now = _at(TUE, 15, 34, 0)
    held = provider.book.depth_after_close(OPTION_ID, now)
    assert held is not None and held[0] is not None
    assert (held[0].bids[0].price, held[0].asks[0].price) == (Decimal("99.55"), Decimal("99.65"))
    assert provider.book.latest_depth(OPTION_ID, now) is None


def test_depth_after_close_of_a_contract_that_ran_through_the_close_is_the_close_frames():
    provider, _clock = _real_sequence()
    held = provider.book.depth_after_close(OPTION_ID, _at(TUE, 15, 34, 0))
    assert held is not None and held[0] is not None
    assert held[0].bids[0].price == Decimal("99.70")  # the 15:29:59 frame (99.75), not the 15:33:48 one


def test_a1_fresh_book_after_a_restart_a_frame_for_a_held_leg_shows_its_price_with_its_own_time():
    """A1 (owner PC 27 Nov): API restarted at 15:50 IST (a fresh book, nothing before the close); the open paper leg is
    held (subscribed), a frame arrives at 15:50:12. The paper DISPLAY price (ADR-212) is that price with its own time,
    not "no live quote"; a later frame does not move it."""
    from ofo.outcome import read_snapshot  # noqa: PLC0415
    from ofo.settings import calc as fq_calc  # noqa: PLC0415
    from ofo.settings import defaults as fq_defaults  # noqa: PLC0415
    from ofo.tracking import paper  # noqa: PLC0415

    day = datetime.date(2026, 10, 12)  # Monday, a trading day; the fixture's NIFTY expiry is 13 Oct
    provider, clock = _feed(("99.60", _at(day, 15, 50, 12), _at(day, 15, 50, 12)))
    quality = fq_calc.forward_quality(fq_defaults())

    def shown(at: datetime.datetime):
        clock.now = at
        snap = read_snapshot(provider, "NIFTY", [OPTION_ID], at, Decimal("0.065"), quality=quality)
        assert snap.market_closed is True
        return paper.display_price(snap, OPTION_ID)

    price = shown(_at(day, 15, 51, 0))
    assert (price.state, price.price, price.at) == ("live", Decimal("99.60"), _at(day, 15, 50, 12))
    provider.on_frame(_packet("101.00", _at(day, 15, 55, 0)), _at(day, 15, 55, 0))
    again = shown(_at(day, 15, 56, 0))
    assert (again.price, again.at) == (Decimal("99.60"), _at(day, 15, 50, 12))


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


# ---- round 2 (Tier A review of 4c8016b0): once a price is served after the close it never moves until the next open
MON = datetime.date(2026, 11, 30)
WED = datetime.date(2026, 12, 2)


def _frame_at(provider: KiteProvider, clock: Clock, ltp: str, stamp: datetime.datetime) -> None:
    clock.now = stamp
    provider.on_frame(_packet(ltp, stamp), stamp)


def test_a7_an_earlier_sessions_close_is_frozen_when_first_served_and_a_later_post_close_frame_never_moves_it():
    """Case A7: Mon 15:29:59 held at 80, no Tue frame. Tue 15:31 serves it (own date-time Mon 15:29:59); a Tue 15:35
    frame at 85 arrives; Tue 15:41 still serves 80 (the figure shown does not move until the next open)."""
    provider, clock = _feed(("80.00", _at(MON, 15, 29, 59), _at(MON, 15, 29, 59)))
    first = _served(provider, clock, _at(TUE, 15, 31, 0))
    assert (first.ltp, first.price_at) == (Decimal("80.00"), _at(MON, 15, 29, 59))
    _frame_at(provider, clock, "85.00", _at(TUE, 15, 35, 0))
    later = _served(provider, clock, _at(TUE, 15, 41, 0))
    assert (later.ltp, later.price_at) == (Decimal("80.00"), _at(MON, 15, 29, 59))
    assert [q.ltp for q in provider.book.quotes(_at(TUE, 15, 41, 0)) if q.instrument_id == OPTION_ID] == [
        Decimal("80.00")]
    held = provider.book.depth_after_close(OPTION_ID, _at(TUE, 15, 41, 0))
    assert held is not None and held[0] is not None and held[0].bids[0].price == Decimal("79.95")  # Mon's frame depth


def test_a7_never_read_after_the_close_the_first_post_close_frame_is_the_figure():
    """The same sequence with no read between 15:31 and 15:35: nothing was served, so the first frame of the session
    (85 at 15:35, own time) is the figure and the later 90 does not move it."""
    provider, clock = _feed(("80.00", _at(MON, 15, 29, 59), _at(MON, 15, 29, 59)))
    _frame_at(provider, clock, "85.00", _at(TUE, 15, 35, 0))
    _frame_at(provider, clock, "90.00", _at(TUE, 15, 50, 0))
    quote = _served(provider, clock, _at(TUE, 15, 51, 0))
    assert (quote.ltp, quote.price_at) == (Decimal("85.00"), _at(TUE, 15, 35, 0))


def test_a4e_a_frame_before_the_open_is_that_days_price_at_its_close_not_the_previous_days_frozen_one():
    """Case A4e: Tue frozen 15:33:48 at 100.10. Wed 09:10 frame at 103 shows in hours AND at Wed 15:31 (it is made by
    Wed's close); the screen never jumps back to Tue's 100.10."""
    provider, clock = _feed(("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    assert _served(provider, clock, _at(TUE, 15, 34, 0)).ltp == Decimal("100.10")
    _frame_at(provider, clock, "103.00", _at(WED, 9, 10, 0))
    assert _served(provider, clock, _at(WED, 9, 20, 0)).ltp == Decimal("103.00")
    after = _served(provider, clock, _at(WED, 15, 31, 0))
    assert (after.ltp, after.timestamp) == (Decimal("103.00"), _at(WED, 9, 10, 0))


def test_a_quiet_contract_with_only_yesterdays_post_close_frame_keeps_it_with_its_own_date_time():
    provider, clock = _feed(("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    quote = _served(provider, clock, _at(WED, 15, 31, 0))
    assert (quote.ltp, quote.price_at) == (Decimal("100.10"), _at(TUE, 15, 33, 48))
    _frame_at(provider, clock, "105.00", _at(WED, 15, 40, 0))
    assert _served(provider, clock, _at(WED, 15, 41, 0)).ltp == Decimal("100.10")


def test_a3_a_late_frame_made_by_the_close_wins_only_if_nothing_was_served_yet():
    """F3: a frame stamped 15:29:58 at 99.70 arrives after the first post-close frame (15:33:48 at 100.10). Not yet
    served: the true close (99.70) is the figure. Already served: the shown 100.10 never moves."""
    unread, clock_u = _feed(("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    _frame_at(unread, clock_u, "99.70", _at(TUE, 15, 29, 58))
    quote = _served(unread, clock_u, _at(TUE, 15, 40, 0))
    assert (quote.ltp, quote.price_at) == (Decimal("99.70"), _at(TUE, 15, 29, 58))
    read, clock_r = _feed(("100.10", _at(TUE, 15, 33, 48), _at(TUE, 15, 33, 48)))
    assert _served(read, clock_r, _at(TUE, 15, 34, 0)).ltp == Decimal("100.10")
    _frame_at(read, clock_r, "99.70", _at(TUE, 15, 29, 58))
    again = _served(read, clock_r, _at(TUE, 15, 40, 0))
    assert (again.ltp, again.price_at) == (Decimal("100.10"), _at(TUE, 15, 33, 48))


def test_a_frame_stamped_before_the_close_never_replaces_a_newer_in_session_close_frame():
    provider, clock = _feed(("99.75", _at(TUE, 15, 29, 59), _at(TUE, 15, 29, 59)))
    _frame_at(provider, clock, "99.10", _at(TUE, 15, 29, 10))  # arrives late, stamped earlier
    assert _served(provider, clock, _at(TUE, 15, 40, 0)).ltp == Decimal("99.75")
