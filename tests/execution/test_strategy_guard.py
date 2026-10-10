"""REQ-036 AC-5 (W-026): Strategy Guard, before execution or modification.

Spec: REQ-036 AC-5 "an action that changes the strategy's risk profile shows 'This action changes your strategy's risk
profile' with the consequences before the user can proceed"; ADR-002 (T1 #74-#75).

Core proof, hand-computed from scenario-calculations.md (§1 per-leg expiry P&L, §3 strategy values, §6 golden
condor, 75 units, entries 42.50 / 86.00 / 91.50 / 44.00):
- Before (the §6 golden condor, published): max profit 6,825; max loss 8,175; breakevens 22,909 / 23,491; net premium
  +6,825 (§3: "the §6 Iron Condor at entry -> 91 x 75 = +6,825").
- After REMOVING the bought 23,600 CE (BUY 22,800 PE, SELL 23,000 PE, SELL 23,400 CE):
  net credit per unit = 86.00 + 91.50 - 42.50 = 135.00 -> net premium +10,125 (still a credit: sign unchanged);
  level 0 and 22,800: -42.50 + (86 - 200) + 91.50 = -65.00/unit -> -4,875; 23,000..23,400: +135/unit -> 10,125 = max
  profit; above 23,400 only the short call moves (slope -75/point) -> max loss UNLIMITED (§3 "only the upper tail can
  be UNLIMITED"); breakevens 22,800 + 65/200 x 200 = 22,865 and 23,400 + 135 = 23,535.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest
from partial_inputs import (
    CONTRACTS,
    LOT,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

from ofo.engine import UNLIMITED, Action, Instrument, Leg, Strategy
from ofo.engine.interfaces import ChargesBreakdown, MarginRequirement
from ofo.execution import DataHealth, DataInput, ExecutionAction, ExecutionContext, VersionState
from ofo.execution.partial import PartialChoice, close_partial_strategy, complete_strategy, submit_confirmed
from ofo.instruments.parser import zerodha_listed
from ofo.instruments import Catalogue, EligibilityRegistry, EligibilityStatus
from ofo.instruments.models import Contract
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.guard import (
    RISK_PROFILE_CHANGED,
    GuardBinding,
    GuardRefused,
    RiskProfile,
    StrategyGuard,
    compare_risk,
)
from ofo.strategy.modification import (
    ChangeKind,
    LegChange,
    confirm_modification,
    execute_confirmed_modification,
    prepare_confirmed_modification,
    propose_modification,
)
from ofo.strategy.versions import ExecutionResult, OutcomeKind, Position, ResultStatus, StrategyRecord

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
QTY = 75
SID = "S-1"
GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00")),
))
PRICES = {(leg.instrument, leg.strike, leg.expiry): leg.entry_price for leg in GOLDEN.legs}
PRICES[(Instrument.PE, D("22900"), EXPIRY)] = D("70.00")
REMOVE_LONG_CALL = (LegChange(ChangeKind.REMOVE, Instrument.CE, D("23600"), EXPIRY),)
ROLL = (
    LegChange(ChangeKind.REMOVE, Instrument.PE, D("23000"), EXPIRY),
    LegChange(ChangeKind.ADD, Instrument.PE, D("22900"), EXPIRY, action=Action.SELL, quantity=QTY),
)


def at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def _pos(*lines: tuple[Instrument, str, int]) -> Position:
    return Position(tuple((("NIFTY", i, D(k), EXPIRY), u) for i, k, u in lines))


FILLED = _pos((Instrument.PE, "22800", QTY), (Instrument.PE, "23000", -QTY), (Instrument.CE, "23400", -QTY),
              (Instrument.CE, "23600", QTY))
WITHOUT_LONG_CALL = _pos((Instrument.PE, "22800", QTY), (Instrument.PE, "23000", -QTY),
                         (Instrument.CE, "23400", -QTY))


def executed_record() -> StrategyRecord:
    rec = StrategyRecord(StrategyDefinition.from_engine("NIFTY", GOLDEN), at=T0,
                         clock=lambda: T0 + datetime.timedelta(days=10))
    rec.confirm(rec.propose_execution(at=at(1)).number, at=at(2))
    assert rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, FILLED, at(3), "exec-1")).kind \
        is OutcomeKind.ACTIVATED
    return rec


class _Margin:
    def __init__(self, *totals: str) -> None:
        self.totals = [D(t) for t in totals]
        self.calls = 0

    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        total = self.totals[min(self.calls, len(self.totals) - 1)]
        self.calls += 1
        return MarginRequirement(total=total, source="test")


class _Charges:
    def charges_for(self, strategy: Strategy) -> ChargesBreakdown:
        return ChargesBreakdown(items=(("brokerage", D("236.40")),))


def propose(rec: StrategyRecord, changes: tuple[LegChange, ...], margin: _Margin | None = None):
    return propose_modification(rec, changes, strategy_id=SID, entry_prices=PRICES, ltps=None,
                                margin_planner=margin or _Margin("50000.00"), charges_model=_Charges())


def _catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load([
        zerodha_listed(instrument_token=tok, exchange_token=tok, tradingsymbol=f"NIFTY{k}{i.value}", name="NIFTY",
                 expiry=EXPIRY, strike=D(k), tick_size=D("0.05"), lot_size=QTY, instrument_type=i.value,
                 segment="NFO-OPT", exchange="NFO")
        for (i, k), tok in {(Instrument.PE, "22800"): 900001, (Instrument.PE, "22900"): 900002,
                            (Instrument.PE, "23000"): 900003, (Instrument.CE, "23400"): 900004,
                            (Instrument.CE, "23600"): 900005}.items()
    ])
    return cat


def _eligibility(cat: Catalogue) -> EligibilityRegistry:
    reg = EligibilityRegistry()
    for entry in cat.all_entries():
        reg.record(EligibilityStatus(entry.contract.id, True, T0))
    return reg


def _context(version_number: int) -> ExecutionContext:
    return ExecutionContext(
        strategy_id=SID, version_id=f"v{version_number}", actor="user:U-1", underlying="NIFTY",
        action=ExecutionAction.ADJUSTMENT, as_of=at(20), market_open=True, broker_connected=True, session_valid=True,
        pro_entitled=True, version_state=VersionState.PROPOSED, rules_valid=True, dependencies_satisfied=True,
        data_health={d: DataHealth.HEALTHY for d in DataInput}, margin_available=D("500000.00"),
        margin_required=D("50000.00"), reconciliation_blocked_strategy_ids=frozenset(), charges_estimate=D("236.40"),
    )


def _gate_kwargs(version_number: int = 2) -> dict:
    cat = _catalogue()
    return dict(strategy_id=SID, context=_context(version_number), catalogue=cat, eligibility=_eligibility(cat))


# -- core ---------------------------------------------------------------------------------------------------------

def test_core_removing_the_bought_23600_ce_is_a_risk_profile_change_needing_acknowledgement():
    """AC-5 (core): removing the bought 23,600 CE turns the upside max loss from 8,175 into UNLIMITED; the guard
    returns the exact message and the hand-computed before/after, and nothing proceeds without its own token."""
    rec = executed_record()
    decision = propose(rec, REMOVE_LONG_CALL).guard
    assert decision.changes_risk_profile is True
    assert decision.message == "This action changes your strategy's risk profile" == RISK_PROFILE_CHANGED
    rows = {c.metric: (c.before, c.after, c.changed) for c in decision.change.consequences}
    assert rows["max profit"] == (D("6825"), D("10125"), True)
    assert rows["max loss"] == (D("8175"), UNLIMITED, True)
    assert rows["breakevens"] == ((D("22909"), D("23491")), (D("22865"), D("23535")), True)
    assert rows["net premium"] == (D("6825"), D("10125"), False)  # still a credit: the sign did not change
    assert rows["margin"] == (D("50000.00"), D("50000.00"), False)
    assert rows["position"] == (True, True, False)
    assert isinstance(decision.acknowledgement, str) and len(decision.acknowledgement) >= 40

    confirm_modification(rec, REMOVE_LONG_CALL, at=at(10))
    result = ExecutionResult(2, ResultStatus.COMPLETE, WITHOUT_LONG_CALL, at(12), "adj-1")
    with pytest.raises(GuardRefused, match="This action changes your strategy's risk profile"):
        prepare_confirmed_modification(rec, 2, **_gate_kwargs())
    with pytest.raises(GuardRefused):
        execute_confirmed_modification(rec, 2, result=result, **_gate_kwargs())
    with pytest.raises(GuardRefused):  # a forged token
        execute_confirmed_modification(rec, 2, result=result, acknowledgement="x" * 43, **_gate_kwargs())
    assert rec.active_version.number == 1 and rec.proposed_version.number == 2  # nothing applied

    assert not prepare_confirmed_modification(rec, 2, acknowledgement=decision.acknowledgement, **_gate_kwargs()).blocked
    outcome = execute_confirmed_modification(rec, 2, result=result, acknowledgement=decision.acknowledgement,
                                             **_gate_kwargs())
    assert outcome.kind is OutcomeKind.ACTIVATED and rec.active_version.number == 2


def test_ac5_a_change_that_alters_no_risk_metric_is_not_flagged():
    """AC-5: the same position written differently (the 23,600 CE split 50 + 25, legs reordered) has identical engine
    metrics and margin: not flagged, no token, and it proceeds with no acknowledgement."""
    split = Strategy((
        Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 50, D("44.00")),
        Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 25, D("44.00")),
        GOLDEN.legs[2], GOLDEN.legs[0], GOLDEN.legs[1],
    ))
    guard = StrategyGuard()
    binding = GuardBinding(SID, "v1", "p-1")
    decision = guard._issue(binding, GOLDEN, split, D("50000"), D("50000"))
    assert decision.changes_risk_profile is False and decision.message is None and decision.acknowledgement is None
    assert all(not c.changed for c in decision.change.consequences)
    assert guard.redeem(binding, None) is decision


def test_ac5_completing_the_planned_strategy_is_not_flagged_and_sends_without_acknowledgement(catalogue, eligibility):
    """AC-5 on the execution path: Complete Strategy (three legs filled, 23,600 CE rejected) leads back to exactly the
    planned version, so the guard does not flag it and the one missing order is sent without any token."""
    book = book_with_three_filled()
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book, FakePlanner(), entry_context(),
                             catalogue, eligibility)
    assert prep.ready and prep.guard is not None and prep.guard.changes_risk_profile is False
    submitter = FakeSubmitter()
    result = submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter)
    assert [(o.contract, o.side, o.quantity) for o in submitter.sent] == [(CONTRACTS[3], Action.BUY, LOT)]
    assert result.submitted == (("leg-4", "NEW-1"),)


def _close_prep(catalogue, eligibility):  # noqa: ANN001, ANN202
    book = book_with_three_filled()
    positions = three_positions((D("40.00"), D("80.00"), D("120.00")))
    prep = close_partial_strategy(plan(), FakeBroker(positions, statuses()), book, FakePlanner(), entry_context(),
                                  catalogue, eligibility)
    assert prep.ready
    return book, prep


def test_ac5_execution_path_close_is_flagged_and_refused_without_its_own_token(catalogue, eligibility):
    """AC-5 on the execution path: closing the filled legs leaves no position (planned 65-unit condor: max profit
    91 x 65 = 5,915, max loss 109 x 65 = 7,085 -> 0 / 0). Without the token, or with a forged one, nothing is sent."""
    book, prep = _close_prep(catalogue, eligibility)
    decision = prep.guard
    assert decision.message == RISK_PROFILE_CHANGED and prep.reason.startswith(RISK_PROFILE_CHANGED)
    rows = {c.metric: (c.before, c.after) for c in decision.change.consequences}
    assert rows["max profit"] == (D("5915.00"), D("0"))
    assert rows["max loss"] == (D("7085.00"), D("0"))
    assert rows["breakevens"] == ((D("22909"), D("23491")), ())
    assert rows["position"] == (True, False)
    submitter = FakeSubmitter()
    for ack in (None, "forged-token", decision.acknowledgement + "x"):
        with pytest.raises(GuardRefused):
            submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                             submitter=submitter, acknowledgement=ack)
    assert submitter.sent == [] and len(book.views_for("S-1")) == 4  # nothing sent, nothing registered
    result = submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                              submitter=submitter, acknowledgement=decision.acknowledgement)
    assert len(result.submitted) == 3 and len(submitter.sent) == 3


def test_ac5_token_reused_after_the_proposal_changed_is_refused(catalogue, eligibility):
    """AC-5: the token is bound to the exact orders; editing the prepared orders after the guard ran (a larger
    quantity) makes the same token worthless and nothing is sent."""
    book, prep = _close_prep(catalogue, eligibility)
    token = prep.guard.acknowledgement
    with pytest.raises(AttributeError):  # a flow-made preparation cannot be changed
        prep.orders = ()
    # even through the in-process reach-around, the seal over the orders refuses the changed quantity
    object.__setattr__(prep, "orders", (dataclasses.replace(prep.orders[0], quantity=prep.orders[0].quantity * 2),)
                       + prep.orders[1:])
    submitter = FakeSubmitter()
    with pytest.raises(ValueError, match="changed after it was checked"):
        submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                         submitter=submitter, acknowledgement=token)
    assert submitter.sent == []


def test_ac5_token_of_another_proposal_is_refused():
    """AC-5: the token issued for removing the 23,600 CE cannot pass the roll that was actually confirmed."""
    rec = executed_record()
    remove_token = propose(rec, REMOVE_LONG_CALL).guard.acknowledgement
    roll_token = propose(rec, ROLL).guard.acknowledgement
    assert remove_token and roll_token and remove_token != roll_token
    confirm_modification(rec, ROLL, at=at(10))
    with pytest.raises(GuardRefused):
        prepare_confirmed_modification(rec, 2, acknowledgement=remove_token, **_gate_kwargs())
    assert not prepare_confirmed_modification(rec, 2, acknowledgement=roll_token, **_gate_kwargs()).blocked


def test_ac5_a_token_works_once_only():
    """AC-5: a redeemed decision is gone; the same token (and a no-change clearance) cannot be used again."""
    guard = StrategyGuard()
    binding = GuardBinding(SID, "v1", "p-2")
    decision = guard._issue(binding, GOLDEN, Strategy(GOLDEN.legs[:3]), D("1"), D("1"))
    guard.redeem(binding, decision.acknowledgement)
    with pytest.raises(GuardRefused):
        guard.redeem(binding, decision.acknowledgement)
    clear = GuardBinding(SID, "v1", "p-3")
    guard._issue(clear, GOLDEN, GOLDEN, D("1"), D("1"))
    guard.redeem(clear, None)
    with pytest.raises(GuardRefused):
        guard.redeem(clear, None)


def test_ac5_an_action_the_guard_never_checked_is_refused():
    """AC-5: with no Before/After step at all, the modification cannot reach the gate (fail closed)."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    with pytest.raises(GuardRefused, match="has not checked"):
        prepare_confirmed_modification(rec, 2, acknowledgement="anything", **_gate_kwargs())


def test_ac5_margin_only_change_and_unknown_margin_are_flagged():
    """AC-5, orchestrator default OD-G2: identical payoff with a different margin is a risk-profile change; an unknown
    margin on either side is also a change (cannot be shown unchanged). Equal known margins are not."""
    guard = StrategyGuard()
    changed = guard._issue(GuardBinding(SID, "v1", "m-1"), GOLDEN, GOLDEN, D("50000"), D("52000"))
    assert changed.changes_risk_profile and [c.metric for c in changed.change.consequences if c.changed] == ["margin"]
    unknown = guard._issue(GuardBinding(SID, "v1", "m-2"), GOLDEN, GOLDEN, D("50000"), None)
    assert unknown.changes_risk_profile and unknown.acknowledgement
    same = guard._issue(GuardBinding(SID, "v1", "m-3"), GOLDEN, GOLDEN, D("50000"), D("50000.00"))
    assert not same.changes_risk_profile


def test_ac5_net_premium_sign_flip_alone_is_flagged():
    """AC-5, OD-G1: net premium counts by sign. Removing both short legs turns the +6,825 credit into a debit of
    (42.50 + 44.00) x 75 = -6,487.50."""
    guard = StrategyGuard()
    debit = Strategy((GOLDEN.legs[0], GOLDEN.legs[3]))
    decision = guard._issue(GuardBinding(SID, "v1", "n-1"), GOLDEN, debit, D("1"), D("1"))
    rows = {c.metric: (c.before, c.after, c.changed) for c in decision.change.consequences}
    assert rows["net premium"] == (D("6825"), D("-6487.50"), True)


def test_ac5_both_margins_unknown_is_flagged():
    """AC-5, OD-G2 (fail closed): with no margin figure on either side the platform cannot show it unchanged."""
    decision = StrategyGuard()._issue(GuardBinding(SID, "v1", "m-4"), GOLDEN, GOLDEN, None, None)
    assert decision.changes_risk_profile
    assert [c.metric for c in decision.change.consequences if c.changed] == ["margin"]


def test_ac5_a_modification_token_is_consumed_by_execution():
    """AC-5: a PARTIAL result keeps the proposal pending (W-012), yet the token that executed it once cannot
    execute it again: the user acknowledges again for a second attempt."""
    rec = executed_record()
    token = propose(rec, REMOVE_LONG_CALL).guard.acknowledgement
    confirm_modification(rec, REMOVE_LONG_CALL, at=at(10))
    partial = ExecutionResult(2, ResultStatus.PARTIAL, FILLED, at(12), "adj-partial")
    outcome = execute_confirmed_modification(rec, 2, result=partial, acknowledgement=token, **_gate_kwargs())
    assert outcome.kind is OutcomeKind.PARTIAL and rec.proposed_version.number == 2
    again = ExecutionResult(2, ResultStatus.COMPLETE, WITHOUT_LONG_CALL, at(13), "adj-2")
    with pytest.raises(GuardRefused):
        execute_confirmed_modification(rec, 2, result=again, acknowledgement=token, **_gate_kwargs())


def test_ac5_the_seal_covers_the_price(catalogue, eligibility):
    """AC-5 (verifier's surviving mutant M9): a changed PRICE alone, set through the reach-around, is refused."""
    book, prep = _close_prep(catalogue, eligibility)
    object.__setattr__(prep, "orders", (dataclasses.replace(prep.orders[0], price=D("0.05")),) + prep.orders[1:])
    submitter = FakeSubmitter()
    with pytest.raises(ValueError, match="changed after it was checked"):
        submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                         submitter=submitter, acknowledgement=prep.guard.acknowledgement)
    assert submitter.sent == []


def test_ac5_position_row_alone_flags_a_change():
    """AC-5 (verifier's surviving mutant M13): two profiles equal in every number but whether a position remains
    are a risk-profile change, on the "position" row only."""
    flat_with, flat_without = (RiskProfile(D("0"), D("0"), (), D("0"), D("0"), has) for has in (True, False))
    change = compare_risk(flat_with, flat_without)
    assert change.changes_risk_profile
    assert [c.metric for c in change.consequences if c.changed] == ["position"]


_NON_ASCII_ACKS = ("Ä" * 43, "é" * 20, "ı" + "x" * 42, "\ud800")


def test_174_non_ascii_acknowledgement_is_refused_on_the_execution_path_never_raises(catalogue, eligibility):
    """#174: a non-ASCII acknowledgement is refused like any wrong one (GuardRefused, not TypeError); nothing sent."""
    book, prep = _close_prep(catalogue, eligibility)
    submitter = FakeSubmitter()
    for ack in _NON_ASCII_ACKS:
        with pytest.raises(GuardRefused):
            submit_confirmed(prep, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-1",
                             submitter=submitter, acknowledgement=ack)
    assert submitter.sent == [] and len(book.views_for("S-1")) == 4


def test_174_non_ascii_acknowledgement_is_refused_by_the_guard_redeem_never_raises():
    """#174: StrategyGuard.redeem refuses a non-ASCII token with GuardRefused; the right token still works after."""
    guard = StrategyGuard()
    binding = GuardBinding(SID, "v1", "p-174")
    decision = guard._issue(binding, GOLDEN, Strategy(GOLDEN.legs[:3]), D("1"), D("1"))
    for ack in _NON_ASCII_ACKS:
        with pytest.raises(GuardRefused):
            guard.redeem(binding, ack)
    guard.redeem(binding, decision.acknowledgement)
