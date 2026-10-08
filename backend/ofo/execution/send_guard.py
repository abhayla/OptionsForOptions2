"""The broker sink: every broker field is re-derived from the strategy's record and the catalogue (REQ-036 AC-1..AC-3).

Spec basis: REQ-036 AC-1 "Every order record references a strategy and strategy version"; AC-2 "No ... API offers a
standalone buy/sell of a single contract"; AC-3 "submission happens only through the strategy's execution flow";
ADR-002. Finding ``caller-supplied-verdict-trusted``: permission to send never comes from an object the caller built.

W-026 round 3 (independent review). Class: the send path checked the story the caller tells, not the order the sink
sends. Threat model (agreed): accidental misuse by future platform code, not a malicious in-process attacker.

- R1: no public name under ``ofo`` can produce a sendable request or reach a broker transport except
  ``ofo.execution.partial.submit_confirmed``. The request type (``_BrokerRequest``), the transport protocol
  (``_Transport``) and the sink (``_BrokerSink``) are private; a request can only be built inside this module.
- R2: ``_BrokerSink.resolve_all`` trusts no broker field of the order. From the bound ``StrategyRecord``'s
  executable version (active or pending) it takes the leg the order names, computes the trading symbol from the
  catalogue (underlying, instrument type, expiry, strike -> the one catalogue entry) and refuses if the order's symbol
  differs; the side is the leg's side (Close: the opposite); the quantity must fit the room the record and the fill
  ledger leave (``allowed_or_refuse``). The request carries only these derived values plus the price the user
  reviewed and the platform's client tag.
- R3: private-name reach-arounds (``_BrokerSink``, ``_MINT`` ...) are out of scope; tests use them only to prove the
  sink's own checks. Adapter boundary (spec/technical-design/legacy-reuse.md "Broker adapter boundary"): the future
  Kite adapter implements only ``_Transport.submit(request)`` and is constructed only inside this module.
"""
from __future__ import annotations

from ofo.errors.user_facing import UserFacing

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Protocol

from ofo.engine import Action
from ofo.errors import UserFacingError, display_text, render
from ofo.instruments import ZERODHA, Catalogue, MissingBrokerRef
from ofo.orders import TERMINAL_STATES, Order, OrderBook
from ofo.strategy.definition import DefinitionLeg
from ofo.strategy.versions import StrategyRecord, Version

_MINT: Final = object()  # only this module builds a broker request


class SendRefused(UserFacing, ValueError):
    """An order is not one the strategy's record, the catalogue and the ledger allow; nothing was sent.

    W-024 round 9 (REQ-065 AC-2, ADR-003 Q226): the words come only from ``render()``. ``message`` is the four-part
    ``UserFacingError``; ``reason`` is its what-happened part (kept for the audit record and ``str(error)``), ``text``
    is what a user is shown (all four parts). A plain string is refused."""

    def __init__(self, message: UserFacingError) -> None:
        if type(message) is not UserFacingError:
            raise TypeError(f"SendRefused needs a UserFacingError from ofo.errors.render(), got {type(message).__name__}")
        super().__init__(message.what_happened)
        self.message = message

    @property
    def reason(self) -> str:
        return self.message.what_happened

    @property
    def text(self) -> str:
        return display_text(self.message)


def _refuse(template_id: str, **slots: object) -> SendRefused:
    return SendRefused(render(template_id, **slots))


@dataclass(frozen=True)
class _BrokerRequest:
    """What a transport sends: every field derived by ``_BrokerSink``, none copied from a caller's claim."""

    strategy_id: str
    version_id: str
    leg_ref: str
    contract: str  # the catalogue trading symbol of the record's leg
    side: Action
    quantity: int
    price: Decimal
    client_tag: str
    _mint: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._mint is not _MINT:
            raise _refuse("send_request_not_from_sink")


class _Transport(Protocol):
    """The broker adapter's only job: send an already-resolved request, return the broker's order id."""

    def submit(self, request: _BrokerRequest) -> str: ...


def executable_version(record: StrategyRecord, number: int) -> Version:
    """The version being executed must be the record's active or pending proposed version."""
    live = {v.number for v in (record.active_version, record.proposed_version) if v is not None}
    if number not in live:
        raise _refuse("send_version_not_live", version=number)
    return record.version(number)


def allowed_or_refuse(
    *, choice: str, orders: Sequence[Order], version: Version, planned: Mapping[str, tuple[str, Action, int]],
    book: OrderBook, strategy_id: str,
) -> None:
    """Refuse unless every order is a permitted leg. ``planned`` maps a contract to (leg_ref, side, planned units)
    of the version's legs. Complete/Retry: the leg's side, units <= planned - held - open on that side. Close: the
    opposite side, units <= held - open exits. Held units come from the fill ledger, open units from the book."""
    reducing = choice == "close"
    if choice not in ("complete", "retry", "close"):
        raise _refuse("send_choice_unknown")
    wanted: dict[str, int] = {}
    for order in orders:
        if order.strategy_id != strategy_id or order.version_id != f"v{version.number}":
            raise _refuse("send_order_wrong_version")
        leg = planned.get(order.contract)
        if leg is None or leg[0] != order.leg_ref:
            raise _refuse("send_contract_not_a_leg", version=version.number)
        if (order.side is leg[1]) == reducing:
            raise _refuse("send_side_not_allowed")
        wanted[order.contract] = wanted.get(order.contract, 0) + order.quantity
    views = book.views_for(strategy_id)
    for contract, units in wanted.items():
        _leg_ref, side, planned_units = planned[contract]
        signed = book.position(strategy_id, contract)
        held = max(0, signed if side is Action.BUY else -signed)
        send_side = side if not reducing else (Action.SELL if side is Action.BUY else Action.BUY)
        open_units = sum(v.quantity - v.filled_quantity for v in views
                         if v.contract == contract and v.side is send_side and v.state not in TERMINAL_STATES)
        room = (held if reducing else planned_units - held) - open_units
        if units > room:
            raise _refuse("send_quantity_exceeds", units=units, room=max(room, 0))


Slot = tuple[str, "Decimal | None", object]


def _slot(leg: object) -> Slot:
    return (leg.instrument.value, leg.strike, leg.expiry)  # type: ignore[attr-defined]


def _catalogue_symbol(catalogue: Catalogue, underlying: str, leg: DefinitionLeg) -> str:
    """The one catalogue entry for the leg (underlying, instrument type, expiry and, for options, strike), and
    Zerodha's symbol from that entry's Zerodha row. No Zerodha row: refused, no symbol is guessed (REQ-054 AC-3)."""
    matches = [e for e in catalogue.all_entries()
               if e.contract.name == underlying and e.contract.instrument_type == leg.instrument.value
               and e.contract.expiry == leg.expiry and (leg.strike is None or e.contract.strike == leg.strike)]
    if len(matches) != 1:
        raise _refuse("send_catalogue_not_one", count=len(matches))
    try:
        return matches[0].ref(ZERODHA).broker_symbol
    except MissingBrokerRef as exc:
        raise _refuse("send_no_zerodha_record") from exc


class _BrokerSink:
    """Created only inside ``submit_confirmed`` for one preparation. The transport lives in a closure; a request is
    sent only if this sink resolved it, and only once."""

    __slots__ = ("resolve_all", "submit")

    def __init__(self, transport: _Transport, *, book: OrderBook, strategy_id: str, catalogue: Catalogue | None,
                 choice: str, leg_slots: Mapping[str, Slot]) -> None:
        if not isinstance(catalogue, Catalogue):
            raise _refuse("send_catalogue_missing")
        record = book.record_for(strategy_id)  # an unbound strategy has no sink
        resolved: dict[int, _BrokerRequest] = {}

        def resolve_all(orders: Sequence[Order]) -> tuple[_BrokerRequest, ...]:
            derived: list[Order] = []
            requests: list[_BrokerRequest] = []
            for order in orders:
                if not isinstance(order, Order) or order.strategy_id != strategy_id:
                    raise _refuse("send_order_other_strategy")
                vid = order.version_id
                if not isinstance(vid, str) or not vid.startswith("v") or not vid[1:].isdigit():
                    raise _refuse("send_version_unreadable")
                version = executable_version(record, int(vid[1:]))
                definition = version.definition
                slot = leg_slots.get(order.leg_ref)
                leg = next((d for d in definition.legs if _slot(d) == slot), None)
                if leg is None:
                    raise _refuse("send_leg_not_in_version", version=version.number)
                symbol = _catalogue_symbol(catalogue, definition.underlying, leg)
                if order.contract != symbol:
                    raise _refuse("send_symbol_mismatch")
                side = leg.action if choice != "close" else (Action.SELL if leg.action is Action.BUY else Action.BUY)
                if order.side is not side:
                    raise _refuse("send_side_not_leg_side")
                one = dataclasses.replace(order, contract=symbol, side=side)
                allowed_or_refuse(choice=choice, orders=(one,), version=version,
                                  planned={symbol: (order.leg_ref, leg.action, leg.quantity)}, book=book,
                                  strategy_id=strategy_id)
                derived.append(one)
                if not isinstance(order.client_tag, str):
                    raise _refuse("send_client_tag_missing")
                requests.append(_BrokerRequest(strategy_id, f"v{version.number}", order.leg_ref, symbol, side,
                                               one.quantity, order.price, order.client_tag, _mint=_MINT))
            by_contract: dict[str, list[Order]] = {}
            for one in derived:
                by_contract.setdefault(one.contract, []).append(one)
            for group in by_contract.values():  # several orders on one contract share one room
                if len(group) > 1:
                    first = group[0]
                    version = record.version(int(first.version_id[1:]))
                    leg = next(d for d in version.definition.legs if _slot(d) == leg_slots[first.leg_ref])
                    allowed_or_refuse(choice=choice, orders=group, version=version,
                                      planned={first.contract: (first.leg_ref, leg.action, leg.quantity)},
                                      book=book, strategy_id=strategy_id)
            for request in requests:
                resolved[id(request)] = request
            return tuple(requests)

        def submit(request: _BrokerRequest) -> str:
            if resolved.pop(id(request), None) is not request:
                raise _refuse("send_request_not_resolved")
            return transport.submit(request)

        object.__setattr__(self, "resolve_all", resolve_all)
        object.__setattr__(self, "submit", submit)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a broker sink cannot be changed")

