"""ADR-096 / REQ-061 AC-2: a held Zerodha position added to an EXISTING strategy, order-free.

Spec basis: ADR-096 "Adding a held position to an existing strategy records the held legs (Zerodha's quantity, average
price as the entry per ADR-084) as a new version of that strategy and prepares NO order for them."; REQ-061 AC-2 "the
user can add it to an existing strategy"; ADR-084 (entry = Zerodha's average price, editable); ADR-019 (an unresolved
reconciliation mismatch blocks).

The core test reads the REAL position row of the owner's order on 2026-10-16 12:20:50 IST (one NIFTY 23650 CE, BUY 65
NRML, average 5.10), copied from the recorded Kite positions reply into tests/fixtures/kite_positions/, and the real
Zerodha instrument list of 2026-10-08 (tests/fixtures/kite_ws/). Symbols are read from the fixtures, never typed here.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from grouping_inputs import (EXP_CONDOR, EXP_SECOND, IN_STRATEGY, LOT, SECOND_EXPIRY_CALL, SENSEX_PUT, audit_log,
                             catalogue as slice_catalogue, key_of, row)
from ofo.audit.catalogue import EventType
from ofo.engine import Action, Instrument
from ofo.instruments import Catalogue, parse_instruments_csv
from ofo.reconciliation.compare import compare
from ofo.reconciliation.grouping import (EntrySource, GroupingError, GroupingSession, ToStrategy, suggest_groups)
from ofo.reconciliation.resolution import record_report
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import (ExecutionResult, OutcomeKind, Position, ResultStatus, StrategyRecord,
                                   VersionError)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
POSITIONS = FIXTURES / "kite_positions" / "positions-2026-10-16-one-ce.json"
INSTRUMENTS = FIXTURES / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T_EXECUTED = datetime.datetime(2026, 10, 16, 10, 0, tzinfo=IST)
T_ADOPT = datetime.datetime(2026, 10, 16, 12, 30, tzinfo=IST)
T_RECON = datetime.datetime(2026, 10, 16, 12, 35, tzinfo=IST)
NOW = datetime.datetime(2026, 10, 16, 13, 0, tzinfo=IST)


def now() -> datetime.datetime:
    return NOW


def real_row() -> dict:
    (only,) = json.loads(POSITIONS.read_text(encoding="utf-8"), parse_float=D)["data"]["net"]
    return only


def real_catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load(parse_instruments_csv(INSTRUMENTS))
    return cat


def contract_of(position) -> tuple:
    return (position.underlying, position.instrument, position.strike, position.expiry)


def executed_record(definition: StrategyDefinition) -> StrategyRecord:
    """A strategy whose version 1 executed completely and reconciled (active, nothing pending)."""
    record = StrategyRecord(definition, at=T_EXECUTED, clock=now)
    version = record.propose_execution(at=T_EXECUTED)
    record.confirm(version.number, at=T_EXECUTED)
    record.apply_result(ExecutionResult(version.number, ResultStatus.COMPLETE, version.intended_position, T_EXECUTED,
                                        "exec-1"))
    assert record.active_version.number == 1 and record.proposed_version is None
    return record


def order_free_violations(record: StrategyRecord, versions_before: int) -> list[str]:
    """Every way an adopt could have prepared an order: a proposal, an unconfirmed version, an execution outcome."""
    problems = []
    if record.proposed_version is not None:
        problems.append("a proposed version is waiting for execution")
    if len(record.versions) != versions_before + 1:
        problems.append(f"expected one new version, got {len(record.versions) - versions_before}")
    if record.active_version is None or record.active_version.number != len(record.versions):
        problems.append("the new version is not the active one")
    if record.outcomes[-1].kind is not OutcomeKind.ADOPTED:
        problems.append(f"last outcome is {record.outcomes[-1].kind}")
    return problems


def real_setup():
    """S-1 holds SELL 65 of the real NIFTY 23650 PE (same expiry as the bought CE); the CE row is the real one."""
    cat, held_row = real_catalogue(), real_row()
    probe = suggest_groups([held_row], {}, cat).groups[0].positions[0]
    pe = DefinitionLeg(Action.SELL, Instrument.PE, probe.strike, probe.expiry, probe.lot_size)
    s1 = StrategyDefinition(probe.underlying, (pe,))
    record = executed_record(s1)
    suggestion = suggest_groups([held_row], {"S-1": s1}, cat)
    log = audit_log()
    session = GroupingSession.start(suggestion, audit=log, clock=now, actor="user-1", session_id="sess-1",
                                    records={"S-1": record})
    return session, record, log, suggestion.groups[0].positions[0]


# ---- the core, on the real row ----------------------------------------------------------------------------------

def test_real_held_ce_joins_existing_strategy_as_new_order_free_version(monkeypatch):
    session, record, log, ce = real_setup()
    assert (ce.net_quantity, ce.average_price, ce.product.value) == (65, D("5.1"), "NRML")
    # Mutation guard: any order-preparing path used by the adopt fails the test outright.
    for name in ("edit", "propose_execution", "confirm", "apply_result"):
        monkeypatch.setattr(StrategyRecord, name, lambda *a, _n=name, **k: pytest.fail(f"adopt called {_n}"))
    session.move(ce.key, ToStrategy("S-1"))
    added = session.confirm_into("S-1", at=T_ADOPT)

    assert order_free_violations(record, 1) == []
    version = record.active_version
    assert (version.number, version.based_on, added.version_number) == (2, 1, 2)
    pe_contract = (ce.underlying, Instrument.PE, ce.strike, ce.expiry)
    assert version.intended_position == Position.of({pe_contract: -65, contract_of(ce): 65})
    assert record.actual_position == version.intended_position and not record.reconciliation_required
    (leg,) = added.legs
    assert (leg.leg.action, leg.leg.quantity, leg.leg.entry_price, leg.entry_source) == (
        Action.BUY, 65, D("5.1"), EntrySource.FROM_ZERODHA)
    assert session.placed_in("S-1") == () and session.groups() == ()


def test_reconciliation_after_adopt_agrees_and_still_detects_a_later_change():
    session, record, log, ce = real_setup()
    session.move(ce.key, ToStrategy("S-1"))
    session.confirm_into("S-1", at=T_ADOPT)
    pe_contract = (ce.underlying, Instrument.PE, ce.strike, ce.expiry)
    broker = {contract_of(ce): real_row()["quantity"], pe_contract: -65}  # the real CE row + S-1's own PE

    report = compare(broker, {"S-1": record}, at=T_RECON, clock=now)
    assert report.mismatches == ()
    record_report(report, {"S-1": record}, audit=log, run_id="run-1")
    assert not record.reconciliation_required

    later = compare({**broker, contract_of(ce): 130}, {"S-1": record}, at=NOW, clock=now)
    (mismatch,) = later.mismatches
    assert mismatch.strategy_ids == ("S-1",) and mismatch.difference == ((contract_of(ce), 65),)


def test_mutation_routing_the_adopt_through_edit_is_caught():
    """Mutation: adopt via ``edit`` (an order-preparing proposal) -> the order-free check reports it."""
    _session, record, _log, ce = real_setup()
    new = StrategyDefinition(ce.underlying, (*record.definition.legs,
                                             DefinitionLeg(Action.BUY, ce.instrument, ce.strike, ce.expiry, 65)))
    record.edit(new, at=T_ADOPT)
    assert "a proposed version is waiting for execution" in order_free_violations(record, 1)


# ---- refusals (slice catalogue) ---------------------------------------------------------------------------------

S1 = StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("23200"), EXP_CONDOR, LOT),))


def slice_session(rows, record, *, strategy_map=None):
    suggestion = suggest_groups(rows, {} if strategy_map is None else strategy_map, slice_catalogue())
    log = audit_log()
    s = GroupingSession.start(suggestion, audit=log, clock=now, actor="user-1", session_id="sess-1",
                              records={"S-1": record})
    return s, log


def refused_reason(log) -> str:
    event = log.events[-1]
    assert event.event_type is EventType.USER_APPROVAL_RECORDED and event.payload["action"] == "add_to_strategy_refused"
    return event.payload["reason"]


def _exited() -> StrategyRecord:
    record = executed_record(S1)
    record.observe_broker_position(Position(), at=T_EXECUTED, reference="flat")
    record.mark_exited(at=T_EXECUTED, actor="u", resolution="closed")
    return record


def _blocked() -> StrategyRecord:
    record = executed_record(S1)
    record.observe_broker_position(Position.of({("NIFTY", Instrument.CE, D("23200"), EXP_CONDOR): -2 * LOT}),
                                   at=T_EXECUTED, reference="moved")
    assert record.reconciliation_required
    return record


def _proposed() -> StrategyRecord:
    record = executed_record(S1)
    record.edit(StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("23200"), EXP_CONDOR,
                                                           2 * LOT),)), at=T_EXECUTED)
    return record


@pytest.mark.parametrize("make", [_exited, _blocked, _proposed, lambda: StrategyRecord(S1, at=T_EXECUTED, clock=now)],
                         ids=["exited", "blocked", "proposed", "never-executed"])
def test_a_strategy_that_cannot_take_a_position_is_refused_and_audited(make):
    record = make()
    versions = len(record.versions)
    s, log = slice_session([row(SECOND_EXPIRY_CALL, -LOT, "120.25")], record)
    s.move(key_of(SECOND_EXPIRY_CALL), ToStrategy("S-1"))
    before = len(log.events)
    with pytest.raises(GroupingError) as err:
        s.confirm_into("S-1", at=T_ADOPT)
    assert err.value.message.code == "RECONCILIATION_MISMATCH_224"
    assert len(log.events) == before + 1 and refused_reason(log) == "grouping_strategy_not_adoptable"
    assert len(record.versions) == versions and [p.tradingsymbol for p in s.placed_in("S-1")] == [SECOND_EXPIRY_CALL]


def test_another_underlying_is_refused_at_the_move_and_audited():
    s, log = slice_session([row(SENSEX_PUT, -20, "310.40", exchange="BFO")], executed_record(S1))
    with pytest.raises(GroupingError) as err:
        s.move(key_of(SENSEX_PUT), ToStrategy("S-1"))
    assert err.value.message is not None and refused_reason(log) == "grouping_move_refused"
    assert s.placed_in("S-1") == ()


def test_unknown_strategy_is_refused_and_audited():
    s, log = slice_session([row(SECOND_EXPIRY_CALL, -LOT, "120.25")], executed_record(S1))
    with pytest.raises(GroupingError):
        s.move(key_of(SECOND_EXPIRY_CALL), ToStrategy("S-404"))
    assert refused_reason(log) == "grouping_choice_unavailable" and log.events[-1].payload["strategy_id"] == "S-404"


@pytest.mark.parametrize("quantity", [LOT, -2 * LOT], ids=["opposite-side", "different-quantity"])
def test_a_contract_the_strategy_already_holds_is_never_netted(quantity):
    """The suggestion was made before S-1 took the contract (empty map), so the row reaches the add step."""
    record = executed_record(S1)
    s, log = slice_session([row(IN_STRATEGY, quantity, "70.00")], record)
    s.move(key_of(IN_STRATEGY), ToStrategy("S-1"))
    with pytest.raises(GroupingError) as err:
        s.confirm_into("S-1", at=T_ADOPT)
    assert err.value.message.code == "RECONCILIATION_MISMATCH_225"
    assert refused_reason(log) == "grouping_strategy_holds_contract" and len(record.versions) == 1
    held = Position.of({("NIFTY", Instrument.CE, D("23200"), EXP_CONDOR): quantity})
    with pytest.raises(VersionError, match="never netted"):
        record.adopt_held(held, at=T_ADOPT, actor="u")


def test_two_rows_of_one_contract_are_refused_not_summed():
    record = executed_record(S1)
    s, log = slice_session([row(SECOND_EXPIRY_CALL, -LOT, "120.25", "NRML"),
                            row(SECOND_EXPIRY_CALL, -LOT, "121.00", "MIS")], record)
    s.move(key_of(SECOND_EXPIRY_CALL, "NRML"), ToStrategy("S-1"))
    s.move(key_of(SECOND_EXPIRY_CALL, "MIS"), ToStrategy("S-1"))
    with pytest.raises(GroupingError):
        s.confirm_into("S-1", at=T_ADOPT)
    assert refused_reason(log) == "grouping_strategy_holds_contract" and len(record.versions) == 1


def test_half_adoption_is_impossible_one_bad_row_refuses_all():
    record = executed_record(S1)
    s, log = slice_session([row(SECOND_EXPIRY_CALL, -LOT, "120.25"), row(IN_STRATEGY, LOT, "70.00")], record)
    s.move(key_of(SECOND_EXPIRY_CALL), ToStrategy("S-1"))
    s.move(key_of(IN_STRATEGY), ToStrategy("S-1"))
    with pytest.raises(GroupingError):
        s.confirm_into("S-1", at=T_ADOPT)
    assert len(record.versions) == 1 and record.actual_position == record.active_version.intended_position
    assert {p.tradingsymbol for p in s.placed_in("S-1")} == {SECOND_EXPIRY_CALL, IN_STRATEGY}
    assert not any(e.payload.get("action") == "add_to_strategy" for e in log.events)


def test_average_finer_than_paise_asks_for_an_entry_and_never_rounds():
    record = executed_record(S1)
    s, log = slice_session([row(SECOND_EXPIRY_CALL, -LOT, "120.255")], record)
    s.move(key_of(SECOND_EXPIRY_CALL), ToStrategy("S-1"))
    with pytest.raises(GroupingError):
        s.confirm_into("S-1", at=T_ADOPT)
    assert refused_reason(log) == "grouping_entry_needed" and len(record.versions) == 1
    s.set_entry(key_of(SECOND_EXPIRY_CALL), D("120.26"))
    (leg,) = s.confirm_into("S-1", at=T_ADOPT).legs
    assert (leg.leg.entry_price, leg.entry_source) == (D("120.26"), EntrySource.EDITED)
    assert isinstance(leg.leg.entry_price, D)


def test_success_writes_one_add_to_strategy_entry_with_version_and_entries():
    record = executed_record(S1)
    s, log = slice_session([row(SECOND_EXPIRY_CALL, -LOT, "120.25")], record)
    s.move(key_of(SECOND_EXPIRY_CALL), ToStrategy("S-1"))
    before = len(log.events)
    s.confirm_into("S-1", at=T_ADOPT)
    assert len(log.events) == before + 1
    event = log.events[-1]
    assert event.event_type is EventType.STRATEGY_CHANGED
    assert (event.payload["action"], event.payload["strategy_id"], event.payload["version"]) == (
        "add_to_strategy", "S-1", 2)
    assert [dict(leg) for leg in event.payload["legs"]] == [{"position": SECOND_EXPIRY_CALL, "entry_price": "120.25",
                                      "entry_source": "from_zerodha", "product": "NRML"}]
    assert record.active_version.intended_position.as_dict()[("NIFTY", Instrument.CE, D("24050"), EXP_SECOND)] == -LOT
    assert log.verify().ok
