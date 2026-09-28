"""Pre-execution safety gate and validation (REQ-059). Pure: no Zerodha call, no network, no mutation.

``check_pre_execution`` evaluates EVERY check and returns every failure (never just the first), each with a stable
code and a plain-language reason; execution is blocked when any check fails (AC-1, AC-2). The strategy is only
read, never rewritten (AC-4, ADR-019). An unavailable contract is reported with the problem and, where the
catalogue has them, the nearest listed and eligible strikes as alternatives; nothing is substituted — any change is
the user's explicit choice (AC-5, ADR-016 Q44). Reason texts are decision-support wording only (ADR-003).
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction

from ofo.engine import UNLIMITED, Action, Instrument, Leg, Strategy, strategy_metrics
from ofo.engine.metrics import _Unlimited, _upper_tail_slope
from ofo.execution.context import (
    EXECUTABLE_VERSION_STATES,
    REQUIRED_DATA_INPUTS,
    DataHealth,
    ExecutionAction,
    ExecutionContext,
)
from ofo.instruments import Catalogue, CatalogueEntry, ContractKind, EligibilityRegistry
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

logger = logging.getLogger("ofo.execution.safety")

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MAX_ALTERNATIVES = 2


class CheckCode(str, Enum):
    UNDERLYING_UNSUPPORTED = "UNDERLYING_UNSUPPORTED"
    MARKET_CLOSED = "MARKET_CLOSED"
    VERSION_NOT_EXECUTABLE = "VERSION_NOT_EXECUTABLE"
    BROKER_NOT_CONNECTED = "BROKER_NOT_CONNECTED"
    SESSION_INVALID = "SESSION_INVALID"
    ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
    DATA_UNHEALTHY = "DATA_UNHEALTHY"
    RULES_INVALID = "RULES_INVALID"
    EXPIRY_PASSED = "EXPIRY_PASSED"
    CONTRACT_NOT_FOUND = "CONTRACT_NOT_FOUND"
    CONTRACT_AMBIGUOUS = "CONTRACT_AMBIGUOUS"
    CONTRACT_NOT_LISTED = "CONTRACT_NOT_LISTED"
    CONTRACT_NOT_ELIGIBLE = "CONTRACT_NOT_ELIGIBLE"
    QUANTITY_INVALID = "QUANTITY_INVALID"
    DUPLICATE_LEG = "DUPLICATE_LEG"
    MARGIN_INSUFFICIENT = "MARGIN_INSUFFICIENT"
    DEPENDENCIES_UNSATISFIED = "DEPENDENCIES_UNSATISFIED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"


# Checks that look at each leg's contract; skipped (reported as not checked) when the underlying is unsupported.
_CONTRACT_CHECKS: tuple[CheckCode, ...] = (
    CheckCode.EXPIRY_PASSED,
    CheckCode.CONTRACT_NOT_FOUND,
    CheckCode.CONTRACT_AMBIGUOUS,
    CheckCode.CONTRACT_NOT_LISTED,
    CheckCode.CONTRACT_NOT_ELIGIBLE,
    CheckCode.QUANTITY_INVALID,
)


class FlagCode(str, Enum):
    """Non-blocking observations shown with the result."""

    MULTI_EXPIRY = "MULTI_EXPIRY"
    UNLIMITED_LOSS = "UNLIMITED_LOSS"
    CHARGES_UNAVAILABLE = "CHARGES_UNAVAILABLE"


@dataclass(frozen=True)
class CheckFailure:
    code: CheckCode
    reason: str
    leg_number: int | None = None
    alternatives: tuple[Decimal, ...] = ()


@dataclass(frozen=True)
class Flag:
    code: FlagCode
    message: str


@dataclass(frozen=True)
class BlockedExecution:
    """The audit record of one blocked execution attempt (REQ-059 AC-2 "the event is logged").

    Plain values only (strings, codes, a timezone-aware time) so the audit log can store it without importing this
    module's types beyond ``CheckCode``.
    """

    strategy_id: str
    version_id: str
    action: str
    failed_codes: tuple[CheckCode, ...]
    reasons: tuple[str, ...]
    at: datetime.datetime
    actor: str


@dataclass(frozen=True)
class SafetyResult:
    failures: tuple[CheckFailure, ...]
    passed: tuple[CheckCode, ...]
    not_checked: tuple[CheckCode, ...]
    flags: tuple[Flag, ...]
    max_loss: Decimal | _Unlimited | None
    margin_required: Decimal | None
    charges_estimate: Decimal | None
    blocked_execution: BlockedExecution | None

    @property
    def blocked(self) -> bool:
        return bool(self.failures)

    @property
    def failed_codes(self) -> frozenset[CheckCode]:
        return frozenset(f.code for f in self.failures)


def _rupees(amount: Decimal) -> str:
    return f"₹{amount:,}"


def _describe(number: int, leg: Leg, underlying: str) -> str:
    what = "FUT" if leg.strike is None else f"{leg.strike:,} {leg.instrument.value}"
    return f"Leg {number} ({leg.action.value} {underlying} {what}, expiry {leg.expiry:%d %b %Y})"


def _kind(leg: Leg) -> ContractKind:
    return ContractKind.FUTURE if leg.instrument is Instrument.FUT else ContractKind.OPTION


_Key = tuple[datetime.date, str, Decimal | None]


def _key(expiry: datetime.date | None, instrument_type: str, strike: Decimal | None) -> _Key:
    return (expiry, instrument_type, None if instrument_type == Instrument.FUT.value else strike)


def _index(catalogue: Catalogue, underlying: str) -> dict[_Key, list[CatalogueEntry]]:
    index: dict[_Key, list[CatalogueEntry]] = {}
    for entry in catalogue.all_entries():
        c = entry.contract
        if c.name == underlying:
            index.setdefault(_key(c.expiry, c.instrument_type, c.strike), []).append(entry)
    return index


def _alternatives(
    leg: Leg, underlying: str, catalogue: Catalogue, eligibility: EligibilityRegistry
) -> tuple[Decimal, ...]:
    """Nearest listed + eligible strikes of the same underlying, expiry and option type. Offered, never applied."""
    if leg.strike is None:
        return ()
    strikes = {
        e.contract.strike
        for e in catalogue.all_entries()
        if e.contract.name == underlying
        and e.contract.expiry == leg.expiry
        and e.contract.instrument_type == leg.instrument.value
        and e.contract.strike != leg.strike
        and e.currently_listed
        and eligibility.is_tradable(e.contract.instrument_token)
    }
    return tuple(sorted(strikes, key=lambda s: (abs(s - leg.strike), s))[:MAX_ALTERNATIVES])


def _alternatives_text(alternatives: tuple[Decimal, ...]) -> str:
    if not alternatives:
        return " No nearby listed strike is available to offer."
    listed = " or ".join(f"{s:,}" for s in alternatives)
    return f" Strikes you could consider instead: {listed}. Your strategy has not been changed."


def _positions(legs: tuple[Leg, ...]) -> dict[tuple[_Key, str], int]:
    """Units held per (contract, side)."""
    held: dict[tuple[_Key, str], int] = {}
    for leg in legs:
        k = (_key(leg.expiry, leg.instrument.value, leg.strike), leg.action.value)
        held[k] = held.get(k, 0) + leg.quantity
    return held


def _reduces_only(active: tuple[Leg, ...], proposed: tuple[Leg, ...]) -> bool:
    """True when ``proposed`` only closes or reduces legs of ``active``: no new contract, no side flip, no increase."""
    before = _positions(active)
    return all(before.get(k, 0) >= units for k, units in _positions(proposed).items())


PRO_REASON = (
    "New entries and adjustments that add or change positions need Pro. Exiting, or closing or reducing legs of an "
    "active strategy, stays available on every plan."
)


def _worst_case_text(min_pnl: Decimal | _Unlimited) -> str:
    if min_pnl is UNLIMITED:
        return "an unlimited loss"
    return f"a loss of {_rupees(-min_pnl)}" if min_pnl < 0 else f"a gain of {_rupees(min_pnl)}"


_ZERO_PREMIUM = Decimal("0.00")


def _premium_free(legs: tuple[Leg, ...]) -> Strategy:
    """The same legs with every option's entry price set to 0 (intrinsic value only); futures keep their entry."""
    return Strategy(tuple(
        dataclasses.replace(leg, entry_price=_ZERO_PREMIUM, ltp=None) if leg.is_option else leg for leg in legs
    ))


def _tail_slope(strategy: Strategy) -> int:
    """Upper-tail payoff slope (rupees per point) from the engine's own tail logic."""
    return sum(_upper_tail_slope(leg) for leg in strategy.legs)


def _worst_at_points(strategy: Strategy, points: set[Decimal]) -> Decimal:
    """Lowest engine payoff at the given levels (level 0 and every strike)."""
    return min(strategy.expiry_pnl_at(p) for p in points)


def _same_share(before: dict[tuple[_Key, str], int], after: dict[tuple[_Key, str], int]) -> bool:
    """Every active position reduced (or kept) by one common share (rule 5c)."""
    shares = {Fraction(after.get(k, 0), units) for k, units in before.items()}
    return len(shares) == 1 and set(after) <= set(before)


def _closes_only_short_options(before: dict[tuple[_Key, str], int], after: dict[tuple[_Key, str], int]) -> bool:
    """Only short option positions shrink; every long and every future is untouched (rule 5d)."""
    for k, units in before.items():
        if after.get(k, 0) < units:
            (_, instrument_type, _), side = k
            if side != Action.SELL.value or instrument_type == Instrument.FUT.value:
                return False
    return True


def _worse_worst_case(active: tuple[Leg, ...], proposed: tuple[Leg, ...]) -> str | None:
    """Rule 5b: the premium-free worst case at expiry after the change must be no worse than before.

    Worst case = level 0, every strike and the upper tail (engine metrics on premium-free legs). An UNLIMITED after
    is allowed only when before was UNLIMITED too, the after upper-tail slope is not steeper, and the worst case at
    level 0 and every strike is not lower.
    """
    before, after = _premium_free(active), _premium_free(proposed)
    b, a = strategy_metrics(before).min_pnl, strategy_metrics(after).min_pnl
    if a is UNLIMITED:
        points = {Decimal(0)} | {leg.strike for leg in active + proposed if leg.is_option}
        if (
            b is UNLIMITED
            and _tail_slope(after) >= _tail_slope(before)
            and _worst_at_points(after, points) >= _worst_at_points(before, points)
        ):
            return None
    elif b is UNLIMITED or a >= b:
        return None
    return (
        "This adjustment makes the strategy's worst case at expiry larger (option premiums excluded): from "
        f"{_worst_case_text(b)} to {_worst_case_text(a)}. Adjustments that add risk need Pro. Exiting, or closing "
        "or reducing legs without a larger worst case, stays available on every plan."
    )


MULTI_EXPIRY_PRO_REASON = (
    "This strategy has legs on more than one expiry. Without Pro it can be exited, reduced by the same share on every "
    "leg, or have only its sold options closed; other adjustments may add risk and need Pro."
)


def pro_requirement(strategy: Strategy, ctx: ExecutionContext) -> str | None:
    """The reason this action needs Pro, or None when it is open to every plan (ADR-037, REQ-059 Gate decisions
    rule 5, by actor intent).

    An EXIT is open to every plan. An ADJUSTMENT is open only if (a) no position grows (no new contract, no quantity
    increase, no side flip) AND one of: (c) every leg is reduced by the same share; (d) for a multi-expiry strategy,
    only short options are closed or reduced; (b) for a single-expiry strategy, the premium-free worst case at expiry
    does not get worse. Fail closed: no active legs to compare needs Pro.
    """
    if ctx.action is ExecutionAction.EXIT:
        return None
    if ctx.action is not ExecutionAction.ADJUSTMENT or ctx.active_legs is None:
        return PRO_REASON
    active, proposed = ctx.active_legs, strategy.legs
    if not _reduces_only(active, proposed):
        return PRO_REASON
    before_pos, after_pos = _positions(active), _positions(proposed)
    if _same_share(before_pos, after_pos):
        return None
    if len({leg.expiry for leg in active + proposed}) > 1:
        return None if _closes_only_short_options(before_pos, after_pos) else MULTI_EXPIRY_PRO_REASON
    return _worse_worst_case(active, proposed)


def _context_failures(ctx: ExecutionContext, pro_reason: str | None) -> list[CheckFailure]:
    out: list[CheckFailure] = []

    def unknown_or(value: bool | None, code: CheckCode, unknown: str, false: str) -> None:
        if value is not True:
            out.append(CheckFailure(code, unknown if value is None else false))

    unknown_or(ctx.market_open, CheckCode.MARKET_CLOSED,
               "We could not confirm that the market is open. Execution is paused until it is confirmed.",
               "The market is closed. Orders can be placed once it opens.")
    if ctx.version_state not in EXECUTABLE_VERSION_STATES[ctx.action]:
        state = "unknown" if ctx.version_state is None else ctx.version_state.value.lower()
        allowed = " or ".join(sorted(s.value.lower() for s in EXECUTABLE_VERSION_STATES[ctx.action]))
        out.append(CheckFailure(
            CheckCode.VERSION_NOT_EXECUTABLE,
            f"This version of the strategy is {state}. This action executes only a version that is {allowed}.",
        ))
    unknown_or(ctx.broker_connected, CheckCode.BROKER_NOT_CONNECTED,
               "We could not confirm your Zerodha connection. Reconnect to continue.",
               "Your Zerodha account is not connected. Connect it to continue.")
    unknown_or(ctx.session_valid, CheckCode.SESSION_INVALID,
               "We could not confirm your Zerodha session. Reconnect to continue.",
               "Your Zerodha session has expired. Reconnect to continue.")
    if pro_reason is not None:
        unknown_or(ctx.pro_entitled, CheckCode.ENTITLEMENT_REQUIRED,
                   "We could not confirm your plan. New entries and adjustments that add or change positions need "
                   "Pro.",
                   pro_reason)
    for data_input in REQUIRED_DATA_INPUTS:
        health = ctx.data_health.get(data_input)
        if health is not DataHealth.HEALTHY:
            label = data_input.value.lower().replace("_", " ")
            state = "has no status" if health is None else ("is out of date" if health is DataHealth.STALE
                                                          else "is unavailable")
            out.append(CheckFailure(
                CheckCode.DATA_UNHEALTHY, f"Market data needed for execution ({label}) {state}. Execution is "
                "paused until it is current."))
    unknown_or(ctx.rules_valid, CheckCode.RULES_INVALID,
               "We could not confirm that this strategy's rules are valid. Review them to continue.",
               "This strategy's rules are not valid. Review them to continue.")
    unknown_or(ctx.dependencies_satisfied, CheckCode.DEPENDENCIES_UNSATISFIED,
               "We could not confirm that the orders this execution depends on are in place.",
               "An order this execution depends on is not in place yet (for example a protective leg).")
    if ctx.margin_available is None or ctx.margin_required is None:
        out.append(CheckFailure(CheckCode.MARGIN_INSUFFICIENT,
                                "We could not confirm your available margin with Zerodha. Execution is paused."))
    elif ctx.margin_available < ctx.margin_required:
        out.append(CheckFailure(
            CheckCode.MARGIN_INSUFFICIENT,
            f"Available margin {_rupees(ctx.margin_available)} is less than the estimated "
            f"{_rupees(ctx.margin_required)} this strategy needs. Zerodha's figure is final. No order has been "
            "submitted.",
        ))
    if ctx.strategy_id in ctx.reconciliation_blocked_strategy_ids:
        out.append(CheckFailure(
            CheckCode.RECONCILIATION_MISMATCH,
            "Your Zerodha positions for this strategy do not match what we recorded. Resolve the mismatch to "
            "continue.",
        ))
    return out


def _leg_failures(
    strategy: Strategy, ctx: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry
) -> list[CheckFailure]:
    out: list[CheckFailure] = []
    underlying = ctx.underlying
    index = _index(catalogue, underlying)
    today = ctx.as_of.astimezone(IST).date()
    seen: dict[_Key, int] = {}
    for number, leg in enumerate(strategy.legs, start=1):
        described = _describe(number, leg, underlying)
        key = _key(leg.expiry, leg.instrument.value, leg.strike)
        if key in seen:
            out.append(CheckFailure(
                CheckCode.DUPLICATE_LEG,
                f"{described} is the same contract as leg {seen[key]}. The legs have not been combined; edit the "
                "strategy to keep one or combine them yourself.",
                leg_number=number,
            ))
        else:
            seen[key] = number
        try:
            lot = catalogue.lot_size(underlying, leg.expiry, _kind(leg))
        except ValueError:
            out.append(CheckFailure(CheckCode.QUANTITY_INVALID,
                                    f"{described}: the lot size for this expiry could not be confirmed.",
                                    leg_number=number))
        else:
            if leg.quantity % lot != 0:
                out.append(CheckFailure(
                    CheckCode.QUANTITY_INVALID,
                    f"{described}: quantity {leg.quantity} is not a whole number of lots. The {underlying} lot size "
                    f"for this expiry is {lot} (for example {lot} or {2 * lot}).",
                    leg_number=number,
                ))
        if leg.expiry < today:
            out.append(CheckFailure(CheckCode.EXPIRY_PASSED, f"{described} has already expired.", leg_number=number))
            continue
        matches = index.get(key, [])
        if len(matches) > 1:
            out.append(CheckFailure(CheckCode.CONTRACT_AMBIGUOUS,
                                    f"{described} matches more than one contract in the instrument list.",
                                    leg_number=number))
            continue
        if not matches:
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            out.append(CheckFailure(
                CheckCode.CONTRACT_NOT_FOUND,
                f"{described} does not exist in Zerodha's instrument list." + _alternatives_text(alts),
                leg_number=number, alternatives=alts,
            ))
            continue
        entry = matches[0]
        if not entry.currently_listed:
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            out.append(CheckFailure(
                CheckCode.CONTRACT_NOT_LISTED,
                f"{described} is no longer listed by Zerodha." + _alternatives_text(alts),
                leg_number=number, alternatives=alts,
            ))
            continue
        status = eligibility.get(entry.contract.instrument_token)
        if status is None or not status.tradable:
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            problem = (
                "has not been confirmed as available on Zerodha yet. Refresh availability to continue."
                if status is None
                else "is currently unavailable on Zerodha. Zerodha isn't accepting fresh orders for this contract "
                "right now."
            )
            out.append(CheckFailure(CheckCode.CONTRACT_NOT_ELIGIBLE, f"{described} {problem}" +
                                    _alternatives_text(alts), leg_number=number, alternatives=alts))
    return out


def _risk_flags(strategy: Strategy, ctx: ExecutionContext) -> tuple[list[Flag], Decimal | _Unlimited | None]:
    flags: list[Flag] = []
    max_loss: Decimal | _Unlimited | None = None
    if strategy.is_single_expiry:
        max_loss = strategy_metrics(strategy).max_loss
        if max_loss is UNLIMITED:
            flags.append(Flag(FlagCode.UNLIMITED_LOSS,
                              "This strategy's possible loss has no upper limit if the market moves far enough."))
    else:
        flags.append(Flag(FlagCode.MULTI_EXPIRY,
                          "This strategy has legs on more than one expiry; its exact at-expiry maximum loss cannot "
                          "be computed."))
    if ctx.charges_estimate is None:
        flags.append(Flag(FlagCode.CHARGES_UNAVAILABLE, "A charges estimate is not available for this strategy."))
    return flags, max_loss


def check_pre_execution(
    strategy: Strategy, context: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry
) -> SafetyResult:
    """Run every pre-execution check (REQ-059 AC-1, AC-3); block if any fails; never change ``strategy``."""
    if not isinstance(strategy, Strategy):
        raise ValueError(f"strategy must be a Strategy, got {strategy!r}")
    if not isinstance(context, ExecutionContext):
        raise ValueError(f"context must be an ExecutionContext, got {context!r}")
    if not isinstance(catalogue, Catalogue) or not isinstance(eligibility, EligibilityRegistry):
        raise ValueError("catalogue and eligibility must be a Catalogue and an EligibilityRegistry")

    pro_reason = pro_requirement(strategy, context)
    failures = _context_failures(context, pro_reason)
    not_checked: tuple[CheckCode, ...] = ()
    if context.underlying not in SUPPORTED_UNDERLYINGS:
        failures.insert(0, CheckFailure(
            CheckCode.UNDERLYING_UNSUPPORTED,
            f"{context.underlying} is not supported. Supported underlyings: {', '.join(SUPPORTED_UNDERLYINGS)}.",
        ))
        not_checked = _CONTRACT_CHECKS + (CheckCode.DUPLICATE_LEG,)
    else:
        failures.extend(_leg_failures(strategy, context, catalogue, eligibility))
    flags, max_loss = _risk_flags(strategy, context)

    failed = {f.code for f in failures}
    applicable = [c for c in CheckCode if pro_reason is not None or c is not CheckCode.ENTITLEMENT_REQUIRED]
    passed = tuple(c for c in applicable if c not in failed and c not in not_checked)
    record = None
    if failures:
        record = BlockedExecution(
            strategy_id=context.strategy_id, version_id=context.version_id, action=context.action.value,
            failed_codes=tuple(f.code for f in failures), reasons=tuple(f.reason for f in failures),
            at=context.as_of, actor=context.actor,
        )
    result = SafetyResult(
        failures=tuple(failures), passed=passed, not_checked=not_checked, flags=tuple(flags), max_loss=max_loss,
        margin_required=context.margin_required, charges_estimate=context.charges_estimate, blocked_execution=record,
    )
    if result.blocked:
        logger.warning(
            "pre-execution blocked strategy=%s action=%s codes=%s", context.strategy_id, context.action.value,
            ",".join(f.code.value for f in result.failures),
        )
    else:
        logger.info("pre-execution passed strategy=%s action=%s", context.strategy_id, context.action.value)
    return result

