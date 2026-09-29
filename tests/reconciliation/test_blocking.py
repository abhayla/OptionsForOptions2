"""REQ-060 AC-6: while a mismatch is unresolved, new execution and adjustment execution are blocked (ADR-018 Q199),
and only for the strategy whose contract quantity disagrees (AC-7).

Tier A extras: a seeded property test (stdlib random) over random broker maps, and mutation tests that swap the
allocation rule and the blocking scope for plausible wrong versions and prove the checks here catch each one.
"""
from __future__ import annotations

import random
from decimal import Decimal as D

import pytest

import ofo.reconciliation.compare as compare_module
from ofo.engine import Action, Instrument
from ofo.reconciliation.blocking import blocked_strategy_ids, is_execution_blocked
from ofo.reconciliation.compare import ReconciliationError, compare
from ofo.reconciliation.resolution import adopt_broker_position, record_report
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from recon_fixtures import (
    BC23600, BP22800, CONDOR, CONDOR_UNITS, EXPIRY, SC23400, SP23000, at, audit_log, c, clock, executed, scaled,
)

CE24000 = c(Instrument.CE, "24000")
PE22000 = c(Instrument.PE, "22000")
SHORT_CALL = StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 50),))
LONG_CALL = StrategyDefinition("NIFTY", (DefinitionLeg(Action.BUY, Instrument.CE, D("24000"), EXPIRY, 75),))

# Hand-written platform picture for the property test (independent of the module's own helpers).
UNITS = {
    "IC-1": dict(CONDOR_UNITS),
    "SC-1": {SC23400: -50},
    "LC-1": {CE24000: 75},
}
STANDALONE = {SC23400: -25, PE22000: 50}
UNIVERSE = [BP22800, SP23000, SC23400, BC23600, CE24000, PE22000, c(Instrument.PE, "21000")]


def records():
    return {"IC-1": executed(), "SC-1": executed(SHORT_CALL, "exec-sc"), "LC-1": executed(LONG_CALL, "exec-lc")}


def expected_by_hand() -> dict:
    total = dict(STANDALONE)
    for units in UNITS.values():
        for contract, value in units.items():
            total[contract] = total.get(contract, 0) + value
    return total


def test_ac6_only_the_disagreeing_strategy_is_blocked():
    """AC-6: IC-1's put wing disagrees -> IC-1 blocked; SC-1 and LC-1 (agreeing) are not."""
    recs = records()
    broker = expected_by_hand() | {BP22800: 50}
    report = compare(broker, recs, STANDALONE, at=at(10), clock=clock)
    assert blocked_strategy_ids(report, recs) == frozenset({"IC-1"})
    assert is_execution_blocked("IC-1", report, recs) and not is_execution_blocked("SC-1", report, recs)


def test_ac6_block_persists_on_the_record_until_resolved():
    """AC-6: once recorded, the block holds even with no report; an explicit resolution plus an agreeing run
    lifts it; a stale report still blocks (fail closed until the next run)."""
    recs = records()
    audit = audit_log()
    broker = expected_by_hand() | {BP22800: 50}
    report = compare(broker, recs, STANDALONE, at=at(10), clock=clock)
    record_report(report, recs, audit=audit, run_id="r1")
    assert blocked_strategy_ids(None, recs) == frozenset({"IC-1"})
    adopt_broker_position("IC-1", recs["IC-1"], report=report, actor="user", at=at(11), reason="adopt Kite",
                          audit=audit)
    assert blocked_strategy_ids(report, recs) == frozenset({"IC-1"})          # stale report: still blocked
    fresh = compare(broker, recs, STANDALONE, at=at(12), clock=clock)
    assert fresh.mismatches == () and blocked_strategy_ids(fresh, recs) == frozenset()


def test_ac6_blocked_record_refuses_new_and_adjustment_execution():
    """AC-6: a flagged record refuses proposing an adjustment (edit) and confirming; the gate sees it blocked."""
    recs = records()
    report = compare(expected_by_hand() | {SC23400: -100}, recs, STANDALONE, at=at(10), clock=clock)
    record_report(report, recs, audit=audit_log(), run_id="r1")
    from ofo.strategy.versions import VersionError
    with pytest.raises(VersionError):
        recs["IC-1"].edit(scaled(CONDOR, 150), at=at(11))
    assert blocked_strategy_ids(report, recs) == frozenset({"IC-1", "SC-1"})   # shared contract: both holders


def test_ac6_rejects_bad_gate_input():
    """AC-6 (input domain): wrong report type, non-record values, bad ids -> refused."""
    recs = records()
    with pytest.raises(ReconciliationError):
        blocked_strategy_ids("report", recs)
    with pytest.raises(ReconciliationError):
        blocked_strategy_ids(None, {"IC-1": object()})
    with pytest.raises(ReconciliationError):
        blocked_strategy_ids(None, [("IC-1", recs["IC-1"])])
    with pytest.raises(ReconciliationError):
        is_execution_blocked("", None, recs)


def test_ac6_property_blocked_iff_a_held_contract_disagrees():
    """AC-6/AC-7 property (seeded, 400 random broker maps): a strategy is blocked iff one of its contracts' broker
    units differ from expected (standalone + every strategy's units); unheld contracts block nobody."""
    rng = random.Random(20260929)
    recs = records()
    expected = expected_by_hand()
    blocked_seen = set()
    for _ in range(400):
        broker = {}
        for contract in UNIVERSE:
            base = expected.get(contract, 0)
            broker[contract] = base if rng.random() < 0.6 else base + rng.choice([-150, -75, -25, 25, 75, 150])
        oracle = {sid for sid, units in UNITS.items() if any(broker[k] != expected.get(k, 0) for k in units)}
        report = compare(broker, recs, STANDALONE, at=at(10), clock=clock)
        assert blocked_strategy_ids(report, recs) == oracle, broker
        differing = {k for k in UNIVERSE if broker[k] != expected.get(k, 0)}
        assert {k for m in report.mismatches for k, _ in m.difference} == differing
        blocked_seen |= oracle
    assert blocked_seen == set(UNITS)     # every strategy was blocked at least once, so the property is not vacuous


# ---- mutation tests -------------------------------------------------------------------------------------------

def _scenarios_hold() -> bool:
    """The checks a mutant must fail. True with the real rule."""
    recs = records()
    agree = compare(expected_by_hand(), recs, STANDALONE, at=at(10), clock=clock)
    shared = compare(expected_by_hand() | {SC23400: -100}, recs, STANDALONE, at=at(10), clock=clock)
    other = compare(expected_by_hand() | {BP22800: 50}, recs, STANDALONE, at=at(10), clock=clock)
    unheld = compare(expected_by_hand() | {PE22000: 0}, recs, STANDALONE, at=at(10), clock=clock)
    return (
        agree.mismatches == ()
        and shared.blocked_strategy_ids == frozenset({"IC-1", "SC-1"})
        and other.blocked_strategy_ids == frozenset({"IC-1"})
        and unheld.blocked_strategy_ids == frozenset() and len(unheld.mismatches) == 1
    )


def _expected_first_strategy_only(actives, standalone):
    expected = dict(standalone)
    for units in actives.values():
        for contract, value in units.items():
            expected.setdefault(contract, value)
    return expected


def _expected_last_writer_wins(actives, standalone):
    expected = dict(standalone)
    for units in actives.values():
        expected.update(units)
    return expected


def _holders_everyone(contract, actives, proposals):
    return tuple(sorted(actives))


def _holders_first_only(contract, actives, proposals):
    held = [sid for sid in sorted(actives) if contract in actives[sid]]
    return tuple(held[:1])


def _holders_none(contract, actives, proposals):
    return ()


def _holders_active_only(contract, actives, proposals):
    return tuple(sorted(sid for sid in actives if contract in actives[sid]))


def per_contract(mutant):
    """Lift a one-contract holders rule onto compare's seam ``holders_by_contract(contracts, actives, proposals)``
    (W-037 indexed holders once per run; the mutants keep their one-contract meaning)."""
    return lambda contracts, actives, proposals: {c: mutant(c, actives, proposals) for c in contracts}


def test_ac6_contract_held_only_in_a_pending_proposal_blocks_that_strategy(monkeypatch):
    """AC-6 (mutant M20): the first execution is in flight (no active version); the broker filled the long put only.
    The contract is held only by the pending proposal, so the mismatch is that strategy's partial execution and
    blocks it; a holders rule that ignores proposals would call it unexpected and block nobody."""
    from ofo.reconciliation.compare import MismatchKind
    from ofo.strategy.versions import StrategyRecord
    from recon_fixtures import T0
    rec = StrategyRecord(CONDOR, at=T0, clock=clock)
    rec.propose_execution(at=at(1))
    rec.confirm(1, at=at(2))
    report = compare({BP22800: 75}, {"IC-1": rec}, at=at(10), clock=clock)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.PARTIAL_EXECUTION and m.strategy_ids == ("IC-1",)
    assert m.difference == ((BP22800, 75),) and blocked_strategy_ids(report, {"IC-1": rec}) == frozenset({"IC-1"})
    monkeypatch.setattr(compare_module, "holders_by_contract", per_contract(_holders_active_only))
    mutated = compare({BP22800: 75}, {"IC-1": rec}, at=at(10), clock=clock)
    assert mutated.blocked_strategy_ids == frozenset()          # the mutant is visible: nobody blocked


@pytest.mark.parametrize("name, mutant", [
    ("expected_units", _expected_first_strategy_only),
    ("expected_units", _expected_last_writer_wins),
    ("holders_by_contract", per_contract(_holders_everyone)),
    ("holders_by_contract", per_contract(_holders_first_only)),
    ("holders_by_contract", per_contract(_holders_none)),
])
def test_ac6_mutants_of_allocation_and_blocking_scope_are_caught(monkeypatch, name, mutant):
    """AC-6 mutation: each plausible wrong allocation rule or blocking scope makes the checks fail."""
    assert _scenarios_hold()
    monkeypatch.setattr(compare_module, name, mutant)
    assert not _scenarios_hold()
