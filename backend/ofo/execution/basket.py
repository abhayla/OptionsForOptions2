"""The read-only Kite basket built from an execution plan (REQ-073 AC-1/AC-2, ADR-054, ADR-060, #115).

Source: Kite's offsite order execution page, saved as ``docs/research/kite-basket-docs-2026-10-16.html``. Quoted:

- target: "POST it as a form field with the name data along with your api_key to https://kite.zerodha.com/connect/basket"
  (a browser request "that has to happen at the user's end, although the basket preparation can happen in the backend").
- per-order JSON keys: ``variety`` ("regular, amo, co"), ``tradingsymbol``, ``exchange``, ``transaction_type``
  ("BUY or SELL"), ``order_type``, ``quantity``, ``product``, ``price`` ("For LIMIT orders"), ``readonly`` ("If set
  to true, the UI does not allow the user to edit values such as quantity, price etc., and they can only review and
  execute"), ``tag`` ("alphanumeric, max 20 chars").
- the example writes prices as JSON numbers (``"price" : 915.15``).

Nothing here places an order: the user presses Execute on Kite's own basket page (ADR-060). No order-placement API is
called anywhere (AC-4; ``tests/test_no_order_placement.py``).

Rules:
- Orders keep the plan's order. Each order's exchange and trading symbol come from the contract's ZERODHA row, found by
  the catalogue and carried with the contract's ``InstrumentId``; a contract with no unique, listed ZERODHA row refuses
  the WHOLE basket with ``MissingBrokerRef`` / ``BasketRefused`` (REQ-054 AC-3: no symbol is guessed or derived).
- The basket calls the freeze check ITSELF through the required ``freeze_check`` parameter, and decides the margin
  ITSELF: it reads Zerodha's available funds and Zerodha's required figure for exactly these orders from the required
  ``margin_source`` (no defaults) and calls ``margin_gate.check_margin`` on the two numbers. No verdict object crosses
  this boundary, so none made, copied or edited elsewhere can produce a basket (finding caller-supplied-verdict-
  trusted). A block, a wrong-typed answer or a raised error refuses the whole basket (fail closed). In production the
  one caller is ``ofo_app.checked_basket``, whose source is the real Zerodha client (REQ-055 AC-1/AC-3).
- Ordinary code cannot make a ``KiteBasket`` except through ``build_basket``: calling the class raises (there is no
  token to borrow), it is an immutable tuple with no attribute storage, subclasses are refused, and
  copy/pickle/``dataclasses.replace`` raise (finding sealed-object-mutable-after-seal). This is not proof against
  deliberate tricks (``tuple.__new__``, ``copyreg``, ``__class__`` swap, a caller's own lying margin source -
  Tier A review 2026-10-17, MINOR); those are out of scope (ADR-003 Q235), the scans catch some, and Zerodha checks
  margin again when the user places the basket on Kite's page. A basket is not tied to a time: callers build it
  again on every request.
- Prices are the plan's ``Decimal`` entry prices, already tick-rounded upstream; never rounded here, and serialised as
  exact decimal text so 3.95 stays 3.95.
- Tag: ``OFS<strategy>V<version>L<leg>`` with positive decimal integers (leg from 0): alphanumeric, at most 20
  characters, unique per leg, decoded by the pure ``parse_tag``. An id that does not fit is refused, never truncated.
"""  # noqa: E501
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Protocol
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.errors import UserFacingError, display_text
from ofo.execution.freeze import FreezeCheck
from ofo.execution.margin_gate import MarginVerdict, check_margin
from ofo.execution.planned import ExecutionPlan
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA, InstrumentId, MissingBrokerRef
from ofo.instruments.parser import ZERODHA_EXCHANGE_TO_SEGMENT

KITE_BASKET_URL: Final = "https://kite.zerodha.com/connect/basket"
MAX_TAG_LENGTH: Final = 20
_TAG_RE: Final = re.compile(r"OFS([1-9][0-9]*)V([1-9][0-9]*)L(0|[1-9][0-9]*)", re.ASCII)
_SEGMENT_TO_EXCHANGE: Final = {segment: exchange for exchange, segment in ZERODHA_EXCHANGE_TO_SEGMENT.items()}


class BasketRefused(ValueError):
    """The whole basket is refused (a gate blocked, a gate could not answer, or a contract/tag cannot be used).

    ``user_message`` carries the gate's own user-facing message when it has one (a margin shortfall: Zerodha's
    available vs required, REQ-055 AC-4); None otherwise."""

    def __init__(self, text: str, user_message: UserFacingError | None = None) -> None:
        super().__init__(text)
        self.user_message = user_message


# -- tags ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TagParts:
    strategy_id: int
    plan_version: int
    leg_index: int


def _positive(value: object, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {value!r}")
    return value


def make_tag(strategy_id: int, plan_version: int, leg_index: int) -> str:
    """The order's own tag. Raises ``ValueError`` when an id is invalid or the tag would exceed 20 characters."""
    s = _positive(strategy_id, "strategy_id", 1)
    v = _positive(plan_version, "plan_version", 1)
    i = _positive(leg_index, "leg_index", 0)
    tag = f"OFS{s}V{v}L{i}"
    if len(tag) > MAX_TAG_LENGTH:
        raise ValueError(f"tag {tag!r} is {len(tag)} characters; Kite allows at most {MAX_TAG_LENGTH}")
    return tag


def parse_tag(tag: object) -> TagParts:
    """Decode a tag made by ``make_tag``; anything else (other prefix, padding, leading zeros, non-ASCII) is refused."""
    if not isinstance(tag, str) or len(tag) > MAX_TAG_LENGTH:
        raise ValueError(f"not a basket tag: {tag!r}")
    m = _TAG_RE.fullmatch(tag)
    if m is None:
        raise ValueError(f"not a basket tag: {tag!r}")
    return TagParts(int(m.group(1)), int(m.group(2)), int(m.group(3)))


# -- the basket ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class KiteOrder:
    instrument_id: InstrumentId  # the exchange identity this order was resolved from (#115); not sent to Kite
    exchange: str
    tradingsymbol: str
    transaction_type: str
    quantity: int
    price: Decimal
    tag: str
    order_type: str = "LIMIT"
    product: str = "NRML"
    variety: str = "regular"
    readonly: bool = True

    def to_json(self) -> str:
        parts = [("variety", json.dumps(self.variety)), ("tradingsymbol", json.dumps(self.tradingsymbol)),
                 ("exchange", json.dumps(self.exchange)), ("transaction_type", json.dumps(self.transaction_type)),
                 ("order_type", json.dumps(self.order_type)), ("product", json.dumps(self.product)),
                 ("price", _number(self.price)), ("quantity", str(self.quantity)),
                 ("readonly", "true" if self.readonly else "false"), ("tag", json.dumps(self.tag))]
        return "{" + ", ".join(json.dumps(k) + ": " + v for k, v in parts) + "}"


class KiteBasket(tuple):
    """The basket of orders ``build_basket`` decided may be sent; sealed (see the module rules)."""

    __slots__ = ()

    def __new__(cls, *_args: object, **_kwargs: object) -> KiteBasket:
        raise TypeError("a KiteBasket comes only from build_basket")

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("KiteBasket cannot be subclassed")

    @property
    def orders(self) -> tuple[KiteOrder, ...]:
        return tuple(self)

    def __copy__(self) -> KiteBasket:
        raise TypeError("a KiteBasket cannot be copied; build it again")

    def __deepcopy__(self, _memo: object) -> KiteBasket:
        raise TypeError("a KiteBasket cannot be copied; build it again")

    def __reduce_ex__(self, _protocol: object) -> object:
        raise TypeError("a KiteBasket cannot be pickled; build it again")

    def __reduce__(self) -> object:
        raise TypeError("a KiteBasket cannot be pickled; build it again")

    def __repr__(self) -> str:
        return f"KiteBasket(orders={self.orders!r})"

    def orders_json(self) -> str:
        """The JSON list for the ``data`` form field."""
        return "[" + ", ".join(o.to_json() for o in self.orders) + "]"

    def form_fields(self, api_key: str) -> dict[str, str]:
        """The two hidden fields to POST, from the user's browser, to ``KITE_BASKET_URL``."""
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        return {"api_key": api_key, "data": self.orders_json()}


def _number(price: Decimal) -> str:
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise BasketRefused(f"a LIMIT price must be a positive finite Decimal, got {price!r}")
    text = format(price, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


FreezeGate = Callable[[ExecutionPlan], FreezeCheck]


class MarginSource(Protocol):
    """Zerodha's two margin figures, read by ``build_basket`` itself. Production passes only
    ``ofo_app.checked_basket``'s adapter over the real Zerodha client (tests/test_margin_from_zerodha_only.py)."""

    def available_funds(self) -> Decimal:
        """Zerodha's available funds (``equity.net``, signed), exact Decimal."""
        ...

    def zerodha_required(self, orders: tuple[KiteOrder, ...]) -> Decimal:
        """Zerodha's required margin for exactly ``orders`` (W-081 ``required_from_basket_reply``), exact Decimal."""
        ...


_STRATEGY_ID_RE: Final = re.compile(r"(?:S-)?([1-9][0-9]*)", re.ASCII)


def _ask(gate: Callable, arg: object, name: str) -> object:
    try:
        return gate(arg)
    except Exception as exc:  # fail closed: a gate that cannot answer is not a pass
        raise BasketRefused(f"the {name} check could not be completed ({type(exc).__name__}); no basket built") from exc


def _strategy_number(plan: ExecutionPlan) -> int:
    """The tag's strategy id is the plan's own (``S-<n>`` or ``<n>``); any other shape cannot be tagged, so refuse."""
    m = _STRATEGY_ID_RE.fullmatch(plan.strategy_id)
    if m is None:
        raise BasketRefused(f"strategy id {plan.strategy_id!r} cannot be written into a tag; no basket built")
    return int(m.group(1))


def zerodha_exchange(segment: str) -> str:
    """Zerodha's exchange name (``NFO``/``BFO``) for a catalogue segment; an unknown segment refuses the basket."""
    exchange = _SEGMENT_TO_EXCHANGE.get(segment)
    if exchange is None:
        raise BasketRefused(f"no Zerodha exchange for segment {segment!r}")
    return exchange


def _resolve(plan: ExecutionPlan, catalogue: Catalogue) -> list[tuple[InstrumentId, str, str]]:
    out = []
    for planned in plan.legs:
        entries = catalogue.entries_for_broker_symbol(ZERODHA, planned.contract)
        if len(entries) != 1:
            raise MissingBrokerRef(detail=f"{planned.contract!r} matches {len(entries)} catalogue rows at {ZERODHA}; "
                                          "it cannot be traded and nothing is guessed")
        entry = catalogue.get(entries[0].id)
        ref = entry.ref(ZERODHA)  # MissingBrokerRef when there is no row
        if not entry.currently_listed:
            raise BasketRefused(f"{ref.broker_symbol} is no longer listed; no basket built")
        c, leg = entry.contract, planned.leg
        if (c.instrument_type != leg.instrument.value or c.expiry != leg.expiry
                or (leg.strike is not None and c.strike != leg.strike)):
            raise BasketRefused(f"{ref.broker_symbol} is not the contract of leg {planned.leg_ref} "
                                "(type, expiry or strike differ); no basket built")
        out.append((entry.id, zerodha_exchange(entry.id.exchange_segment), ref.broker_symbol))
    return out


def build_basket(plan: ExecutionPlan, catalogue: Catalogue, plan_version: int, *,
                 freeze_check: FreezeGate, margin_source: MarginSource) -> KiteBasket:
    """Turn ``plan`` into a basket of read-only LIMIT orders in plan order, or refuse the whole basket.

    The tag's strategy id is read from ``plan.strategy_id``; ``plan_version`` is the one caller value (the plan holds no
    version). ``freeze_check`` (plan -> ``FreezeCheck``) and ``margin_source`` (Zerodha's two figures) are REQUIRED; the
    basket asks them itself, decides the margin with ``check_margin`` itself, and never takes a caller's verdict."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"build_basket needs an ExecutionPlan, got {plan!r}")
    if not isinstance(catalogue, Catalogue):
        raise ValueError(f"build_basket needs a Catalogue, got {catalogue!r}")
    strategy = _strategy_number(plan)
    try:
        tags = [make_tag(strategy, plan_version, i) for i in range(len(plan.legs))]
    except ValueError as exc:
        raise BasketRefused(str(exc)) from exc
    resolved = _resolve(plan, catalogue)
    orders = tuple(
        KiteOrder(instrument_id=iid, exchange=exchange, tradingsymbol=symbol, transaction_type=p.leg.action.value,
                  quantity=p.leg.quantity, price=p.leg.entry_price, tag=tag)
        for p, (iid, exchange, symbol), tag in zip(plan.legs, resolved, tags, strict=False))
    for o in orders:
        _number(o.price)  # refuse a non-positive price before anything is handed out
    freeze = _ask(freeze_check, plan, "freeze-limit")
    if not isinstance(freeze, FreezeCheck):
        raise BasketRefused("the freeze limit check gave no usable answer; no basket built")
    if freeze.blocks:
        raise BasketRefused("a leg is not below its exchange freeze limit; no basket built")
    margin = _decide_margin(margin_source, orders)
    if margin.allowed is not True:
        shown = margin.message
        raise BasketRefused("the margin check did not allow this basket; no basket built"
                            + ("" if shown is None else "\n" + display_text(shown)), shown)
    return tuple.__new__(KiteBasket, orders)


def _decide_margin(source: MarginSource, orders: tuple[KiteOrder, ...]) -> MarginVerdict:
    """Both of Zerodha's figures, read here, then the gate. A read that raises, or a figure that is not an exact finite
    Decimal (``check_margin`` raises), is "not confirmed with Zerodha": blocked with that message, never a pass."""
    try:
        available = source.available_funds()
        required = source.zerodha_required(orders)
        return check_margin(available, required)
    except Exception:  # noqa: BLE001 - fail closed: any failure to read either figure blocks the basket
        return check_margin(None, None)


__all__ = ["KITE_BASKET_URL", "BasketRefused", "KiteBasket", "KiteOrder", "MarginSource", "TagParts", "build_basket",
           "make_tag", "parse_tag", "zerodha_exchange"]
