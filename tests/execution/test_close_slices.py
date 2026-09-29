"""REQ-056 AC-10 (W-032, deferred #50): Close Partial Strategy respects the broker's freeze limit.

Spec basis: REQ-056 AC-10 "The execution engine respects Zerodha's extra rules for API orders: market protection on API
market orders and order rate limits (T1 #66, Q28)"; REQ-058 AC-2 (Close Partial Strategy is a user choice), AC-3
"Successfully executed legs are never unwound automatically". Exit order: partial.py orchestrator default OD-e "close
orders are priced at the broker's LTP; a missing LTP prepares nothing. Buy-backs of shorts go first." Freeze slicing
and lot rounding are sequence.py's (W-028): "a freeze quantity that is not a whole number of lots is rounded DOWN to
whole lots ... a freeze below one lot is refused". Freeze 1,755 / 10 per batch stay the UNVERIFIED placeholders of #43.

The strategy is the golden Iron Condor on the REAL instrument-list fixture (NIFTY 2026-10-06, lot 65 read from the
catalogue) at 10 lots = 650 units per leg; the SENSEX case uses the fixture's SENSEX 2026-10-01 expiry (lot 20).
Expected slices are hand-computed:
- NIFTY, fake freeze 260 = 4 lots: 650 = 260 + 260 + 130 (130 = 2 lots) -> 3 slices;
- NIFTY, 390 filled (6 lots) at freeze 260: 260 + 130 -> 2 slices;
- NIFTY, default freeze 1,755 (27 lots), 30 lots = 1,950 filled: 1,755 + 195 -> 2 slices;
- SENSEX, 12 lots = 240 units, fake freeze 100 = 5 lots: 100 + 100 + 40 -> 3 slices;
- SENSEX, fake freeze 110 (not a lot multiple) rounds DOWN to 100: same 100 + 100 + 40.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from execution_inputs import condor_legs
from partial_inputs import (
    BROKER_IDS,
    CONTRACTS,
    FILL_AT,
    LOT,
    READ_AT,
    REFS,
    REJECT_TEXT,
    STRATEGY_ID,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    entry_context,
    new_book,
    record_for_legs,
)
from plan_inputs import FakeConstraints

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution.partial import (
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionPlan,
    PartialChoice,
    PlannedLeg,
    close_partial_strategy,
    submit_confirmed,
)
from ofo.execution.sequence import exit_orders
from ofo.orders import FillEvent, Order, OrderState
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import StrategyRecord

QTY = 10 * LOT  # 650 units per leg
FREEZE_260 = 260  # 4 whole lots of 65
BUY_PE, SELL_PE, SELL_CE, BUY_CE = REFS
LTPS = (D("40.00"), D("80.00"), D("120.00"), D("30.00"))


def big_plan(qty: int = QTY) -> ExecutionPlan:
    return ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, lg) for r, c, lg in zip(REFS, CONTRACTS, condor_legs(qty))))


def _state(filled: tuple[int, int, int, int], qty: int = QTY):  # noqa: ANN202
    """Each leg's entry order of ``qty`` units filled ``filled[i]`` units; a leg filled less than in full had its order
    CANCELLED (after the partial fill) or REJECTED (nothing filled). Broker positions carry an LTP for every held leg."""
    book = new_book(record=record_for_legs(condor_legs(qty)))
    positions, sts = [], []
    for i, (ref, contract, lg) in enumerate(zip(REFS, CONTRACTS, condor_legs(qty))):
        book.add(Order(STRATEGY_ID, ref, contract, lg.action, qty, lg.entry_price, broker_order_id=BROKER_IDS[i],
                       version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        units = filled[i]
        if units:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, lg.action, units, lg.entry_price,
                                      FILL_AT))
            sign = 1 if lg.action is Action.BUY else -1
            positions.append(BrokerPositionLine(contract, sign * units, lg.entry_price, LTPS[i]))
        if units == qty:
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.EXECUTED, units))
        elif units:
            book.transition(BROKER_IDS[i], OrderState.CANCELLED)
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.CANCELLED, units, "Cancelled by user"))
        else:
            book.transition(BROKER_IDS[i], OrderState.REJECTED)
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.REJECTED, 0, REJECT_TEXT))
    return book, FakeBroker(positions, sts)


def _close(filled, catalogue, eligibility, qty: int = QTY, **kw):  # noqa: ANN001, ANN003, ANN202
    book, broker = _state(filled, qty)
    return close_partial_strategy(big_plan(qty), broker, book, FakePlanner(), entry_context(), catalogue,
                                  eligibility, **kw)


def _rows(prep):  # noqa: ANN001, ANN202
    return [(o.leg_ref, o.side, o.quantity) for o in prep.orders]


# -- Core ------------------------------------------------------------------------------------------------------------


def test_core_close_slices_every_filled_leg_at_the_freeze_shorts_first(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 (core): three legs filled 650 units each, the 23,600 CE rejected; Close with a fake freeze of 260 (4 lots)
    prepares each filled leg as 260 + 260 + 130 (hand computation), every slice a multiple of the catalogue lot 65,
    each leg's slices summing exactly to its 650 filled units; the two shorts are bought back before the long is sold
    (OD-e), and buy-backs and sells never share a batch."""
    prep = _close((QTY, QTY, QTY, 0), catalogue, eligibility,
                  constraints=FakeConstraints(freeze=FREEZE_260, per_batch=10))
    assert prep.ready, prep.reason
    assert _rows(prep) == ([(SELL_PE, Action.BUY, q) for q in (260, 260, 130)]
                           + [(SELL_CE, Action.BUY, q) for q in (260, 260, 130)]
                           + [(BUY_PE, Action.SELL, q) for q in (260, 260, 130)])
    assert len(prep.orders) == 9
    assert all(o.quantity % LOT == 0 for o in prep.orders)
    for ref in (BUY_PE, SELL_PE, SELL_CE):
        assert sum(o.quantity for o in prep.orders if o.leg_ref == ref) == QTY
    assert [(s.step, s.batch, s.leg_ref, s.slice_no, s.quantity) for s in prep.slices] == [
        (1, 1, SELL_PE, 1, 260), (1, 1, SELL_PE, 2, 260), (1, 1, SELL_PE, 3, 130),
        (1, 1, SELL_CE, 1, 260), (1, 1, SELL_CE, 2, 260), (1, 1, SELL_CE, 3, 130),
        (2, 2, BUY_PE, 1, 260), (2, 2, BUY_PE, 2, 260), (2, 2, BUY_PE, 3, 130)]
    # every exit priced at the broker's LTP (OD-e), unchanged by slicing
    assert {(o.leg_ref, o.price) for o in prep.orders} == {(BUY_PE, LTPS[0]), (SELL_PE, LTPS[1]), (SELL_CE, LTPS[2])}


# -- Quantities ------------------------------------------------------------------------------------------------------


def test_ac10_a_partly_filled_leg_closes_only_its_filled_units(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 / reduce-only: the 23,400 CE sale filled 390 of 650 (6 lots) then was cancelled; Close buys back exactly
    390 as 260 + 130, never the planned 650; the fully filled legs still close 650 each."""
    prep = _close((QTY, QTY, 390, 0), catalogue, eligibility,
                  constraints=FakeConstraints(freeze=FREEZE_260, per_batch=10))
    assert prep.ready, prep.reason
    assert [o.quantity for o in prep.orders if o.leg_ref == SELL_CE] == [260, 130]
    assert sum(o.quantity for o in prep.orders if o.leg_ref == SELL_CE) == 390
    assert _rows(prep)[:5] == ([(SELL_PE, Action.BUY, q) for q in (260, 260, 130)]
                               + [(SELL_CE, Action.BUY, q) for q in (260, 130)])


@pytest.mark.parametrize("freeze", [QTY, 1755])
def test_ac10_a_leg_at_or_below_the_freeze_stays_one_order(freeze: int, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10: 650 filled at a freeze of exactly 650 (10 lots) or 1,755 is one order per leg, as before W-032."""
    prep = _close((QTY, QTY, QTY, 0), catalogue, eligibility, constraints=FakeConstraints(freeze=freeze, per_batch=10))
    assert _rows(prep) == [(SELL_PE, Action.BUY, QTY), (SELL_CE, Action.BUY, QTY), (BUY_PE, Action.SELL, QTY)]


def test_ac10_without_constraints_the_labelled_default_freeze_slices_a_large_close(catalogue,  # noqa: ANN001
                                                                                  eligibility) -> None:
    """AC-10: no constraints given -> the UNVERIFIED default 1,755 (27 lots) applies; 30 lots = 1,950 filled closes as
    1,755 + 195 (hand computation: 1,950 - 1,755 = 195 = 3 lots). On origin/main this was one 1,950-unit order."""
    qty = 30 * LOT
    prep = _close((qty, qty, qty, 0), catalogue, eligibility, qty=qty)
    assert prep.ready, prep.reason
    assert _rows(prep) == ([(SELL_PE, Action.BUY, q) for q in (1755, 195)]
                           + [(SELL_CE, Action.BUY, q) for q in (1755, 195)]
                           + [(BUY_PE, Action.SELL, q) for q in (1755, 195)])


def test_ac10_a_freeze_below_one_lot_is_refused(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 negative: a freeze of 64 units holds no whole lot of 65; refused, nothing prepared or held."""
    book, broker = _state((QTY, QTY, QTY, 0))
    with pytest.raises(ValueError, match="below one lot"):
        close_partial_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility,
                               constraints=FakeConstraints(freeze=64, per_batch=10))
    assert not book.has_live_preparation(STRATEGY_ID)


@pytest.mark.parametrize("freeze,expected", [(259, [195, 195, 195, 65]), (200, [195, 195, 195, 65]),
                                             (129, [65] * 10)])
def test_ac10_a_freeze_that_is_not_a_lot_multiple_is_rounded_down(freeze, expected, catalogue,  # noqa: ANN001
                                                                  eligibility) -> None:
    """AC-10 (W-028 default): freeze 259 or 200 holds 3 whole lots (195): 650 = 195x3 + 65; 129 holds one lot: 10x65."""
    prep = _close((QTY, QTY, QTY, 0), catalogue, eligibility, constraints=FakeConstraints(freeze=freeze, per_batch=50))
    assert [o.quantity for o in prep.orders if o.leg_ref == SELL_PE] == expected


def test_ac10_batches_follow_the_constraint_and_never_mix_buy_backs_with_sells(catalogue,  # noqa: ANN001
                                                                              eligibility) -> None:
    """AC-10 (order rate limits): 4 per batch; step 1 has 6 buy-back slices -> batches 1,1,1,1,2,2; step 2 (sells)
    starts a new batch: 3,3,3 (hand computation)."""
    prep = _close((QTY, QTY, QTY, 0), catalogue, eligibility, constraints=FakeConstraints(freeze=FREEZE_260,
                                                                                         per_batch=4))
    assert [(s.step, s.batch) for s in prep.slices] == [(1, b) for b in (1, 1, 1, 1, 2, 2)] + [(2, 3)] * 3


# -- Existing behaviour kept -----------------------------------------------------------------------------------------


def test_ac10_open_entry_orders_are_still_listed_for_cancellation(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 with OD-m (Q223): the 23,600 CE entry order still open (Submitted, nothing filled) is listed as a cancel
    request, never closed; the filled legs are sliced as usual. Close runs in IN_PROGRESS here."""
    book = new_book(record=record_for_legs(condor_legs(QTY)))
    positions, sts = [], []
    for i, (ref, contract, lg) in enumerate(zip(REFS, CONTRACTS, condor_legs(QTY))):
        book.add(Order(STRATEGY_ID, ref, contract, lg.action, QTY, lg.entry_price, broker_order_id=BROKER_IDS[i],
                       version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        if i < 3:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, lg.action, QTY, lg.entry_price, FILL_AT))
            sign = 1 if lg.action is Action.BUY else -1
            positions.append(BrokerPositionLine(contract, sign * QTY, lg.entry_price, LTPS[i]))
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.EXECUTED, QTY))
        else:
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.SUBMITTED, 0))
    prep = close_partial_strategy(big_plan(), FakeBroker(positions, sts), book, FakePlanner(), entry_context(),
                                  catalogue, eligibility, constraints=FakeConstraints(freeze=FREEZE_260, per_batch=10))
    assert prep.ready, prep.reason
    (open_view,) = [v for v in book.views_for(STRATEGY_ID) if v.contract == CONTRACTS[3]]
    assert prep.cancels == (open_view.key,)
    assert BUY_CE not in {o.leg_ref for o in prep.orders}
    assert len(prep.orders) == 9


def test_ac10_all_close_slices_are_sent_in_order_and_the_sink_accepts_their_total(catalogue,  # noqa: ANN001
                                                                                 eligibility) -> None:
    """AC-10: submitting the 9 slices sends them in the prepared order; the sink's reduce-only room (held 650 per leg)
    accepts 260 + 260 + 130 = 650 for each leg."""
    prep = _close((QTY, QTY, QTY, 0), catalogue, eligibility,
                  constraints=FakeConstraints(freeze=FREEZE_260, per_batch=10))
    submitter = FakeSubmitter()
    result = submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter, acknowledgement=prep.guard.acknowledgement)
    assert [(r.leg_ref, r.side, r.quantity) for r in submitter.sent] == _rows(prep)
    assert result.failed is None and len(result.submitted) == 9


def test_ac10_a_refused_buy_back_slice_stops_every_later_slice(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 / no automatic retry: the second buy-back slice of the 23,000 PE is refused; only the first went, nothing
    after it is sent (the long is not sold while a short is still open)."""
    prep = _close((QTY, QTY, QTY, 0), catalogue, eligibility,
                  constraints=FakeConstraints(freeze=FREEZE_260, per_batch=10))
    submitter = FakeSubmitter(refuse=2)
    result = submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter, acknowledgement=prep.guard.acknowledgement)
    assert [(r.leg_ref, r.quantity) for r in submitter.sent] == [(SELL_PE, 260), (SELL_PE, 260)]
    assert result.failed[0] == SELL_PE and result.not_sent == (SELL_PE, SELL_CE, BUY_PE)


# -- exit_orders input domain (the close's own entry point to the shared slicing) ------------------------------------


def _groups(*rows):  # noqa: ANN002, ANN202
    return (tuple(rows),)


@pytest.mark.parametrize("groups,match", [
    (_groups((SELL_PE, 700)), "up to 650"),  # more than the leg: never more than filled/planned (reduce-only cap)
    (_groups((SELL_PE, 100)), "whole number of lots"),  # 100 units is 1.54 lots of 65
    (_groups((SELL_PE, 0)), "positive integer"),
    (_groups((SELL_PE, True)), "positive integer"),
    (_groups(("leg-9", 65)), "not in this plan"),
    ((((SELL_PE, 65),), ((SELL_PE, 65),)), "more than once"),  # the same leg in two steps
    (_groups((SELL_PE, 65), (SELL_PE, 65)), "more than once"),
])
def test_ac10_exit_orders_refuses_bad_exits(groups, match, catalogue) -> None:  # noqa: ANN001
    """AC-10 input domain: an exit above the leg's units, not a whole number of lots, zero, boolean, an unknown leg or
    the same leg twice is refused, never sent or silently merged."""
    with pytest.raises(ValueError, match=match):
        exit_orders(big_plan(), groups, FakeConstraints(freeze=FREEZE_260, per_batch=10), catalogue)


def test_ac10_close_refuses_a_held_quantity_that_is_not_whole_lots(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 negative: exits already open for 100 of the 650 held 23,000 PE units leave 550 to close, 8.46 lots of 65;
    no lot-aligned slicing exists for that, so the close is refused rather than sending a non-lot quantity."""
    book, broker = _state((QTY, QTY, QTY, 0))
    book.add(Order(STRATEGY_ID, SELL_PE, CONTRACTS[1], Action.BUY, 100, D("80.00"), broker_order_id="BRK-X",
                   version_id="v1"))
    book.transition("BRK-X", OrderState.SUBMITTED)
    broker.order_statuses.append(BrokerOrderStatus("BRK-X", CONTRACTS[1], OrderState.SUBMITTED, 0))
    with pytest.raises(ValueError, match="whole number of lots"):
        close_partial_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility,
                               constraints=FakeConstraints(freeze=FREEZE_260, per_batch=10))


# -- SENSEX (lot 20) -------------------------------------------------------------------------------------------------

SENSEX_EXPIRY = datetime.date(2026, 10, 1)
SENSEX_LOT = 20
SENSEX_QTY = 12 * SENSEX_LOT  # 240
SENSEX_CONTRACTS = ("SENSEX26O0173500PE", "SENSEX26O0173800PE", "SENSEX26O0174200CE", "SENSEX26O0174500CE")


def _sensex_legs(qty: int = SENSEX_QTY) -> tuple[Leg, ...]:
    e = SENSEX_EXPIRY
    return (Leg(Action.BUY, Instrument.PE, D("73500"), e, qty, D("110.00")),
            Leg(Action.SELL, Instrument.PE, D("73800"), e, qty, D("190.00")),
            Leg(Action.SELL, Instrument.CE, D("74200"), e, qty, D("205.00")),
            Leg(Action.BUY, Instrument.CE, D("74500"), e, qty, D("100.00")))


@pytest.mark.parametrize("freeze", [100, 110])
def test_ac10_sensex_close_slices_at_lot_20(freeze: int, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-10 (SENSEX, lot 20 from the catalogue): 240 units filled on three legs, freeze 100 (5 lots) or 110 (rounded
    DOWN to 100): each leg closes as 100 + 100 + 40 (hand computation: 240 - 200 = 40 = 2 lots), shorts first."""
    legs = _sensex_legs()
    record = StrategyRecord(StrategyDefinition.from_engine("SENSEX", Strategy(legs)),
                            at=FILL_AT - datetime.timedelta(minutes=10), clock=lambda: READ_AT)
    record.propose_execution(at=FILL_AT - datetime.timedelta(minutes=9))
    book = new_book(record=record)
    ctx = entry_context(underlying="SENSEX")
    positions, sts = [], []
    for i, (ref, contract, lg) in enumerate(zip(REFS, SENSEX_CONTRACTS, legs)):
        book.add(Order(STRATEGY_ID, ref, contract, lg.action, SENSEX_QTY, lg.entry_price,
                       broker_order_id=BROKER_IDS[i], version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        if i < 3:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, lg.action, SENSEX_QTY, lg.entry_price,
                                      FILL_AT))
            sign = 1 if lg.action is Action.BUY else -1
            positions.append(BrokerPositionLine(contract, sign * SENSEX_QTY, lg.entry_price, LTPS[i]))
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.EXECUTED, SENSEX_QTY))
        else:
            book.transition(BROKER_IDS[i], OrderState.REJECTED)
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.REJECTED, 0, REJECT_TEXT))
    plan = ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, lg) for r, c, lg in zip(REFS, SENSEX_CONTRACTS, legs)))
    prep = close_partial_strategy(plan, FakeBroker(positions, sts), book, FakePlanner(), ctx, catalogue, eligibility,
                                  constraints=FakeConstraints(freeze=freeze, per_batch=10))
    assert prep.ready, prep.reason
    assert _rows(prep) == ([(SELL_PE, Action.BUY, q) for q in (100, 100, 40)]
                           + [(SELL_CE, Action.BUY, q) for q in (100, 100, 40)]
                           + [(BUY_PE, Action.SELL, q) for q in (100, 100, 40)])
    assert all(o.quantity % SENSEX_LOT == 0 for o in prep.orders)
