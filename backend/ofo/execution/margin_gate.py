"""The margin gate before the Kite basket is built (W-081, REQ-055 AC-1/AC-3/AC-4, ADR-016, ADR-054).

Zerodha is the authority on margin (ADR-016): the basket is built only if the funds Zerodha reports are at least the
margin Zerodha says the planned orders need. The required figure is the basket reply's ``final.total`` (after the
spread/hedge benefit Zerodha gives a basket), not ``initial.total``: for the 15 Oct 2026 four-leg NIFTY condor that is
Rs 68,498.85 against Rs 2,96,332.80, and ``initial`` would block hedged strategies Zerodha accepts. No platform
estimate takes part in the decision (AC-3).

The basket builder reads both figures from its margin source and CALLS `check_margin` itself; no verdict object
crosses the `build_basket` boundary, so a verdict made, copied or edited elsewhere cannot produce a basket. An amount that is unknown (None) blocks. Money is exact `Decimal`; a float, string, int,
NaN, infinity or negative amount raises.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Protocol

from ofo.errors import UserFacingError, render
from ofo.instruments.models import OPTION_TYPES
from ofo.money import PAISE as _PAISE
from ofo.money import zerodha_paise

class MarginReplyError(ValueError):
    """Zerodha's basket-margin reply has no usable ``final.total``: the basket must not be built."""


def _amount(value: object, name: str, *, signed: bool = False) -> Decimal:
    if type(value) is not Decimal:
        raise TypeError(f"{name} must be exactly Decimal, got {type(value).__name__}")
    if not value.is_finite() or (value < 0 and not signed):
        raise ValueError(f"{name} must be a finite amount{'' if signed else ' of 0 or more'}, got {value!r}")
    return value


class MarginVerdict(tuple):
    """The gate's answer. Only the two amounts (None when unknown) are inputs: `allowed` and the four-part `message`
    are derived from them by `check_margin`. `available` is Zerodha's signed ``equity.net`` (a negative balance always
    blocks).

    Sealed (finding sealed-object-mutable-after-seal): an immutable tuple with no attribute storage, so even
    ``object.__setattr__`` has nothing to write; calling the class raises and there is no mint token to borrow;
    subclasses are refused; `copy`/`deepcopy`/`pickle`/`dataclasses.replace` raise. A verdict is information only:
    `build_basket` takes no verdict, it reads Zerodha's two figures and calls `check_margin` itself."""

    __slots__ = ()

    def __new__(cls, *_args: object, **_kwargs: object) -> MarginVerdict:
        raise TypeError("a MarginVerdict comes only from check_margin")

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("MarginVerdict cannot be subclassed")

    @property
    def available(self) -> Decimal | None:
        return self[0]

    @property
    def required(self) -> Decimal | None:
        return self[1]

    @property
    def allowed(self) -> bool:
        return self[2]

    @property
    def message(self) -> UserFacingError | None:
        return self[3]

    def __copy__(self) -> MarginVerdict:
        raise TypeError("a MarginVerdict cannot be copied; call check_margin again")

    def __deepcopy__(self, _memo: object) -> MarginVerdict:
        raise TypeError("a MarginVerdict cannot be copied; call check_margin again")

    def __reduce_ex__(self, _protocol: object) -> object:
        raise TypeError("a MarginVerdict cannot be pickled; call check_margin again")

    def __reduce__(self) -> object:
        raise TypeError("a MarginVerdict cannot be pickled; call check_margin again")

    def __repr__(self) -> str:
        return f"MarginVerdict(available={self.available!r}, required={self.required!r}, allowed={self.allowed!r})"


def _derive(available: Decimal | None, required: Decimal | None) -> tuple[bool, UserFacingError | None]:
    if available is None or required is None:
        return False, render("gate_margin_unconfirmed")
    if available >= required:
        return True, None
    # Shown to the paisa, never in the user's favour: the shortfall must not display as two equal amounts.
    try:
        return False, render("margin_basket_insufficient", available=available.quantize(_PAISE, rounding=ROUND_FLOOR),
                             required=required.quantize(_PAISE, rounding=ROUND_CEILING))
    except (InvalidOperation, ValueError):
        # An amount too large to round to the paisa or to show (cap 1e12): still blocked, never raises.
        return False, render("gate_margin_unconfirmed")


def check_margin(available: Decimal | None, required: Decimal | None) -> MarginVerdict:
    """Allowed when `available` >= `required` (equal is allowed); otherwise blocked with both amounts shown.

    Both are Zerodha's figures. None (not confirmed with Zerodha) blocks with the "could not confirm" message. Public
    because it is pure: its result cannot be turned into a basket (``build_basket`` takes a margin source, reads
    Zerodha's two figures and calls this itself), so a self-made verdict proves nothing to anyone."""
    if available is not None:
        _amount(available, "available", signed=True)
    if required is not None:
        _amount(required, "required")
    allowed, message = _derive(available, required)
    return tuple.__new__(MarginVerdict, (available, required, allowed, message))


class PlannedOrder(Protocol):
    """The fields of one order as sent to Zerodha's basket-margin call (``ofo_app.kite_margin.BasketOrder`` fits)."""

    @property
    def exchange(self) -> str: ...
    @property
    def tradingsymbol(self) -> str: ...
    @property
    def transaction_type(self) -> str: ...
    @property
    def quantity(self) -> int: ...
    @property
    def price(self) -> Decimal: ...


def _premium(value: object) -> Decimal:
    if type(value) is not Decimal and type(value) is not int:
        raise MarginReplyError("a BUY leg of the basket margin reply has no numeric option_premium")
    amount = Decimal(value)
    if not amount.is_finite() or amount < 0:
        raise MarginReplyError("a BUY leg's option_premium is not a finite amount of 0 or more")
    return zerodha_paise(amount)  # ADR-099/ADR-101: rounded half-up to the paisa where it is parsed


def required_from_basket_reply(data: Mapping[str, object], orders: Sequence[PlannedOrder]) -> Decimal:
    """The margin the basket needs (ADR-094): ``final.total`` of Zerodha's ``POST /margins/basket`` reply ``data``
    plus, for each option BUY leg, ``max(0, quantity x limit price - that leg's option_premium)``.

    Kite prices an option BUY at the lower of the limit and the live price (F-39); the user may pay up to the limit.
    SELL legs and futures add nothing; a negative difference is 0, never a credit, and so is a negative ``final.total``
    (a closing basket). ``orders`` is the request list sent
    to Kite, in the same order as ``data["orders"]``. The reply must have been parsed with ``parse_float=Decimal``.
    Anything unusable (no final.total, a BUY leg's option_premium missing/not a number/negative, a count or identity
    mismatch between request and reply, a bad quantity or price) raises `MarginReplyError`."""
    required = _final_total(data)
    rows = data.get("orders")
    if not isinstance(rows, list) or len(rows) != len(orders):
        raise MarginReplyError("the basket margin reply does not list the orders that were sent")
    for row, order in zip(rows, orders, strict=True):
        if not isinstance(row, Mapping) or (row.get("tradingsymbol"), row.get("exchange")) != (
                order.tradingsymbol, order.exchange):
            raise MarginReplyError("the basket margin reply's orders do not match the orders that were sent")
        if order.transaction_type != "BUY" or order.tradingsymbol[-2:] not in OPTION_TYPES:
            continue
        quantity, price = order.quantity, order.price
        if (type(quantity) is not int or quantity <= 0 or type(price) is not Decimal or not price.is_finite()
                or price <= 0):
            raise MarginReplyError("a BUY leg has no usable quantity and limit price")
        required += max(Decimal(0), quantity * price - _premium(row.get("option_premium")))
    return required


def _final_total(data: Mapping[str, object]) -> Decimal:
    final = data.get("final") if isinstance(data, Mapping) else None
    total = final.get("total") if isinstance(final, Mapping) else None
    if type(total) is not Decimal and type(total) is not int:
        raise MarginReplyError("the basket margin reply has no numeric final.total")
    # ADR-099 / ADR-101: every Kite money figure is rounded half-up to the paisa where it is parsed, so Kite's float
    # noise (68498.85000000001) cannot flip the shortfall flag. The only widening: with both figures rounded, a basket
    # short by under one paisa (needed .854 vs funds .845) can pass; a full paisa short is blocked.
    value = Decimal(total)  # an int (Kite prints whole totals without a point) is exact
    if not value.is_finite():
        raise MarginReplyError("the basket margin reply's final.total is not a finite amount")
    try:
        value = zerodha_paise(value)
    except ValueError:
        raise MarginReplyError("the basket margin reply's final.total is too large to use") from None
    # A basket that closes or reduces held positions releases margin and Kite reports a negative total (real
    # 2026-10-16 exit: -214.5). That needs 0, and is never a credit toward other legs (ADR-094, #321).
    return max(value, Decimal(0))
