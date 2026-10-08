"""W-029 (deferred #45 item 1, follow-up of W-026 round 3): three backup checks in the broker sink and the send
path were proven correct but had no killing test. REQ-036 AC-3 (the sink re-derives every broker field from the
catalogue) and AC-5 (Strategy Guard). Test-only: no production file changes.

Mutants named by the verifier, each with the test below that must turn red against it:
- M7: ``_catalogue_symbol``'s underlying filter (``e.contract.name == underlying``) in
  ``backend/ofo/execution/send_guard.py`` -> ``test_underlying_filter_rejects_a_same_strike_finnifty_twin``.
- M14: the sink's room check ACROSS split orders on one contract in the same ``resolve_all`` call (the
  ``by_contract``/group ``allowed_or_refuse`` in ``_BrokerSink.resolve_all``) -> ``test_split_orders_room_check``.
- M15: the ``guard.binding != binding`` line in ``_authorised_orders`` (``backend/ofo/execution/partial.py``) ->
  ``test_guard_binding_mismatch_is_refused``.

Each was confirmed red against its mutant in a scratch copy of the file (mutant applied, test run, mutant reverted)
before this file was committed; ``git diff --stat`` shows only this new test file.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest
from partial_inputs import (
    CONTRACTS,
    LOT,
    STRATEGY_ID,
    FakeBroker,
    FakePlanner,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

from ofo.engine import Action
from ofo.execution import partial, send_guard
from ofo.execution.partial import Preparation, complete_strategy, discard_preparation
from ofo.execution.send_guard import SendRefused
from ofo.instruments.parser import zerodha_listed
from ofo.instruments import CatalogueEntry, Contract
from ofo.orders import Order
from ofo.strategy.guard import GuardBinding, GuardRefused, proposal_hash

EXPIRY = datetime.date(2026, 10, 6)


def _complete(book, catalogue, eligibility, **ctx) -> Preparation:  # noqa: ANN001
    return complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book, FakePlanner(),
                             entry_context(**ctx), catalogue, eligibility)


def _sink(book, catalogue, choice: str = "complete", leg_slots=None, transport=None):  # noqa: ANN001, ANN202
    slots = leg_slots or {p.leg_ref: (p.leg.instrument.value, p.leg.strike, p.leg.expiry) for p in plan().legs}
    return send_guard._BrokerSink(transport or _CountingTransport(), book=book, strategy_id=STRATEGY_ID,
                                  catalogue=catalogue, choice=choice, leg_slots=slots)


class _CountingTransport:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def submit(self, request: object) -> str:
        self.calls.append(request)
        return f"NEW-{len(self.calls)}"


def _tagged(order: Order) -> Order:
    return dataclasses.replace(order, client_tag="OFO999999999")


def _finnifty_twin() -> Contract:
    """A FINNIFTY contract at the SAME strike, expiry and instrument type as the real 23,600 CE NIFTY fixture leg
    (leg-4, ``CONTRACTS[3]``, the one leg ``book_with_three_filled`` leaves unfilled so it has room), but a
    different underlying name. FINNIFTY is out of the catalogue's supported-underlying scope, so it is inserted
    directly into the catalogue's entries (a data-integrity edge case the sink itself must still refuse, not a
    shape the catalogue's own load would normally admit)."""
    return zerodha_listed(
        instrument_token=900_000_001, exchange_token=900_001, tradingsymbol="FINNIFTY26O0623600CE",
        name="FINNIFTY", expiry=EXPIRY, strike=D("23600"), tick_size=D("0.05"), lot_size=40,
        instrument_type="CE", segment="NFO-OPT", exchange="NFO",
    )


# -- M7: the sink's underlying filter ---------------------------------------------------------------------------

def test_underlying_filter_rejects_a_same_strike_finnifty_twin(catalogue, eligibility) -> None:
    """AC-3: with a FINNIFTY twin of leg-4 (same strike 23,600, same expiry, same CE type) also in the catalogue,
    the sink must still resolve leg-4's order to the real NIFTY symbol, and must refuse an order that names the
    FINNIFTY symbol instead. Deleting the underlying-equality filter in ``_catalogue_symbol`` makes the first
    assertion fail: two instruments then match strike+expiry+type, so the catalogue lookup itself raises instead
    of uniquely resolving to NIFTY."""
    twin = _finnifty_twin()
    catalogue._entries[twin.id] = CatalogueEntry(contract=twin.contract, currently_listed=True,
                                                 broker_refs={r.broker: r for r in twin.broker_refs})

    book = book_with_three_filled()
    transport = _CountingTransport()
    leg4_order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    (request,) = _sink(book, catalogue, transport=transport).resolve_all((_tagged(leg4_order),))
    assert request.contract == CONTRACTS[3]  # still resolves to the real NIFTY symbol, never the FINNIFTY twin

    finnifty_order = Order(STRATEGY_ID, "leg-4", "FINNIFTY26O0623600CE", Action.BUY, LOT, D("44.00"),
                           version_id="v1")
    with pytest.raises(SendRefused):
        _sink(book, catalogue, transport=transport).resolve_all((_tagged(finnifty_order),))


# -- M14: the sink's room check across split orders in one resolve_all call -------------------------------------

def test_split_orders_room_check(catalogue) -> None:
    """AC-3: two orders for the SAME missing leg (leg-4, room = 65 units), 40 units each. Neither alone exceeds the
    room (40 <= 65), so the per-order check passes both; only the running total across the two orders (80 > 65)
    catches it. Deleting that group-level check in ``resolve_all`` lets both resolve; the real sink refuses the
    batch and the transport sees zero calls."""
    book = book_with_three_filled()
    transport = _CountingTransport()
    first = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, 40, D("44.00"), version_id="v1",
                 client_tag="OFO999999901")
    second = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, 40, D("44.00"), version_id="v1",
                  client_tag="OFO999999902")
    with pytest.raises(SendRefused, match="exceed what the strategy allows"):
        _sink(book, catalogue, transport=transport).resolve_all((first, second))
    assert transport.calls == []  # the batch is refused before either request reaches the transport


# -- M15: the guard binding-mismatch line in _authorised_orders --------------------------------------------------

def test_guard_binding_mismatch_is_refused(catalogue, eligibility) -> None:
    """AC-5: a preparation whose Strategy Guard decision is bound to a DIFFERENT proposal (forged via the private
    reach-around only) must be refused by ``_authorised_orders``, even though every other check (seal, gate binding,
    allowed_or_refuse, grounded plan) still passes for the real orders. Only reachable through private names, as
    the public path always issues a guard decision bound to the very orders it prepared."""
    book = book_with_three_filled()
    real = _complete(book, catalogue, eligibility)
    assert real.guard is not None

    other_binding = GuardBinding(STRATEGY_ID, "v1", proposal_hash({"forged": "proposal"}))
    forge_decision = getattr(__import__("ofo.strategy.guard", fromlist=["_decision"]), "_decision")
    forged_guard = forge_decision(other_binding, real.guard.change)
    choice, assessment, orders, gate, guard_book, plan_, catalogue_ = (
        real.choice, real.assessment, real.orders, real.gate, real.book, real.plan, real.catalogue)
    discard_preparation(real)  # frees the strategy's one-live-preparation slot for the reach-around below

    prep = Preparation(choice, assessment, orders, gate, real.message, guard_book, STRATEGY_ID, (),
                       forged_guard, plan_, catalogue_, _mint=getattr(partial, "_MINT"))
    getattr(partial, "_GATE_ORDERS")[id(gate)] = (gate, getattr(partial, "_orders_digest")(orders))

    authorised = getattr(partial, "_authorised_orders")
    with pytest.raises(GuardRefused, match="has not checked this exact action"):
        authorised(prep, book, STRATEGY_ID, forged_guard.acknowledgement)


# -- W-056 (REQ-054 AC-3): Zerodha's symbol comes only from the entry's Zerodha row -------------------------------

def test_a_leg_whose_contract_has_no_zerodha_row_is_refused_and_nothing_is_sent(catalogue) -> None:
    """AC-3: with leg-4's catalogue entry stripped of its Zerodha row (contract still listed), the sink refuses the
    order naming the missing row and the transport sees zero calls; no symbol is derived from the contract."""
    (entry,) = [e for e in catalogue.all_entries() if e.has_ref("zerodha")
                and e.ref("zerodha").broker_symbol == CONTRACTS[3]]
    entry.broker_refs.clear()
    book = book_with_three_filled()
    transport = _CountingTransport()
    leg4_order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    with pytest.raises(SendRefused, match="has no zerodha row"):
        _sink(book, catalogue, transport=transport).resolve_all((_tagged(leg4_order),))
    assert transport.calls == []
