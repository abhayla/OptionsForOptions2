"""Lane N round 3 defect 3 (ADR-330 (39), ADR-016..019): the push listener carried ``book.get(...) or quote``, so while
the book was awaiting its seed (or hid / rejected a frame) the raw incoming frame, health AVAILABLE, reached every
consumer. RCA: the fallback `or quote`. Fix: the push carries only what the book serves; None -> nothing is pushed."""
import datetime

from _kite_fixture import NIFTY_CE_ID, new_provider
from ofo.timeutil import IST_UNNAMED as SEC_TZ

AT = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=SEC_TZ)


def _ltp_frame(token: int, paise: int) -> bytes:
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + paise.to_bytes(4, "big")


def _held(book_answer):
    provider, _clock, _items = new_provider()
    seen = []
    provider.live_quote_stream(seen.append)
    provider.on_connected(AT)
    provider.subscribe([NIFTY_CE_ID])
    provider.drain_subscription_changes()
    if book_answer == "nothing":
        provider.book.get = lambda _i, _now: None  # awaiting its seed / hidden / rejected
    return provider, seen, provider._token_of[NIFTY_CE_ID]


def test_a_frame_the_book_does_not_serve_is_pushed_to_no_one():
    provider, seen, token = _held("nothing")
    out = provider.on_frame(_ltp_frame(token, 12345), AT)
    assert out and seen == [], "the raw frame (health AVAILABLE) reached the push listener"


def test_a_frame_the_book_serves_is_pushed_as_the_book_serves_it():
    provider, seen, token = _held("serves")
    provider.on_frame(_ltp_frame(token, 12345), AT)
    assert len(seen) == 1
    assert seen[0] == provider.book.get(NIFTY_CE_ID, AT)
