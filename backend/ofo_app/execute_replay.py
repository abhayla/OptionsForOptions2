"""TEST-ONLY Execute/return replay (W-101; REQ-073 AC-3, AC-4): the recorded 2026-10-16 Kite session behind both
order routes.

When ``EXECUTE_REPLAY`` is set AND ``APP_ENV`` is ``test``, ``create_app`` overrides the Execute route's Kite session,
quote reader and clock (and so the return route's, which uses the same seams) with the owner's REAL recorded replies
(tests/fixtures/kite_replies, README there; the full depth frame in tests/fixtures/kite_ws). Any other ``APP_ENV``
refuses the setting at start-up, before anything is served, so a production process can never answer Execute from a
recording. Nothing here opens a socket or calls Kite: the transport is the recorded files only, and the runtime egress
gate (``ofo.broker.egress``) stays installed.

The route tests (tests_app/test_execute_route.py, test_execution_return.py) import the same seams from here: one copy.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request
from ofo.engine import Action
from ofo.instruments import NSE_FO, InstrumentId
from ofo.instruments.parser import parse_instruments_csv, zerodha_listed
from ofo.marketdata.kite_provider import IST, KiteProvider

from ofo_app import execute_plan as ep
from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import KiteReads
from ofo_app.routes import execute

ENV_NAME = "EXECUTE_REPLAY"
_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
REPLIES = _ROOT / "kite_replies"
_KITE_WS = _ROOT / "kite_ws"
DEPTH_FRAME = _KITE_WS / "full-frame-12080386-150720.bin"
_FRAME_INSTRUMENTS = _KITE_WS / "instruments-2026-10-08-subscribed.csv"
_SLICE_FILE = _ROOT / "eligibility" / "instruments-2026-10-16-slice.json"

#: the fixed api_key the replay basket carries (a test value, never read from ``.env``)
REPLAY_API_KEY = "kitekey"
_REPLAY_TOKEN = "tok"  # noqa: S105 - not a secret: the recorded transport never sends it anywhere
TOKEN = "12080386"
CORE_ID = InstrumentId(NSE_FO, 47189)
#: the market-hours instant of the real 2026-10-16 entry (the pinned request clock)
AT = datetime.datetime(2026, 10, 16, 15, 7, 21, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
FRAME_AT = datetime.datetime.fromtimestamp(1792143440, IST)  # the depth frame's exchange time, 15:07:20 IST
#: fetch.json's NIFTY spot and its own time (the recorder's index read, README there)
SPOT = (Decimal("23094.95"), datetime.datetime(2026, 10, 16, 15, 7, 17, tzinfo=AT.tzinfo))
REAL_BASKET = json.loads((REPLIES / "basket-121848.json").read_text(encoding="utf-8"))
(REAL_ORDER,) = json.loads(REAL_BASKET["data"], parse_float=Decimal)

#: Zerodha's basket-margin reply per basket total: the EXIT reply is the REAL one (fetch.json ``margin_raw``, SELL 65
#: @ 3.30, final.total -214.5); the ENTRY reply is DERIVED from it with the recorder's entry total 354.25 (README).
_BASKET_REPLIES = {"354.25": "margins-basket-entry-derived.json", "-214.5": "margins-basket-exit-150717.json"}
_MONEY_KEYS = {"last_price", "average_price", "lower_circuit_limit", "upper_circuit_limit", "price", "open", "high",
               "low", "close", "low_limit_price_protection", "high_limit_price_protection"}
_TRUE = {"1", "true", "yes", "on"}


class ExecuteReplayRefused(RuntimeError):
    """The Execute replay was requested outside APP_ENV=test."""


def replay_requested() -> bool:
    return os.environ.get(ENV_NAME, "").strip().lower() in _TRUE


def require_test_env(app_env: str) -> None:
    """Allow-list: exactly ``test``; every other value (empty, production, a case or space variant) is refused."""
    if app_env != "test":
        raise ExecuteReplayRefused(f"{ENV_NAME} is a test-only setting: it needs APP_ENV=test")


# ---- the recorded replies --------------------------------------------------------------------------------------------

def basket_reply(total: str) -> str:
    return (REPLIES / _BASKET_REPLIES[total]).read_text(encoding="utf-8")


def _rows(reply: Any) -> Any:
    return reply["data"] if isinstance(reply, dict) and "data" in reply else reply


class RecordedKite:
    """Transport for both Zerodha clients, answering with recorded replies only (no socket, no Kite)."""

    quote_text: str | None = None  # a /quote body to serve instead of the recorded quote-150720.json
    order_rows: list | None = None  # rows derived from the real replies, else the named fixture
    position_rows: list | None = None

    def __init__(self, *, funds: str, basket_total: str, orders: str | None, positions: str,
                 trades: str | None = None, reads_only: bool = False) -> None:
        self.funds, self.basket_total, self.orders, self.positions = funds, basket_total, orders, positions
        self.trades, self.reads_only = trades, reads_only

    def _reply(self, name: str) -> Any:
        return json.loads((REPLIES / f"{name}.json").read_text(encoding="utf-8"), parse_float=Decimal)

    def __call__(self, method: str, url: str, headers: Any, body: Any) -> tuple[int, str]:  # noqa: ARG002
        if self.reads_only and method != "GET":
            raise AssertionError(f"the return replay answers reads only, not {method} {url}")
        if "/quote?i=" in url:
            return 200, self.quote_text or (REPLIES / "quote-150720.json").read_text(encoding="utf-8")
        if url.endswith("/user/margins"):
            return 200, '{"status": "success", "data": {"equity": {"enabled": true, "net": %s}}}' % self.funds  # noqa: UP031
        if "/margins/basket" in url:
            return 200, basket_reply(self.basket_total)
        if url.endswith("/orders"):
            data = self.order_rows if self.order_rows is not None else (
                [] if self.orders is None else _rows(self._reply(self.orders)))
            return 200, json.dumps({"status": "success", "data": data}, default=str)
        if url.endswith("/trades"):
            data = [] if self.trades is None else _rows(self._reply(self.trades))
            return 200, json.dumps({"status": "success", "data": data}, default=str)
        if url.endswith("/portfolio/positions"):
            data = self._reply(self.positions)
            data = data.get("data", data)
            if self.position_rows is not None:
                data = {**data, "net": self.position_rows}
            return 200, json.dumps({"status": "success", "data": data}, default=str)
        raise AssertionError(f"no recorded reply for {method} {url}")


def session_for(replay: RecordedKite) -> Any:
    """A Kite session (``execute.KiteSession``) whose two clients speak only to ``replay``."""
    reads = KiteReads(api_key=REPLAY_API_KEY, access_token=_REPLAY_TOKEN, transport=replay)
    margin = KiteMargin(api_key=REPLAY_API_KEY, access_token=_REPLAY_TOKEN, transport=replay)
    return execute._Session(REPLAY_API_KEY, reads, margin)  # noqa: SLF001 - the route's own session shape


def entry_replay() -> RecordedKite:
    """Before the 2026-10-16 entry: no order today, flat book (15:10:06 positions), funds 1003, basket 354.25."""
    return RecordedKite(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")


def return_replay() -> RecordedKite:
    """12:21:04, after the entry filled: OFS1V1L0 COMPLETE 65, its trade, +65 held."""
    return RecordedKite(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104",
                        trades="trades-122104", reads_only=True)


# ---- quotes ------------------------------------------------------------------------------------------------------------

def _live(value: object) -> object:
    if isinstance(value, dict):
        return {k: (Decimal(v) if k in _MONEY_KEYS and isinstance(v, str) else _live(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_live(v) for v in value]
    return value


def live_quote() -> dict:
    """quote-151720.json with each money string turned into the Decimal live Kite REST gives (``parse_float``)."""
    return _live(json.loads((REPLIES / "quote-151720.json").read_text(encoding="utf-8"), parse_float=Decimal))


class DepthQuotes:
    """The depth source: depth and last price only, NO band (as the live feed); the band comes from Zerodha's quote."""

    def __init__(self, quote: ep.LegQuote) -> None:
        self.quote = ep.LegQuote(quote.depth, quote.at, quote.last_price, None)

    def leg_quote(self, instrument_id: InstrumentId, token: str) -> ep.LegQuote | None:  # noqa: ARG002
        return self.quote if token == TOKEN else None

    def underlying_price(self, underlying: str) -> tuple[Decimal, datetime.datetime] | None:  # noqa: ARG002
        return SPOT


def frame_quote() -> ep.LegQuote:
    """The recorded full frame of 15:07:20 read through the live feed's own provider (depth + its last price)."""
    provider = KiteProvider(list(parse_instruments_csv(_FRAME_INSTRUMENTS)), clock=lambda: FRAME_AT)
    key = f"{CORE_ID.exchange_segment}:{CORE_ID.exchange_token}"
    provider.subscribe([key])
    provider.on_connected(FRAME_AT)
    provider.on_frame(DEPTH_FRAME.read_bytes(), FRAME_AT)
    depth = provider.latest_depth(key, FRAME_AT)
    priced = execute.price_and_time(provider.book.get(key, FRAME_AT))
    if depth is None or priced is None:
        raise ExecuteReplayRefused("the recorded depth frame holds no depth for the replay contract")
    return ep.LegQuote(depth, priced[1], priced[0], None)


# ---- the app overrides -------------------------------------------------------------------------------------------------

def _replay_session(request: Request) -> Any:
    """The return route reads the 12:21:04 book; every other route (Execute) the book before the entry."""
    if request.url.path.endswith("/execution/return"):
        return session_for(return_replay())
    return session_for(entry_replay())


def install(app: FastAPI) -> None:
    """Overrides the Execute (and so the return) route's session, quote reader and clock with the recording."""
    quotes = DepthQuotes(frame_quote())
    app.dependency_overrides[execute.get_kite_session] = _replay_session
    app.dependency_overrides[execute.get_quote_reader] = lambda: quotes
    app.dependency_overrides[execute.get_execute_clock] = lambda: (lambda: AT)


# ---- the stored strategy (route tests and the seed command) -----------------------------------------------------------

def listed_contract() -> Any:
    """NIFTY26O1923650CE as Zerodha listed it on 2026-10-16 (the eligibility slice)."""
    row = json.loads(_SLICE_FILE.read_text(encoding="utf-8"), parse_float=Decimal)["list"][TOKEN]
    return zerodha_listed(
        instrument_token=int(TOKEN), exchange_token=int(TOKEN) >> 8, tradingsymbol=row["symbol"],
        name=row["group"].split()[0], expiry=datetime.date.fromisoformat(row["expiry"]), strike=Decimal(row["strike"]),
        tick_size=Decimal("0.05"), lot_size=int(row["lot"]), instrument_type=row["type"], segment="NFO-OPT",
        exchange="NFO")


async def store_strategy_one(conn: Any, user: str, app_role: str, units: int = 65) -> int:
    """Strategy id 1 (the real tags OFS1V1...): saved through the store, then given id 1 as the owner role (the
    application role cannot write ``id``), then the transaction continues as the application role and a Pro grant is
    added. The caller owns the transaction (the route tests roll it back; the seed commits it)."""
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    from ofo_app.catalogue_store import apply_update  # noqa: PLC0415
    from ofo_app.strategy_store import build_definition, save_draft  # noqa: PLC0415

    await apply_update(conn, [listed_contract()], as_of=datetime.datetime(2026, 10, 16, 9, 0, tzinfo=AT.tzinfo))
    cid = (await conn.execute(text("SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments b "
                                   "ON b.contract_id = c.id WHERE b.broker_symbol = :s AND NOT c.retired"),
                              {"s": REAL_ORDER["tradingsymbol"]})).scalar_one()
    saved = await build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, units, None)],
                                   rules_ref=None, risk_limits={}, preferences={})
    made = await save_draft(conn, user, saved)
    await conn.execute(text("SET LOCAL session_replication_role = replica"))
    await conn.execute(text("UPDATE public.strategies SET id = 1 WHERE id = :s"), {"s": made.id})
    await conn.execute(text("UPDATE public.strategy_history SET strategy_id = 1 WHERE strategy_id = :s"),
                       {"s": made.id})
    await conn.execute(text("SET LOCAL session_replication_role = origin"))
    await conn.execute(text(f'SET LOCAL ROLE "{app_role}"'))
    await pro_grant(conn, user)
    return 1


async def pro_grant(conn: Any, user: str) -> None:
    """A real Pro grant through the entitlement store, ``granted_at`` = the database's own clock (ADR-023: the
    database refuses a date more than 60 s off its clock; no trigger disabled, nothing backdated)."""
    from ofo.entitlements.events import AuditNote, NewGrant, Source  # noqa: PLC0415

    from ofo_app import eligibility_from_zerodha as elig  # noqa: PLC0415
    from ofo_app import entitlement_store  # noqa: PLC0415

    now = await elig.database_now(conn)
    await entitlement_store.append(conn, user, NewGrant("pro-core", Source.PAID_MONTHLY, now,
                                                        datetime.timedelta(days=30), "pay-core",
                                                        AuditNote("system", "core test")))
