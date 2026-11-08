"""Zerodha reads on a fixed minimum period per user (REQ-118 AC-7, RD-063; REQ-015 AC-12, AC-13, RD-013/RD-014).

The one place a screen or the periodic job asks Zerodha for positions, the profile's user id or the available margin.
Each goes through ``ofo.broker.rate_limit.read_once_per_period`` (the one limiter's memo, not a second limiter): at
most one read of each call per user per period (45 s positions, 30 s numbers); inside the period the last answer comes
back with its own read time, so nothing is ever shown as fresh from an old read. The user is the hash of the access
token (``KiteReads.user_ref``), so the periodic job's read for the owner is the very answer the Positions screen
(``ofo_app.routes.positions``) and the Settings account block (``ofo_app.routes.zerodha_account``) show.

The order path (Execute ``ofo_app.routes.execute``, return ``ofo_app.routes.execution_return``) does NOT come through
here: it reads Zerodha fresh every time (ADR-016), and the periodic job runs as a background request so the limiter
lets the order path's reads go first.

Answer states (standing item d), per read: answered -> stored with its read time and shown; absent field / empty /
bad reply -> ``KiteReadError`` / ``KiteMarginError`` remembered for the period and the screen shows the reason; not
found (no session) -> the caller never calls here; failed (network, 5xx) -> the error, same; rate-limited (429 or the
limiter's own refusal) -> the busy code, same; token expired -> the token code, and the periodic job stops.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Final

from ofo.broker import rate_limit
from ofo.broker.rate_limit import READ_NUMBERS, READ_POSITIONS, PeriodAnswer
from ofo.instruments.models import VIX_NAME

from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import KiteReads

POSITIONS_CALL: Final = "positions_and_orders"  # both replies of one moment: an order filled after a positions read
PROFILE_CALL: Final = "profile_user_id"         # is never compared against positions read 40 s earlier
MARGIN_CALL: Final = "available_margin"
VIX_CALL: Final = "india_vix"
VIX_QUOTE: Final = f"NSE:{VIX_NAME}"
_SHOWN_EACH_END: Final = 2


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def mask_user_id(user_id: str) -> tuple[str | None, int, str | None]:
    """The Zerodha client id as (first 2 characters, how many are hidden, last 2 characters): ``AB1234`` -> ``("AB", 2,
    "34")``, shown ``AB**34``. Enough for the owner to recognise the account, not enough to read the full id off a
    shared or recorded screen; the full id never leaves the server. An id of 4 characters or fewer is hidden entirely
    (showing 2 + 2 of it would show all of it): ``(None, n, None)``."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("no user id to mask")
    if len(user_id) <= 2 * _SHOWN_EACH_END:
        return None, len(user_id), None
    return user_id[:_SHOWN_EACH_END], len(user_id) - 2 * _SHOWN_EACH_END, user_id[-_SHOWN_EACH_END:]


def screen_positions(reads: KiteReads, *, stamp: Any = None) -> PeriodAnswer[tuple[Any, Any]]:
    """Zerodha's positions and order book read together, at most once per 45 s per user."""
    return rate_limit.read_once_per_period(READ_POSITIONS, POSITIONS_CALL, reads.user_ref,
                                           lambda: (reads.fetch_positions(), reads.fetch_orders()), stamp or utc_now)


def masked_user_id(reads: KiteReads, *, stamp: Any = None) -> PeriodAnswer[tuple[str | None, int, str | None]]:
    """The masked client id from ``GET /user/profile``, at most once per 30 s per user. The full id never leaves."""
    return rate_limit.read_once_per_period(READ_NUMBERS, PROFILE_CALL, reads.user_ref,
                                           lambda: mask_user_id(reads.fetch_profile().user_id), stamp or utc_now)


def available_margin(reads: KiteReads, margin: KiteMargin, *, stamp: Any = None) -> PeriodAnswer[Decimal]:
    """Zerodha's own available margin (``GET /user/margins`` ``equity.net``, ``KiteMargin.fetch_available_funds``),
    exactly as read, at most once per 30 s per user. Never computed and never a default: a failure raises."""
    return rate_limit.read_once_per_period(READ_NUMBERS, MARGIN_CALL, reads.user_ref, margin.fetch_available_funds,
                                           stamp or utc_now)


def vix_values(quote: Any) -> tuple[Decimal | None, Decimal | None]:
    """(India VIX now, its previous close) from Kite's quote object (``last_price``, ``ohlc.close``): each exact
    Decimal, or None when absent, not a number, or not above 0 (a 0 is Kite's "no value", never a VIX of 0)."""
    def one(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (Decimal, int)) or value <= 0:
            return None
        return Decimal(value)
    if not isinstance(quote, dict):
        return None, None
    ohlc = quote.get("ohlc")
    return one(quote.get("last_price")), one(ohlc.get("close") if isinstance(ohlc, dict) else None)


def india_vix(reads: KiteReads, *, stamp: Any = None) -> PeriodAnswer[tuple[Decimal | None, Decimal | None]]:
    """ADR-277 (1): India VIX and its previous close from the one index-quote read (``fetch_index_quote``), at most once
    per 30 s per user (the limiter's memo is the cache). Not in the reply -> (None, None); a failed read raises."""
    return rate_limit.read_once_per_period(READ_NUMBERS, VIX_CALL, reads.user_ref,
                                           lambda: vix_values(reads.fetch_index_quote(VIX_QUOTE)), stamp or utc_now)


def background_screen_positions(reads: KiteReads) -> PeriodAnswer[tuple[Any, Any]]:
    """The periodic job's read: a background request (the limiter books it few slots ahead, so the order path's user
    reads still go first when the budget is tight). Runs in a worker thread, so the context is set here."""
    with rate_limit.background():
        return screen_positions(reads)


__all__ = ["MARGIN_CALL", "POSITIONS_CALL", "PROFILE_CALL", "VIX_CALL", "VIX_QUOTE", "available_margin",
           "background_screen_positions", "india_vix", "mask_user_id", "masked_user_id", "screen_positions", "utc_now",
           "vix_values"]
