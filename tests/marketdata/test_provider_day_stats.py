"""REQ-080 AC-5, AC-6, AC-7: the provider interface gives the day values and a listed future's price, or a reason.

Input: the ONE real full packet in ``tests/fixtures/kite_ws/full-frame-12080386-150720.bin`` (the NIFTY 23650 call of
2026-10-19, exchange time 2026-10-16 15:07:20 IST). Expected day values are read off its bytes with ``struct`` (ten
int32 fields at bytes 4..44 of the packet: ltp, last qty, average, volume, buy qty, sell qty, open, high, low, previous
close; last trade time at 44..48), not from the decoder. No recording in the repo holds a future's tick, so the future
is the SAME real packet re-addressed (its 4 token bytes replaced) to a future row built from the real option row's
exchange fields with type FUT; that is said here, not hidden.
"""
from __future__ import annotations

import dataclasses
import datetime
import struct
from decimal import Decimal

from _kite_fixture import FIXTURES, Clock, listed
from ofo.instruments.models import BrokerRef, ListedContract
from ofo.marketdata.kite_provider import KiteProvider
from ofo.marketdata.provider import (
    FEED_NOT_HEALTHY,
    NOT_HELD,
    NOT_OFFERED,
    PACKET_WITHOUT_DAY_FIELDS,
    DayStatsAnswer,
    MarketDataProvider,
)
from ofo.marketdata.quote import SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST

D = Decimal
PACKET = (FIXTURES / "full-frame-12080386-150720.bin").read_bytes()[4:]  # one-packet frame: count, length, then 184
OPTION_ID = "NSE_FO:47189"
FRAME_AT = datetime.datetime.fromtimestamp(1792143440, IST)  # the packet's own exchange time
OPEN, HIGH, LOW, CLOSE, LAST_TRADE = struct.unpack(">5i", PACKET[28:48])
FUTURE_TOKEN = 51001  # exchange token of the re-addressed future row
FUTURE_EXPIRY = datetime.date(2026, 10, 27)
FUTURE_ID = f"NSE_FO:{FUTURE_TOKEN}"
ONE_PACKET, FULL_LEN, QUOTE_LEN, LTP_LEN = 1, 184, 44, 8
STALE_AFTER = datetime.timedelta(seconds=600)


def _frame(packet: bytes) -> bytes:
    return ONE_PACKET.to_bytes(2, "big") + len(packet).to_bytes(2, "big") + packet


def _future_row() -> ListedContract:
    option = next(lc for lc in listed() if f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" == OPTION_ID)
    contract = dataclasses.replace(option.contract, exchange_token=FUTURE_TOKEN, expiry=FUTURE_EXPIRY,
                                   strike=D(0), instrument_type="FUT")
    ref = option.ref("zerodha")
    broker = BrokerRef("zerodha", str(FUTURE_TOKEN << 8 | 2), "NIFTY26OCTFUT", ref.broker_segment, ref.lot_size,
                       ref.tick_size, ref.seen_on)
    return ListedContract(contract, (broker,))


def _provider(*ids: str) -> tuple[KiteProvider, Clock]:
    clock = Clock(FRAME_AT)
    provider = KiteProvider([*listed(), _future_row()], clock=clock)
    provider.subscribe(list(ids))
    provider.on_connected(FRAME_AT)
    return provider, clock


def test_attack_2_a_recorded_full_frame_gives_open_high_low_previous_close_and_last_trade_time():
    """Attack 2: exact values from the real packet's bytes reach the interface method."""
    provider, _ = _provider(OPTION_ID)
    provider.on_frame(_frame(PACKET), FRAME_AT)
    answer = provider.latest_day_stats(OPTION_ID, FRAME_AT)
    assert answer.reason is None and answer.stats is not None
    assert (answer.stats.day_open, answer.stats.day_high, answer.stats.day_low, answer.stats.prev_close) == (
        D(OPEN) / 100, D(HIGH) / 100, D(LOW) / 100, D(CLOSE) / 100)
    assert answer.stats.last_trade_ts == LAST_TRADE
    assert (answer.stats.day_open, answer.stats.prev_close) == (D("3.30"), D("3.00"))  # the same, as typed once


def test_every_answer_state_of_the_day_values_names_its_reason():
    """Answer states: not held, a packet without day fields, a feed that is not healthy, a provider with none."""
    provider, clock = _provider(OPTION_ID)
    assert provider.latest_day_stats(OPTION_ID, FRAME_AT) == DayStatsAnswer.unavailable(NOT_HELD)  # nothing received
    provider.on_frame(_frame(PACKET[:LTP_LEN]), FRAME_AT)  # an ltp-only packet
    assert provider.latest_day_stats(OPTION_ID, FRAME_AT) == DayStatsAnswer.unavailable(PACKET_WITHOUT_DAY_FIELDS)
    provider.on_frame(_frame(PACKET[:QUOTE_LEN]), FRAME_AT)  # a quote packet: day values, no last trade time
    quote_day = provider.latest_day_stats(OPTION_ID, FRAME_AT).stats
    assert quote_day is not None and quote_day.last_trade_ts is None and quote_day.day_high == D(HIGH) / 100
    provider.on_frame(_frame(PACKET), FRAME_AT)
    later = FRAME_AT + STALE_AFTER
    clock.now = later
    assert provider.latest_day_stats(OPTION_ID, later) == DayStatsAnswer.unavailable(FEED_NOT_HEALTHY)


class Bare(MarketDataProvider):  # only the abstract operations
    def subscribe(self, instrument_ids): ...
    def unsubscribe(self, instrument_ids): ...
    def live_quote_stream(self, listener): ...
    def option_chain_snapshot(self, underlying, expiry): return []
    def instrument_master(self): return []
    def underlying_quote(self, underlying): return None
    def futures_quote(self, underlying, expiry): return None
    def historical(self, instrument_id, start, end): return []
    def status(self): ...
    def source_metadata(self): return SourceMetadata("bare", "bare")


def test_a_provider_that_offers_no_day_values_says_not_offered_and_no_depth():
    """Answer state: the interface default (a provider without the feature) is an explicit reason, never a lookup."""
    assert Bare().latest_day_stats(OPTION_ID) == DayStatsAnswer.unavailable(NOT_OFFERED)
    assert Bare().latest_depth(OPTION_ID) is None


def test_attack_3_a_future_tick_gives_its_ltp_and_no_tick_gives_none():
    """Attack 3 (provider half): a held future's tick is its LTP; no tick or no subscription is None, never raised."""
    provider, _ = _provider(FUTURE_ID)
    assert provider.futures_quote("NIFTY", FUTURE_EXPIRY) is None  # held, no tick yet
    provider.on_frame(_frame(FUTURE_TOKEN_PACKET), FRAME_AT)
    quote = provider.futures_quote("NIFTY", FUTURE_EXPIRY)
    assert quote is not None and quote.ltp == D(struct.unpack(">i", PACKET[4:8])[0]) / 100
    assert quote.health is DataHealth.AVAILABLE and quote.instrument_id == FUTURE_ID
    assert provider.futures_quote("NIFTY", datetime.date(2026, 11, 24)) is None  # no such listed future
    provider.unsubscribe([FUTURE_ID])
    assert provider.futures_quote("NIFTY", FUTURE_EXPIRY) is None  # released: no stale price outlives the lease


FUTURE_TOKEN_PACKET = (FUTURE_TOKEN << 8 | 2).to_bytes(4, "big") + PACKET[4:]
