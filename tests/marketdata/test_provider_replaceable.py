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
        self.feed.on_data(at)
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
    fan.pump()
    assert [q.ltp for q in got] == [Decimal("100.50")] * 2
    # the same health rule: 61 s with the feed live (activity every second) keeps the quiet contract available
    for s in range(1, 62):
        fake.feed.on_activity(T0 + datetime.timedelta(seconds=s))
    assert fake.book.get("X:1", T0 + datetime.timedelta(seconds=61)).health is DataHealth.AVAILABLE


ADAPTER_FILES = {"kite_frames.py", "kite_provider.py", "kite_ws.py"}  # the market-data Kite adapter (by name)
#: The broker-login Kite adapter (W-058), by path relative to backend/. REQ-063 AC-1: "Broker, market-data and
#: payment integrations each sit behind an adapter." Each entry is part of that adapter, not domain code.
BROKER_ADAPTER_PATHS = {
    "ofo/broker/kite_auth.py": "the Kite login port itself (login URL, checksum, KiteAuthPort) - REQ-063 AC-1",
    "ofo/broker/__init__.py": "re-exports the Kite login port for the adapter's callers - REQ-063 AC-1",
    "ofo_app/kite_client.py": "the HTTP implementation of the Kite login port - REQ-063 AC-1",
    "ofo_app/routes/broker.py": "composition root wiring the Kite login port to its HTTP client - REQ-063 AC-1",
    "ofo_app/replay_mode.py": "test-only composition root: feeds the Kite market-data provider from the recorded "
                              "frames for the outcome route (APP_ENV=test only, W-064) - REQ-063 AC-1",
    "ofo_app/broker_token_store.py": "the broker adapter's token store: ends a session on Kite's TokenException "
                                     "(adapter error type) - REQ-063 AC-1",
    "ofo_app/live_market.py": "live composition root: wires the Kite market-data provider and socket to the owner's "
                              "stored session (W-065; the live twin of replay_mode.py) - REQ-063 AC-1",
}


def _kite_importers(root: pathlib.Path, allowed_paths) -> list[str]:
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if path.name in ADAPTER_FILES or rel in allowed_paths:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "")] + [f"{node.module}.{a.name}" for a in node.names]
            if any(n.split(".")[-1].startswith("kite_") or ".kite_" in n or n.startswith("kite_") for n in names):
                offenders.append(f"{rel}: {names}")
    return offenders


def test_nothing_outside_the_kite_adapter_imports_the_kite_modules():
    assert _kite_importers(BACKEND, BROKER_ADAPTER_PATHS) == []


def test_every_allowlisted_broker_adapter_file_exists_and_cites_req_063():
    for rel, reason in BROKER_ADAPTER_PATHS.items():
        assert (BACKEND / rel).is_file(), rel
        assert "REQ-063 AC-1" in reason


def test_the_import_scan_would_catch_a_leak(tmp_path):
    leak = tmp_path / "leaky.py"
    leak.write_text("from ofo.marketdata.kite_frames import parse_frame\n", encoding="utf-8")
    node = next(n for n in ast.walk(ast.parse(leak.read_text())) if isinstance(n, ast.ImportFrom))
    names = [(node.module or "")] + [f"{node.module}.{a.name}" for a in node.names]
    assert any(".kite_" in n for n in names)


def test_a_new_importer_of_the_broker_login_port_is_still_flagged(tmp_path):
    # the same scanner on a tree holding one allowlisted adapter file and one domain file importing the Kite port
    (tmp_path / "ofo_app" / "routes").mkdir(parents=True)
    (tmp_path / "ofo" / "strategy").mkdir(parents=True)
    (tmp_path / "ofo_app" / "routes" / "broker.py").write_text("from ofo.broker.kite_auth import login_url\n")
    (tmp_path / "ofo" / "strategy" / "leaky.py").write_text("from ofo.broker.kite_auth import checksum\n")
    (tmp_path / "ofo" / "strategy" / "broker.py").write_text("from ofo_app.kite_client import HttpKiteAuth\n")
    flagged = _kite_importers(tmp_path, BROKER_ADAPTER_PATHS)
    assert sorted(f.split(":")[0] for f in flagged) == ["ofo/strategy/broker.py", "ofo/strategy/leaky.py"]
