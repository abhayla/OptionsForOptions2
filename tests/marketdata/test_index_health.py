"""REQ-072 AC-2 (W-060): NIFTY 50 and SENSEX carry the same feed-state health as option quotes (REQ-049 AC-2); a
stale or missing index value is shown as such and never used silently in a calculation.

Replays the real 2026-10-08 recording, then inserts a gap (nothing for 5 s, longer than FEED_STALE) and a disconnect.
"""
import datetime
from decimal import Decimal

import pytest

from ofo.instruments.models import NSE_INDEX
from ofo.marketdata.feed_health import FEED_STALE, RECONNECT_WINDOW
from ofo.marketdata.forward import ForwardUnavailable, parity_forward
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.rules.inputs import DataHealth

from _kite_fixture import all_instrument_ids, listed, new_provider, recorded_frames, replay

SEC = datetime.timedelta(seconds=1)
RATE = Decimal("0.065")
EXPIRY = datetime.date(2026, 10, 13)


def _live():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    return provider, clock, replay(provider, clock)


def _forward(provider, at):
    return parity_forward(provider.option_chain_snapshot("NIFTY", EXPIRY), provider.underlying_quote("NIFTY"),
                          EXPIRY, at, RATE)


def test_live_index_values_are_available_and_from_the_index_segments():
    provider, _clock, end = _live()
    nifty, sensex = provider.underlying_quote("NIFTY 50"), provider.underlying_quote("SENSEX")
    assert (nifty.instrument_id, nifty.segment, nifty.ltp, nifty.health) == (
        "NSE_INDEX:1001", NSE_INDEX, Decimal("22533.25"), DataHealth.AVAILABLE)
    assert (sensex.instrument_id, sensex.ltp, sensex.health) == ("BSE_INDEX:1", Decimal("72443.48"), DataHealth.AVAILABLE)
    assert provider.underlying_quote("NIFTY") == nifty
    assert provider.counters["unmapped_token"] == 20  # INDIA VIX's ticks: not in AC-1, never priced
    assert _forward(provider, end).spot_timestamp == nifty.timestamp  # the spot's time travels with the forward


def test_inserted_gap_makes_the_index_stale_and_the_calculation_refuses():
    provider, clock, end = _live()
    gap_end = end + 5 * SEC
    assert 5 * SEC > FEED_STALE
    clock.now = gap_end
    nifty = provider.underlying_quote("NIFTY")
    assert nifty is not None and nifty.health is DataHealth.STALE  # shown as stale, not dropped
    option = provider.book.get("NSE_FO:44614", gap_end)
    assert option.health is nifty.health  # same health state as the option quotes
    with pytest.raises(ForwardUnavailable, match="stale"):
        _forward(provider, gap_end)
    provider.on_frame(b"\x00", gap_end)  # data (a heartbeat) resumes
    assert provider.underlying_quote("NIFTY").health is DataHealth.AVAILABLE
    assert _forward(provider, gap_end).source == "parity"


def test_disconnect_past_the_window_is_unavailable_and_refuses():
    provider, clock, end = _live()
    provider.on_disconnected(end)
    clock.now = end + RECONNECT_WINDOW + SEC
    assert provider.underlying_quote("SENSEX").health is DataHealth.UNAVAILABLE
    with pytest.raises(ForwardUnavailable, match="unavailable"):
        _forward(provider, clock.now)


def test_missing_index_value_refuses():
    items = [lc for lc in listed() if not lc.contract.is_index()]  # a catalogue without the index rows
    clock_at = recorded_frames()[0][0]
    provider = KiteProvider(items, clock=lambda: clock_at)
    assert provider.underlying_quote("NIFTY") is None
    with pytest.raises(ForwardUnavailable, match="missing"):
        parity_forward([], provider.underlying_quote("NIFTY"), EXPIRY,
                       datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST), RATE)
