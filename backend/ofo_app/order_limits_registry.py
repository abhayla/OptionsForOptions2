"""The Zerodha rules the code encodes, each with its source and date (W-133; REQ-053 AC-5).

Spec basis (quoted): REQ-053 AC-5 "Any Zerodha rule encoded in code (market-order limits, SL-M limits on index options,
freak-trade protection, OI and strike restrictions, basket execution) cites a current Zerodha source and date; 'options
are limit-only' is never hard-coded." Finding guard-as-forbidden-list: this is an ALLOW-LIST. A module-level constant in
the scoped trees (``backend/ofo/execution``, ``backend/ofo/broker``, ``backend/ofo_app/kite_*``) whose value is an order
type, a product, an exchange segment or a quantity/price limit must be listed here, either as a Zerodha rule with its
source (``RULES``) or as a constant that is not a Zerodha rule, with the reason (``NOT_A_ZERODHA_RULE``).
``tests_app/test_zerodha_rules_cited.py`` discovers the constants by AST and fails closed.

Honesty about dates: ``recorded_on`` is the day the entry was written; ``verified`` is True only when someone read the
cited source and compared the value (2026-10-22, spec/findings.md F-57: five entries match Zerodha's current docs;
the others say why they are not verified). REQ-056 AC-10 keeps re-checking them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZerodhaRule:
    constant: str  # "<module path>:<NAME>", resolved by the test against the file's module-level names
    rule: str  # what the rule is, in words
    source: str  # a URL or a document name
    recorded_on: str  # ISO date the entry was written
    verified: bool  # True only after the value was compared with the source


RULES: tuple[ZerodhaRule, ...] = (
    # Checked against Zerodha's current docs on 2026-10-22 (spec/findings.md F-57; WebFetch summaries of each page).
    ZerodhaRule("ofo.execution.sequence:DEFAULT_FREEZE_UNITS",
                "fallback freeze quantity per order (NIFTY) when NSE's daily file is missing: 27 lots x 65 = 1,755, "
                "the largest lot multiple under 1,800 - 1 (ADR-081); the live value comes from NSE's daily file",
                "Zerodha bulletin 'Quantity freeze limits for indices from April 01, 2026' (NIFTY 1,800) "
                "https://zerodha.com/marketintel/bulletin/445684/"
                "quantity-freeze-limits-for-indices-from-april-01-2026; "
                "a reported NSE rise to 3,510 from 2026-10-05 is unconfirmed (F-57)", "2026-10-22", False),
    ZerodhaRule("ofo.execution.sequence:DEFAULT_MAX_ORDERS_PER_BATCH",
                "orders per batch in the order planner (sequence.py; the code labels it an UNVERIFIED placeholder)",
                "not verified: the Kite Publisher basket allows 'maximum 10' items "
                "https://kite.trade/docs/connect/v3/publisher/ (fetched 2026-10-22), but this constant is the "
                "planner's batch size, not the basket limit (row 5 verifier round 2)", "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_reads:QUOTE_LIMIT", "instruments per GET /quote call (500)",
                "Kite market quotes docs: 'complete market data snapshot of up to 500 instruments in one go' "
                "https://kite.trade/docs/connect/v3/market-quotes/ (fetched 2026-10-22)", "2026-10-22", True),
    ZerodhaRule("ofo_app.kite_ws:MAX_TOKENS_PER_CONNECTION", "instrument tokens per websocket connection (3000)",
                "Kite websocket docs: 'up to 3000 instruments on a single WebSocket connection' "
                "https://kite.trade/docs/connect/v3/websocket/ (fetched 2026-10-22)", "2026-10-22", True),
    ZerodhaRule("ofo_app.kite_ws:MAX_CONNECTIONS_PER_KEY",
                "websocket connections per API key, across all users of one Kite Connect app (3)",
                "Kite websocket docs: 'Single API key can have upto 3 websocket connections.' "
                "https://kite.trade/docs/connect/v3/websocket/ (fetched 2026-10-22); Zerodha staff on the developer "
                "forum: 'The 3 connections limit is per api_key and not based on user' (F-59, ADR-170)",
                "2026-10-22", True),
    ZerodhaRule("ofo_app.kite_margin:_ORDER_TYPES", "order types this platform sends to the order-margins call",
                "Kite margins docs list only 'Order type (MARKET, LIMIT etc.)' "
                "https://kite.trade/docs/connect/v3/margins/ (fetched 2026-10-22): the full list is not stated",
                "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_margin:_PRODUCTS", "products this platform sends to the order-margins call",
                "Kite margins docs: 'Margin product to use for the order', no list (CNC, NRML in examples) "
                "https://kite.trade/docs/connect/v3/margins/ (fetched 2026-10-22): not stated", "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_replies:_NEVER_OURS_EXCHANGES",
                "exchange codes Kite reports whose rows this platform never owns (the exchange list itself)",
                "Kite user docs list NSE, NFO, BFO, CDS, BSE, MCX, BCD, MF as enabled exchanges "
                "https://kite.trade/docs/connect/v3/user/ (fetched 2026-10-22); NCO is not stated there",
                "2026-10-22", False),
    ZerodhaRule("ofo.execution.basket:MAX_TAG_LENGTH",
                "longest `tag` the Kite Publisher basket accepts (8 characters)",
                "Kite Publisher docs: 'alphanumeric, max 8 chars' https://kite.trade/docs/connect/v3/publisher/ "
                "(fetched 2026-10-22); also measured as an InputException 2026-10-19 10:19:48 IST", "2026-10-22", True),
    ZerodhaRule("ofo.execution.basket:_LEGACY_TAG_MAX_LENGTH",
                "longest tag of the legacy grammar (the API-order tag cap of 20), decode only",
                "Kite orders docs: 'alphanumeric, max 20 chars' https://kite.trade/docs/connect/v3/orders/ "
                "(fetched 2026-10-22)", "2026-10-22", True),
    ZerodhaRule("ofo.broker.session:KITE_EXPIRY_TIME_IST",
                "the daily Kite session lapses at 06:00 IST the next day",
                "Kite Connect login-flow docs https://kite.trade/docs/connect/v3/user/ - not fetched on 2026-10-22 "
                "(follow-up REQ-056 AC-10)", "2026-10-22", False),
)


def _grouped(groups: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {constant: reason for reason, constants in groups.items() for constant in constants}


#: EVERY other module-level constant of the scoped trees that carries a number or a string: constant -> why it is not
#: a Zerodha rule. A reason is required; a constant that is in neither table is red.
NOT_A_ZERODHA_RULE: dict[str, str] = {
    "ofo.execution.sequence:MAX_BATCH_SIZE": "this product's sanity cap on a provider's answer, not a Zerodha limit",
    "ofo.execution.partial:MAX_ORDER_STATUSES": "this product's cap on order statuses read in one pass (orchestrator default OD-g)",  # noqa: E501
    "ofo.execution.sequence:MAX_SLICES_PER_LEG": "this product's cap on how many slices one leg is split into",
    **_grouped({
        "an endpoint path, host or URL of Kite's published API; the call itself is allow-listed in ALLOWED_CALLS": (
            "ofo.broker.kite_auth:KITE_LOGIN_BASE", "ofo.broker.kite_endpoints:KITE_API_HOST",
            "ofo.broker.kite_endpoints:KITE_WS_HOST", "ofo.broker.kite_endpoints:ALLOWED_CALLS",
            "ofo.broker.kite_endpoints:NETWORK_DOORS", "ofo.execution.basket:KITE_BASKET_URL",
            "ofo_app.kite_client:KITE_API_ROOT", "ofo_app.kite_history:KITE_API_URL",
            "ofo_app.kite_margin:KITE_API_URL", "ofo_app.kite_ws:KITE_WS_URL",
            "ofo_app.kite_margin:BASKET_PATH", "ofo_app.kite_margin:FUNDS_PATH",
            "ofo_app.kite_reads:HOLDINGS_PATH", "ofo_app.kite_reads:ORDERS_PATH",
            "ofo_app.kite_reads:POSITIONS_PATH", "ofo_app.kite_reads:PROFILE_PATH",
            "ofo_app.kite_reads:QUOTE_PATH", "ofo_app.kite_reads:TRADES_PATH", "ofo.broker.kite_http:METHODS",
            "ofo.broker.kite_http:_BARE_TARGETS",
        ),
        "this product's own grammar for an input it validates (a pattern or a key list), not a limit Zerodha sets": (
            "ofo.broker.kite_http:QUOTE_INSTRUMENT", "ofo.broker.kite_http:_PLAIN_NETLOC",
            "ofo.broker.kite_http:_PLAIN_WS_NETLOC", "ofo.broker.kite_http:_QUOTE_TARGET",
            "ofo.broker.kite_flags:_ENTRY_KEYS", "ofo.execution.basket:_LEGACY_TAG_RE",
            "ofo.execution.basket:_STRATEGY_ID_RE", "ofo.execution.basket:_TAG_RE",
            "ofo_app.kite_reads:_PLAIN_NUMBER", "ofo_app.kite_replies:_DECIMAL_LITERAL",
            "ofo_app.kite_replies:_FO_SYMBOL", "ofo_app.kite_replies:_FULL_TIMESTAMP",
            "ofo_app.kite_http:_TIMEOUT_KEYS", "ofo_app.kite_reads:PROFILE_LIST_KEYS",
            "ofo_app.kite_reads:PROFILE_TEXT_KEYS", "ofo_app.kite_reads:QUANTITY_FIELDS",
        ),
        "the product's own basket-tag layout (8 characters in total is the Zerodha rule, MAX_TAG_LENGTH)": (
            "ofo.execution.basket:TAG_DIGITS", "ofo.execution.basket:TAG_LEG_WIDTH",
            "ofo.execution.basket:TAG_PLAN_WIDTH", "ofo.execution.basket:TAG_PREFIX",
            "ofo.execution.basket:TAG_STRATEGY_WIDTH", "ofo.execution.basket:MAX_TAG_LEG_INDEX",
            "ofo.execution.basket:MAX_TAG_PLAN_VERSION", "ofo.execution.basket:MAX_TAG_STRATEGY_ID",
        ),
        "a timeout, retry, backoff, nesting or polling figure of this product's own network code": (
            "ofo.broker.egress:_MAX_DEPTH", "ofo_app.kite_client:EXCHANGE_TIMEOUT_SECONDS",
            "ofo_app.kite_http:_MAX_NESTING", "ofo_app.kite_http:_TIMEOUT", "ofo_app.kite_ws:BACKOFF_MAX",
            "ofo_app.kite_ws:BACKOFF_START", "ofo_app.kite_ws:_POLL_SECONDS", "ofo.execution.partial:UNCONFIRMED_GRACE",
            "ofo.execution.freeze:STALE_AFTER_DAYS",
        ),
        "an event name or address family of the egress guard (Python's audit events), not Zerodha": (
            "ofo.broker.egress:_CONNECT_EVENTS", "ofo.broker.egress:_DOOR", "ofo.broker.egress:_SEND_EVENTS",
            "ofo.broker.egress:_SPAWN_EVENTS", "ofo.broker.egress:_UNIX",
        ),
        "a status code, state name, side or message key of this product's own mapping": (
            "ofo_app.kite_reads:_BUSY", "ofo_app.kite_reads:_DENIED", "ofo_app.kite_reads:_OK",
            "ofo_app.kite_reads:_SERVER_ERROR", "ofo_app.kite_replies:_OPTION_TYPES", "ofo_app.kite_replies:_SIDES",
            "ofo_app.kite_margin:_SIDES", "ofo_app.kite_replies:_WORKING_STATUS_WORDS", "ofo_app.kite_ws:SESSION_ENDED",
            "ofo_app.kite_ws:STOPPED", "ofo.execution.cost:_SIGN", "ofo.execution.partial:_SEND_KIND",
            "ofo.execution.partial:IN_FLIGHT", "ofo.execution.partial:NEEDS_FRESH_READ",
            "ofo.execution.partial:WAITING", "ofo.execution.safety:BAND_UNKNOWN_ON_EXIT",
            "ofo.execution.safety:FUTURES_ENTRY_UNKNOWN", "ofo.execution.safety:MULTI_EXPIRY_PRO",
            "ofo.execution.safety:PRO_REQUIRED", "ofo.execution.safety:STALE_ON_EXIT",
            "ofo.execution.sequence:MARGIN_NOT_USED", "ofo.execution.sequence:ORDERING_BASIS",
        ),
        "this product's sanity cap or label, not a Zerodha limit": (
            "ofo.execution.partial:MAX_POSITION_LINES", "ofo.execution.partial:_MAX_OPEN_GATES",
            "ofo.execution.planned:MAX_PLAN_LEGS", "ofo.execution.safety:MAX_ALTERNATIVES",
            "ofo.execution.alternatives:_ZERO", "ofo.execution.safety:_ZERO_PREMIUM",
            "ofo.broker.session:BROKER_ZERODHA", "ofo.execution.review:BROKER",
            "ofo.broker.kite_flags:FLAG_FILE", "ofo_app.kite_client:SESSION_TOKEN_PATH",
        ),
    }),
}
