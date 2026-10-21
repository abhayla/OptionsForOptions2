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
import functools
import json
import pathlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi import Request
from ofo.engine import Action
from ofo.execution.basket import make_tag
from ofo.instruments import NSE_FO, InstrumentId
from ofo.instruments.parser import parse_instruments_csv, zerodha_listed
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.timeutil import IST_UNNAMED

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execute_plan as ep
from ofo_app.execute_replay_switch import ENV_NAME, ExecuteReplayRefused, replay_requested, require_test_env
from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import KiteReads
from ofo_app.routes import execute

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
AT = datetime.datetime(2026, 10, 16, 15, 7, 21, tzinfo=IST_UNNAMED)
#: the recorded day's instrument-list load: the seed stores the listed contract with this ``as_of``, and the replay's
#: list stamp answers it (``replay_list_stamp``). After Zerodha's 08:30 publish time, the same day as ``AT``.
LIST_LOADED_AT = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=IST_UNNAMED)
FRAME_AT = datetime.datetime.fromtimestamp(1792143440, IST)  # the depth frame's exchange time, 15:07:20 IST
#: fetch.json's NIFTY spot and its own time (the recorder's index read, README there)
SPOT = (Decimal("23094.95"), datetime.datetime(2026, 10, 16, 15, 7, 17, tzinfo=AT.tzinfo))

#: Zerodha's basket-margin reply per basket total: the EXIT reply is the REAL one (fetch.json ``margin_raw``, SELL 65
#: @ 3.30, final.total -214.5); the ENTRY reply is DERIVED from it with the recorder's entry total 354.25 (README).
_BASKET_REPLIES = {"354.25": "margins-basket-entry-derived.json", "-214.5": "margins-basket-exit-150717.json"}
_MONEY_KEYS = {"last_price", "average_price", "lower_circuit_limit", "upper_circuit_limit", "price", "open", "high",
               "low", "close", "low_limit_price_protection", "high_limit_price_protection"}
__all__ = ["ENV_NAME", "ExecuteReplayRefused", "replay_requested", "require_test_env"]  # the switch, re-exported


# ---- every fixture is read lazily (inside a function): importing this module reads no file ---------------------------

#: A legacy tag as a whole JSON string value, plain ("OFS1V1L0") or inside an escaped JSON string (\"OFS1V1L0\").
_LEGACY_RECORDED_TAG = re.compile(r'(?<=")OFS([1-9][0-9]*)V([1-9][0-9]*)L(0|[1-9][0-9]*)(?=\\?")', re.ASCII)


def retag_recorded(text: str) -> str:
    """A recording's text with every legacy tag ``OFS<s>V<p>L<l>`` replaced by ``make_tag(s, p, l)``.

    The recordings (tests/fixtures/kite_replies) were made on 2026-10-16, before the 8-character basket grammar of
    2026-10-19 (finding basket-tag-exceeds-publisher-limit, migration 0018). A test or the test-only replay that runs
    Execute stores the new grammar, so the recorded book is read with the same tags; the translation touches only a
    whole JSON string value matching the legacy grammar and preserves every other byte. TEST AND REPLAY ONLY: the
    product reads Zerodha's real book as it is, and ``parse_tag`` decodes a real legacy tag with its old meaning."""
    return _LEGACY_RECORDED_TAG.sub(lambda m: make_tag(int(m[1]), int(m[2]), int(m[3])), text)


def recorded_text(name: str) -> str:
    """``REPLIES / name`` as text, legacy tags translated (``retag_recorded``)."""
    return retag_recorded((REPLIES / name).read_text(encoding="utf-8"))


@functools.cache
def real_basket() -> dict:
    """The entry basket the owner sent on 2026-10-16 (basket-121848.json), its tag translated (``retag_recorded``)."""
    return json.loads(recorded_text("basket-121848.json"))


def real_order() -> dict:
    (order,) = json.loads(real_basket()["data"], parse_float=Decimal)
    return order


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

    def __init__(self, *, funds: str, basket_total: str, orders: str | None, positions: str,  # noqa: PLR0913
                 trades: str | None = None, reads_only: bool = False) -> None:
        self.funds, self.basket_total, self.orders, self.positions = funds, basket_total, orders, positions
        self.trades, self.reads_only = trades, reads_only
        self.calls: list[str] = []  # every Kite URL asked (W-102: the cost adds no Zerodha read)

    def _reply(self, name: str) -> Any:
        return json.loads(recorded_text(f"{name}.json"), parse_float=Decimal)

    def __call__(self, method: str, url: str, headers: Any, body: Any) -> tuple[int, str]:
        if self.reads_only and method != "GET":
            raise AssertionError(f"the return replay answers reads only, not {method} {url}")
        self.calls.append(url)
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


@dataclass(frozen=True)
class ReplaySession:
    """An ``execute.KiteSession`` whose two clients speak only to a ``RecordedKite``."""

    api_key: str
    reads: KiteReads
    margin: KiteMargin


def session_for(replay: RecordedKite) -> ReplaySession:
    reads = KiteReads(api_key=REPLAY_API_KEY, access_token=_REPLAY_TOKEN, transport=replay)
    margin = KiteMargin(api_key=REPLAY_API_KEY, access_token=_REPLAY_TOKEN, transport=replay)
    return ReplaySession(REPLAY_API_KEY, reads, margin)


def entry_replay() -> RecordedKite:
    """Before the 2026-10-16 entry: no order today, flat book (15:10:06 positions), funds 1003, basket 354.25."""
    return RecordedKite(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")


def return_replay() -> RecordedKite:
    """12:21:04, after the entry filled: OFS1V1L0 COMPLETE 65, its trade, +65 held."""
    return RecordedKite(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104",
                        trades="trades-122104", reads_only=True)


# ---- quotes ----------------------------------------------------------------------------------------------------------

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

    def leg_quote(self, instrument_id: InstrumentId, token: str) -> ep.LegQuote | None:
        return self.quote if token == TOKEN else None

    def underlying_price(self, underlying: str) -> tuple[Decimal, datetime.datetime] | None:
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


# ---- the app overrides -----------------------------------------------------------------------------------------------

def _replay_session(request: Request) -> ReplaySession:
    """The return route reads the 12:21:04 book; every other route (Execute) the book before the entry."""
    if request.url.path.endswith("/execution/return"):
        return session_for(return_replay())
    return session_for(entry_replay())


async def database_clock_today(conn: Any) -> datetime.date:
    """India date of the DATABASE clock (the clock that stamps a plan's ``created_at``), never the test-only pin."""
    return (await elig.database_now(conn)).astimezone(IST).date()


def _today_reader(request: Request) -> Callable[[Any], Awaitable[datetime.date]]:
    """The return route judges "today's session" on the database clock, so plan 1 (stamped by that clock) is today's
    on any date; every other route keeps the eligibility reader (the TEST_CATALOGUE_DATE pin, contract expiry)."""
    if request.url.path.endswith("/execution/return"):
        return database_clock_today
    return elig.get_eligibility_today()


async def replay_list_stamp(conn: Any) -> tuple[datetime.datetime | None, datetime.datetime]:
    """The list-freshness inputs on the RECORDED day, so the gate's rule (``execute._list_health``, unchanged) judges
    a seed made at any wall-clock hour the same way: the load at ``LIST_LOADED_AT`` judged at ``AT``. Whether a list
    was loaded at all is still read from the database (never loaded -> no stamp -> UNAVAILABLE). The database's own
    stamp time is NOT used: the trigger stamps ``clock_timestamp()`` at seed time, which before 08:30 IST is a
    pre-publish load on the database clock (round-2 MAJOR 2: CI runs 00:00-08:30 IST read STALE)."""
    return (None if await elig.list_loaded_at(conn) is None else LIST_LOADED_AT), AT


def replay_clocks() -> dict[Callable[..., Any], Callable[..., Any]]:
    """Every clock the Execute gate judges against, pinned to the recorded day TOGETHER: the request clock and the
    list-freshness pair. One dict, installed by ``overrides`` and by every route test, so no test can pin one clock
    and leave the other on the wall clock (``tests_app/test_execute_clock_seams.py`` enforces it)."""
    return {execute.get_execute_clock: lambda: (lambda: AT), execute.get_list_stamp: lambda: replay_list_stamp}


def overrides() -> dict[Callable[..., Any], Callable[..., Any]]:
    """The Execute (and so the return) route's session, quote reader and clocks, answered from the recording;
    ``create_app`` installs them (the one app-assembly file)."""
    quotes = DepthQuotes(frame_quote())
    return {execute.get_kite_session: _replay_session, execute.get_quote_reader: lambda: quotes,
            **replay_clocks(), elig.get_eligibility_today: _today_reader}


# ---- the stored strategy (route tests and the seed command) ----------------------------------------------------------

def listed_contract() -> Any:
    """NIFTY26O1923650CE as Zerodha listed it on 2026-10-16 (the eligibility slice)."""
    row = json.loads(_SLICE_FILE.read_text(encoding="utf-8"), parse_float=Decimal)["list"][TOKEN]
    return zerodha_listed(
        instrument_token=int(TOKEN), exchange_token=int(TOKEN) >> 8, tradingsymbol=row["symbol"],
        name=row["group"].split()[0], expiry=datetime.date.fromisoformat(row["expiry"]), strike=Decimal(row["strike"]),
        tick_size=Decimal("0.05"), lot_size=int(row["lot"]), instrument_type=row["type"], segment="NFO-OPT",
        exchange="NFO")


async def store_strategy_one(conn: Any, user: str, app_role: str, units: int = 65, entry: Any = None) -> int:
    """Strategy id 1 (the real tags OFS1V1...): saved through the store, then given id 1 as the owner role (the
    application role cannot write ``id``), then the transaction continues as the application role and a Pro grant is
    added. The caller owns the transaction (the route tests roll it back; the seed commits it). ``entry`` is the leg's
    ADR-075 planned entry (``stored_form.LegEntry``): the route tests store none; the seed stores the recorded one, as
    a strategy saved from the Strategy Builder carries it (W-104: the Execute screen follows only a priced strategy)."""
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    from ofo_app.catalogue_store import apply_update  # noqa: PLC0415
    from ofo_app.strategy_store import build_definition, save_draft  # noqa: PLC0415

    await apply_update(conn, [listed_contract()], as_of=LIST_LOADED_AT)
    cid = (await conn.execute(text("SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments b "
                                   "ON b.contract_id = c.id WHERE b.broker_symbol = :s AND NOT c.retired"),
                              {"s": real_order()["tradingsymbol"]})).scalar_one()
    saved = await build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, units, entry)],
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
    database refuses a date more than 60 s off its clock; nothing backdated). ``store_strategy_one`` disables
    triggers (``session_replication_role = replica``) only for the id-1 renumbering and restores them before this
    grant, so the grant runs with every trigger on."""
    from ofo.entitlements.events import AuditNote, NewGrant, Source  # noqa: PLC0415

    from ofo_app import eligibility_from_zerodha as elig  # noqa: PLC0415
    from ofo_app import entitlement_store  # noqa: PLC0415

    now = await elig.database_now(conn)
    await entitlement_store.append(conn, user, NewGrant("pro-core", Source.PAID_MONTHLY, now,
                                                        datetime.timedelta(days=30), "pay-core",
                                                        AuditNote("system", "core test")))
