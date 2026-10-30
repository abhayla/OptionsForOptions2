"""REQ-048 AC-1 (W-134): a price reaches a subscriber only through the server's stages.

Vendor frames -> provider (decode) -> normalised quote -> latest-quote store -> event stream (fan-out) -> subscriber.
The real 2026-10-08 recording is replayed; each stage's output type is asserted and the LTP a subscriber receives is
the one the frame carried. The import graph is an ALLOW-LIST: only named modules may import a concrete provider or
the quote store (finding guard-as-forbidden-list); a screen's feed reaches the provider only through ``FanOut``.
"""
import ast
import pathlib

import pytest
from _kite_fixture import NIFTY_CE_ID, new_provider, recorded_frames, replay
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_frames import parse_frame
from ofo.marketdata.quote import NormalizedQuote

pytestmark = pytest.mark.repo_scan  # reads the source of every backend module

BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"

#: module (dotted, under backend/) -> reason it may import the CONCRETE provider (`kite_provider`)
MAY_IMPORT_CONCRETE_PROVIDER = {
    "ofo.marketdata.kite_provider": "the stage itself",
    "ofo_app.kite_ws": "the socket that owns the vendor connection (the provider's one producer)",
    "ofo_app.live_market": "builds the single process-wide provider and its FanOut",
    "ofo_app.replay_mode": "builds the recorded-replay provider for dev/e2e (APP_ENV=test)",
    "ofo_app.scenario_mode": "builds the scenario provider from the adjustment library (APP_ENV dev/test)",
    "ofo_app.execute_replay": "builds the recorded replay used by the Execute tests and replay mode",
}
#: module -> reason it may import the fan-out (the event stream every screen push subscribes to)
MAY_IMPORT_FANOUT = {
    "ofo.history.recorder": "records the stream",
    "ofo_app.live_market": "builds the process-wide FanOut",
    "ofo_app.live_push": "the platform socket pushes subscribe through it",
    "ofo_app.replay_mode": "the replay context's FanOut",
    "ofo_app.scenario_mode": "the scenario context's FanOut (dev/test)",
}
#: module -> reason it may import the quote store / feed state directly (health labels only, never a price path)
MAY_IMPORT_FEED_HEALTH = {
    "ofo.marketdata.kite_provider": "the stage itself",
    "ofo_app.live_market": "reads the feed phase constants",
    "ofo_app.routes.broker_status": "reads the feed phase constants for the status label",
    "ofo_app.kite_ws": "market_closed_for only: the one market-state answer for the closed-hours reconnect wait (F1)",
    "ofo_app.routes.outcome": "market_closed_for only: the market-state answer the outcome carries (REQ-114 AC-7)",
    "ofo.outcome.snapshot": "market_closed_for only: the snapshot market_closed every outcome path reads (ADR-200)",
    "ofo.marketdata.spot_source": "FEED_STALE only: the one freshness number the spot resolver reuses (REQ-155)",
}


def _imports() -> dict[str, set[str]]:
    """Every module under backend/ -> the dotted modules it imports (discovered; a file that does not parse is an
    error, never skipped)."""
    out: dict[str, set[str]] = {}
    for path in BACKEND.rglob("*.py"):
        if "alembic" in path.parts:
            continue
        mod = ".".join(path.relative_to(BACKEND).with_suffix("").parts)
        names: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
                names.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
        out[mod] = names
    return out


def importers_of(imports: dict[str, set[str]], target: str) -> set[str]:
    return {mod for mod, names in imports.items() if target in names}


def test_only_named_modules_import_the_concrete_provider_the_fanout_and_the_quote_store():
    imports = _imports()
    assert imports, "no backend modules discovered"
    for target, allowed in (("ofo.marketdata.kite_provider", MAY_IMPORT_CONCRETE_PROVIDER),
                            ("ofo.marketdata.fanout", MAY_IMPORT_FANOUT),
                            ("ofo.marketdata.feed_health", MAY_IMPORT_FEED_HEALTH)):
        extra = importers_of(imports, target) - set(allowed)
        assert extra == set(), f"{sorted(extra)} import {target} outside the allow-list; add a reason or go via FanOut"
        assert all(allowed.values())


def test_a_planted_module_importing_the_provider_is_outside_the_allow_list():
    imports = _imports() | {"ofo_app.routes.some_screen": {"ofo.marketdata.kite_provider"}}
    assert importers_of(imports, "ofo.marketdata.kite_provider") - set(MAY_IMPORT_CONCRETE_PROVIDER) == {
        "ofo_app.routes.some_screen"}


def test_screen_routes_never_import_a_provider_or_the_book():
    imports = _imports()
    for mod, names in imports.items():
        if mod.startswith("ofo_app.routes."):
            bad = {n for n in names if n in ("ofo.marketdata.kite_provider", "ofo.marketdata.fanout")
                   or n.startswith("ofo.marketdata.kite_provider.")}
            assert bad == set(), f"{mod} feeds a screen around the stages: {bad}"


def test_recorded_frames_pass_every_stage_and_reach_a_subscriber_with_the_frames_own_ltp():
    provider, clock, items = new_provider()  # noqa: RUF059
    fan = FanOut(provider)
    got: list[NormalizedQuote] = []
    fan.subscribe(got.append, [NIFTY_CE_ID])
    assert provider.subscribed_tokens(), "stage 1: the provider (vendor subscription) is asked by the fan-out only"

    # stage 1: the recording's raw ticks for this instrument (what the frame carried, before any stage)
    frames = recorded_frames()
    token = int(NIFTY_CE_ID.split(":")[1])
    raw = [t for _, f in frames for t in parse_frame(f).ticks if t.token >> 8 == token]  # Kite packs the segment in the low byte  # noqa: E501
    assert raw, "the recording carries ticks for the instrument"

    last = replay(provider, clock, frames)
    # stage 3: nothing reached the subscriber before the fan-out pumps (the producer only enqueues)
    assert got == []
    fan.pump()
    # stage 4/5: the subscriber's quotes are normalised, all for its instrument, and equal the store's latest quote
    assert got and all(isinstance(q, NormalizedQuote) and q.instrument_id == NIFTY_CE_ID for q in got)
    stored = provider.book.get(NIFTY_CE_ID, last)
    assert stored is not None and stored.ltp == got[-1].ltp
    assert got[-1].ltp == raw[-1].ltp  # the subscriber's last price is the last price the last frame carried
    assert len(got) == len(raw)  # no tick skipped, none invented
