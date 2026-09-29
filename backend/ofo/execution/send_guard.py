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

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Protocol

from ofo.engine import Action
from ofo.instruments import Catalogue
from ofo.orders import TERMINAL_STATES, Order, OrderBook
from ofo.strategy.definition import DefinitionLeg
from ofo.strategy.versions import StrategyRecord, Version

_MINT: Final = object()  # only this module builds a broker request


class SendRefused(ValueError):
    """An order is not one the strategy's record, the catalogue and the ledger allow; nothing was sent."""


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
            raise SendRefused("a broker request is built only by the broker sink")


class _Transport(Protocol):
    """The broker adapter's only job: send an already-resolved request, return the broker's order id."""

    def submit(self, request: _BrokerRequest) -> str: ...


def executable_version(record: StrategyRecord, number: int) -> Version:
    """The version being executed must be the record's active or pending proposed version."""
    live = {v.number for v in (record.active_version, record.proposed_version) if v is not None}
    if number not in live:
        raise SendRefused(f"version v{number} is neither the active nor the pending version of this strategy")
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
        raise SendRefused(f"the choice {choice!r} sends no orders")
    wanted: dict[str, int] = {}
    for order in orders:
        if order.strategy_id != strategy_id or order.version_id != f"v{version.number}":
            raise SendRefused(f"order {order.leg_ref!r} does not belong to this strategy version")
        leg = planned.get(order.contract)
        if leg is None or leg[0] != order.leg_ref:
            raise SendRefused(f"{order.contract!r} is not a leg of version v{version.number}; nothing was sent")
        if (order.side is leg[1]) == reducing:
            raise SendRefused(f"{order.side.value} {order.contract} is not the "
                              f"{'reducing' if reducing else 'planned'} side of that leg; nothing was sent")
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
            raise SendRefused(f"{units} units of {contract} exceed what the strategy allows ({max(room, 0)}); "
                              "nothing was sent")


Slot = tuple[str, "Decimal | None", object]


def _slot(leg: object) -> Slot:
    return (leg.instrument.value, leg.strike, leg.expiry)  # type: ignore[attr-defined]


def _catalogue_symbol(catalogue: Catalogue, underlying: str, leg: DefinitionLeg) -> str:
    """The one catalogue entry for the leg: underlying, instrument type, expiry and (options) strike."""
    matches = {e.contract.tradingsymbol for e in catalogue.all_entries()
               if e.contract.name == underlying and e.contract.instrument_type == leg.instrument.value
               and e.contract.expiry == leg.expiry and (leg.strike is None or e.contract.strike == leg.strike)}
    if len(matches) != 1:
        raise SendRefused(f"the catalogue has {len(matches)} instruments for {leg.describe()}; nothing was sent")
    return next(iter(matches))


class _BrokerSink:
    """Created only inside ``submit_confirmed`` for one preparation. The transport lives in a closure; a request is
    sent only if this sink resolved it, and only once."""

    __slots__ = ("resolve_all", "submit")

    def __init__(self, transport: _Transport, *, book: OrderBook, strategy_id: str, catalogue: Catalogue | None,
                 choice: str, leg_slots: Mapping[str, Slot]) -> None:
        if not isinstance(catalogue, Catalogue):
            raise SendRefused("the broker sink needs the catalogue to derive trading symbols; nothing was sent")
        record = book.record_for(strategy_id)  # an unbound strategy has no sink
        resolved: dict[int, _BrokerRequest] = {}

        def resolve_all(orders: Sequence[Order]) -> tuple[_BrokerRequest, ...]:
            derived: list[Order] = []
            requests: list[_BrokerRequest] = []
            for order in orders:
                if not isinstance(order, Order) or order.strategy_id != strategy_id:
                    raise SendRefused("the order does not belong to this strategy; nothing was sent")
                vid = order.version_id
                if not isinstance(vid, str) or not vid.startswith("v") or not vid[1:].isdigit():
                    raise SendRefused(f"no version {vid!r}; nothing was sent")
                version = executable_version(record, int(vid[1:]))
                definition = version.definition
                slot = leg_slots.get(order.leg_ref)
                leg = next((d for d in definition.legs if _slot(d) == slot), None)
                if leg is None:
                    raise SendRefused(f"{order.leg_ref!r} is not a leg of v{version.number}; nothing was sent")
                symbol = _catalogue_symbol(catalogue, definition.underlying, leg)
                if order.contract != symbol:
                    raise SendRefused(f"{order.contract!r} is not the catalogue symbol {symbol!r} of leg "
                                      f"{order.leg_ref!r}; nothing was sent")
                side = leg.action if choice != "close" else (Action.SELL if leg.action is Action.BUY else Action.BUY)
                if order.side is not side:
                    raise SendRefused(f"{order.side.value} is not the side of leg {order.leg_ref!r}; nothing was sent")
                one = dataclasses.replace(order, contract=symbol, side=side)
                allowed_or_refuse(choice=choice, orders=(one,), version=version,
                                  planned={symbol: (order.leg_ref, leg.action, leg.quantity)}, book=book,
                                  strategy_id=strategy_id)
                derived.append(one)
                if not isinstance(order.client_tag, str):
                    raise SendRefused("the platform client tag is missing; nothing was sent")
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
                raise SendRefused("this sink did not resolve that request (or it was already sent)")
            return transport.submit(request)

        object.__setattr__(self, "resolve_all", resolve_all)
        object.__setattr__(self, "submit", submit)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a broker sink cannot be changed")

