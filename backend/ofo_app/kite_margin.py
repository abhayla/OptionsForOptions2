"""Zerodha's margin figures over HTTP for the owner's own connection (W-081, REQ-055 AC-1, ADR-016, ADR-054).

``GET /user/margins`` gives the funds (``equity.net``); ``POST /margins/basket?consider_positions=true`` gives the
margin the planned orders need (request shape recorded 2026-10-15 in
docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json). Neither call sends an order.

The transport is injected (tests replay the recorded reply files; no network in tests). The access token travels only
in the Authorization header and is never logged or put in an exception: an error carries a code and nothing else.
Fail closed: a non-200 status, a transport error, a body that is not JSON, a reply that is not ``status: success``, or a
missing or non-numeric figure raises `KiteMarginError`, and `margin_verdict` turns that into a blocked verdict.
Replies are parsed with ``parse_float=Decimal``, so no money touches a float (ADR-008).

Codes: kite_margin_token (403 / TokenException) · kite_margin_busy (429) · kite_margin_refused (other 4xx) ·
kite_margin_unavailable (5xx, network, junk body) · kite_margin_no_figure (success reply without a usable figure).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from urllib.error import HTTPError

from ofo.broker.kite_endpoints import KITE_API_HOST
from ofo.broker.kite_http import KiteCallRefused
from ofo.broker.kite_http import open_url as kite_open_url
from ofo.broker.rate_limit import KiteBusy
from ofo.execution.margin_gate import (
    MARGIN_BUSY_CODE,
    MarginReplyError,
    MarginVerdict,
    basket_requirement,
    check_margin,
)
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo.instruments.parser import ZERODHA_EXCHANGE_TO_SEGMENT
from ofo.money import zerodha_paise

log = logging.getLogger("ofo_app.kite_margin")
KITE_API_URL: Final = f"https://{KITE_API_HOST}"
FUNDS_PATH: Final = "/user/margins"
BASKET_PATH: Final = "/margins/basket?consider_positions=true"
#: (method, url, headers, body or None) -> (HTTP status, response text)
Transport = Callable[[str, str, dict[str, str], str | None], tuple[int, str]]

_SIDES: Final = frozenset({"BUY", "SELL"})
_PRODUCTS: Final = frozenset({"NRML", "MIS"})
_ORDER_TYPES: Final = frozenset({"LIMIT", "MARKET"})
# NFO (NIFTY) is proven on the 2026-10-15 reply; BFO (SENSEX -> BSE_FO) is unproven on real data until a BFO basket
# reply is recorded.
_EXCHANGES: Final = frozenset(code for code, segment in ZERODHA_EXCHANGE_TO_SEGMENT.items()
                              if segment in SUPPORTED_UNDERLYINGS.values())  # Zerodha codes of the home's segments


class KiteMarginError(Exception):
    """A margin read failed. Carries only a code; never the token, a header, a URL or the response body."""

    def __init__(self, code: str, *, empty: bool = False) -> None:
        super().__init__(code)
        self.code = code
        #: only with ``kite_margin_no_figure``: Zerodha answered in full and stated NO figure at all (an EMPTY answer),
        #: as opposed to an AMBIGUOUS one (rows that do not match the basket, a figure missing beside others)
        self.empty = empty


@dataclass(frozen=True)
class BasketOrder:
    """One planned order as Zerodha's basket-margin call takes it (a closed shape: nothing else is sent)."""

    exchange: str
    tradingsymbol: str
    transaction_type: str
    product: str
    order_type: str
    quantity: int
    price: Decimal
    variety: str = "regular"

    def __post_init__(self) -> None:
        if self.transaction_type not in _SIDES:
            raise ValueError(f"transaction_type must be one of {sorted(_SIDES)}")
        if self.product not in _PRODUCTS:
            raise ValueError(f"product must be one of {sorted(_PRODUCTS)}")
        if self.order_type not in _ORDER_TYPES:
            raise ValueError(f"order_type must be one of {sorted(_ORDER_TYPES)}")
        if self.exchange not in _EXCHANGES or self.variety != "regular":
            raise ValueError("only regular NFO or BFO orders are checked")
        if not isinstance(self.tradingsymbol, str) or not self.tradingsymbol.isalnum():
            raise ValueError("tradingsymbol must be a plain symbol")
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError("quantity must be a positive int")
        if type(self.price) is not Decimal or not self.price.is_finite() or self.price < 0:
            raise ValueError("price must be a finite Decimal of 0 or more")

    def as_json(self) -> str:
        """The order as a JSON object; the price is written as a JSON number from its Decimal text, never via float."""
        head = json.dumps({"exchange": self.exchange, "tradingsymbol": self.tradingsymbol,
                           "transaction_type": self.transaction_type, "variety": self.variety,
                           "product": self.product, "order_type": self.order_type, "quantity": self.quantity})
        return f'{head[:-1]}, "price": {self.price:f}}}'


@dataclass(frozen=True)
class OrderMargin:
    tradingsymbol: str
    total: Decimal


@dataclass(frozen=True)
class BasketMargin:
    """The basket's margin. `zerodha_total` is Zerodha's own ``final.total`` (after the hedge benefit); show it only as
    "Zerodha says". `required_total` is what the check needs: that figure plus the ADR-094 top-up for option BUY legs
    up to their limit price (never below `zerodha_total`). `top_up` is that ADR-094 top-up alone, as computed for
    `required_total` (GC-UI D-A47: the Builder's sentence names it only when above 0)."""

    zerodha_total: Decimal
    required_total: Decimal
    initial_total: Decimal
    orders: tuple[OrderMargin, ...]
    top_up: Decimal


def urllib_transport(method: str, url: str, headers: dict[str, str], body: str | None, *,
                     timeout: float = 20) -> tuple[int, str]:
    data = None if body is None else body.encode("utf-8")
    try:
        with kite_open_url(url, method=method, data=data, headers=headers, timeout=timeout) as response:  # door first
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        try:
            return exc.code, exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001 - the status alone decides
            return exc.code, ""
    except KiteBusy:  # the rate limiter refused at once, nothing sent (REQ-118 AC-3): the caller's 429 rule applies
        return 429, ""
    except KiteCallRefused:
        raise KiteMarginError("kite_margin_refused") from None
    except Exception:  # noqa: BLE001 - IncompleteRead, bad UTF-8, resets, timeouts: all "not confirmed"
        raise KiteMarginError("kite_margin_unavailable") from None


def _money(value: object) -> Decimal:
    if type(value) is not Decimal and type(value) is not int:
        raise KiteMarginError("kite_margin_no_figure")
    amount = Decimal(value)
    if not amount.is_finite():
        raise KiteMarginError("kite_margin_no_figure")
    try:
        return zerodha_paise(amount)  # ADR-099/ADR-101: half-up to the paisa where the figure is parsed
    except ValueError:  # too large to round to the paisa: not a usable figure, so "not confirmed" (fail closed)
        raise KiteMarginError("kite_margin_no_figure") from None


def _is_figure(value: object) -> bool:
    """A stated amount: a JSON number (parsed as Decimal or int; a bool is not one)."""
    return type(value) is Decimal or type(value) is int


def _no_figure(*, empty: bool) -> KiteMarginError:
    return KiteMarginError("kite_margin_no_figure", empty=empty)


def _basket_empty(data: Mapping[str, object], orders: Sequence[BasketOrder]) -> bool:
    """EMPTY, not ambiguous: ``initial`` and ``final`` are present, the rows are exactly the orders sent (same count,
    same symbol and exchange, same order), and no margin total is stated anywhere (final, initial, any row). Anything
    else - a row missing, extra or reordered, ``initial`` missing, a total stated beside missing ones - is AMBIGUOUS."""
    initial, final, rows = data.get("initial"), data.get("final"), data.get("orders")
    if not isinstance(initial, dict) or not isinstance(final, dict) or not isinstance(rows, list):
        return False
    if [(r.get("tradingsymbol"), r.get("exchange")) if isinstance(r, dict) else None for r in rows] != [
            (o.tradingsymbol, o.exchange) for o in orders]:
        return False
    return not any(_is_figure(x.get("total")) for x in (initial, final, *rows))


class KiteMargin:
    def __init__(self, *, api_key: str, access_token: str, transport: Transport = urllib_transport,
                 base_url: str = KITE_API_URL) -> None:
        self._headers = kite_headers(api_key, access_token)  # never logged
        self._call = transport
        self._base = base_url

    def __repr__(self) -> str:
        return "KiteMargin()"

    def _data(self, method: str, path: str, body: str | None, extra: dict[str, str] | None = None) -> Mapping[str, object]:  # noqa: E501
        headers = {**self._headers, **(extra or {})}
        try:
            status, text = self._call(method, self._base + path, headers, body)
        except Exception:  # noqa: BLE001 - whatever the transport raises, the answer is "not confirmed"
            raise KiteMarginError("kite_margin_unavailable") from None
        if status != 200:  # noqa: PLR2004
            log.warning("kite margin HTTP status %s", status)
            if status == 403 or error_type(text) == "TokenException":  # noqa: PLR2004
                raise KiteMarginError("kite_margin_token")
            if status == 429:  # noqa: PLR2004
                raise KiteMarginError(MARGIN_BUSY_CODE)
            raise KiteMarginError("kite_margin_unavailable" if status >= 500 else "kite_margin_refused")  # noqa: PLR2004
        try:
            reply = json.loads(text, parse_float=Decimal)
        except (ValueError, RecursionError):  # deeply nested JSON raises RecursionError, not ValueError
            raise KiteMarginError("kite_margin_unavailable") from None
        data = reply.get("data") if isinstance(reply, dict) else None
        if not isinstance(reply, dict) or reply.get("status") != "success" or not isinstance(data, dict):
            raise KiteMarginError("kite_margin_no_figure")
        return data

    def fetch_available_funds(self) -> Decimal:
        """``GET /user/margins``: ``equity.net``, Zerodha's available funds, as an exact Decimal."""
        data = self._data("GET", FUNDS_PATH, None)
        equity = data.get("equity")
        if not isinstance(equity, dict) or equity.get("net") is None:
            raise _no_figure(empty=not any(isinstance(s, dict) and _is_figure(s.get("net")) for s in data.values()))
        return _money(equity.get("net"))

    def fetch_basket_margin(self, orders: Sequence[BasketOrder]) -> BasketMargin:
        """``POST /margins/basket?consider_positions=true`` for the planned orders."""
        if not orders or any(type(o) is not BasketOrder for o in orders):
            raise ValueError("fetch_basket_margin needs one or more BasketOrder")
        body = "[" + ", ".join(o.as_json() for o in orders) + "]"
        data = self._data("POST", BASKET_PATH, body, {"Content-Type": "application/json"})
        try:
            final_total, top_up = basket_requirement(data, orders)  # ADR-094, computed once (GC-UI D-A47)
        except MarginReplyError:
            raise _no_figure(empty=_basket_empty(data, orders)) from None
        required_total = final_total + top_up  # exactly required_from_basket_reply's sum
        final = data.get("final")  # a dict with a numeric total: basket_requirement just read it
        zerodha_total = _money(final.get("total") if isinstance(final, dict) else None)
        initial = data.get("initial")
        rows = data.get("orders")
        if not isinstance(initial, dict) or not isinstance(rows, list):
            raise KiteMarginError("kite_margin_no_figure")
        per_order = tuple(OrderMargin(str(r.get("tradingsymbol")), _money(r.get("total")))
                          for r in rows if isinstance(r, dict))
        if len(per_order) != len(rows):
            raise KiteMarginError("kite_margin_no_figure")
        return BasketMargin(zerodha_total, required_total, _money(initial.get("total")), per_order, top_up)


def kite_headers(api_key: str, access_token: str) -> dict[str, str]:
    """The headers every Kite REST call carries. The token lives only here; never log or repr the result."""
    return {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}"}


def error_type(text: str) -> str | None:
    """Kite's ``error_type`` from an error body (e.g. ``TokenException``), or None when the body has none."""
    try:
        body = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return body.get("error_type") if isinstance(body, dict) else None


def margin_verdict(client: KiteMargin, orders: Sequence[BasketOrder]) -> MarginVerdict:
    """Both figures from Zerodha, then the domain gate, as a verdict to show. The basket does NOT take this verdict:
    the basket builder reads the same two figures through ``checked_basket``'s source and calls the gate itself. Any
    failure to read either figure blocks (the gate's "could not confirm" message); nothing is retried. A negative
    balance is compared and shown as Zerodha gives it."""
    try:
        available: Decimal | None = client.fetch_available_funds()
        required: Decimal | None = client.fetch_basket_margin(orders).required_total
    except KiteMarginError as exc:
        available = required = None
        return check_margin(available, required, busy=exc.code == MARGIN_BUSY_CODE)
    return check_margin(available, required)
