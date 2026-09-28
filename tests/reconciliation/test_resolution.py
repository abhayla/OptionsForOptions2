"""REQ-060 AC-5: manual reconciliation is allowed, explicit and audited (ADR-018 Q198: adopt actual broker position,
close/reconcile through a prepared order, mark as requiring attention; no casual ignore), plus broker flat ->
strategy Exited (ADR-019 Q200; deferred issue #19)."""
from __future__ import annotations

import pytest

from ofo.audit.catalogue import EventType
from ofo.engine import Action
from ofo.reconciliation.blocking import blocked_strategy_ids
from ofo.reconciliation.compare import ReconciliationError, compare
from ofo.reconciliation.resolution import (
    ClosingTarget,
    ProposedOrder,
    ResolutionKind,
    adopt_broker_position,
    mark_exited_broker_flat,
    mark_requires_attention,
    prepare_closing_order,
    record_report,
)
from ofo.strategy.versions import OutcomeKind, Position, VersionError
from recon_fixtures import BC23600, BP22800, CONDOR, CONDOR_UNITS, SC23400, SP23000, at, audit_log, clock, executed

# The user closed the 23600 CE hedge in Kite: broker = condor without it.
HEDGE_CLOSED = {BP22800: 75, SP23000: -75, SC23400: -75}


def flagged(broker=None):
    rec = executed()
    audit = audit_log()
    report = compare(HEDGE_CLOSED if broker is None else broker, {"IC-1": rec}, at=at(10), clock=clock)
    record_report(report, {"IC-1": rec}, audit=audit, run_id="run-1")
    assert rec.reconciliation_required
    return rec, audit, len(audit.events)


def test_ac5_adopt_broker_position_audited_and_unblocks():
    """AC-5: adopt -> new active version = broker position; audited with actor, time, reason, before/after."""
    rec, audit, n = flagged()
    res = adopt_broker_position("IC-1", rec, actor="user:abhay", at=at(20), reason="I closed the hedge in Kite",
                                audit=audit)
    assert res.kind is ResolutionKind.ADOPT_BROKER_POSITION and not res.still_blocked
    assert res.before_platform == Position.of(CONDOR_UNITS) and res.before_broker == Position.of(HEDGE_CLOSED)
    assert res.after_platform == Position.of(HEDGE_CLOSED)
    assert rec.active_version.number == 2 and rec.outcomes[-1].kind is OutcomeKind.RECONCILED
    event = audit.events[n]
    assert (event.event_type, event.actor, event.timestamp) == (EventType.RECONCILIATION_RECORDED, "user:abhay", at(20))
    assert event.payload["resolution"] == "adopt actual broker position"
    assert event.payload["reason"] == "I closed the hedge in Kite"
    # Lines are in contract order (underlying, instrument CE before PE, strike); the audit log freezes lists.
    assert event.payload["before_platform"] == (("NIFTY 23400 CE 2026-10-27", -75), ("NIFTY 23600 CE 2026-10-27", 75),
                                                ("NIFTY 22800 PE 2026-10-27", 75), ("NIFTY 23000 PE 2026-10-27", -75))
    assert event.payload["after_platform"] == (("NIFTY 23400 CE 2026-10-27", -75), ("NIFTY 22800 PE 2026-10-27", 75),
                                               ("NIFTY 23000 PE 2026-10-27", -75))
    assert audit.verify().ok
    # The next run agrees with the new active version -> nothing blocked.
    after = compare(HEDGE_CLOSED, {"IC-1": rec}, at=at(21), clock=clock)
    assert after.mismatches == () and blocked_strategy_ids(after, {"IC-1": rec}) == frozenset()


def test_ac5_prepared_order_is_a_proposal_and_keeps_the_block():
    """AC-5: prepared orders (restore the hedge, or close all) are proposals; the strategy stays blocked."""
    rec, audit, n = flagged()
    res = prepare_closing_order("IC-1", rec, actor="user", at=at(20), reason="restore hedge", audit=audit)
    assert res.proposal.orders == (ProposedOrder(Action.BUY, BC23600, 75),)          # 75 - 0
    assert res.still_blocked and rec.reconciliation_required
    flat = prepare_closing_order("IC-1", rec, actor="user", at=at(21), reason="close all", audit=audit,
                                 target=ClosingTarget.FLAT)
    # Closing each broker line: -75 short call -> BUY 75; +75 long put -> SELL 75; -75 short put -> BUY 75.
    assert flat.proposal.orders == (ProposedOrder(Action.BUY, SC23400, 75), ProposedOrder(Action.SELL, BP22800, 75),
                                    ProposedOrder(Action.BUY, SP23000, 75))
    assert audit.events[n].payload["prepared_orders"] == (("BUY", "NIFTY 23600 CE 2026-10-27", 75),)
    assert rec.versions[-1].number == 1                     # nothing placed, no version, nothing changed


def test_ac5_mark_requires_attention_keeps_block_and_is_audited():
    """AC-5: marked as requiring attention -> audited, still blocked."""
    rec, audit, n = flagged()
    res = mark_requires_attention("IC-1", rec, actor="user", at=at(20), reason="checking with Zerodha", audit=audit)
    assert res.still_blocked and rec.reconciliation_required
    assert audit.events[n].payload["resolution"] == "mark as requiring attention"


def test_ac5_broker_flat_exits_the_strategy_issue_19():
    """AC-5 / issue #19: everything closed in Kite -> adopt is refused, exit is allowed, the block is gone."""
    rec, audit, n = flagged(broker={})
    with pytest.raises(ReconciliationError):
        adopt_broker_position("IC-1", rec, actor="user", at=at(20), reason="adopt", audit=audit)
    res = mark_exited_broker_flat("IC-1", rec, actor="user", at=at(21), reason="closed all in Kite", audit=audit)
    assert res.kind is ResolutionKind.BROKER_FLAT_EXITED and rec.exited and not rec.reconciliation_required
    assert res.after_platform == Position() and audit.events[-1].payload["exited"] is True
    assert blocked_strategy_ids(None, {"IC-1": rec}) == frozenset()
    with pytest.raises(VersionError):
        rec.edit(CONDOR, at=at(22))
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, actor="user", at=at(23), reason="again", audit=audit)


def test_ac5_exit_refused_while_the_broker_still_holds_a_position():
    """AC-5 (negative): broker not flat -> exit refused, strategy still blocked."""
    rec, audit, _ = flagged()
    with pytest.raises(ReconciliationError):
        mark_exited_broker_flat("IC-1", rec, actor="user", at=at(20), reason="exit", audit=audit)
    assert not rec.exited and rec.reconciliation_required


@pytest.mark.parametrize("field, value", [("actor", ""), ("reason", ""), ("reason", "   "), ("reason", "x" * 201),
                                          ("actor", None)])
def test_ac5_no_casual_ignore_actor_and_reason_required(field, value):
    """AC-5 (negative): every resolution needs a named actor and a real reason."""
    rec, audit, n = flagged()
    kwargs = dict(actor="user", at=at(20), reason="why", audit=audit) | {field: value}
    for resolve in (adopt_broker_position, prepare_closing_order, mark_requires_attention):
        with pytest.raises(ReconciliationError):
            resolve("IC-1", rec, **kwargs)
    assert len(audit.events) == n and rec.reconciliation_required


def test_ac5_resolution_refused_when_nothing_to_reconcile_or_backdated():
    """AC-5 (negative): no mismatch -> refused; a backdated resolution -> refused by the record's clock order."""
    rec = executed()
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, actor="user", at=at(20), reason="why", audit=audit_log())
    rec2, audit, _ = flagged()
    with pytest.raises(ReconciliationError):
        adopt_broker_position("IC-1", rec2, actor="user", at=at(0), reason="why", audit=audit)
    assert rec2.reconciliation_required
