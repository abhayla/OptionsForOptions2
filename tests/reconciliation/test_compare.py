"""REQ-060 AC-2 and AC-3: compare detects each mismatch kind and records time, broker state, platform state,
difference and the required next action.

Core proof (W-021): the golden Iron Condor is the active version; the broker also holds a recorded standalone 25
units on the sold 23400 CE, and the put wing (BUY 22800 PE) shows 50 instead of 75. Exactly one mismatch, on that
strategy, difference -25. Expected values are hand-computed from the leg list in recon_fixtures.py.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import STANDALONE, MismatchKind, ReconciliationError, compare
from ofo.strategy.definition import DefinitionLeg
from ofo.strategy.versions import Position
from recon_fixtures import (
    BC23600, BP22800, CONDOR, CONDOR_UNITS, EXPIRY, NEXT_EXPIRY, SC23400, SP23000, at, c, clock, executed, scaled,
    single_leg, with_legs,
)


def run(broker, strategies, standalone=None, **kw):
    return compare(broker, strategies, standalone, at=at(10), clock=clock, **kw)


def test_core_golden_condor_one_wrong_wing_one_mismatch_standalone_not_a_mismatch():
    """AC-2: core proof. Condor active; broker = condor + standalone -25 on 23400 CE, put wing 50 not 75."""
    broker = {BP22800: 50, SP23000: -75, SC23400: -100, BC23600: 75}
    report = run(broker, {"IC-1": executed()}, {SC23400: -25})
    assert len(report.mismatches) == 1
    m = report.mismatches[0]
    assert m.kind is MismatchKind.QUANTITY_MISMATCH
    assert m.strategy_ids == ("IC-1",)
    assert m.difference == ((BP22800, -25),)        # 50 - 75
    assert m.broker_state == ((BP22800, 50),)
    assert m.platform_state == ((BP22800, 75),)
    assert report.blocked_strategy_ids == frozenset({"IC-1"})
    # The strategy's broker share on the put wing is 50; every other leg is the active version's.
    assert report.share("IC-1").as_dict() == {BP22800: 50, SP23000: -75, SC23400: -75, BC23600: 75}


def test_ac3_mismatch_records_time_broker_platform_difference_and_next_action():
    """AC-3: every field of the record, including the per-holder platform breakdown."""
    broker = {BP22800: 75, SP23000: -75, SC23400: -50, BC23600: 75}
    report = run(broker, {"IC-1": executed()}, {SC23400: -25})
    (m,) = report.mismatches
    assert m.at == at(10)
    assert m.broker_state == ((SC23400, -50),)
    assert m.platform_state == ((SC23400, -100),)    # -75 strategy + -25 standalone
    assert m.platform_breakdown == ((STANDALONE, SC23400, -25), ("IC-1", SC23400, -75))
    assert m.difference == ((SC23400, 50),)
    assert m.next_action.startswith("Reconcile this strategy: adopt the broker position")
    assert "you should" not in m.next_action.lower()


def test_ac3_mismatches_that_block_nothing_are_still_recorded_in_the_audit_log():
    """AC-3 (mutant M11): an unexpected position on an unheld contract and a changed standalone block no strategy,
    but each is recorded with time, broker state, platform state, difference and next action."""
    from ofo.audit.catalogue import EventType
    from ofo.reconciliation.resolution import record_report
    from recon_fixtures import audit_log
    extra, alone = c(Instrument.CE, "24000"), c(Instrument.PE, "22000")
    rec = executed()
    report = run(dict(CONDOR_UNITS) | {extra: 75, alone: 25}, {"IC-1": rec}, {alone: 50})
    assert report.blocked_strategy_ids == frozenset()
    audit = audit_log()
    record_report(report, {"IC-1": rec}, audit=audit, run_id="run-1")
    assert not rec.reconciliation_required
    by_kind = {e.payload["kind"]: e for e in audit.events}
    assert set(by_kind) == {"unexpected broker position", "standalone position changed"}
    unexpected = by_kind["unexpected broker position"]
    assert unexpected.event_type is EventType.RECONCILIATION_RECORDED and unexpected.timestamp == at(10)
    assert unexpected.payload["strategy_ids"] == ()
    assert unexpected.payload["broker_state"] == (("NIFTY 24000 CE 2026-10-27", 75),)
    assert unexpected.payload["platform_state"] == (("NIFTY 24000 CE 2026-10-27", 0),)
    assert unexpected.payload["difference"] == (("NIFTY 24000 CE 2026-10-27", 75),)
    assert unexpected.payload["next_action"].startswith("Choose how to group it")
    changed = by_kind["standalone position changed"]
    assert changed.payload["strategy_ids"] == ()
    assert changed.payload["broker_state"] == (("NIFTY 22000 PE 2026-10-27", 25),)
    assert changed.payload["platform_state"] == (("NIFTY 22000 PE 2026-10-27", 50),)
    assert changed.payload["difference"] == (("NIFTY 22000 PE 2026-10-27", -25),)       # 25 - 50
    assert changed.payload["next_action"].startswith("Review the standalone position")


def test_ac2_agreement_is_no_mismatch():
    """AC-2 (negative): broker equals strategy + standalone on every contract -> nothing reported, nothing blocked."""
    broker = dict(CONDOR_UNITS)
    broker[SC23400] = -100
    report = run(broker, {"IC-1": executed()}, {SC23400: -25})
    assert report.mismatches == () and report.blocked_strategy_ids == frozenset()


def test_ac2_missing_platform_position():
    """AC-2: the strategy holds the 23600 CE; the broker shows none of it."""
    broker = {BP22800: 75, SP23000: -75, SC23400: -75}
    (m,) = run(broker, {"IC-1": executed()}).mismatches
    assert m.kind is MismatchKind.MISSING_PLATFORM_POSITION and m.difference == ((BC23600, -75),)
    assert m.strategy_ids == ("IC-1",)


def test_ac2_unexpected_broker_position_blocks_no_strategy():
    """AC-2/AC-7: a 24000 CE in no strategy and not recorded standalone -> grouping choice, blocks none."""
    extra = c(Instrument.CE, "24000")
    broker = dict(CONDOR_UNITS) | {extra: 75}
    (m,) = run(broker, {"IC-1": executed()}).mismatches
    assert m.kind is MismatchKind.UNEXPECTED_BROKER_POSITION
    assert m.strategy_ids == () and not m.blocks
    assert m.next_action.startswith("Choose how to group it")


def test_ac2_side_mismatch():
    """AC-2: strategy SELLs the 23000 PE (-75); broker is long +75 on it."""
    broker = dict(CONDOR_UNITS) | {SP23000: 75}
    (m,) = run(broker, {"IC-1": executed()}).mismatches
    assert m.kind is MismatchKind.SIDE_MISMATCH and m.difference == ((SP23000, 150),)


def test_ac2_strike_mismatch_pairs_the_moved_leg():
    """AC-2: short call moved in Kite from 23400 to 23500 (same expiry, same units) -> ONE strike mismatch."""
    moved = c(Instrument.CE, "23500")
    broker = {BP22800: 75, SP23000: -75, moved: -75, BC23600: 75}
    (m,) = run(broker, {"IC-1": executed()}).mismatches
    assert m.kind is MismatchKind.STRIKE_MISMATCH and m.strategy_ids == ("IC-1",)
    assert m.difference == ((SC23400, 75), (moved, -75))
    assert run(broker, {"IC-1": executed()}).share("IC-1").as_dict() == {
        BP22800: 75, SP23000: -75, moved: -75, BC23600: 75}


def test_ac2_expiry_mismatch_pairs_the_rolled_leg():
    """AC-2: short call rolled in Kite to the next expiry, same strike -> ONE expiry mismatch."""
    rolled = c(Instrument.CE, "23400", NEXT_EXPIRY)
    broker = {BP22800: 75, SP23000: -75, rolled: -75, BC23600: 75}
    (m,) = run(broker, {"IC-1": executed()}).mismatches
    assert m.kind is MismatchKind.EXPIRY_MISMATCH and m.difference == ((SC23400, 75), (rolled, -75))


def test_ac2_ambiguous_move_is_not_paired():
    """AC-2 (negative): two candidate strikes with the same units -> no pairing; the extras block no strategy."""
    a, b = c(Instrument.CE, "23500"), c(Instrument.CE, "23300")
    broker = {BP22800: 75, SP23000: -75, a: -75, b: -75, BC23600: 75}
    kinds = sorted((m.kind.value, m.strategy_ids) for m in run(broker, {"IC-1": executed()}).mismatches)
    assert kinds == [("missing platform position", ("IC-1",)), ("unexpected broker position", ()),
                     ("unexpected broker position", ())]


def test_ac2_partially_executed_strategy():
    """AC-2: v2 (2 lots) in flight; the broker filled the extra lot on the put wing only -> partial execution."""
    rec = executed()
    rec.edit(scaled(CONDOR, 150), at=at(4), reason="add a lot")
    rec.confirm(2, at=at(5))
    broker = dict(CONDOR_UNITS) | {BP22800: 150}
    (m,) = run(broker, {"IC-1": rec}).mismatches
    assert m.kind is MismatchKind.PARTIAL_EXECUTION and m.difference == ((BP22800, 75),)
    assert m.next_action.startswith("Partially executed: Complete Strategy")
    # Overfill beyond the proposal (225 > 150) is outside the path: a quantity mismatch, not a partial.
    (over,) = run(dict(CONDOR_UNITS) | {BP22800: 225}, {"IC-1": rec}).mismatches
    assert over.kind is MismatchKind.QUANTITY_MISMATCH


def test_ac2_external_modification_kind():
    """AC-2/AC-4: a strategy-contract difference with an unexplained broker change is an external modification."""
    broker = dict(CONDOR_UNITS) | {SC23400: -25}
    (m,) = run(broker, {"IC-1": executed()}, external={SC23400: 50}).mismatches
    assert m.kind is MismatchKind.EXTERNAL_MODIFICATION and m.difference == ((SC23400, 50),)


def test_ac2_standalone_changed_blocks_nothing():
    """AC-7 via AC-2: the recorded standalone 24000 CE was closed in Kite -> recorded, blocks no strategy."""
    extra = c(Instrument.CE, "24000")
    (m,) = run(dict(CONDOR_UNITS), {"IC-1": executed()}, {extra: 50}).mismatches
    assert m.kind is MismatchKind.STANDALONE_CHANGED and m.strategy_ids == () and m.difference == ((extra, -50),)


def test_ac2_shared_contract_blocks_every_holder_fail_closed():
    """AC-2 allocation rule: two strategies hold the 23400 CE; the broker disagrees -> both blocked."""
    short_call = executed(with_legs(CONDOR, [DefinitionLeg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 50)]),
                          "exec-sc")
    broker = dict(CONDOR_UNITS) | {SC23400: -100}   # expected -125
    report = run(broker, {"IC-1": executed(), "SC-1": short_call})
    (m,) = report.mismatches
    assert m.strategy_ids == ("IC-1", "SC-1") and m.difference == ((SC23400, 25),)
    assert report.share("IC-1").as_dict()[SC23400] == -50    # -100 - (-50 held by SC-1)
    assert report.share("SC-1").as_dict() == {SC23400: -25}  # -100 - (-75 held by IC-1)


@pytest.mark.parametrize("bad", [
    {("NIFTY", Instrument.CE, 23400, EXPIRY): -75},                     # strike not a Decimal
    {("BANKNIFTY", Instrument.CE, D("23400"), EXPIRY): -75},            # unsupported underlying
    {SC23400: 1.5},                                                     # float units
    {SC23400: True},                                                    # bool units
    {SC23400: 10**9},                                                   # absurd size
    [(SC23400, -75)],                                                   # not a mapping
])
def test_ac2_rejects_invalid_broker_input(bad):
    """AC-2 (input domain): malformed broker maps are refused, never defaulted."""
    with pytest.raises(ReconciliationError):
        run(bad, {"IC-1": executed()})


def test_ac2_rejects_bad_time_ids_and_sizes():
    """AC-3 (input domain): naive or future timestamps, bad ids, duplicate records and absurd sizes are refused."""
    rec = executed()
    with pytest.raises(ReconciliationError):
        compare({}, {"IC-1": rec}, at=datetime.datetime(2026, 10, 1, 9, 30), clock=clock)
    with pytest.raises(ReconciliationError):
        compare({}, {"IC-1": rec}, at=at(60 * 24 * 3), clock=clock)
    for bad_id in ("", "  ", STANDALONE, "x" * 201, 7):
        with pytest.raises(ReconciliationError):
            run({}, {bad_id: rec})
    with pytest.raises(ReconciliationError):
        run({}, {"A": rec, "B": rec})
    with pytest.raises(ReconciliationError):
        run({c(Instrument.CE, str(20000 + i)): 1 for i in range(1001)}, {})
    with pytest.raises(ReconciliationError):
        run({}, {"IC-1": "not a record"})


def test_ac2_exited_strategy_expects_nothing():
    """AC-2: an exited strategy's old legs are not expected; a leftover broker position is unexpected."""
    rec = executed()
    rec.observe_broker_position(Position(), at=at(5), reference="flat")
    rec.mark_exited(at=at(6), actor="user", resolution="closed everything in Kite")
    (m,) = run({SC23400: -75}, {"IC-1": rec}).mismatches
    assert m.kind is MismatchKind.UNEXPECTED_BROKER_POSITION and m.strategy_ids == ()


def test_ac2_large_account_is_fast():
    """AC-2: 1,000 broker contracts and 200 strategies compare with linear work in the contracts: doubling the
    contracts (against 10 strategies) at most doubles the calls made (no quadratic blow-up per contract; work is
    counted, not timed). Work also grows with the number of strategies holding a mismatched contract (each strategy is
    checked against each owner list), which the spec's account sizes keep small; that is not asserted here."""
    from work_count import assert_linear

    def compare_at(contracts: int, strategy_count: int):
        broker = {c(Instrument.CE, str(20000 + i)): -1 for i in range(contracts)}
        strategies = {f"S{i}": executed(reference=f"e{i}") for i in range(strategy_count)}
        return lambda: run(broker, strategies)

    assert_linear(lambda n: compare_at(n, 10), 500)
    report = compare_at(1000, 200)()
    assert len(report.mismatches) == 1004     # 1000 unexpected + 4 condor contracts (200 x 75 expected, 0 held)


def test_ac2_strike_move_to_a_lower_strike_still_blocks_the_holder():
    """AC-2 regression (found by the AC-6 property test): the long put moved in Kite from 22800 to 21000. The
    unheld 21000 PE sorts BEFORE the held 22800 PE; the pair must still be attributed to, and block, IC-1."""
    lower = c(Instrument.PE, "21000")
    broker = {lower: 75, SP23000: -75, SC23400: -75, BC23600: 75}
    report = run(broker, {"IC-1": executed()})
    (m,) = report.mismatches
    assert m.kind is MismatchKind.STRIKE_MISMATCH and m.strategy_ids == ("IC-1",)
    assert m.difference == ((lower, 75), (BP22800, -75))
    assert report.blocked_strategy_ids == frozenset({"IC-1"})


def test_ac2_share_of_a_strategy_the_run_did_not_cover_is_refused():
    """AC-2 (W-037 indexed ``share``): only a covered strategy has a share; an exited one, an unknown id and a
    non-string id are refused with ReconciliationError, never answered from another strategy or a stale index."""
    import dataclasses

    gone = executed(reference="e-gone")
    gone.observe_broker_position(Position(), at=at(5), reference="flat")
    gone.mark_exited(at=at(6), actor="user", resolution="closed in Kite")
    report = run(dict(CONDOR_UNITS), {"IC-1": executed(), "GONE": gone})
    assert report.covered_strategy_ids == frozenset({"IC-1"})
    assert report.share("IC-1").as_dict() == CONDOR_UNITS
    for bad in ("GONE", "IC-2", ["IC-1"], None):
        with pytest.raises(ReconciliationError, match="not covered"):
            report.share(bad)
    # A report rebuilt with other shares answers from ITS shares, not the original's.
    flat = dataclasses.replace(report, shares=(("IC-9", Position()),))
    assert flat.share("IC-9") == Position()
    with pytest.raises(ReconciliationError, match="not covered"):
        flat.share("IC-1")


def _all_mismatched(strategy_count: int, shared: bool):
    """``strategy_count`` executed strategies, zero broker contracts, so every strategy is mismatched. ``shared``:
    every strategy is the golden condor (4 contracts, each held by all of them: the Q224 case); otherwise each
    strategy sells its own 23400+i CE x 75 (one contract per strategy)."""
    if shared:
        strategies = {f"S{i}": executed(reference=f"e{i}") for i in range(strategy_count)}
    else:
        strategies = {
            f"S{i}": executed(single_leg(Action.SELL, Instrument.CE, str(23400 + i), 75), f"e{i}")
            for i in range(strategy_count)
        }
    return lambda: run({}, strategies)


@pytest.mark.parametrize("shared", [True, False], ids=["shared-condor", "one-contract-each"])
def test_ac2_work_is_linear_in_active_strategies(shared):
    """AC-2 (W-037, issue #64): every run compares all non-exited strategies, and its work grows linearly in their
    number: with every strategy mismatched and the broker flat, doubling the strategies (100 -> 200) costs at most
    DOUBLING_LIMIT (2.5x) times the calls (was 3.5x: each differing contract re-scanned every strategy). Work is
    counted, not timed (tests/work_count.py)."""
    from work_count import assert_linear

    assert_linear(lambda n: _all_mismatched(n, shared), 100)
    report = _all_mismatched(200, shared)()
    assert len(report.covered_strategy_ids) == 200 and len(report.blocked_strategy_ids) == 200
    # Hand count: shared -> the condor's 4 contracts, each one mismatch held by all 200; else one per strategy.
    assert len(report.mismatches) == (4 if shared else 200)
