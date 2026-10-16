"""ADR-096 round 2 (Tier A MAJOR): a leg that enters a strategy WITHOUT a platform fill is in the order book's ledger.

Class: every leg adopted from a held Zerodha position - added to an existing strategy (``confirm_into``) or opened as a
new strategy (W-083 ``confirm`` + ``open_adopted``). Before: the ledger held 0 for every adopted leg, so Complete saw
room for a second BUY (planned 65 - held 0), Close saw no room (held 0: no working exit, finding
``state-with-no-working-exit``), and a broker 0 looked like a "missing leg". After: the ledger holds exactly the adopted
units as an adopted holding (no platform order id invented).

Real input: the owner's NIFTY 23650 CE row of 2026-10-16 (BUY 65 NRML, average 5.10) and the real 2026-10-08
instrument list. The PE leg of the existing strategy is the real catalogue PE at the same strike and expiry.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from test_adopt_into_existing import (T_ADOPT, T_EXECUTED, audit_log, now, real_catalogue, real_row)
from ofo.engine import Action, Instrument, Leg
from ofo.execution.partial import _position_mismatches
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.send_guard import SendRefused, allowed_or_refuse
from ofo.instruments.models import ZERODHA
from ofo.orders.model import Order, OrderBook
from ofo.reconciliation.grouping import GroupingSession, ToStrategy, open_adopted, suggest_groups
from ofo.reconciliation.positions import BrokerPositionLine

UNITS = 65  # one NIFTY lot: the real row's quantity


def pe_row(cat, ce: dict) -> dict:
    """The real catalogue PE at the CE's strike and expiry, held SELL 65 (the existing strategy's leg)."""
    (ce_entry,) = [e for e in cat.all_entries() if e.broker_refs.get(ZERODHA) is not None
                   and e.broker_refs[ZERODHA].broker_token == str(ce["instrument_token"])]
    (pe_entry,) = [e for e in cat.all_entries() if e.contract.name == ce_entry.contract.name
                   and e.contract.expiry == ce_entry.contract.expiry and e.contract.strike == ce_entry.contract.strike
                   and e.contract.instrument_type == "PE"]
    ref = pe_entry.broker_refs[ZERODHA]
    return {**ce, "tradingsymbol": ref.broker_symbol, "instrument_token": int(ref.broker_token), "quantity": -65,
            "average_price": D("7.00")}


def create_new(book: OrderBook, rows, strategy_id: str):
    cat = real_catalogue()
    suggestion = suggest_groups(rows, {}, cat)
    s = GroupingSession.start(suggestion, audit=audit_log(), clock=now, actor="user-1", session_id="new")
    adopted = s.confirm(suggestion.groups[0].id, strategy_id=strategy_id)
    return adopted, open_adopted(adopted, book=book, at=T_EXECUTED, clock=now, actor="user-1")


def both_paths():
    """S-1 opened from the held PE (create-new), then the real held CE added to it (add-to-existing)."""
    cat, ce = real_catalogue(), real_row()
    pe = pe_row(cat, ce)
    book = OrderBook(clock=now)
    _adopted, record = create_new(book, [pe], "S-1")
    suggestion = suggest_groups([pe, ce], {"S-1": record.definition}, cat)
    s = GroupingSession.start(suggestion, audit=audit_log(), clock=now, actor="user-1", session_id="add",
                              records={"S-1": record}, book=book)
    (position,) = suggestion.groups[0].positions
    s.move(position.key, ToStrategy("S-1"))
    s.confirm_into("S-1", at=T_ADOPT)
    return book, record, ce["tradingsymbol"], pe["tradingsymbol"]


def plan_of(record, ce_symbol: str, pe_symbol: str) -> ExecutionPlan:
    by_kind = {leg.instrument: leg for leg in record.definition.legs}
    legs = []
    for ref, symbol, kind in (("L1", pe_symbol, Instrument.PE), ("L2", ce_symbol, Instrument.CE)):
        d = by_kind[kind]
        legs.append(PlannedLeg(ref, symbol, Leg(d.action, d.instrument, d.strike, d.expiry, d.quantity, D("1"))))
    return ExecutionPlan("S-1", tuple(legs))


def order(record, symbol: str, side: Action, units: int, leg_ref: str) -> Order:
    return Order("S-1", leg_ref, symbol, side, units, D("5.10"), version_id=f"v{record.active_version.number}")


def ledger_violations(book, record, ce, pe) -> list[str]:
    problems = []
    if book.position("S-1", ce) != UNITS or book.position("S-1", pe) != -UNITS:
        problems.append(f"ledger CE={book.position('S-1', ce)} PE={book.position('S-1', pe)}")
    planned = {pe: ("L1", Action.SELL, 65), ce: ("L2", Action.BUY, 65)}
    version = record.active_version
    try:
        allowed_or_refuse(choice="complete", orders=[order(record, ce, Action.BUY, 65, "L2")], version=version,
                          planned=planned, book=book, strategy_id="S-1")
        problems.append("complete allowed a second BUY 65 of the adopted CE")
    except SendRefused:
        pass
    try:
        allowed_or_refuse(choice="close", orders=[order(record, ce, Action.SELL, 65, "L2")], version=version,
                          planned=planned, book=book, strategy_id="S-1")
    except SendRefused as exc:
        problems.append(f"close of the adopted CE refused: {exc}")
    return problems


def test_both_adopt_paths_write_the_adopted_units_into_the_ledger():
    book, record, ce, pe = both_paths()
    assert ledger_violations(book, record, ce, pe) == []
    planned = {pe: ("L1", Action.SELL, 65), ce: ("L2", Action.BUY, 65)}
    with pytest.raises(SendRefused) as err:
        allowed_or_refuse(choice="close", orders=[order(record, ce, Action.SELL, 130, "L2")],
                          version=record.active_version, planned=planned, book=book, strategy_id="S-1")
    assert "65 units remain" in str(err.value)


def test_complete_room_is_zero_for_the_adopted_contract():
    book, record, ce, _pe = both_paths()
    with pytest.raises(SendRefused) as err:
        allowed_or_refuse(choice="complete", orders=[order(record, ce, Action.BUY, 65, "L2")],
                          version=record.active_version, planned={ce: ("L2", Action.BUY, 65)}, book=book,
                          strategy_id="S-1")
    assert "0 units remain" in str(err.value)


def test_create_new_alone_puts_the_real_ce_in_the_ledger():
    book = OrderBook(clock=now)
    ce = real_row()
    _adopted, record = create_new(book, [ce], "S-N")
    assert book.position("S-N", ce["tradingsymbol"]) == UNITS and book.record_for("S-N") is record
    assert record.active_version.number == 1 and record.proposed_version is None
    assert record.actual_position == record.active_version.intended_position
    assert book.views_for("S-N") == ()  # no order was registered, none invented


def test_partial_assessment_agrees_with_zerodha_and_a_flat_broker_is_a_mismatch_not_a_missing_leg():
    book, record, ce, pe = both_paths()
    plan = plan_of(record, ce, pe)
    held = [BrokerPositionLine(ce, 65, D("5.10")), BrokerPositionLine(pe, -65, D("7.00"))]
    assert _position_mismatches(plan, held, book) == []
    flat = [BrokerPositionLine(ce, 0, D("5.10")), BrokerPositionLine(pe, -65, D("7.00"))]
    (mismatch,) = _position_mismatches(plan, flat, book)
    assert "ledger" in mismatch.lower() or "fills" in mismatch.lower() or "record" in mismatch.lower(), mismatch


def test_mutation_dropping_the_ledger_write_is_caught(monkeypatch):
    monkeypatch.setattr(OrderBook, "record_adopted", lambda self, holdings: None)
    book, record, ce, pe = both_paths()
    assert ledger_violations(book, record, ce, pe) != []
    assert _position_mismatches(plan_of(record, ce, pe), [BrokerPositionLine(ce, 65, D("5.10")),
                                                          BrokerPositionLine(pe, -65, D("7.00"))], book) != []
