"""DEV/TEST-ONLY scenario mode (GC-ADJ1 step 1b, W-196; goal contract GC-ADJ1 "Running the app").

With ``APP_ENV`` exactly ``development`` or ``test`` and ``OFO_SCENARIO=<ADJ-id>`` the API serves that scenario of the
adjustment library (``tests/fixtures/adjust_scenarios/<id>.json``): its option chain, index spot, clock, data state
and broker answers. The market goes through the SAME parsers the real Kite path uses: the scenario becomes Zerodha
instrument-list rows (``ofo.instruments.parser.parse_instruments_rows``) and Kite binary full / index packets fed to a
``KiteProvider`` (``ofo.marketdata.kite_frames.parse_frame``), exactly as ``replay_mode`` feeds recorded frames; the
broker margin answer is the scenario's Kite JSON reply read by the real ``KiteMargin`` client through its transport
seam (fixture shape of ``tests/fixtures/kite_margins``); the broker quote answer is a Kite ``/quote`` JSON reply (shape
of ``tests/fixtures/kite_quotes``).

Unlike ``pinned_clock`` / ``replay_mode`` (test only), this mode is allowed in ``development`` too: the owner looks at
the scenario screens on ofo_dev. Any other ``APP_ENV`` (production, staging, unset, a case or space variant) refuses
the setting at start-up, twice: ``config.Settings`` validator and ``require_dev_or_test`` here (called by
``main.create_app`` before anything is served). An empty or blank ``OFO_SCENARIO`` is "not set".

ONE reader: ``_raw()`` is the only code that reads ``OFO_SCENARIO`` (finding setting-read-from-two-sources; a repo test
greps for the name). ``config.Settings`` declares the field only to refuse it.

No order path in this mode: ``refuse_orders`` (409, catalogue ``scenario_no_orders``) runs first on every route that
posts a basket, places, modifies or cancels (``order_path_switch.require_order_path`` asks it first; the paper order
and trigger routes carry it as a route dependency). ``main.create_app`` also refuses to start in scenario mode when a
mutating route is in neither ``ORDER_ROUTES`` nor ``NON_ORDER_ROUTES`` (fail closed on a new route).

Answer states of each scenario source (standing item d):
- id: stated + matches ``ADJ-[0-9]{2}[a-e]?`` and is a file in the fixture folder -> served; absent / blank -> mode off;
  malformed (``../x``, ``ADJ-02.json``) or not found -> ``ScenarioRefused`` at start-up (no file outside the folder is
  ever opened).
- clock: stated -> the one answer clock and the provider clock; absent / not ISO -> ``ScenarioRefused``.
- chain rows: listed -> an instrument row + a full packet; ``listed: false`` -> no instrument row (the strike is not
  in the instrument list, ADJ-20d); ``ltp`` null on a listed row -> instrument row, no packet (unpriced); empty chain ->
  no contracts (the chain answers with none, never an error).
- data_state.feed: ``ok`` -> packets received ``age_seconds`` before the clock; ``stale`` -> the same, so the feed's
  own health rule reads them stale (ADJ-19); ``missing`` -> no index packet (spot absent from the feed, ADJ-24a/b);
  any other value -> ``ScenarioRefused``.
- data_state.rest (REST index quote, ``rest_index_quote``): ``ok`` -> a Kite success reply with the spot; ``failed`` ->
  a Kite NetworkException error reply; anything else -> ``ScenarioRefused``.
- broker.margin: ``stated`` / ``empty`` -> the reply as HTTP 200 (empty data -> the real client's "no figure");
  ``failed`` -> HTTP 504 with the error reply (the client's "unavailable"); other -> ``ScenarioRefused``.
- broker.quote legs: ``stated`` -> in the ``/quote`` data; ``not found`` -> absent from data (what Kite does for an
  unknown symbol); other -> ``ScenarioRefused``.
- low_oi: carried as the scenario states it (``stated`` / ``unknown``) in ``low_oi_state`` for the adjustment route.

Known bypasses (out of the threat model: dev must not be protected from a developer editing code):
- a route that reads ``datetime.now`` itself instead of ``outcome.get_answer_clock`` / the context clock shows the real
  time; listed in the work report (``catalogue_picker.database_today`` reads the DATABASE clock, so the stored
  catalogue routes ``/api/catalogue/*`` still show the real catalogue, not the scenario's contracts).
- the chain / index sockets and the strategy socket serve the scenario snapshot, not a moving market.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.instruments.models import BSE_INDEX, INDEX_ROWS, NSE_INDEX
from ofo.instruments.parser import parse_instruments_rows
from ofo.marketdata.kite_provider import KiteProvider

ENV_NAME = "OFO_SCENARIO"
OPEN_ENVIRONMENTS = frozenset({"development", "test"})
FIXTURES = pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "adjust_scenarios"
_ID = re.compile(r"ADJ-[0-9]{2}[a-e]?")
TEMPLATE = "scenario_no_orders"

#: (method, path) of every route that posts a basket, places, modifies or cancels an order (real or paper).
ORDER_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/strategies/{strategy_id}/execute"),
    ("POST", "/strategies/{strategy_id}/execution/return"),
    ("POST", "/paper/strategies/{strategy_id}/orders"),
    ("POST", "/paper/strategies/{strategy_id}/triggers"),
    ("DELETE", "/paper/strategies/{strategy_id}/triggers/{trigger_id}"),
    ("POST", "/strategies/{strategy_id}/tracking/exit"),  # places paper exit orders (paper_store.place)
})
#: Every other mutating route, each one checked: none of them prepares, places, modifies or cancels an order.
NON_ORDER_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/broker/disconnect"),  # ends the broker session
    ("POST", "/api/strategies/leg-edit"),  # engine answer for one edited leg
    ("POST", "/api/strategies/outcome"),  # engine answer (a read)
    ("POST", "/paper/alerts/read"),  # marks alerts read
    ("POST", "/api/strategies/planned-entry"),  # captures planned prices
    ("POST", "/api/strategies/load-template"),  # a ready-made shape into the builder
    ("POST", "/api/strategies/quick-pick"),  # a quick pick into the builder
    ("POST", "/strategies"),
    ("PATCH", "/strategies/{strategy_id}/name"),
    ("DELETE", "/strategies/{strategy_id}"),
    ("POST", "/strategies/{strategy_id}/undelete"),
    ("PUT", "/strategies/{strategy_id}"),
    ("POST", "/strategies/{strategy_id}/restore/{seq}"),
    ("POST", "/strategies/{strategy_id}/versions/{number}/confirm"),
})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_SEGMENT_CODE = {"NFO": 2, "BFO": 4}  # Kite instrument_token low byte (ofo.marketdata.kite_frames.SEGMENT_DIVISOR)
_INDEX_SEGMENT_CODE = 9
_INDEX_OF = {"NIFTY": (NSE_INDEX, "NSE"), "SENSEX": (BSE_INDEX, "BSE")}
_FIRST_TOKEN = 900_000  # synthetic exchange tokens: far from the real catalogue's, never written to the database
_FEED_STATES = frozenset({"ok", "stale", "missing"})
_REST_STATES = frozenset({"ok", "failed"})


class ScenarioRefused(RuntimeError):
    """Scenario mode was requested outside APP_ENV development/test, or names no valid scenario."""


def _raw() -> str:
    """THE one read of OFO_SCENARIO (blank = not set)."""
    return os.environ.get(ENV_NAME, "").strip()


def scenario_requested() -> bool:
    return bool(_raw())


def require_dev_or_test(app_env: str | None) -> None:
    if app_env not in OPEN_ENVIRONMENTS:
        raise ScenarioRefused(f"{ENV_NAME} is a development/test-only setting: it needs APP_ENV=development or test")


def scenario_path(scenario_id: str) -> pathlib.Path:
    """The fixture file of a scenario id; refuses anything but ``ADJ-nn`` (+ one letter a-e) naming a file there."""
    if not _ID.fullmatch(scenario_id):
        raise ScenarioRefused(f"{ENV_NAME} must look like ADJ-02 or ADJ-20a")
    path = FIXTURES / f"{scenario_id}.json"
    if path.resolve().parent != FIXTURES or not path.is_file():
        raise ScenarioRefused(f"{ENV_NAME}: no such scenario in the library")
    return path


def _at(text: object) -> datetime.datetime:
    try:
        at = datetime.datetime.fromisoformat(str(text))
    except ValueError:
        raise ScenarioRefused("scenario clock is not an ISO time") from None
    if at.tzinfo is None:
        raise ScenarioRefused("scenario clock has no offset")
    return at


def instrument_id(lc: Any) -> str:
    """The platform's instrument id of a contract: ``<exchange_segment>:<exchange_token>``."""
    return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"


def _paise(value: object) -> int:
    return int(Decimal(str(value)).scaleb(2).to_integral_value())  # rupees -> integer paise, as Kite sends them


def _full_packet(token: int, row: Mapping[str, Any], ts: int) -> bytes:
    """A Kite full-mode packet (184 bytes, layout of ofo.marketdata.kite_frames): ltp, OI, exchange time, one depth
    level per side (bid / ask; a missing side is price 0 = absent, F-29)."""
    ltp = _paise(row["ltp"])
    head = struct.pack(">i10i", token, ltp, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    tail = struct.pack(">iiiii", ts, int(row.get("oi") or 0), 0, 0, ts)
    levels = b""
    for side in ("bid", "ask"):
        quoted = row.get(side) is not None
        levels += struct.pack(">iihh", 650 if quoted else 0, _paise(row[side]) if quoted else 0,
                              5 if quoted else 0, 0)
        levels += struct.pack(">iihh", 0, 0, 0, 0) * 4
    return head + tail + levels


def _index_packet(token: int, spot: object, ts: int) -> bytes:
    """A Kite index packet (32 bytes: ltp, high, low, open, close, change, exchange time)."""
    return struct.pack(">i6ii", token, _paise(spot), 0, 0, 0, 0, 0, ts)


def _frame(packets: list[bytes]) -> bytes:
    out = len(packets).to_bytes(2, "big")
    for p in packets:
        out += len(p).to_bytes(2, "big") + p
    return out


@dataclass
class Scenario:
    """One loaded scenario: its parsed contracts, fed provider and broker answers."""

    scenario_id: str
    data: dict
    clock_at: datetime.datetime
    provider: KiteProvider
    rows_by_id: dict[str, dict]  # instrument_id -> the scenario chain row (low-OI state, listed, tradable)

    def clock(self) -> datetime.datetime:
        return self.clock_at

    @property
    def rate(self) -> Decimal:
        return Decimal(str(self.data["market"].get("rate") or "0.065"))

    @property
    def data_state(self) -> dict:
        return dict(self.data.get("data_state") or {})

    def banner(self) -> str:
        return f"Scenario {self.scenario_id} - test data, not the market"

    def low_oi_state(self, instrument_id: str) -> str | None:
        row = self.rows_by_id.get(instrument_id)
        return None if row is None else (row.get("low_oi") or {}).get("state")

    # ---- broker answers in Kite's own reply shapes ------------------------------------------------------------
    def margin_transport(self, method: str, url: str, headers: dict[str, str], body: str | None) -> tuple[int, str]:
        """``KiteMargin``'s transport seam: the scenario's margin reply as Kite sends it."""
        margin = self.data["broker"]["margin"]
        state = margin.get("state")
        if state in ("stated", "empty"):
            return 200, json.dumps(margin["reply"])
        if state == "failed":
            return 504, json.dumps(margin["reply"])
        raise ScenarioRefused(f"unknown margin state {state!r}")

    def quote_reply(self) -> dict:
        """Kite ``GET /quote`` reply for the position's legs; a ``not found`` leg is absent from ``data``."""
        data: dict[str, dict] = {}
        exchange = self.data.get("exchange", "NFO")
        for leg in self.data["broker"]["quote"]["legs"]:
            state = leg.get("state")
            if state == "not found":
                continue
            if state != "stated":
                raise ScenarioRefused(f"unknown quote leg state {state!r}")
            data[f"{exchange}:{leg['tradingsymbol']}"] = {
                "last_price": leg["last_price"], "timestamp": leg["timestamp"], "depth": leg["depth"]}
        return {"status": "success", "data": data}

    def rest_index_quote(self) -> tuple[int, dict]:
        """Kite ``GET /quote?i=NSE:NIFTY 50`` (REST index spot, F-76) as (HTTP status, reply)."""
        state = self.data_state.get("rest", "ok")
        if state == "failed":
            return 504, {"status": "error", "error_type": "NetworkException", "message": "Gateway timed out",
                         "data": None}
        if state != "ok":
            raise ScenarioRefused(f"unknown REST state {state!r}")
        underlying = self.data["underlying"]
        segment, exchange = _INDEX_OF[underlying]
        name = next(n for (s, _t), (n, _u) in INDEX_ROWS.items() if s == segment)
        stamp = self.clock_at.strftime("%Y-%m-%d %H:%M:%S")
        return 200, {"status": "success", "data": {f"{exchange}:{name}": {
            "last_price": float(Decimal(str(self.data["market"]["spot"]))),  # float-ok: Kite's own JSON shape
            "timestamp": stamp}}}


def _instrument_rows(scn: dict) -> tuple[list[dict], list[tuple[int, dict]], int]:
    """Zerodha instrument-list rows (the real CSV columns) for the index and every LISTED chain row, the (token, row)
    pairs that get a packet, and the index token."""
    underlying, exchange = scn["underlying"], scn.get("exchange", "NFO")
    segment, index_exchange = _INDEX_OF[underlying]
    index_token_ex = next(t for (s, t) in INDEX_ROWS if s == segment)
    index_name = INDEX_ROWS[(segment, index_token_ex)][0]
    index_token = index_token_ex * 256 + _INDEX_SEGMENT_CODE
    rows = [{"instrument_token": str(index_token), "exchange_token": str(index_token_ex), "tradingsymbol": index_name,
             "name": index_name, "last_price": "0", "expiry": "", "strike": "0", "tick_size": "0", "lot_size": "0",
             "instrument_type": "EQ", "segment": "INDICES", "exchange": index_exchange}]
    priced: list[tuple[int, dict]] = []
    code = _SEGMENT_CODE[exchange]
    n = _FIRST_TOKEN
    for chain in scn["market"].get("chains") or []:
        for row in chain["rows"]:
            n += 1
            if not row.get("listed", True):
                continue  # not in the instrument list (ADJ-20d)
            token = n * 256 + code
            rows.append({"instrument_token": str(token), "exchange_token": str(n),
                         "tradingsymbol": row["tradingsymbol"], "name": underlying, "last_price": "0",
                         "expiry": chain["expiry"], "strike": str(row["strike"]), "tick_size": str(scn["tick"]),
                         "lot_size": str(scn["lot"]), "instrument_type": row["type"], "segment": f"{exchange}-OPT",
                         "exchange": exchange})
            if row.get("ltp") is not None:
                priced.append((token, row))
    return rows, priced, index_token


def load(scenario_id: str) -> Scenario:
    """Loads and feeds one scenario (no environment read here: ``current`` passes the id)."""
    scn = json.loads(scenario_path(scenario_id).read_text(encoding="utf-8"))
    clock_at = _at((scn.get("clock") or {}).get("ist"))
    state = scn.get("data_state") or {}
    feed = state.get("feed", "ok")
    if feed not in _FEED_STATES:
        raise ScenarioRefused(f"unknown feed state {feed!r}")
    if state.get("rest", "ok") not in _REST_STATES:
        raise ScenarioRefused(f"unknown REST state {state.get('rest')!r}")
    rows, priced, index_token = _instrument_rows(scn)
    listed = list(parse_instruments_rows(rows))  # the real instrument-list parser
    provider = KiteProvider(listed, clock=lambda: clock_at)
    provider.subscribe([instrument_id(lc) for lc in listed])
    received = clock_at - datetime.timedelta(seconds=int(state.get("age_seconds") or 0))
    ts = int(received.timestamp())
    provider.on_connected(received)
    packets = [_full_packet(token, row, ts) for token, row in priced]
    if feed != "missing":
        packets.append(_index_packet(index_token, scn["market"]["spot"], ts))
    if packets:
        provider.on_frame(_frame(packets), received)  # the real frame parser
    by_token = {int(lc.broker_refs[0].broker_token): lc for lc in listed}
    rows_by_id = {instrument_id(by_token[t]): r for t, r in priced}
    return Scenario(scenario_id, scn, clock_at, provider, rows_by_id)


_loaded: dict[str, Scenario] = {}  # the one loaded scenario, by id


def current() -> Scenario | None:
    """The running app's scenario, or None when the mode is off. Refuses outside APP_ENV development/test."""
    if not scenario_requested():
        return None
    from ofo_app.config import app_env  # noqa: PLC0415 - late: keep this module import-light

    require_dev_or_test(app_env())
    sid = _raw()
    if sid not in _loaded:
        _loaded.clear()
        _loaded[sid] = load(sid)
    return _loaded[sid]


def scenario_flag() -> str | None:
    """The id the banner shows, or None. Never raises (a read-only status answer); start-up already refused."""
    try:
        scn = current()
    except ScenarioRefused:
        return None
    return None if scn is None else scn.scenario_id


def refuse_orders() -> None:
    """The order refusal (409, catalogue ``scenario_no_orders``) while scenario mode is on; runs before the endpoint's
    own dependencies, so no Kite call and no database write happen."""
    if scenario_requested():
        from ofo_app.errors import Failure  # noqa: PLC0415 - late, like order_path_switch
        from ofo_app.routes.strategies import StrategyRefused  # noqa: PLC0415

        raise StrategyRefused(TEMPLATE, Failure.CONFLICT)


def overrides(scn: Scenario) -> dict[Any, Any]:
    """The dependency overrides (main.create_app installs them) wiring the scenario at the seams the replay
    mode and the tests use: the market context (outcome, chain, indices,
    leg picker, planned entry, tracking all depend on ``outcome.get_market_context``), the answer clock, the stored
    catalogue readers of the chain and leg picker, the margin source, and the shared live feed (sockets)."""
    from ofo.marketdata.fanout import FanOut  # noqa: PLC0415 - only in scenario mode

    from ofo_app.catalogue_picker import PickableContract  # noqa: PLC0415
    from ofo_app.chain_push import ChainCatalogue  # noqa: PLC0415
    from ofo_app.kite_margin import KiteMargin  # noqa: PLC0415
    from ofo_app.live_push import LiveFeed  # noqa: PLC0415
    from ofo_app.outcome_margin import OutcomeMargin  # noqa: PLC0415
    from ofo_app.routes import chain, leg_picker, live, outcome, planned_entry  # noqa: PLC0415

    ctx = outcome.MarketContext(scn.provider, scn.clock, scn.rate)
    feed = LiveFeed(ctx, FanOut(scn.provider))
    contracts: list[Any] = []
    permissions: dict[str, str] = {}
    for lc in scn.provider.instrument_master():
        c = lc.contract
        if c.expiry is None:
            continue  # the index row
        iid = instrument_id(lc)
        contracts.append(PickableContract(contract_id=c.exchange_token, instrument_id=iid,
                                          exchange_segment=c.exchange_segment, exchange_token=c.exchange_token,
                                          instrument_type=c.instrument_type, expiry=c.expiry, strike=c.strike,
                                          lot_size=c.lot_size, symbol=lc.broker_refs[0].broker_symbol))
        row = scn.rows_by_id.get(iid)
        permissions[iid] = "permitted" if row is None or row.get("tradable", True) else "restricted"
    expiries = tuple(sorted({c.expiry for c in contracts}))

    async def chain_reader(underlying: str, expiry: datetime.date) -> ChainCatalogue:
        if underlying != scn.data["underlying"]:
            return ChainCatalogue(expiries=(), contracts=())
        options = tuple(c for c in contracts if c.expiry == expiry)
        return ChainCatalogue(expiries=expiries, contracts=options,
                              permissions={c.instrument_id: permissions[c.instrument_id] for c in options})

    async def futures_reader(underlying: str) -> leg_picker.FuturesCatalogue:
        own = underlying == scn.data["underlying"]
        return leg_picker.FuturesCatalogue(option_expiries=expiries if own else (), futures=())

    async def open_client() -> KiteMargin:
        return KiteMargin(api_key="scenario", access_token="scenario",  # noqa: S106 - no real token: the
                          transport=scn.margin_transport)  # scenario transport never reaches Kite

    margin = OutcomeMargin(lambda: ("scenario", scn.scenario_id), open_client, clock=scn.clock)
    live.set_replay_feed(lambda: feed)
    return {
        outcome.get_market_context: lambda: ctx,
        outcome.get_answer_clock: lambda: scn.clock,
        outcome.get_streaming: lambda: None,
        outcome.get_margin_source: lambda: margin,
        chain.get_chain_reader: lambda: chain_reader,
        leg_picker.get_picker_reader: lambda: chain_reader,
        leg_picker.get_futures_reader: lambda: futures_reader,
        leg_picker.get_feed: lambda: feed,
        planned_entry.get_live_feed: lambda: feed,
    }


def unclassified_mutating_routes(routes: list[Any]) -> list[tuple[str, str]]:
    """Every (method, path) of a mutating HTTP route in neither ORDER_ROUTES nor NON_ORDER_ROUTES."""
    out = []
    for r in routes:
        for m in sorted(getattr(r, "methods", None) or ()):
            key = (m, getattr(r, "path", ""))
            if m in MUTATING_METHODS and key not in ORDER_ROUTES and key not in NON_ORDER_ROUTES:
                out.append(key)
    return out
