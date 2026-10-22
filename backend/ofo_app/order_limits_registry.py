"""The Zerodha rules the code encodes, each with its source and date (W-133; REQ-053 AC-5).

Spec basis (quoted): REQ-053 AC-5 "Any Zerodha rule encoded in code (market-order limits, SL-M limits on index options,
freak-trade protection, OI and strike restrictions, basket execution) cites a current Zerodha source and date; 'options
are limit-only' is never hard-coded." Finding guard-as-forbidden-list: this is an ALLOW-LIST. A module-level constant in
the scoped trees (``backend/ofo/execution``, ``backend/ofo/broker``, ``backend/ofo_app/kite_*``) whose value is an order
type, a product, an exchange segment or a quantity/price limit must be listed here, either as a Zerodha rule with its
source (``RULES``) or as a constant that is not a Zerodha rule, with the reason (``NOT_A_ZERODHA_RULE``).
``tests/test_zerodha_rules_cited.py`` discovers the constants by AST and fails closed.

Honesty about dates: ``recorded_on`` is the day the entry was written; ``verified`` is True only when someone read the
cited source and compared the value. Every entry below is ``verified=False`` today: none of the values has been
re-checked against Zerodha's current documentation (REQ-056 AC-10 is the check). That is visible here, not hidden.
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
    ZerodhaRule("ofo.execution.sequence:DEFAULT_FREEZE_UNITS",
                "freeze quantity per order (NIFTY): the largest one-lot multiple under NSE's historical 1,800 units",
                "NSE freeze quantity circular for NIFTY; Kite Connect order-placement documentation "
                "https://kite.trade/docs/connect/v3/orders/", "2026-10-22", False),
    ZerodhaRule("ofo.execution.sequence:DEFAULT_MAX_ORDERS_PER_BATCH",
                "orders per batch placed in one go (placeholder, labelled UNVERIFIED in the code)",
                "Kite Connect order-placement documentation https://kite.trade/docs/connect/v3/orders/",
                "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_reads:QUOTE_LIMIT", "instruments per quote call",
                "Kite Connect market quotes documentation https://kite.trade/docs/connect/v3/market-quotes/",
                "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_ws:MAX_TOKENS_PER_CONNECTION", "instrument tokens per websocket connection",
                "Kite Connect websocket streaming documentation https://kite.trade/docs/connect/v3/websocket/",
                "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_margin:_ORDER_TYPES", "order types the order-margins call accepts",
                "Kite Connect margin calculation documentation https://kite.trade/docs/connect/v3/margins/",
                "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_margin:_PRODUCTS", "products the order-margins call accepts",
                "Kite Connect margin calculation documentation https://kite.trade/docs/connect/v3/margins/",
                "2026-10-22", False),
    ZerodhaRule("ofo_app.kite_replies:_NEVER_OURS_EXCHANGES",
                "exchange codes Kite reports whose rows this platform never owns (the exchange list itself)",
                "Kite Connect user profile documentation (exchanges) https://kite.trade/docs/connect/v3/user/",
                "2026-10-22", False),
)

#: Constants the scan matches by shape that are NOT a Zerodha rule: constant -> why. A reason is required.
NOT_A_ZERODHA_RULE: dict[str, str] = {
    "ofo.execution.sequence:MAX_BATCH_SIZE": "this product's sanity cap on a provider's answer, not a Zerodha limit",
    "ofo.execution.partial:MAX_ORDER_STATUSES": "this product's cap on order statuses read in one pass (orchestrator default OD-g)",
    "ofo.execution.sequence:MAX_SLICES_PER_LEG": "this product's cap on how many slices one leg is split into",
}
