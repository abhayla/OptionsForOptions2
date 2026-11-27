"""ADR-330 (36) (LR-Q18): the one after-close banner function. A trade with legs frozen at the close AND legs first
priced after it reads "Prices are from <frozen>; 1 leg as of <later>" (plural for more); all one kind, or in session:
unchanged. Quotes are real NormalizedQuote values (timestamps on Thursday 8 Oct 2026, a trading day)."""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.engine.legs import Instrument
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app.routes.outcome import MarketState, closed_label

D = Decimal
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 13)
FEED_21 = datetime.datetime(2026, 10, 8, 21, 5, tzinfo=IST)


def _t(hh: int, mm: int, ss: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, 8, hh, mm, ss, tzinfo=IST)


def _q(at: datetime.datetime, *, index: bool = False) -> NormalizedQuote:
    kind, strike = (None, None) if index else (Instrument.CE, D("22500"))
    return NormalizedQuote("NSE_INDEX:256265" if index else "NSE_FO:44612", "NIFTY", "NSE",
                           "INDICES" if index else "NSE_FO", kind, None if index else EXPIRY, strike, D("100.00"),
                           None, None, None, None, None, None,
                           None, None, None, None, at, SourceMetadata("recorded", "kite-2026-10-08"),
                           DataHealth.STALE)


CLOSED = MarketState(closed=True, last_price_at=FEED_21)
IN_HOURS = MarketState(closed=False, last_price_at=_t(11, 0, 1))
SPOT = _q(_t(15, 29, 58), index=True)


def test_one_frozen_leg_and_one_first_priced_later_reads_one_leg_as_of():
    out = closed_label(CLOSED, [_q(_t(15, 30, 0)), _q(_t(15, 33, 48))], SPOT)
    assert str(out.text) == "Market closed. Prices are from 15:30:00; 1 leg as of 15:33:48."
    assert out.last_price_at == _t(15, 30, 0)


def test_the_frozen_time_is_its_own_time_up_to_the_close():
    """A leg frozen at 15:29:59 is labelled 15:29:59 (its own time, ADR-200 (4)), not invented as 15:30:00."""
    out = closed_label(CLOSED, [_q(_t(15, 29, 59)), _q(_t(15, 33, 48))], SPOT)
    assert str(out.text) == "Market closed. Prices are from 15:29:59; 1 leg as of 15:33:48."


def test_two_later_legs_read_the_plural_with_the_earliest_later_time():
    out = closed_label(CLOSED, [_q(_t(15, 29, 59)), _q(_t(15, 36, 5)), _q(_t(15, 33, 48))], SPOT)
    assert str(out.text) == "Market closed. Prices are from 15:29:59; 2 legs as of 15:33:48."


def test_the_spot_is_never_counted_as_a_leg_and_stays_in_the_frozen_group():
    out = closed_label(CLOSED, [_q(_t(15, 20, 0)), _q(_t(15, 33, 48))], SPOT)
    assert str(out.text) == "Market closed. Prices are from 15:29:58; 1 leg as of 15:33:48."
    late_spot = closed_label(CLOSED, [_q(_t(15, 20, 0)), _q(_t(15, 33, 48))], _q(_t(15, 40, 0), index=True))
    assert str(late_spot.text) == "Market closed. Prices are from 15:20:00; 1 leg as of 15:33:48."


def test_all_frozen_is_unchanged():
    out = closed_label(CLOSED, [_q(_t(15, 29, 59)), _q(_t(15, 29, 40))], SPOT)
    assert (out.text, out.last_price_at) == (None, _t(15, 29, 59))


def test_all_first_priced_after_one_shared_time_is_unchanged_no_added_text():
    out = closed_label(CLOSED, [_q(_t(15, 33, 48)), _q(_t(15, 33, 48))], SPOT)
    assert (out.text, out.last_price_at) == (None, _t(15, 33, 48))  # banner: "Market closed. Prices are from 15:33:48."


def test_f4_all_first_priced_after_at_different_times_names_the_earliest_and_counts_the_later_legs():
    """Review F4: legs first priced at 15:33:48 and 15:59:10 read "Prices are from 15:33:48; 1 leg as of 15:59:10",
    never the latest time over a figure that is older."""
    out = closed_label(CLOSED, [_q(_t(15, 33, 48)), _q(_t(15, 59, 10))], SPOT)
    assert str(out.text) == "Market closed. Prices are from 15:33:48; 1 leg as of 15:59:10."
    assert out.last_price_at == _t(15, 33, 48)
    three = closed_label(CLOSED, [_q(_t(15, 33, 48)), _q(_t(15, 59, 10)), _q(_t(16, 2, 0))], SPOT)
    assert str(three.text) == "Market closed. Prices are from 15:33:48; 2 legs as of 15:59:10."


def test_f1_a_price_time_from_an_earlier_day_carries_its_date():
    """Review F1: a leg whose price is from Thursday 8 Oct while the other is from Friday 9 Oct is not read as today's:
    its time is printed with its date."""
    fri = lambda hh, mm, ss: datetime.datetime(2026, 10, 9, hh, mm, ss, tzinfo=IST)  # noqa: E731
    state = MarketState(closed=True, last_price_at=fri(21, 5, 0))
    out = closed_label(state, [_q(fri(15, 30, 0)), _q(_t(15, 40, 0))], None)
    assert str(out.text) == "Market closed. Prices are from 15:30:00; 1 leg as of 8 Oct, 15:40:00."
    older_frozen = closed_label(state, [_q(_t(15, 29, 59)), _q(fri(15, 33, 48))], None)
    assert str(older_frozen.text) == "Market closed. Prices are from 8 Oct, 15:29:59; 1 leg as of 15:33:48."


def test_in_session_is_unchanged():
    out = closed_label(IN_HOURS, [_q(_t(11, 0, 0)), _q(_t(11, 0, 1))], SPOT)
    assert (out.text, out.last_price_at) == (None, IN_HOURS.last_price_at)


def test_no_quotes_invents_no_time():
    assert closed_label(CLOSED, [], None) == closed_label(CLOSED, [None], None)
    assert closed_label(CLOSED, [], None).last_price_at is None
