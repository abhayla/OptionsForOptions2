"""REQ-058 AC-4 (W-028, deferred #43): Complete and Retry follow the full execution plan.

Spec basis: REQ-058 AC-4 "Before completing, the platform re-fetches positions and order status, computes the actual
remaining strategy, re-checks margin, verifies the missing leg and submits only the required order(s)"; REQ-056 AC-2
"an order sequence based on protection, margin impact, dependencies and broker constraints", AC-4 "If a protective
leg fails, the sell leg that depends on it is not submitted", AC-9 "lot validity"; ADR-017 Q26.

The strategy is the golden Iron Condor on the REAL instrument-list fixture (NIFTY 2026-10-06, lot 65 read from the
catalogue), at 10 lots = 650 units per leg. Expected slices are hand-computed:
- fake freeze 200 units -> rounded DOWN to 3 whole lots = 195 units (orchestrator default, W-028);
- 650 = 195 + 195 + 195 + 65, i.e. 4 slices, each a multiple of 65.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest
from partial_inputs import (
    BROKER_IDS,
    CONTRACTS,
    FILL_AT,
    LOT,
    REFS,
    REJECT_TEXT,
    STRATEGY_ID,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    condor_record,
    entry_context,
    new_book,
)
from execution_inputs import condor_legs
from plan_inputs import FakeConstraints, FakeMargin

from ofo.engine import Action
from ofo.execution import send_guard
from ofo.execution.partial import (
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionPlan,
    PartialChoice,
    PlannedLeg,
    complete_strategy,
    retry_failed_leg,
    submit_confirmed,
)
from ofo.execution.send_guard import SendRefused
from ofo.execution.sequence import sequence_plan
from ofo.orders import FillEvent, Order, OrderState

LOTS = 10
QTY = LOTS * LOT  # 650 units per leg
SMALL_FREEZE = 200  # not a lot multiple: 3 lots (195) fit under it, 4 lots (260) do not
SLICES_650_AT_195 = [195, 195, 195, 65]  # hand computation: 3 x 195 + 65 = 650
BUY_PE, SELL_PE, SELL_CE, BUY_CE = REFS


def big_plan() -> ExecutionPlan:
    return ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, lg)
                                            for r, c, lg in zip(REFS, CONTRACTS, condor_legs(QTY))))


def _state(filled: tuple[int, ...]):  # noqa: ANN202
    """Book, positions and broker order statuses where the legs at ``filled`` (0-based) filled in full and every
    other leg's order was REJECTED with nothing filled."""
    book = new_book(record=condor_record(QTY))
    positions, sts = [], []
    for i, (ref, contract, lg) in enumerate(zip(REFS, CONTRACTS, condor_legs(QTY))):
        book.add(Order(STRATEGY_ID, ref, contract, lg.action, QTY, lg.entry_price, broker_order_id=BROKER_IDS[i],
                       version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        if i in filled:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, lg.action, QTY, lg.entry_price, FILL_AT))
            sign = 1 if lg.action is Action.BUY else -1
            positions.append(BrokerPositionLine(contract, sign * QTY, lg.entry_price))
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.EXECUTED, QTY))
        else:
            book.transition(BROKER_IDS[i], OrderState.REJECTED)
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.REJECTED, 0, REJECT_TEXT))
    return book, FakeBroker(positions, sts)


def _complete(filled, catalogue, eligibility, **kw):  # noqa: ANN001, ANN003, ANN202
    book, broker = _state(filled)
    kw.setdefault("constraints", FakeConstraints(freeze=SMALL_FREEZE, per_batch=2))
    return complete_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, **kw)


def _rows(prep):  # noqa: ANN001, ANN202
    return [(o.leg_ref, o.contract, o.side, o.quantity) for o in prep.orders]


# -- Core ------------------------------------------------------------------------------------------------------------


def test_core_complete_slices_only_the_missing_23600_ce_and_a_refused_first_slice_withholds_the_dependent_sell(
        catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 (core): with 23,600 CE (650 units) missing and a freeze of 200, Complete prepares exactly four lot-aligned
    slices of that leg (195, 195, 195, 65), all in step 1, batches of 2 (1, 1, 2, 2), and nothing else. With the
    23,400 CE sale ALSO missing, a refused FIRST slice of the 23,600 CE sends no slice of the sale that depends on it."""
    prep = _complete((0, 1, 2), catalogue, eligibility)
    assert prep.ready, prep.reason
    assert _rows(prep) == [(BUY_CE, CONTRACTS[3], Action.BUY, q) for q in SLICES_650_AT_195]
    assert [(s.step, s.batch, s.leg_ref, s.slice_no, s.quantity) for s in prep.slices] == [
        (1, 1, BUY_CE, 1, 195), (1, 1, BUY_CE, 2, 195), (1, 2, BUY_CE, 3, 195), (1, 2, BUY_CE, 4, 65)]
    assert all(o.quantity % LOT == 0 for o in prep.orders)

    both = _complete((0, 1), catalogue, eligibility)
    assert _rows(both) == ([(BUY_CE, CONTRACTS[3], Action.BUY, q) for q in SLICES_650_AT_195]
                           + [(SELL_CE, CONTRACTS[2], Action.SELL, q) for q in SLICES_650_AT_195])
    submitter = FakeSubmitter(refuse=1)
    result = submit_confirmed(both, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(r.leg_ref, r.side, r.quantity) for r in submitter.sent] == [(BUY_CE, Action.BUY, 195)]
    assert result.failed == (BUY_CE, "Order rejected: RMS:Margin Exceeds")
    assert result.not_sent == (BUY_CE, SELL_CE)


# -- Lot alignment ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("freeze,expected", [(195, SLICES_650_AT_195), (130, [130] * 5), (650, [650]),
                                             (1755, [650])])
def test_ac4_every_slice_quantity_is_a_whole_number_of_catalogue_lots(freeze, expected, catalogue,  # noqa: ANN001
                                                                      eligibility) -> None:
    """AC-4: the lot (65) comes from the catalogue; every slice is a multiple of it and the slices sum to the missing
    650 units (hand computation: 650/130 = 5; 650 <= 650 and 1,755 -> one order)."""
    prep = _complete((0, 1, 2), catalogue, eligibility, constraints=FakeConstraints(freeze=freeze, per_batch=10))
    assert [o.quantity for o in prep.orders] == expected
    assert all(q % LOT == 0 for q in expected) and sum(expected) == QTY


@pytest.mark.parametrize("freeze,expected", [(200, SLICES_650_AT_195), (259, SLICES_650_AT_195),
                                             (129, [65] * 10), (66, [65] * 10)])
def test_ac4_a_freeze_limit_that_is_not_a_lot_multiple_is_rounded_down(freeze, expected, catalogue,  # noqa: ANN001
                                                                       eligibility) -> None:
    """AC-4 (orchestrator default W-028): a freeze of 200 or 259 units holds 3 whole lots (195), 129 or 66 holds one
    (65); the slice is never the raw freeze figure (200 is not a multiple of 65)."""
    prep = _complete((0, 1, 2), catalogue, eligibility, constraints=FakeConstraints(freeze=freeze, per_batch=10))
    assert [o.quantity for o in prep.orders] == expected


def test_ac4_a_freeze_below_one_lot_is_refused(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 negative (W-043, #71): a freeze of 64 units holds no whole lot of 65, so no order can be sized; refused as
    a "Nothing prepared: <reason>" result (was a raised ValueError), with no order and no held preparation."""
    prep = _complete((0, 1, 2), catalogue, eligibility, constraints=FakeConstraints(freeze=64, per_batch=10))
    assert not prep.ready and prep.orders == () and prep.gate is None
    assert prep.reason.startswith("Nothing prepared: ") and "below one lot of 65" in prep.reason


def test_ac4_a_missing_quantity_that_is_not_a_whole_number_of_lots_is_refused(catalogue) -> None:  # noqa: ANN001
    """AC-4 negative (issue #43 item 3): a 3,000-unit leg (46.15 lots of 65) is refused, and so is a missing 100."""
    odd = ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, dataclasses.replace(lg, quantity=3000))
                                           for r, c, lg in zip(REFS, CONTRACTS, condor_legs())))
    with pytest.raises(ValueError, match="whole number of lots"):
        sequence_plan(odd, catalogue=catalogue)
    with pytest.raises(ValueError, match="whole number of lots"):
        sequence_plan(big_plan(), catalogue=catalogue, quantities={BUY_CE: 100})
    with pytest.raises(ValueError, match="3000 units is not a whole number of lots"):  # the leg itself, even when
        sequence_plan(odd, catalogue=catalogue, quantities={BUY_CE: LOT})  # the part still to order is one lot


def test_ac4_a_symbol_held_by_two_catalogue_instruments_is_refused(catalogue) -> None:  # noqa: ANN001
    """AC-4 negative: the catalogue is keyed by instrument token, so a second token with the 23,600 CE symbol (lot 75
    here) makes the lot size ambiguous; refused rather than picking one."""
    (entry,) = [e for e in catalogue.all_entries() if e.contract.tradingsymbol == CONTRACTS[3]]
    twin = dataclasses.replace(entry.contract, instrument_token=entry.contract.instrument_token + 1, lot_size=75)
    catalogue.load([twin])
    with pytest.raises(ValueError, match="2 instruments with that symbol"):
        sequence_plan(big_plan(), catalogue=catalogue)
    with pytest.raises(ValueError, match="instrument catalogue"):
        sequence_plan(big_plan(), catalogue={CONTRACTS[3]: 65})  # a caller's own lot table is not the catalogue


def test_ac4_a_plan_contract_outside_the_catalogue_is_refused(catalogue) -> None:  # noqa: ANN001
    """AC-4 negative (grid from the grid): a contract symbol the catalogue does not hold has no lot size; refused."""
    legs = list(big_plan().legs)
    legs[3] = PlannedLeg(BUY_CE, "NIFTY26O0623625CE", legs[3].leg)  # grep of the fixture: 0 rows
    with pytest.raises(ValueError, match="catalogue"):
        sequence_plan(ExecutionPlan(STRATEGY_ID, tuple(legs)), catalogue=catalogue)


@pytest.mark.parametrize("quantities", [{"leg-9": 65}, {BUY_CE: 0}, {BUY_CE: -65}, {BUY_CE: True},
                                        {BUY_CE: QTY + LOT}, {BUY_CE: "65"}, [(BUY_CE, 65)]])
def test_ac4_bad_remaining_quantities_are_refused(quantities, catalogue) -> None:  # noqa: ANN001
    """AC-4 input domain: an unknown leg, a zero/negative/boolean/string quantity, or more than the leg's planned
    units is refused, never ignored."""
    with pytest.raises(ValueError):
        sequence_plan(big_plan(), catalogue=catalogue, quantities=quantities)


# -- Plan order: margin planner and batches --------------------------------------------------------------------------


def test_ac4_complete_uses_the_plans_margin_planner_within_a_step(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: both wings missing (step 1). With no planner the user's order holds (22,800 PE, then 23,600 CE); with the
    plan's MarginPlanner saying the 23,600 CE frees more margin (impact -5,000 vs +1,000) it goes first."""
    plain = _complete((1, 2), catalogue, eligibility, constraints=FakeConstraints(freeze=1755, per_batch=10))
    assert [o.leg_ref for o in plain.orders] == [BUY_PE, BUY_CE]
    legs = condor_legs(QTY)
    margin = FakeMargin({legs[0]: D("1000"), legs[3]: D("-5000")})
    ordered = _complete((1, 2), catalogue, eligibility, constraints=FakeConstraints(freeze=1755, per_batch=10),
                        margin_planner=margin)
    assert [o.leg_ref for o in ordered.orders] == [BUY_CE, BUY_PE]
    assert margin.asked


def test_ac4_batches_never_span_a_step(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: 23,600 CE (step 1) and 23,400 CE (step 2) missing, freeze 195, 3 per batch: step 1 batches 1,1,1,2;
    step 2 starts batch 3: 3,3,3,4 (hand computation)."""
    prep = _complete((0, 1), catalogue, eligibility, constraints=FakeConstraints(freeze=195, per_batch=3))
    assert [(s.step, s.batch, s.leg_ref) for s in prep.slices] == (
        [(1, b, BUY_CE) for b in (1, 1, 1, 2)] + [(2, b, SELL_CE) for b in (3, 3, 3, 4)])


# -- Withholding at send ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("refused", [1, 2, 3, 4])
def test_ac4_a_refused_protective_slice_withholds_every_dependent_slice(refused: int, catalogue,  # noqa: ANN001
                                                                       eligibility) -> None:
    """AC-4 / invariant 21: whichever 23,600 CE slice is refused, no slice of the 23,400 CE sale is sent; the slices
    before it were sent, none after it."""
    prep = _complete((0, 1), catalogue, eligibility)
    submitter = FakeSubmitter(refuse=refused)
    result = submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(r.leg_ref, r.quantity) for r in submitter.sent] == [(BUY_CE, q) for q in SLICES_650_AT_195[:refused]]
    assert SELL_CE not in {r.leg_ref for r in submitter.sent}
    assert len(result.submitted) == refused - 1
    assert result.failed[0] == BUY_CE


def test_ac4_all_slices_accepted_send_every_slice_in_plan_order(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 positive: with no refusal all 8 slices go, protector first, and the book holds 8 platform orders."""
    prep = _complete((0, 1), catalogue, eligibility)
    submitter = FakeSubmitter()
    result = submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(r.leg_ref, r.quantity) for r in submitter.sent] == (
        [(BUY_CE, q) for q in SLICES_650_AT_195] + [(SELL_CE, q) for q in SLICES_650_AT_195])
    assert result.failed is None and result.not_sent == () and len(result.submitted) == 8


def test_ac4_simulate_maps_a_failed_slice_to_a_failed_leg(catalogue) -> None:  # noqa: ANN001
    """AC-4: in the plan's simulation a failed slice (23,600 CE slice 3) counts as a failed 23,600 CE leg, so the
    23,400 CE sale is withheld; a failed sale slice withholds nothing."""
    seq = sequence_plan(big_plan(), constraints=FakeConstraints(freeze=200, per_batch=2), catalogue=catalogue,
                        quantities={SELL_CE: QTY, BUY_CE: QTY})
    sim = seq.simulate_slices([(BUY_CE, 3)])
    assert sim.failed == (BUY_CE,) and sim.withheld == (SELL_CE,)
    sale = seq.simulate_slices([(SELL_CE, 1)])
    assert sale.failed == (SELL_CE,) and sale.withheld == ()


@pytest.mark.parametrize("bad", [[(BUY_CE, 5)], [(BUY_PE, 1)], [(BUY_CE, 1), (BUY_CE, 1)], (BUY_CE, 1),
                                 [("leg-9", 1)], [(BUY_CE, True)]])
def test_ac4_simulate_slices_refuses_unknown_duplicate_or_malformed_slices(bad, catalogue) -> None:  # noqa: ANN001
    """AC-4 input domain: a slice number the sequence does not have (23,600 CE has 4), a leg with no orders, a
    duplicate, a bare tuple instead of a collection, an unknown leg or a boolean slice number is refused."""
    seq = sequence_plan(big_plan(), constraints=FakeConstraints(freeze=200, per_batch=2), catalogue=catalogue,
                        quantities={SELL_CE: QTY, BUY_CE: QTY})
    with pytest.raises(ValueError):
        seq.simulate_slices(bad)


# -- Retry -----------------------------------------------------------------------------------------------------------


def test_ac4_retry_sends_slices_too(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 (Retry): retrying the failed 23,600 CE prepares the same four lot-aligned slices, sent in order."""
    book, broker = _state((0, 1, 2))
    margin = FakeMargin({})
    prep = retry_failed_leg(big_plan(), BUY_CE, broker, book, FakePlanner(), entry_context(), catalogue, eligibility,
                            margin_planner=margin, constraints=FakeConstraints(freeze=SMALL_FREEZE, per_batch=2))
    assert _rows(prep) == [(BUY_CE, CONTRACTS[3], Action.BUY, q) for q in SLICES_650_AT_195]
    submitter = FakeSubmitter()
    submit_confirmed(prep, choice=PartialChoice.RETRY_FAILED_LEG, confirmed_by="user:U-1", submitter=submitter)
    assert [r.quantity for r in submitter.sent] == SLICES_650_AT_195


def test_ac4_complete_without_constraints_uses_the_labelled_default(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: no constraints given -> the labelled UNVERIFIED default (1,755 = 27 lots) still applies: 650 is one order."""
    book, broker = _state((0, 1, 2))
    prep = complete_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert _rows(prep) == [(BUY_CE, CONTRACTS[3], Action.BUY, QTY)]


# -- The sink's room across slices -----------------------------------------------------------------------------------


class _Transport:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def submit(self, request: object) -> str:
        self.calls.append(request)
        return f"NEW-{len(self.calls)}"


def _slice(qty: int, tag: int) -> Order:
    return Order(STRATEGY_ID, BUY_CE, CONTRACTS[3], Action.BUY, qty, D("44.00"), version_id="v1",
                 client_tag=f"OFO{tag:09d}")


def _sink(catalogue, transport: _Transport):  # noqa: ANN001, ANN202
    book, _ = _state((0, 1, 2))
    slots = {p.leg_ref: (p.leg.instrument.value, p.leg.strike, p.leg.expiry) for p in big_plan().legs}
    return send_guard._BrokerSink(transport, book=book, strategy_id=STRATEGY_ID, catalogue=catalogue,
                                  choice="complete", leg_slots=slots)


def test_ac4_sink_accepts_slices_whose_total_fits_the_room(catalogue) -> None:  # noqa: ANN001
    """AC-4: room for 23,600 CE = 650 planned - 0 held - 0 open; slices 195+195+195+65 = 650 resolve to 4 requests."""
    transport = _Transport()
    requests = _sink(catalogue, transport).resolve_all(tuple(_slice(q, i) for i, q in enumerate(SLICES_650_AT_195)))
    assert [r.quantity for r in requests] == SLICES_650_AT_195


def test_ac4_sink_refuses_a_slice_beyond_the_room(catalogue) -> None:  # noqa: ANN001
    """AC-4: each slice alone fits (195 <= 650), but a fifth 195 takes the total to 845 > 650: refused, nothing sent.
    Kills the mutant where the room ignores earlier slices of the same leg (W-026 survivor M14)."""
    transport = _Transport()
    sink = _sink(catalogue, transport)
    with pytest.raises(SendRefused, match="exceed what the strategy allows"):
        sink.resolve_all(tuple(_slice(195, i) for i in range(4)))  # 780 > 650
    with pytest.raises(SendRefused, match="exceed what the strategy allows"):
        sink.resolve_all(tuple(_slice(q, i) for i, q in enumerate(SLICES_650_AT_195 + [65])))  # 715 > 650
    assert transport.calls == []
