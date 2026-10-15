"""REQ-061 AC-4 (W-083, ADR-084): "The grouping logic is explicit and auditable (every grouping decision recorded)."

Every action (suggest, move, standalone, set_entry, confirm, confirm_existing) appends exactly ONE entry through the
audit log's public ``append``; a refused action appends nothing; the chain still verifies.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from grouping_inputs import (EXP_CONDOR, EXP_SECOND, IN_STRATEGY, SECOND_EXPIRY_CALL, SENSEX_PUT, SPOTS, audit_log,
                             catalogue, clock, key_of, seven_rows, strategies, templates)
from ofo.audit import EventType
from ofo.reconciliation.grouping import (STANDALONE, GroupingError, GroupingSession, ToGroup, ToStrategy,
                                         suggest_groups)

CONDOR_GROUP = f"NIFTY:{EXP_CONDOR}"
CALL = "NIFTY26O0623400CE"


def started():
    log = audit_log()
    suggestion = suggest_groups(seven_rows(), strategies(), catalogue(), templates=templates(), spots=SPOTS)
    s = GroupingSession.start(suggestion, audit=log, clock=clock, actor="user-1", session_id="sess-1",
                              strategies=strategies())
    return s, log


def test_start_records_one_suggest_entry_listing_groups_and_resemblance():
    s, log = started()
    (event,) = log.events
    assert event.event_type is EventType.RECONCILIATION_RECORDED and event.actor == "user-1"
    assert event.correlation_id == "sess-1" and event.timestamp == clock()
    payload = event.payload
    assert payload["action"] == "suggest"
    assert {g["id"]: g["resembles"] for g in payload["groups"]}[CONDOR_GROUP] == "Iron Condor"
    assert IN_STRATEGY not in str(payload)


def test_move_and_standalone_each_write_one_entry_naming_position_from_and_to():
    s, log = started()
    s.move(key_of(SECOND_EXPIRY_CALL), ToGroup(CONDOR_GROUP))
    s.move(key_of(SENSEX_PUT), STANDALONE)
    moves = [e.payload for e in log.events[1:]]
    assert len(log.events) == 3
    assert [(m["action"], m["position"], m["from"], m["to"]) for m in moves] == [
        ("move", SECOND_EXPIRY_CALL, f"group:NIFTY:{EXP_SECOND}", f"group:{CONDOR_GROUP}"),
        ("standalone", SENSEX_PUT, "group:SENSEX:2026-10-01", "standalone"),
    ]
    assert all(e.event_type is EventType.USER_APPROVAL_RECORDED for e in log.events[1:])


def test_set_entry_writes_one_entry_with_old_and_new_price():
    s, log = started()
    s.set_entry(key_of(CALL), D("95.05"))
    payload = log.events[-1].payload
    assert len(log.events) == 2
    assert (payload["action"], payload["position"], payload["old_price"], payload["new_price"]) == (
        "set_entry", CALL, "91.50", "95.05")


def test_confirm_writes_one_entry_with_prices_sources_and_products():
    s, log = started()
    s.set_entry(key_of(CALL), D("95.05"))
    s.confirm(CONDOR_GROUP, strategy_id="S-C")
    event = log.events[-1]
    assert len(log.events) == 3 and event.event_type is EventType.STRATEGY_CHANGED
    legs = {leg["position"]: leg for leg in event.payload["legs"]}
    assert legs[CALL]["entry_price"] == "95.05" and legs[CALL]["entry_source"] == "edited"
    assert legs["NIFTY26O0623000PE"]["entry_source"] == "from_zerodha" and legs["NIFTY26O0623000PE"]["product"] == "MIS"
    assert event.payload["strategy_id"] == "S-C" and event.payload["resembles"] == "Iron Condor"


def test_move_into_an_existing_strategy_is_refused_and_not_audited():
    s, log = started()
    with pytest.raises(GroupingError):
        s.move(key_of(SECOND_EXPIRY_CALL), ToStrategy("S-1"))
    assert len(log.events) == 1


def test_audit_entries_name_the_product_so_two_rows_of_one_contract_are_distinct():
    log = audit_log()
    from grouping_inputs import row
    suggestion = suggest_groups([row(CALL, -65, "80.00", "NRML"), row(CALL, -65, "86.00", "MIS")], {}, catalogue(),
                                templates=templates(), spots=SPOTS)
    s = GroupingSession.start(suggestion, audit=log, clock=clock, actor="u", session_id="x")
    s.set_entry(key_of(CALL, "MIS"), D("87.00"))
    s.move(key_of(CALL, "NRML"), STANDALONE)
    set_entry, move = (e.payload for e in log.events[1:])
    assert (set_entry["product"], set_entry["old_price"], set_entry["new_price"]) == ("MIS", "86.00", "87.00")
    assert (move["product"], move["action"]) == ("NRML", "standalone")


def test_a_refused_action_appends_nothing_and_changes_nothing():
    s, log = started()
    before = len(log.events)
    refusals = [
        lambda: s.move(key_of(SENSEX_PUT), ToGroup(CONDOR_GROUP)),
        lambda: s.move(key_of(IN_STRATEGY), STANDALONE),
        lambda: s.move(key_of(CALL), ToStrategy("S-1")),
        lambda: s.set_entry(key_of(CALL), D("0")),
        lambda: s.set_entry(key_of(CALL), 91.5),
        lambda: s.confirm("NIFTY:2000-01-01", strategy_id="S-C"),
        lambda: s.confirm(CONDOR_GROUP, strategy_id="S-1"),
    ]
    for refusal in refusals:
        with pytest.raises(GroupingError):
            refusal()
    assert len(log.events) == before and s.adopted == ()
    assert s.entry_of(next(p for p in next(g for g in s.groups() if g.id == CONDOR_GROUP).positions if p.tradingsymbol == CALL))[0] == D("91.50")


def test_the_audit_chain_verifies_after_a_whole_session():
    s, log = started()
    s.move(key_of(SENSEX_PUT), STANDALONE)
    s.set_entry(key_of(CALL), D("95.05"))
    s.confirm(CONDOR_GROUP, strategy_id="S-C")
    assert log.verify().ok and len(log.events) == 4


def test_the_session_writes_only_through_the_public_append():
    """A forged audit entry is impossible: the module touches the log only through ``AuditLog.append``."""
    import inspect

    import ofo.reconciliation.grouping as grouping

    source = inspect.getsource(grouping)
    assert "._events" not in source and "AuditEvent(" not in source
    assert source.count("self._audit.append(") == 1


def test_the_clock_seam_is_used_not_the_wall_clock():
    import inspect

    import ofo.reconciliation.grouping as grouping

    source = inspect.getsource(grouping)
    assert "datetime.now" not in source and "utcnow" not in source and "time.time" not in source
