"""REQ-048 AC-3: a provider can be replaced without changing product-domain logic.

A second, fake provider stands in for Kite and the same domain consumers (fan-out, feed health) run unchanged; no
module outside the Kite adapter imports the Kite modules."""
import ast
import datetime
import pathlib
from decimal import Decimal

from ofo.marketdata.fanout import FanOut
from ofo.marketdata.feed_health import FeedState, QuoteBook
from ofo.marketdata.provider import MarketDataProvider, NotSupported, ProviderStatus
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=IST)
BACKEND = pathlib.Path(__file__).resolve().parent.parent.parent / "backend"


class FakeProvider(MarketDataProvider):
    def __init__(self):
        self.listener = None
        self.subscribed = []
        self.feed = FeedState()
        self.book = QuoteBook(self.feed)

    def subscribe(self, instrument_ids):
        self.subscribed += list(instrument_ids)

    def unsubscribe(self, instrument_ids): ...
    def live_quote_stream(self, listener): self.listener = listener
    def option_chain_snapshot(self, underlying, expiry): return []
    def instrument_master(self): return []
    def underlying_quote(self, underlying): return None
    def futures_quote(self, underlying, expiry): raise NotSupported
    def historical(self, instrument_id, start, end): raise NotSupported
    def status(self): return ProviderStatus(self.feed.health(T0), self.feed.connected)
    def source_metadata(self): return SourceMetadata(provider="fake", feed_id="fake-1")

    def push(self, instrument_id: str, ltp: str, at: datetime.datetime):
        self.feed.on_activity(at)
        q = NormalizedQuote(
            instrument_id=instrument_id, underlying="NIFTY", exchange="NSE", segment="INDEX", instrument_type=None,
            expiry=None, strike=None, ltp=Decimal(ltp), bid=None, ask=None, volume=None, oi=None, oi_change=None,
            iv=None, delta=None, gamma=None, theta=None, vega=None, timestamp=at, source=self.source_metadata(),
            health=DataHealth.AVAILABLE)
        self.book.update(q)
        self.listener(q)


def test_fanout_and_feed_health_run_unchanged_on_a_second_provider():
    fake = FakeProvider()
    fan = FanOut(fake)
    got = []
    fan.subscribe(got.append, ["X:1"])
    fan.subscribe(got.append, ["X:1"])
    assert fake.subscribed == ["X:1"]  # one vendor subscription for two subscribers
    fake.feed.on_connected(T0)
    fake.push("X:1", "100.50", T0)
    assert [q.ltp for q in got] == [Decimal("100.50")] * 2
    # the same health rule: 61 s with the feed live (activity every second) keeps the quiet contract available
    for s in range(1, 62):
        fake.feed.on_activity(T0 + datetime.timedelta(seconds=s))
    assert fake.book.get("X:1", T0 + datetime.timedelta(seconds=61)).health is DataHealth.AVAILABLE


def test_nothing_outside_the_kite_adapter_imports_the_kite_modules():
    adapter_files = {"kite_frames.py", "kite_provider.py", "kite_ws.py"}
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if path.name in adapter_files:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "")] + [f"{node.module}.{a.name}" for a in node.names]
            if any(n.split(".")[-1].startswith("kite_") or ".kite_" in n or n.startswith("kite_") for n in names):
                offenders.append(f"{path.relative_to(BACKEND)}: {names}")
    assert offenders == []


def test_the_import_scan_would_catch_a_leak(tmp_path):
    leak = tmp_path / "leaky.py"
    leak.write_text("from ofo.marketdata.kite_frames import parse_frame\n", encoding="utf-8")
    node = next(n for n in ast.walk(ast.parse(leak.read_text())) if isinstance(n, ast.ImportFrom))
    names = [(node.module or "")] + [f"{node.module}.{a.name}" for a in node.names]
    assert any(".kite_" in n for n in names)
