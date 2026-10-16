"""Kite orders / trades / positions replies -> the existing domain types (W-091, REQ-054 AC-1, REQ-057, REQ-060).

F-40 / finding `broker-reply-shape-unproven-at-domain-boundary`: the domain parsers accept only exact Decimal / int
money, and nothing turned a real Kite reply into that shape. This module is that boundary, one function per endpoint;
it takes the reply's ``data`` (already parsed) and calls no network.

* Money (`kite_money`): a `Decimal` or `int` as is (a JSON number read with ``json.loads(text, parse_float=Decimal)``,
  kite_margin.py's pattern); a Python float (what the kiteconnect SDK hands over) via ``Decimal(str(v))``, NaN /
  infinity refused; a string only when it is an exact decimal literal (the recorder's shape, ``"5.1"``). Every figure
  is then rounded half-up to the paisa by `ofo.money.zerodha_paise` (ADR-099/ADR-101). No float arithmetic anywhere.
* Flat row: `ofo.reconciliation.positions.is_flat_row`, the ONE rule shared with grouping: a ``quantity 0`` row is
  "no position", never a 0-price holding.
* Contract key (issue #115): tradingsymbol + instrument_token -> the reconcile key ``(underlying, Instrument, strike,
  expiry)`` through a `ContractIndex` built from the catalogue (or a recorded instrument slice); 0 or 2+ matching rows
  are refused, never guessed.
* Trades: one `FillEvent` per row, timestamp = the row's FULL ``fill_timestamp`` as IST (Kite sends naive IST). The
  trades reply's ``order_timestamp`` is time-only ("12:20:50") and is never used; neither is the wall clock.
* Orders: `BrokerOrderRow` with the broker's cumulative ``filled_quantity`` for `OrderBook.reconcile_cumulative`. The
  status word is kept as read and drives nothing here (finding `trust-broker-status-word`).
Any missing or unknown required field raises `KiteReplyError` (fail closed).
"""
from __future__ import annotations

import datetime
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.engine.legs import Action, Instrument
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import ZERODHA
from ofo.money import zerodha_paise
from ofo.orders.model import FillEvent
from ofo.reconciliation.positions import BrokerPositionLine, is_flat_row, position_line_from_kite_row
from ofo.timeutil import IST

_DECIMAL_LITERAL: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_FULL_TIMESTAMP: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")
_SIDES: Final = {"BUY": Action.BUY, "SELL": Action.SELL}
_OPTION_TYPES: Final = {"CE": Instrument.CE, "PE": Instrument.PE}

#: The reconcile contract key: (underlying, Instrument, strike or None for a future, expiry).
ContractKey = tuple


class KiteReplyError(ValueError):
    """A Kite reply field that cannot be turned into a domain value; nothing is guessed."""


def kite_money(value: object, name: str) -> Decimal:
    """One Kite money figure as an exact Decimal at the paisa (see the module docstring for the accepted shapes)."""
    if isinstance(value, bool):
        raise KiteReplyError(f"{name} must be a number, got {value!r}")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise KiteReplyError(f"{name} must be finite, got {value!r}")
        value = Decimal(str(value))  # the SDK's float: its shortest repr, never its binary expansion
    elif isinstance(value, str):
        if not _DECIMAL_LITERAL.fullmatch(value):
            raise KiteReplyError(f"{name} must be an exact decimal literal, got {value!r}")
        value = Decimal(value)
    elif type(value) is not Decimal and type(value) is not int:
        raise KiteReplyError(f"{name} must be a Decimal, int, float or decimal string, got {value!r}")
    try:
        return zerodha_paise(value)
    except (TypeError, ValueError) as exc:
        raise KiteReplyError(f"{name}: {exc}") from None


def _field(row: Mapping[str, object], name: str) -> object:
    if not isinstance(row, Mapping):
        raise KiteReplyError(f"a reply row must be a mapping, got {row!r}")
    if name not in row:
        raise KiteReplyError(f"reply row is missing {name!r}")
    return row[name]


def _text(row: Mapping[str, object], name: str) -> str:
    value = _field(row, name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise KiteReplyError(f"{name} must be a non-empty string, got {value!r}")
    return value


def _whole(row: Mapping[str, object], name: str) -> int:
    value = _field(row, name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise KiteReplyError(f"{name} must be a whole number, got {value!r}")
    return value


def _side(row: Mapping[str, object]) -> Action:
    word = _field(row, "transaction_type")
    if word not in _SIDES:
        raise KiteReplyError(f"transaction_type must be BUY or SELL, got {word!r}")
    return _SIDES[word]


def _token(row: Mapping[str, object]) -> str | None:
    token = row.get("instrument_token")
    if token is None:
        return None
    if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
        raise KiteReplyError(f"instrument_token must be a positive whole number, got {token!r}")
    return str(token)


def ist_timestamp(value: object, name: str) -> datetime.datetime:
    """A Kite full date-time (naive IST text "2026-10-16 12:20:50", or the SDK's naive datetime) as aware IST."""
    if isinstance(value, str):
        text = value
        try:
            if not _FULL_TIMESTAMP.fullmatch(text):
                raise ValueError(text)
            return datetime.datetime.fromisoformat(text).replace(tzinfo=IST)  # Kite's naive text is IST
        except ValueError:
            raise KiteReplyError(f"{name} must be a full date-time 'YYYY-MM-DD HH:MM:SS', got {text!r}") from None
    if not isinstance(value, datetime.datetime):
        raise KiteReplyError(f"{name} must be a date-time, got {value!r}")
    return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)


@dataclass(frozen=True)
class _IndexRow:
    token: str
    symbol: str
    key: ContractKey


class ContractIndex:
    """tradingsymbol / instrument_token -> reconcile contract key. Exactly one matching row, or refused."""

    def __init__(self, rows: Iterable[_IndexRow]) -> None:
        self._rows = tuple(rows)

    @classmethod
    def from_catalogue(cls, catalogue: Catalogue) -> ContractIndex:
        rows = []
        for entry in catalogue.all_entries():
            ref = entry.broker_refs.get(ZERODHA)
            contract = entry.contract
            if ref is None or contract.expiry is None:
                continue
            if contract.is_future():
                key = (contract.name, Instrument.FUT, None, contract.expiry)
            elif contract.is_option():
                key = (contract.name, Instrument(contract.instrument_type), contract.strike, contract.expiry)
            else:
                continue
            rows.append(_IndexRow(ref.broker_token, ref.broker_symbol, key))
        return cls(rows)

    @classmethod
    def from_instrument_slice(cls, slice_rows: Mapping[str, Mapping[str, object]]) -> ContractIndex:
        """The recorder's instrument map: token -> {symbol, group "NIFTY 2026-10-19", type, strike, expiry}."""
        rows = []
        for token, row in slice_rows.items():
            symbol = _text(row, "symbol")
            underlying = _text(row, "group").split(" ")[0]
            kind = _text(row, "type")
            if underlying not in SUPPORTED_UNDERLYINGS or kind not in (*_OPTION_TYPES, "FUT"):
                continue  # an index or an unsupported underlying is never a reconcile contract
            expiry = datetime.date.fromisoformat(_text(row, "expiry"))
            if kind == "FUT":
                key = (underlying, Instrument.FUT, None, expiry)
            else:
                strike = _text(row, "strike")
                if not _DECIMAL_LITERAL.fullmatch(strike):
                    raise KiteReplyError(f"strike must be an exact decimal literal, got {strike!r}")
                key = (underlying, _OPTION_TYPES[kind], Decimal(strike), expiry)
            rows.append(_IndexRow(str(token), symbol, key))
        return cls(rows)

    def resolve(self, row: Mapping[str, object]) -> ContractKey:
        symbol = _text(row, "tradingsymbol")
        token = _token(row)
        found = [r for r in self._rows if r.symbol == symbol and (token is None or r.token == token)]
        if len(found) != 1:
            raise KiteReplyError(f"{symbol} (token {token}) matches {len(found)} instrument rows; need exactly 1")
        return found[0].key


@dataclass(frozen=True)
class PositionsRead:
    """The ``net`` positions reply: broker net units per contract key (flat rows dropped) and the parsed lines."""

    net: Mapping[ContractKey, int]
    lines: tuple[BrokerPositionLine, ...]


def positions_from_reply(data: Mapping[str, object], index: ContractIndex) -> PositionsRead:
    rows = _field(data, "net")
    if not isinstance(rows, list):
        raise KiteReplyError(f"positions 'net' must be a list, got {rows!r}")
    net: dict[ContractKey, int] = {}
    lines = []
    for row in rows:
        if is_flat_row(row):
            continue  # quantity 0: no position (never a 0-price holding)
        parsed = {**row, "average_price": kite_money(_field(row, "average_price"), "average_price")}
        if row.get("last_price") is not None:
            parsed["last_price"] = kite_money(row["last_price"], "last_price")
        try:
            line = position_line_from_kite_row(parsed)
        except ValueError as exc:
            raise KiteReplyError(f"position row {row.get('tradingsymbol')!r}: {exc}") from None
        key = index.resolve(row)
        net[key] = net.get(key, 0) + line.net_quantity
        lines.append(line)
    return PositionsRead({k: q for k, q in net.items() if q != 0}, tuple(lines))


def fill_from_trade_row(row: Mapping[str, object]) -> FillEvent:
    """One trades-reply row as a `FillEvent` (timestamp from ``fill_timestamp``; ``order_timestamp`` unused)."""
    try:
        return FillEvent(_text(row, "trade_id"), _text(row, "order_id"), _text(row, "tradingsymbol"), _side(row),
                         _whole(row, "quantity"), kite_money(_field(row, "average_price"), "average_price"),
                         ist_timestamp(_field(row, "fill_timestamp"), "fill_timestamp"))
    except KiteReplyError:
        raise
    except ValueError as exc:
        raise KiteReplyError(f"trade row {row.get('trade_id')!r}: {exc}") from None


def fills_from_reply(data: object) -> tuple[FillEvent, ...]:
    if not isinstance(data, list):
        raise KiteReplyError(f"trades 'data' must be a list, got {data!r}")
    return tuple(fill_from_trade_row(row) for row in data)


@dataclass(frozen=True)
class BrokerOrderRow:
    """One orders-reply row, as read. ``filled_quantity`` is the broker's cumulative fill count for
    `OrderBook.reconcile_cumulative`; ``status`` is the raw word, informational only."""

    order_id: str
    tag: str | None
    tradingsymbol: str
    side: Action
    quantity: int
    filled_quantity: int
    price: Decimal
    average_price: Decimal
    status: str


def order_from_row(row: Mapping[str, object]) -> BrokerOrderRow:
    tag = row.get("tag")
    if tag is not None and (not isinstance(tag, str) or not tag):
        raise KiteReplyError(f"tag must be a non-empty string or null, got {tag!r}")
    quantity, filled = _whole(row, "quantity"), _whole(row, "filled_quantity")
    if quantity <= 0 or not 0 <= filled <= quantity:
        raise KiteReplyError(f"order {row.get('order_id')!r}: filled {filled} of {quantity} is impossible")
    return BrokerOrderRow(_text(row, "order_id"), tag, _text(row, "tradingsymbol"), _side(row), quantity, filled,
                          kite_money(_field(row, "price"), "price"),
                          kite_money(_field(row, "average_price"), "average_price"), _text(row, "status"))


def orders_from_reply(data: object) -> tuple[BrokerOrderRow, ...]:
    if not isinstance(data, list):
        raise KiteReplyError(f"orders 'data' must be a list, got {data!r}")
    return tuple(order_from_row(row) for row in data)
