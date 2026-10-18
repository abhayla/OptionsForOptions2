"""REQ-058 AC-4 (W-028, deferred #43): Complete and Retry follow the full execution plan.

Spec basis: REQ-058 AC-4 "Before completing, the platform re-fetches positions and order status, computes the actual
remaining strategy, re-checks margin, verifies the missing leg and submits only the required order(s)"; REQ-056 AC-2
"an order sequence based on protection, margin impact, dependencies and broker constraints", AC-4 "If a protective
leg fails, the sell leg that depends on it is not submitted", AC-9 "lot validity"; ADR-017 Q26.

The strategy is the golden Iron Condor on the REAL instrument-list fixture (NIFTY 2026-10-06, lot 65 read from the
catalogue), at 10 lots = 650 units per leg. ADR-092 (issue 255) supersedes W-028's freeze slicing: every missing
leg is ONE order of its whole missing units (the freeze limit itself is tested in test_never_split.py). The sink tests
below still send several orders of one leg to prove the room counts every earlier order of that leg.
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
from partial_inputs import STORED_FREEZE
from execution_inputs import condor_legs
from plan_inputs import FakeConstraints, FakeMargin

from ofo.instruments.models import ListedContract
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
SLICES_650_AT_195 = [195, 195, 195, 65]  # several orders of one leg for the sink's room: 650 in total
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
    kw.setdefault("constraints", FakeConstraints(per_batch=2))
    kw.setdefault("stored_freeze", STORED_FREEZE)
    return complete_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, **kw)


def _rows(prep):  # noqa: ANN001, ANN202
    return [(o.leg_ref, o.contract, o.side, o.quantity) for o in prep.orders]


# -- Core ------------------------------------------------------------------------------------------------------------


def test_core_complete_prepares_only_the_missing_23600_ce_as_one_order_and_a_refused_protector_withholds_the_sell(
        catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 (core, ADR-092 never split): with 23,600 CE (650 units) missing, Complete prepares exactly ONE order of 650
    for that leg, step 1 batch 1, and nothing else (W-028 listed 195/195/195/65). With the 23,400 CE sale ALSO missing,
    a refused 23,600 CE order sends nothing of the sale that depends on it."""
    prep = _complete((0, 1, 2), catalogue, eligibility)
    assert prep.ready, prep.reason
    assert _rows(prep) == [(BUY_CE, CONTRACTS[3], Action.BUY, QTY)]
    assert [(s.step, s.batch, s.leg_ref, s.quantity) for s in prep.slices] == [(1, 1, BUY_CE, QTY)]
    assert prep.warnings == ()

    both = _complete((0, 1), catalogue, eligibility)
    assert _rows(both) == [(BUY_CE, CONTRACTS[3], Action.BUY, QTY), (SELL_CE, CONTRACTS[2], Action.SELL, QTY)]
    submitter = FakeSubmitter(refuse=1)
    result = submit_confirmed(both, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(r.leg_ref, r.side, r.quantity) for r in submitter.sent] == [(BUY_CE, Action.BUY, QTY)]
    assert result.failed == (BUY_CE, "Order rejected: RMS:Margin Exceeds")
    assert SELL_CE in result.not_sent


# -- Lot alignment ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("per_batch", [1, 2, 10])
def test_ac4_every_order_is_the_whole_missing_leg_in_catalogue_lots(per_batch, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 / ADR-092: whatever the batch size, the missing 650 units (10 lots of the catalogue's 65) are ONE order."""
    prep = _complete((0, 1, 2), catalogue, eligibility, constraints=FakeConstraints(per_batch=per_batch))
    assert [o.quantity for o in prep.orders] == [QTY] and QTY % LOT == 0


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
    """AC-4 negative: the catalogue is keyed by the exchange identity, so a second contract with the 23,600 CE symbol (lot 75
    here) makes the lot size ambiguous; refused rather than picking one."""
    (entry,) = [e for e in catalogue.all_entries() if e.ref("zerodha").broker_symbol == CONTRACTS[3]]
    ref = entry.ref("zerodha")
    twin = ListedContract(
        dataclasses.replace(entry.contract, exchange_token=entry.contract.exchange_token + 1, lot_size=75),
        (dataclasses.replace(ref, broker_token=str(int(ref.broker_token) + 1), lot_size=75),))
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
    plain = _complete((1, 2), catalogue, eligibility, constraints=FakeConstraints(per_batch=10))
    assert [o.leg_ref for o in plain.orders] == [BUY_PE, BUY_CE]
    legs = condor_legs(QTY)
    margin = FakeMargin({legs[0]: D("1000"), legs[3]: D("-5000")})
    ordered = _complete((1, 2), catalogue, eligibility, constraints=FakeConstraints(per_batch=10),
                        margin_planner=margin)
    assert [o.leg_ref for o in ordered.orders] == [BUY_CE, BUY_PE]
    assert margin.asked


def test_ac4_batches_never_span_a_step(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: 22,800 PE and 23,600 CE (step 1) and 23,400 CE (step 2) missing, one order each. Batches of 3: step 1 is
    batch 1 (two orders), step 2 starts batch 2; batches of 1: 1, 2, 3 (hand computation)."""
    three = _complete((1,), catalogue, eligibility, constraints=FakeConstraints(per_batch=3))
    assert [(s.step, s.batch, s.leg_ref) for s in three.slices] == [(1, 1, BUY_PE), (1, 1, BUY_CE), (2, 2, SELL_CE)]
    one = _complete((1,), catalogue, eligibility, constraints=FakeConstraints(per_batch=1))
    assert [(s.step, s.batch) for s in one.slices] == [(1, 1), (1, 2), (2, 3)]


# -- Withholding at send ---------------------------------------------------------------------------------------------


def test_ac4_a_refused_protective_order_withholds_its_dependent_sell(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 / invariant 21: the 23,600 CE order refused -> the 23,400 CE sale is never sent."""
    prep = _complete((0, 1), catalogue, eligibility)
    submitter = FakeSubmitter(refuse=1)
    result = submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(r.leg_ref, r.quantity) for r in submitter.sent] == [(BUY_CE, QTY)]
    assert SELL_CE not in {r.leg_ref for r in submitter.sent}
    assert result.submitted == () and result.failed[0] == BUY_CE


def test_ac4_all_orders_accepted_send_every_order_in_plan_order(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 positive: with no refusal both orders go, protector first, each the whole 650 units."""
    prep = _complete((0, 1), catalogue, eligibility)
    submitter = FakeSubmitter()
    result = submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(r.leg_ref, r.quantity) for r in submitter.sent] == [(BUY_CE, QTY), (SELL_CE, QTY)]
    assert result.failed is None and result.not_sent == () and len(result.submitted) == 2


def test_ac4_simulate_maps_a_failed_protector_to_a_withheld_sell(catalogue) -> None:  # noqa: ANN001
    """AC-4: in the plan's simulation a failed 23,600 CE withholds the 23,400 CE sale; a failed sale withholds nothing."""
    seq = sequence_plan(big_plan(), constraints=FakeConstraints(per_batch=2), catalogue=catalogue,
                        quantities={SELL_CE: QTY, BUY_CE: QTY})
    assert [(o.leg_ref, o.quantity) for o in seq.orders] == [(BUY_CE, QTY), (SELL_CE, QTY)]
    sim = seq.simulate([BUY_CE])
    assert sim.failed == (BUY_CE,) and sim.withheld == (SELL_CE,)
    sale = seq.simulate([SELL_CE])
    assert sale.failed == (SELL_CE,) and sale.withheld == ()


@pytest.mark.parametrize("bad", [[BUY_CE, BUY_CE], BUY_CE, ["leg-9"]])
def test_ac4_simulate_refuses_unknown_duplicate_or_malformed_failures(bad, catalogue) -> None:  # noqa: ANN001
    """AC-4 input domain: a duplicate, a bare string instead of a collection, or an unknown leg is refused."""
    seq = sequence_plan(big_plan(), constraints=FakeConstraints(per_batch=2), catalogue=catalogue,
                        quantities={SELL_CE: QTY, BUY_CE: QTY})
    with pytest.raises(ValueError):
        seq.simulate(bad)


# -- Retry -----------------------------------------------------------------------------------------------------------


def test_ac4_retry_sends_one_order_too(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 (Retry, ADR-092): retrying the failed 23,600 CE prepares ONE order of the missing 650 units."""
    book, broker = _state((0, 1, 2))
    prep = retry_failed_leg(big_plan(), BUY_CE, broker, book, FakePlanner(), entry_context(), catalogue, eligibility,
                            margin_planner=FakeMargin({}), constraints=FakeConstraints(per_batch=2),
                            stored_freeze=STORED_FREEZE)
    assert _rows(prep) == [(BUY_CE, CONTRACTS[3], Action.BUY, QTY)]
    submitter = FakeSubmitter()
    submit_confirmed(prep, choice=PartialChoice.RETRY_FAILED_LEG, confirmed_by="user:U-1", submitter=submitter)
    assert [r.quantity for r in submitter.sent] == [QTY]


def test_ac4_complete_without_constraints_uses_the_labelled_default(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: no constraints given -> the labelled UNVERIFIED default batch size; 650 is one order."""
    book, broker = _state((0, 1, 2))
    prep = complete_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility,
                             stored_freeze=STORED_FREEZE)
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
