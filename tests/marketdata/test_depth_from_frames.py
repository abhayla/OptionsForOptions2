"""W-097: the 5-level depth of a Kite full frame, kept in the live book and read for the Execute price (ADR-080 (3)).

The fixture is ONE real packet cut from the 2026-10-16 recording (NIFTY 23650 CE of 19 Oct, token 12080386,
exchange time 15:07:20 IST); its ten levels equal Zerodha's REST quote of that second
(docs/research/depth-proof-2026-10-17).
Expected values below are the REST quote's, typed once from real-order/fetch.json, not read back from the parser.
"""
import dataclasses
import datetime
import struct
from decimal import Decimal

import pytest
from _kite_fixture import FIXTURES, Clock, listed
from ofo.engine.executable_price import Depth, DepthLevel, depth_from_levels, depth_from_quote, executable_limit
from ofo.engine.legs import Action
from ofo.marketdata.kite_frames import parse_frame
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.marketdata.quote import SourceMetadata

FRAME = (FIXTURES / "full-frame-12080386-150720.bin").read_bytes()
TOKEN = 12080386
INSTRUMENT_ID = "NSE_FO:47189"  # exchange token 47189 of NFO, from the catalogue fixture
AT = datetime.datetime.fromtimestamp(1792143440, IST)  # the frame's own exchange time, 15:07:20 IST
TICK = Decimal("0.05")

D = Decimal
BIDS = ((D("3.3"), 55250), (D("3.25"), 67535), (D("3.2"), 57330), (D("3.15"), 51025), (D("3.1"), 47515))
ASKS = ((D("3.35"), 56810), (D("3.4"), 53755), (D("3.45"), 76050), (D("3.5"), 41860), (D("3.55"), 35945))


def _level_at(side_first_index: int, i: int) -> int:
    """Byte offset of depth entry ``i`` of a side inside the 184-byte packet (4-byte frame head + packet at 64+12n)."""
    return 4 + 64 + 12 * (side_first_index + i)


def _with_price(frame: bytes, entry: int, paise: int) -> bytes:
    """The fixture with depth entry ``entry`` (0-4 bids, 5-9 asks) price replaced; quantity and orders kept."""
    at = _level_at(0, entry) + 4
    return frame[:at] + struct.pack(">i", paise) + frame[at + 4:]


def _as_quote_packet(frame: bytes) -> bytes:
    """The same token as a 44-byte quote-mode packet (no depth, no OI, no exchange time)."""
    return (1).to_bytes(2, "big") + (44).to_bytes(2, "big") + frame[4:4 + 44]


def _provider(subscribed: bool = True) -> tuple[KiteProvider, Clock]:
    clock = Clock(AT)
    provider = KiteProvider(listed(), clock=clock)
    if subscribed:
        provider.subscribe([INSTRUMENT_ID])
    provider.on_connected(AT)
    return provider, clock


def _fed() -> tuple[KiteProvider, Clock]:
    provider, clock = _provider()
    provider.on_frame(FRAME, AT)
    return provider, clock


def test_fixture_is_one_real_full_packet():
    """AC-1: the cut frame is a 184-byte full packet of the expected token (the fixture is what it says)."""
    assert len(FRAME) == 4 + 184 and int.from_bytes(FRAME[4:8], "big") == TOKEN


def test_full_frame_parses_to_exact_five_plus_five_levels():
    """AC-1: all ten levels equal Zerodha's REST quote of the same second; the best bid/ask fields are unchanged."""
    tick = parse_frame(FRAME).ticks[0]
    assert tick.kind == "full"
    assert tick.depth_bids == BIDS  # exact Decimal and quantity equality: x10 paise or a float would be red
    assert tick.depth_asks == ASKS
    assert (tick.bid, tick.ask) == (D("3.3"), D("3.35"))
    assert all(isinstance(price, Decimal) for price, _ in tick.depth_bids + tick.depth_asks)


def test_price_zero_level_is_dropped_never_a_rupee_zero_level():
    """AC-1: F-29 - price 0 is absent. Ask 0 and 2 emptied: three asks left, the ask field None, no Rs 0."""
    tick = parse_frame(_with_price(_with_price(FRAME, 7, 0), 5, 0)).ticks[0]
    assert tick.depth_asks == (ASKS[1], ASKS[3], ASKS[4])
    assert tick.ask is None
    assert tick.depth_bids == BIDS
    assert all(price > 0 for price, _ in tick.depth_bids + tick.depth_asks)


def test_quote_packet_has_no_depth_not_an_empty_depth():
    """AC-1: a quote (44) packet carries no depth -> None, which must not read as 'no liquidity' (empty tuples)."""
    tick = parse_frame(_as_quote_packet(FRAME)).ticks[0]
    assert tick.kind == "quote"
    assert tick.depth_bids is None and tick.depth_asks is None
    provider, _ = _provider()
    provider.on_frame(_as_quote_packet(FRAME), AT)
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None


def test_ltp_packet_has_no_depth():
    """AC-1: an 8-byte ltp packet has no depth either."""
    ltp = (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + FRAME[4:12]
    tick = parse_frame(ltp).ticks[0]
    assert tick.kind == "ltp" and tick.depth_bids is None and tick.depth_asks is None


def test_provider_keeps_depth_and_execute_price_walks_the_right_side():
    """AC-1: latest_depth returns the domain Depth; BUY 65 walks the ASKS -> 3.35, SELL 65 the BIDS -> 3.30."""
    provider, _ = _fed()
    depth = provider.latest_depth(INSTRUMENT_ID, AT)
    assert isinstance(depth, Depth)
    assert depth == depth_from_levels(BIDS, ASKS)
    buy = executable_limit(depth, Action.BUY, 65, TICK, D("3.35"))
    sell = executable_limit(depth, Action.SELL, 65, TICK, D("3.30"))
    assert (buy.fillable, buy.limit) == (True, D("3.35"))  # a swapped side would give 3.30
    assert (sell.fillable, sell.limit) == (True, D("3.30"))  # a swapped side would give 3.35


def test_execute_price_walks_to_the_second_level_for_a_large_quantity():
    """AC-1: BUY 60,000 = 56,810 @ 3.35 + 3,190 @ 3.40 -> limit 3.40, walked 190,313.50 + 10,846.00 = 201,159.50."""
    provider, _ = _fed()
    result = executable_limit(provider.latest_depth(INSTRUMENT_ID, AT), Action.BUY, 60000, TICK, D("3.35"))
    assert (result.limit, result.walked_cost) == (D("3.40"), D("201159.50"))


def test_depth_levels_are_the_domain_depth_level_type():
    """AC-1: one Depth type, no copy - the levels are the engine's DepthLevel."""
    depth = _fed()[0].latest_depth(INSTRUMENT_ID, AT)
    assert depth.bids[0] == DepthLevel(D("3.3"), 55250) and depth.asks[-1] == DepthLevel(D("3.55"), 35945)


def test_no_depth_before_any_full_frame():
    """AC-1: an instrument with no frame yet has no depth."""
    provider, _ = _provider()
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None


def test_stale_feed_gives_no_depth():
    """AC-1: past the feed's staleness limit (FEED_STALE, the one the quote already uses) the depth is not offered."""
    provider, _ = _fed()
    assert provider.latest_depth(INSTRUMENT_ID, AT + datetime.timedelta(seconds=2)) is not None
    assert provider.latest_depth(INSTRUMENT_ID, AT + datetime.timedelta(seconds=10)) is None


def test_a_quiet_contract_keeps_its_depth_while_the_feed_is_alive():
    """AC-1: finding staleness-by-last-change-age - another contract's frames keep the feed fresh; this depth, unchanged
    for 59 s, is still current (health follows the feed, never the contract's own age)."""
    provider, _ = _fed()
    later = AT + datetime.timedelta(seconds=59)
    provider.feed.on_data(later)  # some other contract's frame arrived just now
    assert provider.latest_depth(INSTRUMENT_ID, later) is not None


def test_disconnected_or_ended_feed_gives_no_depth():
    """AC-1: a dropped connection (inside the reconnect window) and an ended session both read no depth."""
    provider, _ = _fed()
    provider.on_disconnected(AT)
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None
    ended, _ = _fed()
    ended.on_session_ended(AT)
    assert ended.latest_depth(INSTRUMENT_ID, AT) is None


def test_reconnected_feed_gives_no_depth_until_new_data():
    """AC-1: after a reconnect the old depth is not current until a data frame arrives."""
    provider, _ = _fed()
    provider.on_disconnected(AT)
    provider.on_connected(AT + datetime.timedelta(seconds=1))
    assert provider.latest_depth(INSTRUMENT_ID, AT + datetime.timedelta(seconds=1)) is None


def test_depth_removed_with_the_subscription():
    """AC-1: REQ-049 AC-4 - no depth outlives its subscription: unreadable at once, still gone after the send."""
    provider, _ = _fed()
    provider.unsubscribe([INSTRUMENT_ID])
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None
    provider.drain_subscription_changes()
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None
    provider.subscribe([INSTRUMENT_ID])  # a NEW subscription starts empty: the old depth never comes back
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None


def test_released_and_retaken_before_the_send_restores_the_depth():
    """AC-1: same park/restore rule as the quote - Kite never stopped sending it, so the depth is back."""
    provider, _ = _fed()
    provider.drain_subscription_changes()  # Kite holds the token
    provider.unsubscribe([INSTRUMENT_ID])
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None
    provider.subscribe([INSTRUMENT_ID])
    assert provider.latest_depth(INSTRUMENT_ID, AT) == depth_from_levels(BIDS, ASKS)


def test_tick_for_a_released_token_never_brings_depth_back():
    """AC-1: a late frame for a token Kite was told to drop does not make its depth readable."""
    provider, _ = _fed()
    provider.drain_subscription_changes()
    provider.unsubscribe([INSTRUMENT_ID])
    provider.drain_subscription_changes()
    provider.on_frame(FRAME, AT)
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None


def test_unsubscribed_token_frame_is_not_kept():
    """AC-1: a frame for a token nobody holds never reaches the book (fail closed)."""
    provider, _ = _provider(subscribed=False)
    provider.on_frame(FRAME, AT)
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None


def test_a_later_quote_packet_clears_the_older_depth():
    """AC-1: depth must belong to the latest price - a quote-mode packet after a full frame leaves no old depth."""
    provider, _ = _fed()
    provider.on_frame(_as_quote_packet(FRAME), AT)
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None


def test_newer_full_frame_replaces_the_depth():
    """AC-1: the latest full frame wins (bid level 0 changed 3.30 -> 3.32 in the new frame)."""
    provider, _ = _fed()
    provider.on_frame(_with_price(FRAME, 0, 332), AT)
    assert provider.latest_depth(INSTRUMENT_ID, AT).bids[0].price == D("3.32")


@pytest.mark.parametrize("bad", ["x", 1.5, None])
def test_depth_from_levels_refuses_non_decimal_prices(bad):
    """AC-1: no float or string price becomes a level."""
    with pytest.raises(ValueError):
        depth_from_levels([(bad, 10)], [])


def test_depth_from_levels_drops_a_price_zero_or_quantity_zero_level():
    """AC-1: F-29 at the domain too - a Rs 0 price or 0 quantity entry is padding, never a level to walk."""
    depth = depth_from_levels([(D("0"), 10), (D("3.3"), 0), (D("3.25"), 5)], [(D("0"), 7)])
    assert depth.bids == (DepthLevel(D("3.25"), 5),)
    assert depth.asks == ()


def _with_quantity(frame: bytes, entry: int, qty: int) -> bytes:
    at = _level_at(0, entry)
    return frame[:at] + struct.pack(">i", qty) + frame[at + 4:]


def test_negative_quantity_level_never_crashes_the_frame():
    """AC-1: a priced level with a negative quantity: that instrument's depth is None (the whole depth, never half a
    book), its quote and every LATER tick of the frame still land, and the 'unmappable' counter moves."""
    bad = _with_quantity(FRAME, 6, -5)  # ask level 1 of the real fixture
    ltp_packet = (8).to_bytes(2, "big") + FRAME[4:8] + FRAME[12:16]  # a second packet, same token
    frame = (2).to_bytes(2, "big") + bad[2:] + ltp_packet
    provider, _ = _provider()
    out = provider.on_frame(frame, AT)
    assert [q.ask for q in out] == [D("3.35"), None]  # the damaged packet's quote landed, then the later packet
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None
    assert provider.counters["unmappable"] == 1
    assert parse_frame(bad).ticks[0].depth_unusable is True


def test_good_frame_does_not_move_the_unmappable_counter():
    """AC-1: the clean fixture counts nothing."""
    provider, _ = _fed()
    assert provider.counters["unmappable"] == 0


@pytest.mark.parametrize(("bids", "asks"), [
    ([(D("3.25"), 10), (D("3.3"), 10)], [(D("3.35"), 10)]),  # bids ascending
    ([(D("3.3"), 10), (D("3.3"), 10)], [(D("3.35"), 10)]),  # bids repeated (not strictly descending)
    ([(D("3.3"), 10)], [(D("3.45"), 10), (D("3.35"), 100)]),  # asks descending
    ([(D("3.3"), 10)], [(D("3.35"), 10), (D("3.35"), 10)]),  # asks repeated
    ([(D("3.35"), 10)], [(D("3.35"), 10)]),  # best bid == best ask
    ([(D("3.4"), 10)], [(D("3.35"), 10)]),  # crossed
])
def test_unsorted_or_crossed_depth_is_refused(bids, asks):
    """AC-1: a side not best-first, or a crossed book, is refused (ValueError) - never walked."""
    with pytest.raises(ValueError):
        depth_from_levels(bids, asks)


def test_unsorted_quote_reply_depth_is_refused_too():
    """AC-1: depth_from_quote shares the rule (REST replies)."""
    reply = {"depth": {"buy": [{"price": D("3.3"), "quantity": 5}],
                       "sell": [{"price": D("3.45"), "quantity": 10}, {"price": D("3.35"), "quantity": 100}]}}
    with pytest.raises(ValueError):
        depth_from_quote(reply)


def test_a_book_with_one_empty_side_is_still_a_depth():
    """AC-1: an empty side is not a crossing; the other side is still walkable."""
    assert depth_from_levels([], [(D("3.35"), 10)]).asks[0].price == D("3.35")


def test_provider_counts_and_drops_an_unsorted_full_frame():
    """AC-1: a real frame with ask 0 patched to 3.40 (= ask 1, not strictly ascending): depth None, counter moves,
    the quote still lands."""
    bad = _with_price(FRAME, 5, 340)
    provider, _ = _provider()
    assert len(provider.on_frame(bad, AT)) == 1
    assert provider.latest_depth(INSTRUMENT_ID, AT) is None
    assert provider.counters["unmappable"] == 1


def _book_depth(provider, mutate):
    entry = provider.book._entries[INSTRUMENT_ID]
    provider.book.update(mutate(entry.quote), entry.depth)
    return provider.latest_depth(INSTRUMENT_ID, AT)


def test_quote_with_validation_errors_gives_no_depth():
    """AC-1: a quote that records a validation error (crossed bid/ask) is UNHEALTHY -> no depth."""
    provider, _ = _fed()
    assert _book_depth(provider, lambda q: dataclasses.replace(q, bid=D("4"), ask=D("3"))) is None


def test_quote_with_declared_delay_gives_no_depth():
    """AC-1: a delayed source (declared delay > 0) is DELAYED, not AVAILABLE -> no depth for an order price."""
    provider, _ = _fed()
    delayed = SourceMetadata(provider="zerodha-kite", feed_id="kite-ws-full", declared_delay_seconds=D("900"))
    assert _book_depth(provider, lambda q: dataclasses.replace(q, source=delayed)) is None
