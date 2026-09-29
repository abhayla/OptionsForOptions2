"""What may be sent: re-derived at the send from the strategy's own record and the fill ledger (REQ-036 AC-1..AC-3).

Spec basis: REQ-036 AC-1 "Every order record references a strategy and strategy version"; AC-2 "No ... API offers a
standalone buy/sell of a single contract"; AC-3 "submission happens only through the strategy's execution flow";
ADR-002. Finding ``caller-supplied-verdict-trusted``: permission to send never comes from an object the caller built.

``allowed_or_refuse`` runs inside ``submit_confirmed`` on every send. It trusts neither the preparation's gate nor its
guard decision for WHAT is sent: every order must be a leg of the version the strategy's bound ``StrategyRecord``
holds (the active or the pending proposed version, whose legs the plan must equal), in the plan's contract, and:
- Complete / Retry: the plan's side, and per contract no more than the planned units minus the units the fill ledger
  already holds minus units still open on the book on that side;
- Close: the opposite side (reduce-only), and per contract no more than the held units minus exits already open.
Anything else is refused before the first order is sent. A modification sends no orders (it applies a broker result),
so it has no entry here.

``SendCapability``: the broker ``OrderSubmitter.submit(order, capability)`` must call
``SendCapability.redeem(capability, order)`` first. Only ``submit_confirmed`` mints one (module-private sentinel),
for exactly one order, usable once. Trust boundary, stated plainly: code running in this process can always import a
raw broker client or reach private names (``getattr``, ``importlib``); these checks stop every PUBLIC path and every
object a caller can build, not in-process code that deliberately reaches around them. The future Kite adapter MUST
refuse any call without a redeemable capability, so the only route to the broker is ``submit_confirmed``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from ofo.engine import Action
from ofo.orders import TERMINAL_STATES, Order, OrderBook
from ofo.strategy.versions import StrategyRecord, Version

_MINT: Final = object()  # only this module mints a SendCapability


class SendRefused(ValueError):
    """An order is not one the strategy's record and ledger allow; nothing was sent."""


class SendCapability:
    """A one-shot permission to send exactly one order, minted only by ``submit_confirmed``."""

    __slots__ = ("_order", "_spent")

    def __init__(self, order: Order, *, _mint: object = None) -> None:
        if _mint is not _MINT:
            raise SendRefused("a send capability is minted only by submit_confirmed")
        object.__setattr__(self, "_order", order)
        object.__setattr__(self, "_spent", False)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a send capability cannot be changed")

    @staticmethod
    def redeem(capability: object, order: Order) -> None:
        """Every broker submitter calls this first. Refuses anything but an unspent capability for this order."""
        if type(capability) is not SendCapability or capability._spent or capability._order is not order:
            raise SendRefused("no valid send capability for this order: orders reach the broker only through "
                              "submit_confirmed")
        object.__setattr__(capability, "_spent", True)


def mint_capability(order: Order) -> SendCapability:
    return SendCapability(order, _mint=_MINT)


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
    """Refuse unless every order is a permitted leg (see module docstring). ``planned`` maps a contract to
    (leg_ref, side, planned units) of a plan already checked equal to ``version``'s legs."""
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
        leg_ref, side, _units = leg
        if (order.side is side) == reducing:
            raise SendRefused(f"{order.side.value} {order.contract} is not the "
                              f"{'reducing' if reducing else 'planned'} side of that leg; nothing was sent")
        wanted[order.contract] = wanted.get(order.contract, 0) + order.quantity
    views = book.views_for(strategy_id)
    for contract, units in wanted.items():
        leg_ref, side, planned_units = planned[contract]
        signed = book.position(strategy_id, contract)
        held = max(0, signed if side is Action.BUY else -signed)
        send_side = side if not reducing else (Action.SELL if side is Action.BUY else Action.BUY)
        open_units = sum(v.quantity - v.filled_quantity for v in views
                         if v.contract == contract and v.side is send_side and v.state not in TERMINAL_STATES)
        room = (held if reducing else planned_units - held) - open_units
        if units > room:
            raise SendRefused(f"{units} units of {contract} exceed what the strategy allows ({max(room, 0)}); "
                              "nothing was sent")
