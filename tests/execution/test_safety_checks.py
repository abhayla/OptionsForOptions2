"""REQ-059 AC-1 / AC-2: the pre-execution gate blocks on every failed check, explains it, and logs it.

Core proof (W-014): with every check true the golden Iron Condor passes on the REAL instrument list; flipping any
single AC-1 check (mutation style) blocks with exactly that check's code and reason, and the strategy is unchanged.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime
import logging
import re
from decimal import Decimal as D
from typing import Callable

import pytest

from execution_inputs import AS_OF, EXPIRY, all_true_context, condor_legs, find_token
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import (
    CheckCode,
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    VersionState,
    check_pre_execution,
)
from ofo.instruments import Catalogue, EligibilityRegistry, EligibilityStatus, parse_instruments_csv
from execution_inputs import FIXTURE

Inputs = tuple[Strategy, ExecutionContext, Catalogue, EligibilityRegistry]

# ADR-003 forbidden wording (plus "you should"): no reason text may carry it.
FORBIDDEN = re.compile(r"you should|best trade|best adjustment|recommended|guarantee|risk-free|certain profit", re.I)


def _ctx(**overrides: object) -> Callable[[Strategy, Catalogue, EligibilityRegistry], Inputs]:
    return lambda s, c, e: (s, all_true_context(**overrides), c, e)


def _strike_off_ladder(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    legs = list(s.legs)
    legs[1] = dataclasses.replace(legs[1], strike=D("23010"))
    return Strategy(tuple(legs)), all_true_context(), c, e


def _unlisted(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    token = find_token(c, "PE", "23000")
    c.update([x for x in parse_instruments_csv(FIXTURE) if x.instrument_token != token])
    return s, all_true_context(), c, e


def _not_eligible(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    e.record(EligibilityStatus(find_token(c, "CE", "23400"), False, AS_OF, "OI limit reached"))
    return s, all_true_context(), c, e


def _eligibility_unknown(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    fresh = EligibilityRegistry()
    skip = find_token(c, "CE", "23600")
    for entry in c.all_entries():
        if entry.contract.instrument_token != skip:
            fresh.record(EligibilityStatus(entry.contract.instrument_token, True, AS_OF))
    return s, all_true_context(), c, fresh


def _ambiguous(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    (orig,) = [x for x in parse_instruments_csv(FIXTURE) if x.instrument_token == find_token(c, "PE", "22800")]
    c.load([dataclasses.replace(orig, instrument_token=999_000_001, exchange_token=999_001)])
    return s, all_true_context(), c, e


def _bad_quantity(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    return Strategy(condor_legs(quantity=100)), all_true_context(), c, e


def _expired(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    return s, all_true_context(as_of=AS_OF.replace(month=10, day=7)), c, e


def _duplicate(s: Strategy, c: Catalogue, e: EligibilityRegistry) -> Inputs:
    return Strategy(s.legs + (s.legs[0],)), all_true_context(), c, e


_stale = {d: DataHealth.HEALTHY for d in DataInput} | {DataInput.LEG_PRICES: DataHealth.STALE}
_missing = {d: DataHealth.HEALTHY for d in DataInput if d is not DataInput.UNDERLYING_PRICE}

# (case id, mutation, expected code, expected reason — exact string or a regex fragment)
MUTATIONS = [
    ("market-closed", _ctx(market_open=False), CheckCode.MARKET_CLOSED,
     "The market is closed. Orders can be placed once it opens."),
    ("market-unknown", _ctx(market_open=None), CheckCode.MARKET_CLOSED,
     "We could not confirm that the market is open. Execution is paused until it is confirmed."),
    ("version-superseded", _ctx(version_state=VersionState.SUPERSEDED), CheckCode.VERSION_NOT_EXECUTABLE,
     "This version of the strategy is superseded. This action executes only a version that is active."),
    ("version-proposed-for-entry", _ctx(version_state=VersionState.PROPOSED), CheckCode.VERSION_NOT_EXECUTABLE,
     "This version of the strategy is proposed. This action executes only a version that is active."),
    ("version-unknown", _ctx(version_state=None), CheckCode.VERSION_NOT_EXECUTABLE,
     "This version of the strategy is unknown. This action executes only a version that is active."),
    ("broker-disconnected", _ctx(broker_connected=False), CheckCode.BROKER_NOT_CONNECTED,
     "Your Zerodha account is not connected. Connect it to continue."),
    ("broker-unknown", _ctx(broker_connected=None), CheckCode.BROKER_NOT_CONNECTED,
     "We could not confirm your Zerodha connection. Reconnect to continue."),
    ("session-expired", _ctx(session_valid=False), CheckCode.SESSION_INVALID,
     "Your Zerodha session has expired. Reconnect to continue."),
    ("session-unknown", _ctx(session_valid=None), CheckCode.SESSION_INVALID,
     "We could not confirm your Zerodha session. Reconnect to continue."),
    ("not-pro", _ctx(pro_entitled=False), CheckCode.ENTITLEMENT_REQUIRED,
     "New entries and adjustments that add or change positions need Pro. Exiting, or closing or reducing legs of "
     "an active strategy, stays available on every plan."),
    ("data-stale", _ctx(data_health=_stale), CheckCode.DATA_UNHEALTHY,
     "Market data needed for execution (leg prices) is out of date. Execution is paused until it is current."),
    ("data-missing", _ctx(data_health=_missing), CheckCode.DATA_UNHEALTHY,
     "Market data needed for execution (underlying price) has no status. Execution is paused until it is current."),
    ("rules-invalid", _ctx(rules_valid=False), CheckCode.RULES_INVALID,
     "This strategy's rules are not valid. Review them to continue."),
    ("dependencies", _ctx(dependencies_satisfied=False), CheckCode.DEPENDENCIES_UNSATISFIED,
     "An order this execution depends on is not in place yet (for example a protective leg)."),
    ("margin-short", _ctx(margin_available=D("48210.74")), CheckCode.MARGIN_INSUFFICIENT,
     "Available margin ₹48,210.74 is less than the estimated ₹48,210.75 this strategy needs. Zerodha's figure is "
     "final. No order has been submitted."),
    ("margin-unknown", _ctx(margin_available=None), CheckCode.MARGIN_INSUFFICIENT,
     "We could not confirm your available margin with Zerodha. Execution is paused."),
    ("reconciliation", _ctx(reconciliation_blocked_strategy_ids=frozenset({"S-1"})), CheckCode.RECONCILIATION_MISMATCH,
     "Your Zerodha positions for this strategy do not match what we recorded. Resolve the mismatch to continue."),
    ("underlying", _ctx(underlying="BANKNIFTY"), CheckCode.UNDERLYING_UNSUPPORTED,
     "BANKNIFTY is not supported. Supported underlyings: NIFTY, SENSEX."),
    ("strike-not-found", _strike_off_ladder, CheckCode.CONTRACT_NOT_FOUND,
     "Leg 2 (SELL NIFTY 23,010 PE, expiry 06 Oct 2026) does not exist in Zerodha's instrument list. Strikes you "
     "could consider instead: 23,000 or 23,050. Your strategy has not been changed."),
    ("contract-ambiguous", _ambiguous, CheckCode.CONTRACT_AMBIGUOUS,
     "Leg 1 (BUY NIFTY 22,800 PE, expiry 06 Oct 2026) matches more than one contract in the instrument list."),
    ("contract-unlisted", _unlisted, CheckCode.CONTRACT_NOT_LISTED,
     "Leg 2 (SELL NIFTY 23,000 PE, expiry 06 Oct 2026) is no longer listed by Zerodha. Strikes you could consider "
     "instead: 22,950 or 23,050. Your strategy has not been changed."),
    ("contract-not-eligible", _not_eligible, CheckCode.CONTRACT_NOT_ELIGIBLE,
     "Leg 3 (SELL NIFTY 23,400 CE, expiry 06 Oct 2026) is currently unavailable on Zerodha. Zerodha isn't "
     "accepting fresh orders for this contract right now. Strikes you could consider instead: 23,350 or 23,450. "
     "Your strategy has not been changed."),
    ("eligibility-unknown", _eligibility_unknown, CheckCode.CONTRACT_NOT_ELIGIBLE,
     "Leg 4 (BUY NIFTY 23,600 CE, expiry 06 Oct 2026) has not been confirmed as available on Zerodha yet. "
     "Refresh availability to continue. Strikes you could consider instead: 23,550 or 23,650. Your strategy has "
     "not been changed."),
    ("quantity", _bad_quantity, CheckCode.QUANTITY_INVALID, None),  # 4 legs; reason checked in test_validation
    ("expired", _expired, CheckCode.EXPIRY_PASSED, None),
    ("duplicate", _duplicate, CheckCode.DUPLICATE_LEG,
     "Leg 5 (BUY NIFTY 22,800 PE, expiry 06 Oct 2026) is the same contract as leg 1. The legs have not been "
     "combined; edit the strategy to keep one or combine them yourself."),
]


def test_core_all_checks_true_golden_condor_passes(condor, catalogue, eligibility):
    """AC-1: with every context check true, the golden Iron Condor on the real instrument list is not blocked."""
    before = copy.deepcopy(condor)
    result = check_pre_execution(condor, all_true_context(), catalogue, eligibility)
    assert result.failures == ()
    assert result.blocked is False
    assert set(result.passed) == set(CheckCode)
    assert result.not_checked == ()
    assert result.max_loss == D("7085.00")  # (200 - 91) x 65: the §6 condor (8175 at 75 units) at one lot of 65
    assert condor == before


def test_mutation_table_covers_every_check_code():
    """AC-1: the mutation loop below flips every check the gate has; a new code without a mutation fails here."""
    assert {code for _, _, code, _ in MUTATIONS} == set(CheckCode)


@pytest.mark.parametrize("case,mutate,code,reason", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_flipping_one_check_blocks_with_exactly_that_code(case, mutate, code, reason, condor, catalogue, eligibility):
    """AC-1: flip one check -> blocked, only that check's code, its reason, strategy unchanged."""
    strategy, ctx, cat, elig = mutate(condor, catalogue, eligibility)
    before = copy.deepcopy(strategy)
    legs_before = strategy.legs
    result = check_pre_execution(strategy, ctx, cat, elig)
    assert result.blocked is True
    assert result.failed_codes == {code}, [f.reason for f in result.failures]
    assert code not in result.passed
    if reason is not None:
        assert [f.reason for f in result.failures] == [reason]
    assert strategy == before and strategy.legs is legs_before


def test_multiple_failures_are_all_reported_in_order(condor, catalogue, eligibility):
    """AC-2: several failures at once are ALL reported (not just the first), each with its own reason."""
    ctx = all_true_context(market_open=False, session_valid=False, margin_available=D("100"))
    result = check_pre_execution(Strategy(condor_legs(quantity=130 + 1)), ctx, catalogue, eligibility)
    assert [f.code for f in result.failures] == [
        CheckCode.MARKET_CLOSED,
        CheckCode.SESSION_INVALID,
        CheckCode.MARGIN_INSUFFICIENT,
        CheckCode.QUANTITY_INVALID,
        CheckCode.QUANTITY_INVALID,
        CheckCode.QUANTITY_INVALID,
        CheckCode.QUANTITY_INVALID,
    ]
    assert [f.leg_number for f in result.failures[3:]] == [1, 2, 3, 4]
    assert result.blocked is True
    assert CheckCode.BROKER_NOT_CONNECTED in result.passed


def test_blocked_event_is_logged_with_every_code(condor, catalogue, eligibility, caplog):
    """AC-2: a blocked check is logged with the strategy, the action and every failed code."""
    ctx = all_true_context(broker_connected=False, reconciliation_blocked_strategy_ids=frozenset({"S-1"}))
    with caplog.at_level(logging.INFO, logger="ofo.execution.safety"):
        check_pre_execution(condor, ctx, catalogue, eligibility)
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert record.getMessage() == (
        "pre-execution blocked strategy=S-1 action=NEW_ENTRY codes=BROKER_NOT_CONNECTED,RECONCILIATION_MISMATCH"
    )


def test_every_reason_is_plain_decision_support_wording(condor, catalogue, eligibility):
    """AC-2 (ADR-003): every failure reason across the mutation table is non-empty and free of advice wording."""
    seen = 0
    for _, mutate, _, _ in MUTATIONS:
        cat = Catalogue()
        cat.load(parse_instruments_csv(FIXTURE))
        elig = EligibilityRegistry()
        for entry in cat.all_entries():
            elig.record(EligibilityStatus(entry.contract.instrument_token, True, AS_OF))
        result = check_pre_execution(*mutate(Strategy(condor_legs()), cat, elig))
        for failure in result.failures:
            assert failure.reason.strip() and not FORBIDDEN.search(failure.reason), failure.reason
            seen += 1
    assert seen >= len(MUTATIONS)


def test_exit_allowed_for_limited_user_new_entry_blocked(condor, catalogue, eligibility):
    """AC-1 (ADR-037): a Limited user (no Pro) may exit an active strategy; a new entry or adjustment is blocked."""
    exit_result = check_pre_execution(
        condor, all_true_context(pro_entitled=False, action=ExecutionAction.EXIT), catalogue, eligibility
    )
    assert exit_result.failures == ()
    assert CheckCode.ENTITLEMENT_REQUIRED not in exit_result.passed  # not applicable to an exit
    entry = check_pre_execution(condor, all_true_context(pro_entitled=False), catalogue, eligibility)
    assert entry.failed_codes == {CheckCode.ENTITLEMENT_REQUIRED}
    adjust = check_pre_execution(
        condor,
        all_true_context(pro_entitled=False, action=ExecutionAction.ADJUSTMENT, version_state=VersionState.PROPOSED),
        catalogue,
        eligibility,
    )
    assert adjust.failed_codes == {CheckCode.ENTITLEMENT_REQUIRED}


def test_adjustment_executes_only_a_proposed_version(condor, catalogue, eligibility):
    """AC-1: 'version active/proposed as appropriate' - an adjustment of an ACTIVE version is refused."""
    ok = all_true_context(action=ExecutionAction.ADJUSTMENT, version_state=VersionState.PROPOSED)
    assert check_pre_execution(condor, ok, catalogue, eligibility).failures == ()
    bad = all_true_context(action=ExecutionAction.ADJUSTMENT, version_state=VersionState.ACTIVE)
    assert check_pre_execution(condor, bad, catalogue, eligibility).failed_codes == {CheckCode.VERSION_NOT_EXECUTABLE}


def test_reconciliation_block_on_another_strategy_does_not_block_this_one(condor, catalogue, eligibility):
    """AC-1 (REQ-060 AC-7): a mismatch blocks only its own strategy."""
    other = all_true_context(reconciliation_blocked_strategy_ids=frozenset({"S-2", "S-3"}))
    assert check_pre_execution(condor, other, catalogue, eligibility).blocked is False
    mine = all_true_context(strategy_id="S-2", reconciliation_blocked_strategy_ids=frozenset({"S-2", "S-3"}))
    assert check_pre_execution(condor, mine, catalogue, eligibility).failed_codes == {CheckCode.RECONCILIATION_MISMATCH}


def test_reconciliation_mismatch_blocks_an_exit_too(condor, catalogue, eligibility):
    """AC-1 (ADR-019 Q200: Reconciliation Required -> execute no): exits are blocked by this strategy's mismatch."""
    ctx = all_true_context(action=ExecutionAction.EXIT, reconciliation_blocked_strategy_ids=frozenset({"S-1"}))
    assert check_pre_execution(condor, ctx, catalogue, eligibility).failed_codes == {CheckCode.RECONCILIATION_MISMATCH}


def test_margin_exactly_equal_passes(condor, catalogue, eligibility):
    """AC-1: margin sufficient means available >= required; equal passes, one paisa short blocks (above)."""
    ctx = all_true_context(margin_available=D("48210.75"))
    assert check_pre_execution(condor, ctx, catalogue, eligibility).blocked is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"market_open": 1},
        {"session_valid": "yes"},
        {"as_of": AS_OF.replace(tzinfo=None)},
        {"margin_available": 150000.0},
        {"margin_required": D("-1")},
        {"charges_estimate": D("NaN")},
        {"data_health": {"LEG_PRICES": DataHealth.HEALTHY}},
        {"data_health": {DataInput.LEG_PRICES: "HEALTHY"}},
        {"reconciliation_blocked_strategy_ids": "S-1"},
        {"strategy_id": " "},
        {"version_state": "ACTIVE"},
        {"action": "EXIT"},
    ],
    ids=lambda o: next(iter(o)),
)
def test_malformed_context_is_refused(overrides):
    """AC-1 (fail closed): a malformed input is refused at construction, never defaulted to a passing value."""
    with pytest.raises(ValueError):
        all_true_context(**overrides)


def test_context_cannot_be_changed_after_construction():
    """AC-1: a raw state change bypassing construction (e.g. flipping market_open) is refused."""
    ctx = all_true_context(market_open=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.market_open = True  # type: ignore[misc]


def test_futures_leg_is_checked_against_the_real_futures_contract(catalogue, eligibility):
    """AC-1: a futures leg matches the real NIFTY 27 Oct 2026 future (lot 65); a wrong expiry is not found."""
    import datetime

    fut = Leg(Action.BUY, Instrument.FUT, None, datetime.date(2026, 10, 27), 65, D("23250"))
    assert check_pre_execution(Strategy((fut,)), all_true_context(), catalogue, eligibility).failures == ()
    wrong = dataclasses.replace(fut, expiry=EXPIRY)
    result = check_pre_execution(Strategy((wrong,)), all_true_context(), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.CONTRACT_NOT_FOUND, CheckCode.QUANTITY_INVALID}
    assert all(f.alternatives == () for f in result.failures)


# ---------------------------------------------------------------- ADR-037 by actor intent (fix round 1)

PRO_REASON = (
    "New entries and adjustments that add or change positions need Pro. Exiting, or closing or reducing legs of an "
    "active strategy, stays available on every plan."
)
ACTIVE_TWO_LOTS = condor_legs(quantity=130)


def _limited_adjustment(
    proposed: tuple[Leg, ...], pro: bool | None = False, active: tuple[Leg, ...] | None = ACTIVE_TWO_LOTS
) -> tuple[Strategy, ExecutionContext]:
    ctx = all_true_context(action=ExecutionAction.ADJUSTMENT, version_state=VersionState.PROPOSED,
                           pro_entitled=pro, active_legs=active)
    return Strategy(proposed), ctx


def _replace_leg(index: int, **changes: object) -> tuple[Leg, ...]:
    legs = list(ACTIVE_TWO_LOTS)
    legs[index] = dataclasses.replace(legs[index], **changes)
    return tuple(legs)


NEAR = datetime.date(2026, 9, 29)  # real NIFTY options AND futures expiry in the fixture


def _l(action: Action, kind: Instrument, strike: str | None, qty: int = 65, price: str = "50.00",
       expiry: datetime.date = EXPIRY) -> Leg:
    return Leg(action, kind, None if strike is None else D(strike), expiry, qty, D(price))


B, S, CE, PE, FUT = Action.BUY, Action.SELL, Instrument.CE, Instrument.PE, Instrument.FUT
IC = ACTIVE_TWO_LOTS
IC_PUT_2_TO_1 = (IC[0], dataclasses.replace(IC[1], quantity=65), IC[2], IC[3])
COVERED_CALL = (_l(B, FUT, None, price="23250.00", expiry=NEAR), _l(S, CE, "23400", expiry=NEAR))
PROTECTIVE_PUT = (_l(B, FUT, None, price="23250.00", expiry=NEAR), _l(B, PE, "23200", expiry=NEAR))
RATIO = (_l(B, CE, "23400"), _l(S, CE, "23600", qty=130))
TWO_BULL_PUTS = (_l(S, PE, "23000"), _l(B, PE, "22800"), _l(S, PE, "22600"), _l(B, PE, "22400"))
STRADDLE = (_l(B, CE, "23200", expiry=NEAR), _l(B, PE, "23200", expiry=NEAR))
CALENDAR = (_l(S, CE, "23400", expiry=NEAR), _l(B, CE, "23400"))

# (case, active legs, proposed legs, allowed for a Limited user) - the independent reviewer's rule-5 table.
RULE5_TABLE = [
    ("ic-close-bought-22800-pe-only", IC, IC[1:], False),  # premium-free -26,000 -> -2,990,000
    ("ic-close-whole-put-spread", IC, IC[2:], True),  # -26,000 -> -26,000
    ("ic-sell-23000-pe-2-to-1", IC, IC_PUT_2_TO_1, True),
    ("ic-every-leg-2-to-1", IC, condor_legs(quantity=65), True),  # -26,000 -> -13,000
    ("covered-call-close-short-ce", COVERED_CALL, COVERED_CALL[:1], True),
    ("covered-call-close-long-fut", COVERED_CALL, COVERED_CALL[1:], False),  # -> UNLIMITED
    ("ratio-1x2-close-long-ce", RATIO, RATIO[1:], False),  # upper slope -65 -> -130 (per unit: -1 -> -2 lots)
    ("ratio-1x2-short-2-to-1", RATIO, (RATIO[0], dataclasses.replace(RATIO[1], quantity=65)), True),  # UNLIMITED -> 0
    ("two-bull-puts-close-l22800-and-s22600", TWO_BULL_PUTS, (TWO_BULL_PUTS[0], TWO_BULL_PUTS[3]), False),
    ("protective-put-close-the-put", PROTECTIVE_PUT, PROTECTIVE_PUT[:1], False),
    ("long-straddle-close-the-ce", STRADDLE, STRADDLE[1:], True),
    ("calendar-close-far-long-only", CALENDAR, CALENDAR[:1], False),
    ("calendar-close-near-short-only", CALENDAR, CALENDAR[1:], True),
    # Rule 5c isolated: closing the long would fail 5d, but every leg halves by the same share.
    ("calendar-every-leg-2-to-1", tuple(dataclasses.replace(x, quantity=130) for x in CALENDAR), CALENDAR, True),
]


@pytest.mark.parametrize("case,active,proposed,allowed", RULE5_TABLE, ids=[r[0] for r in RULE5_TABLE])
def test_rule5_limited_adjustment_table(case, active, proposed, allowed, catalogue, eligibility):
    """AC-1 (ADR-037, REQ-059 Gate decisions rule 5): a Limited user may adjust only if no position grows AND the
    premium-free worst case at expiry is no worse (same-share reduction always; calendars only close shorts)."""
    strategy, ctx = _limited_adjustment(proposed, active=active)
    result = check_pre_execution(strategy, ctx, catalogue, eligibility)
    if allowed:
        assert result.failures == (), [f.reason for f in result.failures]
    else:
        assert result.failed_codes == {CheckCode.ENTITLEMENT_REQUIRED}, [f.reason for f in result.failures]


@pytest.mark.parametrize("case,active,proposed,allowed", RULE5_TABLE, ids=[r[0] for r in RULE5_TABLE])
def test_rule5_pro_user_passes_every_case(case, active, proposed, allowed, catalogue, eligibility):
    """AC-1: a Pro user passes every rule-5 case."""
    strategy, ctx = _limited_adjustment(proposed, pro=True, active=active)
    assert check_pre_execution(strategy, ctx, catalogue, eligibility).failures == ()


def test_rule5_blocked_reason_names_the_premium_free_worst_cases(catalogue, eligibility):
    """AC-1: the Pro reason for a larger worst case states both premium-free numbers (reviewer: -26,000 ->
    -2,990,000 when only the bought 22,800 PE wing of the 2-lot condor is closed)."""
    strategy, ctx = _limited_adjustment(IC[1:])
    (failure,) = check_pre_execution(strategy, ctx, catalogue, eligibility).failures
    assert failure.reason == (
        "This adjustment makes the strategy's worst case at expiry larger (option premiums excluded): from a loss "
        "of ₹26,000.00 to a loss of ₹2,990,000.00. Adjustments that add risk need Pro. Exiting, or closing or "
        "reducing legs without a larger worst case, stays available on every plan."
    )


def test_rule5_unlimited_after_finite_before_says_unlimited(catalogue, eligibility):
    """AC-1: closing the long future of a covered call leaves a naked short call: 'to an unlimited loss'."""
    strategy, ctx = _limited_adjustment(COVERED_CALL[1:], active=COVERED_CALL)
    (failure,) = check_pre_execution(strategy, ctx, catalogue, eligibility).failures
    assert "to an unlimited loss" in failure.reason


def test_closing_all_four_legs_is_an_exit_open_to_limited_user(condor, catalogue, eligibility):
    """AC-1 (ADR-037): closing every leg is an EXIT (a strategy cannot have zero legs), allowed without Pro."""
    ctx = all_true_context(action=ExecutionAction.EXIT, pro_entitled=False)
    assert check_pre_execution(condor, ctx, catalogue, eligibility).failures == ()


def test_multi_expiry_adjustment_closing_a_long_needs_pro(catalogue, eligibility):
    """AC-1 (rule 5d): a multi-expiry adjustment that closes a long leg (not same-share, not shorts only) needs Pro."""
    active = IC + (_l(B, CE, "23400", expiry=NEAR),)
    strategy, ctx = _limited_adjustment(active[1:], active=active)
    assert check_pre_execution(strategy, ctx, catalogue, eligibility).failed_codes == {CheckCode.ENTITLEMENT_REQUIRED}


def test_both_unlimited_but_worse_downside_needs_pro(catalogue, eligibility):
    """AC-1 (rule 5b, 'worst case at level 0, at every strike'): short call + short put with a bought put wing;
    closing the wing keeps the same UNLIMITED upper slope but the premium-free worst case at level 0 falls from
    -13,000 to -1,495,000 -> needs Pro (the slope comparison alone would allow it)."""
    active = (_l(S, CE, "23400"), _l(S, PE, "23000"), _l(B, PE, "22800"))
    strategy, ctx = _limited_adjustment(active[:2], active=active)
    assert check_pre_execution(strategy, ctx, catalogue, eligibility).failed_codes == {CheckCode.ENTITLEMENT_REQUIRED}


@pytest.mark.parametrize("proposed", [
    pytest.param(ACTIVE_TWO_LOTS + (Leg(Action.BUY, Instrument.CE, D("23800"), EXPIRY, 65, D("20.00")),),
                 id="add-new-leg"),
    pytest.param(_replace_leg(2, strike=D("23450")), id="roll-to-new-strike"),
    pytest.param(_replace_leg(1, action=Action.BUY), id="side-flip"),
    pytest.param(_replace_leg(1, quantity=195), id="quantity-increase"),
])
def test_limited_user_is_blocked_from_risk_adding_or_rolling_adjustments(proposed, catalogue, eligibility):
    """AC-1 (ADR-037): a new contract, a side flip or a quantity increase needs Pro; the Pro reason is shown."""
    strategy, ctx = _limited_adjustment(proposed)
    result = check_pre_execution(strategy, ctx, catalogue, eligibility)
    assert [(f.code, f.reason) for f in result.failures] == [(CheckCode.ENTITLEMENT_REQUIRED, PRO_REASON)]
    pro_strategy, pro_ctx = _limited_adjustment(proposed, pro=True)
    assert check_pre_execution(pro_strategy, pro_ctx, catalogue, eligibility).failures == ()


def test_adjustment_without_active_legs_needs_pro(catalogue, eligibility):
    """AC-1 (fail closed): without the active legs the adjustment cannot be shown to reduce only, so it needs Pro."""
    strategy, ctx = _limited_adjustment(_replace_leg(1, quantity=65), active=None)
    assert check_pre_execution(strategy, ctx, catalogue, eligibility).failed_codes == {CheckCode.ENTITLEMENT_REQUIRED}


# ---------------------------------------------------------------- AC-2 structured audit record (fix round 1)


@pytest.mark.parametrize("case,mutate,code,reason", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_every_blocked_result_carries_a_blocked_execution_record(case, mutate, code, reason, condor, catalogue,
                                                                 eligibility):
    """AC-2: every blocked result carries the audit record: strategy, version, action, codes, reasons, time, actor."""
    strategy, ctx, cat, elig = mutate(condor, catalogue, eligibility)
    result = check_pre_execution(strategy, ctx, cat, elig)
    record = result.blocked_execution
    assert record is not None
    assert (record.strategy_id, record.version_id, record.action, record.actor) == (
        "S-1", "V-3", "NEW_ENTRY", "user:U-42")
    assert record.failed_codes == tuple(f.code for f in result.failures)
    assert record.reasons == tuple(f.reason for f in result.failures)
    assert record.at == ctx.as_of and record.at.utcoffset() is not None


def test_passed_result_carries_no_blocked_record(condor, catalogue, eligibility):
    """AC-2: a result that is not blocked carries no blocked-execution record."""
    assert check_pre_execution(condor, all_true_context(), catalogue, eligibility).blocked_execution is None


@pytest.mark.parametrize("overrides", [{"version_id": ""}, {"actor": None}, {"active_legs": ["leg"]}],
                         ids=["version_id", "actor", "active_legs"])
def test_malformed_record_inputs_are_refused(overrides):
    """AC-2 (fail closed): the record's identity inputs are required and typed."""
    with pytest.raises(ValueError):
        all_true_context(**overrides)
