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
import logging
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.engine.legs import Action, Instrument
from ofo.execution.partial import BrokerOrderStatus
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import ZERODHA
from ofo.instruments.parser import ZERODHA_EXCHANGE_TO_SEGMENT
from ofo.money import zerodha_paise
from ofo.orders.model import FillEvent, OrderState
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


def _exact_figure(value: Decimal | int, name: str) -> Decimal:
    """An average price kept as Kite sent it: 5.1 -> 5.10 (same value), 5.125 stays; an int (Kite's
    "average_price": 0 on an unfilled order) is exact too; non-finite or too large -> KiteReplyError."""
    exact_value = Decimal(value)
    if not exact_value.is_finite():
        raise KiteReplyError(f"{name} must be finite, got {value!r}")
    try:
        at_paisa = zerodha_paise(exact_value)
    except (TypeError, ValueError) as exc:
        raise KiteReplyError(f"{name}: {exc}") from None
    return at_paisa if at_paisa == exact_value else exact_value


def kite_money(value: object, name: str, *, exact: bool = False) -> Decimal:
    """One Kite money figure as an exact Decimal at the paisa (see the module docstring for the accepted shapes).

    ``exact=True`` keeps the figure as Kite sent it, not rounded: for an AVERAGE price (5.125 after two fills is a fact
    about the fills, not a money amount to settle; ADR-101 rounds the figures a margin comparison uses). GC-2b
    architect decision, recorded in ADR-102."""
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
    if exact:
        return _exact_figure(value, name)
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
    lot: int | None = None  # Zerodha's lot size (catalogue rows only; the recorder's slice carries none)


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
            rows.append(_IndexRow(ref.broker_token, ref.broker_symbol, key, ref.lot_size))
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

    def symbol_of(self, key: ContractKey) -> str | None:
        """The Zerodha trading symbol of a reconcile key, or None when the catalogue has none (W-111)."""
        found = sorted({r.symbol for r in self._rows if r.key == key})
        return found[0] if found else None

    def lot_of(self, key: ContractKey) -> int | None:
        """Zerodha's lot size of a reconcile key: exactly one positive value among its rows, else None (never guessed;
        W-111's outside-lots count)."""
        found = {r.lot for r in self._rows if r.key == key}
        if len(found) != 1:
            return None
        (lot,) = found
        return lot if isinstance(lot, int) and lot > 0 else None

    def resolve(self, row: Mapping[str, object]) -> ContractKey:
        symbol = _text(row, "tradingsymbol")
        token = _token(row)
        found = [r for r in self._rows if r.symbol == symbol and (token is None or r.token == token)]
        if len(found) != 1:
            raise KiteReplyError(f"{symbol} (token {token}) matches {len(found)} instrument rows; need exactly 1")
        return found[0].key


@dataclass(frozen=True)
class PositionsRead:
    """The ``net`` positions reply: broker net units per contract key (flat rows dropped), the parsed lines, and the
    non-flat rows the platform can never own (``"EXCHANGE:SYMBOL"``, reply order), kept for audit, never lost."""

    net: Mapping[ContractKey, int]
    lines: tuple[BrokerPositionLine, ...]
    ignored: tuple[str, ...] = ()


#: A Kite F&O tradingsymbol: underlying, 2-digit year, then a monthly ``OCT`` or weekly ``O19`` expiry, then a strike
#: and CE/PE, or FUT (NIFTY26OCT24000CE, NIFTY26O1923650CE, NIFTY26OCTFUT). The lazy underlying makes SENSEX50... read
#: as SENSEX50, never SENSEX.
_FO_SYMBOL: Final = re.compile(r"(?P<underlying>[A-Z0-9&-]+?)[0-9]{2}(?:[A-Z]{3}|[1-9OND][0-9]{2})"
                               r"(?:[0-9]+(?:\.[0-9]+)?(?:CE|PE)|FUT)")


#: Kite exchanges whose rows the platform can never own (equity, commodity, currency); any exchange in neither this set
#: nor ZERODHA_EXCHANGE_TO_SEGMENT is unknown and refuses the read.
_NEVER_OURS_EXCHANGES: Final = frozenset({"NSE", "BSE", "MCX", "CDS", "BCD", "NCO"})

log = logging.getLogger(__name__)


def log_ignored(read: PositionsRead, where: str) -> None:
    """One INFO line per positions read naming the rows skipped as never ours (EXCHANGE:SYMBOL only: no money, no
    account id), so a skipped row is never silently lost."""
    if read.ignored:
        log.info("%s: positions read ignored %d non-platform rows: %s", where, len(read.ignored),
                 ", ".join(read.ignored))


def platform_may_own(row: Mapping[str, object]) -> bool:
    """True when the row could be the platform's: an F&O exchange it trades (ZERODHA_EXCHANGE_TO_SEGMENT) AND an
    underlying of SUPPORTED_UNDERLYINGS listed on that exchange's segment. An allowlist of what is ours: anything else
    (equity CNC/MIS, MCX/CDS, BANKNIFTY or stock F&O) is never ours. A missing or malformed exchange, or an F&O
    symbol whose underlying cannot be read, refuses (KiteReplyError): never read as "not ours"."""
    exchange = _text(row, "exchange")
    segment = ZERODHA_EXCHANGE_TO_SEGMENT.get(exchange)
    if segment is None:
        if exchange in _NEVER_OURS_EXCHANGES:
            return False
        raise KiteReplyError(f"unknown exchange {exchange!r}")  # nfo, NSEFO, a new code: could be ours, never skipped
    symbol = _text(row, "tradingsymbol")
    shape = _FO_SYMBOL.fullmatch(symbol)
    if shape is None:
        raise KiteReplyError(f"{exchange} row {symbol!r} is not a Kite F&O symbol; its underlying cannot be read")
    return SUPPORTED_UNDERLYINGS.get(shape["underlying"]) == segment


def positions_from_reply(data: Mapping[str, object], index: ContractIndex) -> PositionsRead:
    rows = _field(data, "net")
    if not isinstance(rows, list):
        raise KiteReplyError(f"positions 'net' must be a list, got {rows!r}")
    net: dict[ContractKey, int] = {}
    lines = []
    ignored = []
    for row in rows:
        if is_flat_row(row):
            continue  # quantity 0: no position (never a 0-price holding)
        if not platform_may_own(row):
            ignored.append(f"{_text(row, 'exchange')}:{_text(row, 'tradingsymbol')}")
            continue  # e.g. the owner's own stock trade (CNC): never in the catalogue, never a reconcile contract
        parsed = {**row, "average_price": kite_money(_field(row, "average_price"), "average_price", exact=True)}
        if row.get("last_price") is not None:
            parsed["last_price"] = kite_money(row["last_price"], "last_price")
        try:
            line = position_line_from_kite_row(parsed)
        except ValueError as exc:
            raise KiteReplyError(f"position row {row.get('tradingsymbol')!r}: {exc}") from None
        key = index.resolve(row)
        net[key] = net.get(key, 0) + line.net_quantity
        lines.append(line)
    return PositionsRead({k: q for k, q in net.items() if q != 0}, tuple(lines), tuple(ignored))


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
    if not isinstance(row, Mapping):  # allow-list: only a mapping is a row ('x', None, 5 are refused, never a crash)
        raise KiteReplyError(f"an orders row must be a mapping, got {row!r}")
    tag = row.get("tag")
    if tag is not None and (not isinstance(tag, str) or not tag):
        raise KiteReplyError(f"tag must be a non-empty string or null, got {tag!r}")
    quantity, filled = _whole(row, "quantity"), _whole(row, "filled_quantity")
    if quantity <= 0 or not 0 <= filled <= quantity:
        raise KiteReplyError(f"order {row.get('order_id')!r}: filled {filled} of {quantity} is impossible")
    return BrokerOrderRow(_text(row, "order_id"), tag, _text(row, "tradingsymbol"), _side(row), quantity, filled,
                          kite_money(_field(row, "price"), "price"),
                          kite_money(_field(row, "average_price"), "average_price", exact=True), _text(row, "status"))


#: Kite's order status words that mean "still working at the broker" (Kite's own list). An allow-list: a word in none of
#: these sets and not COMPLETE / REJECTED / CANCELLED is refused, never read as pending (W-131).
_WORKING_STATUS_WORDS: Final = frozenset({
    "PUT ORDER REQ RECEIVED", "VALIDATION PENDING", "OPEN PENDING", "MODIFY VALIDATION PENDING", "MODIFY PENDING",
    "TRIGGER PENDING", "CANCEL PENDING", "AMO REQ RECEIVED", "OPEN"})


def order_status_from_row(row: Mapping[str, object]) -> BrokerOrderStatus:
    """One orders-reply row as the broker's current view of that order (REQ-054 AC-1 "fetch order status").

    COMPLETE needs every unit filled; a working word with some (not all) units filled is Partially Executed; REJECTED
    and CANCELLED are terminal and keep the cumulative fill. ``reason`` is Kite's ``status_message`` text, or None."""
    parsed = order_from_row(row)
    word, filled = parsed.status, parsed.filled_quantity
    if word == "COMPLETE":
        if filled != parsed.quantity:
            raise KiteReplyError(f"order {parsed.order_id!r}: COMPLETE with {filled} of {parsed.quantity} filled")
        state = OrderState.EXECUTED
    elif word in ("REJECTED", "CANCELLED"):
        state = OrderState.REJECTED if word == "REJECTED" else OrderState.CANCELLED
    elif word in _WORKING_STATUS_WORDS:
        state = OrderState.PARTIALLY_EXECUTED if 0 < filled < parsed.quantity else OrderState.PENDING
    else:
        raise KiteReplyError(f"order {parsed.order_id!r}: unknown status word {word!r}")
    message = row.get("status_message")
    reason = message if isinstance(message, str) and message.strip() else None
    return BrokerOrderStatus(parsed.order_id, parsed.tradingsymbol, state, filled, reason, parsed.tag)


def orders_from_reply(data: object) -> tuple[BrokerOrderRow, ...]:
    if not isinstance(data, list):
        raise KiteReplyError(f"orders 'data' must be a list, got {data!r}")
    return tuple(order_from_row(row) for row in data)
