"""REQ-059 AC-3 / AC-4 / AC-5: what validation covers, that it never changes the strategy, and how an unavailable
contract is reported (problem + optional alternatives, never a substitution). Real instrument list throughout."""
from __future__ import annotations

import copy
import dataclasses
import datetime
from decimal import Decimal as D

import pytest

from execution_inputs import check, AS_OF, EXPIRY, FIXTURE, all_true_context, condor_legs, find_token
from ofo.audit import AuditLog
from ofo.engine import UNLIMITED, Action, Instrument, Leg, Strategy
from ofo.execution import (
    CheckCode,
    DataHealth,
    DataInput,
    FlagCode,
    SafetyResult,
    margin_required_from,
)
from ofo.instruments import EligibilityStatus, parse_instruments_csv

SENSEX_EXPIRY = datetime.date(2026, 10, 8)
NEAR_NIFTY_EXPIRY = datetime.date(2026, 9, 29)


def _flags(result: SafetyResult) -> set[FlagCode]:
    return {f.code for f in result.flags}


# ---------------------------------------------------------------- AC-3: what validation covers


def test_supported_underlying_sensex_passes_on_real_contracts(catalogue, eligibility):
    """AC-3: SENSEX is supported; a real SENSEX spread (lot 20) on the 08 Oct 2026 expiry passes."""
    legs = (
        Leg(Action.SELL, Instrument.CE, D("76000"), SENSEX_EXPIRY, 20, D("310.00")),
        Leg(Action.BUY, Instrument.CE, D("76500"), SENSEX_EXPIRY, 20, D("150.00")),
    )
    result = check(Strategy(legs), all_true_context(underlying="SENSEX"), catalogue, eligibility)
    assert result.failures == ()
    assert result.max_loss == D("6800.00")  # (500 - 160) x 20


def test_unsupported_underlying_skips_contract_checks_and_says_so(condor, catalogue, eligibility):
    """AC-3: an unsupported underlying is refused; the contract checks are listed as not checked, never as passed."""
    result = check(condor, all_true_context(underlying="BANKNIFTY"), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.UNDERLYING_UNSUPPORTED}
    assert CheckCode.CONTRACT_NOT_FOUND in result.not_checked
    assert CheckCode.QUANTITY_INVALID in result.not_checked
    assert not set(result.not_checked) & set(result.passed)


def test_nifty_quantity_not_a_multiple_of_lot_65_is_refused_with_the_lot_size(catalogue, eligibility):
    """AC-3: NIFTY quantity 100 is refused and the reason names the real lot size 65; 130 (two lots) passes."""
    legs = list(condor_legs())
    legs[0] = dataclasses.replace(legs[0], quantity=100)
    result = check(Strategy(tuple(legs)), all_true_context(), catalogue, eligibility)
    assert [(f.code, f.leg_number, f.reason) for f in result.failures] == [(
        CheckCode.QUANTITY_INVALID,
        1,
        "Leg 1 (BUY NIFTY 22,800 PE, expiry 06 Oct 2026): quantity 100 is not a whole number of lots. The NIFTY lot "
        "size for this expiry is 65 (for example 65 or 130).",
    )]
    ok = check(Strategy(condor_legs(quantity=130)), all_true_context(), catalogue, eligibility)
    assert ok.failures == ()


def test_sensex_quantity_uses_sensex_lot_20_not_nifty(catalogue, eligibility):
    """AC-3: lot size is per underlying: 65 units of SENSEX is refused (lot 20); 60 passes."""
    leg = Leg(Action.BUY, Instrument.CE, D("76000"), SENSEX_EXPIRY, 65, D("310.00"))
    result = check(Strategy((leg,)), all_true_context(underlying="SENSEX"), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.QUANTITY_INVALID}
    assert "The SENSEX lot size for this expiry is 20" in result.failures[0].reason
    ok = dataclasses.replace(leg, quantity=60)
    assert check(Strategy((ok,)), all_true_context(underlying="SENSEX"), catalogue, eligibility).failures == ()


def test_expiry_not_in_instrument_list_is_refused(catalogue, eligibility):
    """AC-3: an expiry with no real contracts (13 Oct 2026) is not found and its lot size cannot be confirmed."""
    leg = Leg(Action.BUY, Instrument.CE, D("23400"), datetime.date(2026, 10, 13), 65, D("50.00"))
    result = check(Strategy((leg,)), all_true_context(), catalogue, eligibility)
    assert [(f.code, f.reason) for f in result.failures] == [
        (CheckCode.QUANTITY_INVALID,
         "Leg 1 (BUY NIFTY 23,400 CE, expiry 13 Oct 2026): the lot size for this expiry could not be confirmed."),
        (CheckCode.CONTRACT_NOT_FOUND,
         "Leg 1 (BUY NIFTY 23,400 CE, expiry 13 Oct 2026) does not exist in Zerodha's instrument list. No nearby "
         "listed strike is available to offer."),
    ]


def test_side_is_a_typed_action_never_a_free_string():
    """AC-3: side validity - a leg side must be BUY or SELL (typed); anything else is refused before validation."""
    with pytest.raises(ValueError):
        Leg("SELL", Instrument.CE, D("23400"), EXPIRY, 65, D("91.50"))  # type: ignore[arg-type]


def test_multi_expiry_is_allowed_and_flagged(catalogue, eligibility):
    """AC-3: multi-expiry legs are allowed (not blocked) and flagged; exact max loss is not claimed."""
    legs = (
        Leg(Action.SELL, Instrument.CE, D("23400"), NEAR_NIFTY_EXPIRY, 65, D("91.50")),
        Leg(Action.BUY, Instrument.CE, D("23400"), EXPIRY, 65, D("120.00")),
    )
    result = check(Strategy(legs), all_true_context(), catalogue, eligibility)
    assert result.failures == ()
    assert FlagCode.MULTI_EXPIRY in _flags(result)
    assert result.max_loss is None


def test_duplicate_leg_is_flagged_and_never_merged(condor, catalogue, eligibility):
    """AC-3: the same contract twice (even opposite sides) blocks as DUPLICATE_LEG; both legs stay in the strategy."""
    extra = Leg(Action.SELL, Instrument.PE, D("22800"), EXPIRY, 65, D("40.00"))
    strategy = Strategy(condor.legs + (extra,))
    result = check(strategy, all_true_context(), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.DUPLICATE_LEG}
    assert result.failures[0].leg_number == 5
    assert len(strategy.legs) == 5 and strategy.legs[4] is extra


def test_unlimited_risk_is_flagged_not_blocked(catalogue, eligibility):
    """AC-3: risk from the engine - a naked short call has UNLIMITED max loss, which is flagged."""
    leg = Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 65, D("91.50"))
    result = check(Strategy((leg,)), all_true_context(), catalogue, eligibility)
    assert result.failures == ()
    assert result.max_loss is UNLIMITED
    assert FlagCode.UNLIMITED_LOSS in _flags(result)
    bounded = check(Strategy(condor_legs()), all_true_context(), catalogue, eligibility)
    assert FlagCode.UNLIMITED_LOSS not in _flags(bounded)


class _Planner:
    def __init__(self, answer: object) -> None:
        self.answer = answer

    def required_margin(self, strategy: Strategy) -> object:
        return self.answer


def test_margin_estimate_comes_from_the_planner_and_is_validated(condor, catalogue, eligibility):
    """AC-3: the margin estimate is the planner's Decimal; a float or negative answer is refused (fail closed)."""
    required = margin_required_from(_Planner(D("48210.75")), condor)
    result = check(condor, all_true_context(margin_required=required), catalogue, eligibility)
    assert result.margin_required == D("48210.75") and result.blocked is False
    for bad in (48210.75, D("-1"), D("Infinity"), None):
        with pytest.raises(ValueError):
            margin_required_from(_Planner(bad), condor)
    short = all_true_context(margin_required=D("150000.01"))
    assert check(condor, short, catalogue, eligibility).failed_codes == {CheckCode.MARGIN_INSUFFICIENT}


def test_charges_estimate_where_available(condor, catalogue, eligibility):
    """AC-3: a charges estimate is carried exactly when given; when absent it is flagged, not blocked."""
    given = check(condor, all_true_context(), catalogue, eligibility)
    assert given.charges_estimate == D("236.40") and FlagCode.CHARGES_UNAVAILABLE not in _flags(given)
    absent = check(condor, all_true_context(charges_estimate=None), catalogue, eligibility)
    assert absent.blocked is False and absent.charges_estimate is None
    assert FlagCode.CHARGES_UNAVAILABLE in _flags(absent)


def test_data_freshness_every_required_input(condor, catalogue, eligibility):
    """AC-3: each required data input that is stale or unavailable is reported on its own."""
    health = {d: DataHealth.STALE for d in DataInput}
    health[DataInput.INSTRUMENT_LIST] = DataHealth.UNAVAILABLE
    result = check(condor, all_true_context(data_health=health), catalogue, eligibility)
    assert [f.reason for f in result.failures] == [
        "Market data needed for execution (underlying price) is out of date. Execution is paused until it is current.",
        "Market data needed for execution (leg prices) is out of date. Execution is paused until it is current.",
        "Market data needed for execution (instrument list) is unavailable. Execution is paused until it is current.",
    ]


def test_rule_validity_and_dependencies_are_checked(condor, catalogue, eligibility):
    """AC-3: rule validity and execution dependencies are validated (unknown fails closed)."""
    result = check(
        condor, all_true_context(rules_valid=None, dependencies_satisfied=None), catalogue, eligibility
    )
    assert [f.code for f in result.failures] == [CheckCode.RULES_INVALID, CheckCode.DEPENDENCIES_UNSATISFIED]


# ---------------------------------------------------------------- AC-4: never changes the strategy


def test_validation_never_changes_strategy_catalogue_or_eligibility(catalogue, eligibility):
    """AC-4: with many failures at once, the strategy, the catalogue and eligibility are deep-equal before/after."""
    legs = list(condor_legs(quantity=100))
    legs[1] = dataclasses.replace(legs[1], strike=D("23010"))
    strategy = Strategy(tuple(legs) + (legs[0],))
    eligibility.record(EligibilityStatus(find_token(catalogue, "CE", "23400"), False, AS_OF))
    before_strategy = copy.deepcopy(strategy)
    before_legs = [id(leg) for leg in strategy.legs]
    before_catalogue = [(e.contract, e.currently_listed) for e in catalogue.all_entries()]
    before_elig = {e.contract.instrument_token: eligibility.get(e.contract.instrument_token)
                   for e in catalogue.all_entries()}

    result = check(strategy, all_true_context(market_open=False), catalogue, eligibility)

    assert result.blocked is True
    assert strategy == before_strategy
    assert [id(leg) for leg in strategy.legs] == before_legs
    assert [(e.contract, e.currently_listed) for e in catalogue.all_entries()] == before_catalogue
    assert {t: eligibility.get(t) for t in before_elig} == before_elig
    assert not any(isinstance(getattr(result, f.name), Strategy) for f in dataclasses.fields(result))


# ---------------------------------------------------------------- AC-5: unavailable contracts


def test_unlisted_contract_is_reported_with_alternatives_not_replaced(condor, catalogue, eligibility):
    """AC-5: a contract missing from a newer list stays in the catalogue, is reported, alternatives are offered,
    and the strategy still holds the original strike."""
    token = find_token(catalogue, "PE", "23000")
    catalogue.update([c for c in parse_instruments_csv(FIXTURE) if c.instrument_token != token], as_of=AS_OF, force=True, reason="test delisting", actor="test-admin", audit_log=AuditLog())
    result = check(condor, all_true_context(), catalogue, eligibility)
    (failure,) = result.failures
    assert failure.code is CheckCode.CONTRACT_NOT_LISTED
    assert failure.leg_number == 2
    assert failure.alternatives == (D("22950"), D("23050"))
    assert condor.legs[1].strike == D("23000")
    kept = [e for e in catalogue.all_entries() if e.contract.instrument_token == token]
    assert len(kept) == 1 and kept[0].currently_listed is False


def test_alternatives_exclude_unlisted_and_ineligible_strikes(condor, catalogue, eligibility):
    """AC-5: alternatives are only listed AND eligible strikes of the same type and expiry, nearest first."""
    eligibility.record(EligibilityStatus(find_token(catalogue, "PE", "23000"), False, AS_OF, "OI limit"))
    eligibility.record(EligibilityStatus(find_token(catalogue, "PE", "22950"), False, AS_OF, "OI limit"))
    result = check(condor, all_true_context(), catalogue, eligibility)
    (failure,) = result.failures
    assert failure.code is CheckCode.CONTRACT_NOT_ELIGIBLE
    assert failure.alternatives == (D("23050"), D("22900"))  # 22,950 ineligible; 22,900 and 23,100 tie -> lower


def test_unavailable_futures_contract_offers_no_strike_alternatives(catalogue, eligibility):
    """AC-5: an ineligible future is reported; no strike alternative is invented for a futures leg."""
    fut = Leg(Action.BUY, Instrument.FUT, None, datetime.date(2026, 10, 27), 65, D("23250"))
    (token,) = [c.instrument_token for c in catalogue.contracts_for("NIFTY", fut.expiry, frozenset({"FUT"}))]
    eligibility.record(EligibilityStatus(token, False, AS_OF))
    result = check(Strategy((fut,)), all_true_context(), catalogue, eligibility)
    (failure,) = result.failures
    assert failure.code is CheckCode.CONTRACT_NOT_ELIGIBLE and failure.alternatives == ()
    assert failure.reason.endswith("No nearby listed strike is available to offer.")
