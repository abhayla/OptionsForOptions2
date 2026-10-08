"""Defect-fix contract, class `staleness-by-last-change-age`: a quote's health follows its FEED's state.

Replays the real 2026-10-08 recording. RCA: the per-quote age rule (health.py, stale after 60 s) marks every quiet but
current contract stale while the feed is live, because Kite sends only changes (F-32)."""
import datetime

from _kite_fixture import all_instrument_ids, new_provider, replay

from ofo.marketdata.feed_health import FEED_STALE, RECONNECT_WINDOW
from ofo.marketdata.health import build_quote
from ofo.rules.inputs import DataHealth

SEC = datetime.timedelta(seconds=1)


def _live_provider():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    end = replay(provider, clock)
    return provider, clock, end


def _heartbeats(provider, clock, start, seconds):
    for s in range(1, seconds + 1):
        clock.now = start + s * SEC
        provider.on_frame(b"\x00", clock.now)
    return clock.now


def test_the_old_per_quote_age_rule_is_the_defect():
    """Red-today evidence: the age rule flags every ticked contract after 61 s although the feed is live."""
    provider, clock, end = _live_provider()
    later = end + 61 * SEC
    flagged = 0
    for q in provider.book.quotes(later):
        rebuilt = build_quote(
            instrument_id=q.instrument_id, underlying=q.underlying, exchange=q.exchange, segment=q.segment,
            instrument_type=q.instrument_type, expiry=q.expiry, strike=q.strike, ltp=q.ltp, bid=q.bid, ask=q.ask,
            volume=q.volume, oi=q.oi, oi_change=None, iv=None, delta=None, gamma=None, theta=None, vega=None,
            timestamp=q.timestamp, source=q.source, now=later)
        flagged += rebuilt.health is DataHealth.STALE
    assert flagged == 983


def test_no_contract_is_stale_after_61_s_while_the_feed_is_live():
    provider, clock, end = _live_provider()
    now = _heartbeats(provider, clock, end, 61)
    quotes = provider.book.quotes(now)
    assert len(quotes) == 983
    assert {q.health for q in quotes} == {DataHealth.AVAILABLE}
    # the contract's own age is information only
    assert now - provider.book.last_changed_at("NSE_FO:44614") > 60 * SEC


def test_inserted_gap_makes_every_contract_stale_then_data_resumes():
    provider, clock, end = _live_provider()
    gap_end = end + 5 * SEC  # 5 s with nothing at all, longer than FEED_STALE
    assert 5 * SEC > FEED_STALE
    assert {q.health for q in provider.book.quotes(gap_end)} == {DataHealth.STALE}
    assert len(provider.book.quotes(gap_end)) == 983
    clock.now = gap_end
    provider.on_frame(b"\x00", gap_end)  # data (a heartbeat) resumes
    assert {q.health for q in provider.book.quotes(gap_end)} == {DataHealth.AVAILABLE}


def test_disconnect_session_end_and_never_connected():
    provider, clock, end = _live_provider()
    provider.on_disconnected(end)
    assert {q.health for q in provider.book.quotes(end + RECONNECT_WINDOW)} == {DataHealth.STALE}
    assert {q.health for q in provider.book.quotes(end + RECONNECT_WINDOW + SEC)} == {DataHealth.UNAVAILABLE}
    provider.on_connected(end + 40 * SEC)
    assert {q.health for q in provider.book.quotes(end + 41 * SEC)} == {DataHealth.AVAILABLE}
    provider.on_session_ended(end + 42 * SEC)  # 403 at connect: no retry
    assert {q.health for q in provider.book.quotes(end + 42 * SEC)} == {DataHealth.UNAVAILABLE}
    assert provider.status().session_ended is True
    fresh, _, _ = new_provider()
    assert fresh.status().health is DataHealth.UNAVAILABLE
