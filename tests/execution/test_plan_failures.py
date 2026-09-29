"""REQ-056 AC-4 (core invariant 21): if a protective leg fails, the sell leg that depends on it is not submitted. W-022.

Expected sets are read off the golden Iron Condor (scenario-calculations.md §6, ADR-017 Q26 sequence: 22,800 PE buy,
23,600 CE buy, 23,000 PE sell, 23,400 CE sell) and hand-built legs whose protection follows from the strikes.
"""
from __future__ import annotations

import pytest
from partial_inputs import LOT, REFS, plan
from plan_inputs import BUY, CE, NEXT, SELL, leg, mk

from ofo.execution.sequence import sequence_plan

BUY_PE, SELL_PE, SELL_CE, BUY_CE = REFS


def test_ac4_call_wing_failure_withholds_only_the_call_sale() -> None:
    """AC-4: the 23,600 CE purchase fails -> the 23,400 CE sale is not submitted; the put side goes through."""
    sim = sequence_plan(plan()).simulate({BUY_CE})
    assert sim.sent == (BUY_PE, BUY_CE, SELL_PE)
    assert sim.failed == (BUY_CE,)
    assert sim.withheld == (SELL_CE,)


def test_ac4_both_wings_fail_so_no_sale_is_submitted() -> None:
    """AC-4: both bought wings fail -> neither sold leg is submitted; nothing naked is opened."""
    sim = sequence_plan(plan()).simulate([BUY_PE, BUY_CE])
    assert sim.sent == (BUY_PE, BUY_CE)
    assert sim.withheld == (SELL_PE, SELL_CE)


def test_ac4_a_failed_sold_leg_withholds_nothing() -> None:
    """AC-4 (red case): a failing SELL protects nothing, so every other leg is still submitted."""
    sim = sequence_plan(plan()).simulate({SELL_PE})
    assert sim.sent == (BUY_PE, BUY_CE, SELL_PE, SELL_CE)
    assert sim.withheld == ()


def test_ac4_no_failure_submits_every_leg_in_sequence() -> None:
    """AC-4 (red case): with no failure every leg is submitted in the plan's sequence."""
    sim = sequence_plan(plan()).simulate(())
    assert sim.sent == (BUY_PE, BUY_CE, SELL_PE, SELL_CE) and sim.failed == () and sim.withheld == ()


def test_ac4_sold_leg_with_two_protectors_is_withheld_if_either_fails() -> None:
    """AC-4: BUY 1 lot 23,000 CE + BUY 1 lot 23,100 CE protect SELL 2 lots 23,200 CE together; with either missing the
    sale's protection is incomplete, so it is withheld (each protector tried separately)."""
    seq = sequence_plan(mk(leg(BUY, CE, "23000"), leg(BUY, CE, "23100"), leg(SELL, CE, "23200", qty=2 * LOT)))
    assert seq.protectors_of("L3") == ("L1", "L2")
    for failing in ("L1", "L2"):
        sim = seq.simulate({failing})
        assert sim.withheld == ("L3",)
        assert sim.sent == ("L1", "L2")


def test_ac4_withholding_is_transitive_a_withheld_leg_counts_as_failed() -> None:
    """AC-4: the dependency graph is walked to a fixpoint: a failure removes its dependents and, through them, their
    own dependents. With the rules in the spec a sold leg protects nothing, so the graph is one level deep; this test
    fixes that a withheld leg is never reported as sent or failed and that every dependent of the failure is gone,
    on two independent condor groups (only the group whose wing failed loses its sale)."""
    seq = sequence_plan(mk(leg(BUY, CE, "23600"), leg(SELL, CE, "23400"),
                           leg(BUY, CE, "23600", expiry=NEXT), leg(SELL, CE, "23400", expiry=NEXT)))
    sim = seq.simulate({"L1"})
    assert sim.withheld == ("L2",)
    assert sim.sent == ("L1", "L3", "L4")
    assert set(sim.sent) & set(sim.withheld) == set()


@pytest.mark.parametrize("bad", [{"leg-9"}, "leg-1", ["leg-1", "leg-1"]])
def test_ac4_unknown_duplicate_or_bare_string_failures_are_refused(bad: object) -> None:
    """AC-4 (input domain): an unknown leg, a duplicate, or a bare string instead of a collection raises."""
    with pytest.raises(ValueError):
        sequence_plan(plan()).simulate(bad)  # type: ignore[arg-type]
