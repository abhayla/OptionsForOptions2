"""The Kite implementation of ``MarketDataProvider`` (W-059). The only module that joins Kite frames to the product.

Frames come in through ``on_frame`` (the live socket in ``ofo_app.kite_ws`` or a recording replay calls it with the
same bytes); identity comes from the catalogue's per-broker table (``BrokerRef('zerodha', instrument_token)``, ADR-050);
health comes from the feed's state (``feed_health``), never a contract's own age. Standard library only, no clock of
its own (times are passed in), never places or sends an order.

Field mapping (F-29): bid = depth buy[0], ask = depth sell[0], 0 means absent (None); exchange time is epoch seconds
and gets IST attached; Kite sends no OI change, IV or Greeks, so those are None here.
"""
from __future__ import annotations

import datetime
import json
from collections import Counter
from decimal import Decimal
from typing import Callable, Iterable, Sequence

from ofo.engine.legs import Instrument
from ofo.instruments.models import (BSE_FO, BSE_INDEX, INDEX_ROWS, NSE_FO, NSE_INDEX, ZERODHA, ListedContract)
from ofo.marketdata.feed_health import FeedState, QuoteBook
from ofo.marketdata.kite_frames import RawTick, parse_frame
from ofo.marketdata.provider import MarketDataProvider, NotSupported, ProviderStatus, QuoteListener
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
SOURCE = SourceMetadata(provider="zerodha-kite", feed_id="kite-ws-full")

# Index identity (REQ-072 AC-1, W-060): the NIFTY 50 and SENSEX rows come from the catalogue's NSE_INDEX / BSE_INDEX
# segments through the per-broker table, like every option; there is no token table here. INDIA VIX is not in AC-1.
_EXCHANGE_OF_SEGMENT = {NSE_FO: "NSE", BSE_FO: "BSE", NSE_INDEX: "NSE", BSE_INDEX: "BSE"}


def _ist(epoch_seconds: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(epoch_seconds, IST)


class KiteProvider(MarketDataProvider):
    def __init__(self, listed: Iterable[ListedContract], *, clock: Callable[[], datetime.datetime],
                 feed: FeedState | None = None) -> None:
        self._clock = clock  # injected: the provider never reads the wall clock itself
        self._master = list(listed)
        self._by_token: dict[int, ListedContract] = {}
        self._token_of: dict[str, int] = {}
        for lc in self._master:
            token = int(lc.ref(ZERODHA).broker_token)
            self._by_token[token] = lc
            self._token_of[self._contract_id(lc)] = token
        # underlying name or index name -> the index contract id, from the catalogue rows only
        self._index_id: dict[str, str] = {}
        for lc in self._master:
            key = (lc.contract.exchange_segment, lc.contract.exchange_token)
            if key in INDEX_ROWS:
                name, underlying = INDEX_ROWS[key]
                self._index_id[name] = self._index_id[underlying] = self._contract_id(lc)
        self.feed = feed or FeedState()
        self.book = QuoteBook(self.feed)
        self._listener: QuoteListener | None = None
        self._wanted: set[int] = set()
        self._added: list[int] = []
        self._removed: list[int] = []
        self.counters: Counter = Counter()

    @staticmethod
    def _contract_id(lc: ListedContract) -> str:
        return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"

    # ---- inbound: the socket's answer states, each counted -------------------------------------------------
    def on_frame(self, data: bytes, received_at: datetime.datetime) -> list[NormalizedQuote]:
        """A binary message: a data frame or a heartbeat. Returns the quotes it produced, in order."""
        result = parse_frame(data)
        if result.malformed == 0:  # only a well-formed frame or a heartbeat is activity
            if result.ticks:
                self.feed.on_data(received_at)
            else:
                self.feed.on_activity(received_at)
        self.counters["frames"] += 1
        self.counters["heartbeats"] += result.heartbeat
        self.counters["unknown_packets"] += result.unknown_packets
        self.counters["unsupported_segment"] += result.unsupported_segment
        self.counters["malformed"] += result.malformed
        out = []
        for tick in result.ticks:
            try:
                quote = self.normalise(tick, received_at)
            except (ValueError, KeyError):  # unknown instrument type / segment, invalid value: skip, never raise
                self.counters["unmappable"] += 1
                continue
            if quote is None:
                self.counters["unmapped_token"] += 1
                continue
            self.counters["ticks"] += 1
            self.book.update(quote)
            out.append(quote)
            if self._listener is not None:
                self._listener(self._with_health(quote, received_at))
        return out

    def on_text(self, message: str) -> None:
        """A text message (order update or error): counted by type only, nothing stored."""
        try:
            kind = json.loads(message).get("type", "other")
        except (ValueError, AttributeError):
            kind = "unparsed"
        self.counters[f"text:{kind if isinstance(kind, str) else 'other'}"] += 1

    def on_connected(self, now: datetime.datetime) -> None:
        self.feed.on_connected(now)

    def on_disconnected(self, now: datetime.datetime) -> None:
        self.feed.on_disconnected(now)

    def on_session_ended(self, now: datetime.datetime) -> None:
        self.feed.on_session_ended(now)

    # ---- normalisation ---------------------------------------------------------------------------------------
    def normalise(self, tick: RawTick, received_at: datetime.datetime) -> NormalizedQuote | None:
        ts = _ist(tick.exchange_ts) if tick.exchange_ts else received_at.astimezone(IST)
        lc = self._by_token.get(tick.token)
        if lc is None:
            return None
        c = lc.contract
        index = INDEX_ROWS.get((c.exchange_segment, c.exchange_token))
        if index is not None:
            return NormalizedQuote(
                instrument_id=self._contract_id(lc), underlying=index[1], exchange=_EXCHANGE_OF_SEGMENT[c.exchange_segment],
                segment=c.exchange_segment, instrument_type=None, expiry=None, strike=None, ltp=tick.ltp, bid=None,
                ask=None, volume=None, oi=None, oi_change=None, iv=None, delta=None, gamma=None, theta=None, vega=None,
                timestamp=ts, source=SOURCE, health=DataHealth.AVAILABLE)
        if c.is_index():  # an index segment row outside AC-1's two: never priced
            return None
        return NormalizedQuote(
            instrument_id=self._contract_id(lc), underlying=c.name, exchange=_EXCHANGE_OF_SEGMENT[c.exchange_segment],
            segment=c.exchange_segment, instrument_type=Instrument(c.instrument_type), expiry=c.expiry,
            strike=None if c.instrument_type == "FUT" else c.strike, ltp=tick.ltp, bid=tick.bid, ask=tick.ask,
            volume=tick.volume, oi=tick.oi, oi_change=None, iv=None, delta=None, gamma=None, theta=None,
            vega=None, timestamp=ts, source=SOURCE, health=DataHealth.AVAILABLE)

    def _with_health(self, quote: NormalizedQuote, now: datetime.datetime) -> NormalizedQuote:
        return self.book.get(quote.instrument_id, now) or quote

    # ---- MarketDataProvider ----------------------------------------------------------------------------------
    def subscribe(self, instrument_ids: Sequence[str]) -> None:
        unknown = [i for i in instrument_ids if i not in self._token_of]
        if unknown:  # validate everything first: a bad id subscribes nothing
            raise KeyError(f"no Kite token for instrument(s) {unknown[:5]!r}")
        for i in instrument_ids:
            token = self._token_of[i]
            if token not in self._wanted:
                self._wanted.add(token)
                self._added.append(token)
                self.counters["vendor_subscribe"] += 1

    def unsubscribe(self, instrument_ids: Sequence[str]) -> None:
        for i in instrument_ids:
            self.book.remove(i)  # no stale price may outlive the subscription
            token = self._token_of.get(i)
            if token in self._wanted:
                self._wanted.discard(token)
                self._removed.append(token)

    def subscribed_tokens(self) -> list[int]:
        return sorted(self._wanted)

    def drain_subscription_changes(self) -> tuple[list[int], list[int]]:
        """(tokens to subscribe, tokens to unsubscribe) since the last call; the socket sends them."""
        added, removed, self._added, self._removed = self._added, self._removed, [], []
        return added, removed

    def live_quote_stream(self, listener: QuoteListener) -> None:
        self._listener = listener

    def option_chain_snapshot(self, underlying: str, expiry: datetime.date) -> list[NormalizedQuote]:
        now = self._now()
        return [q for q in self.book.quotes(now) if q.underlying == underlying and q.expiry == expiry
                and q.instrument_type in (Instrument.CE, Instrument.PE)]

    def instrument_master(self) -> list[ListedContract]:
        return list(self._master)

    def underlying_quote(self, underlying: str) -> NormalizedQuote | None:
        instrument_id = self._index_id.get(underlying)
        return None if instrument_id is None else self.book.get(instrument_id, self._now())

    def index_id(self, underlying: str) -> str | None:
        """The catalogue id ("NSE_INDEX:1001" / "BSE_INDEX:1") of an index by its name or underlying name."""
        return self._index_id.get(underlying)

    def futures_quote(self, underlying: str, expiry: datetime.date) -> NormalizedQuote | None:
        raise NotSupported("Kite futures quotes are not offered in V1")

    def historical(self, instrument_id: str, start: datetime.datetime, end: datetime.datetime) -> list[NormalizedQuote]:
        raise NotSupported("historical data is not offered in V1")

    def status(self) -> ProviderStatus:
        now = self._now()
        return ProviderStatus(self.feed.health(now), self.feed.connected, self.feed.session_ended)

    def source_metadata(self) -> SourceMetadata:
        return SOURCE

    def _now(self) -> datetime.datetime:
        return self._clock()
