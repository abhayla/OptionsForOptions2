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
    active_legs_hash,
)
from ofo.instruments import ZERODHA, Catalogue, CatalogueEntry, ContractKind, EligibilityRegistry
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo import wording as shared_wording
from ofo.errors import LegValue, UserFacingError, display_text, render

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
    EXIT_NOT_REDUCE_ONLY = "EXIT_NOT_REDUCE_ONLY"
    ACTIVE_LEGS_UNVERIFIED = "ACTIVE_LEGS_UNVERIFIED"
    STRATEGY_MISMATCH = "STRATEGY_MISMATCH"
    INTERNAL_ERROR = "INTERNAL_ERROR"
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
    DATA_STALE_ON_EXIT = "DATA_STALE_ON_EXIT"


@dataclass(frozen=True)
class CheckFailure:
    """One failed check. Its words come only from `render()` (W-024 round 9, REQ-065 AC-2, ADR-003 Q226): `message`
    is the four-part `UserFacingError`; a plain string is refused, so no reason text can be built here by hand."""

    code: CheckCode
    message: UserFacingError
    leg_number: int | None = None
    alternatives: tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        if type(self.message) is not UserFacingError:
            raise TypeError(
                f"CheckFailure {getattr(self.code, 'value', self.code)} needs a UserFacingError from "
                f"ofo.errors.render(), got {type(self.message).__name__}"
            )

    @property
    def reason(self) -> str:
        """The what-happened part (the sentence W-014 showed; kept for the audit record)."""
        return self.message.what_happened

    @property
    def text(self) -> str:
        """What the user is shown: all four parts (`ofo.errors.templates.display_text`)."""
        return display_text(self.message)


def _fail(code: CheckCode, template_id: str, *, leg_number: int | None = None,
          alternatives: tuple[Decimal, ...] = (), **slots: object) -> CheckFailure:
    return CheckFailure(code, render(template_id, **slots), leg_number=leg_number, alternatives=alternatives)


@dataclass(frozen=True)
class Flag:
    code: FlagCode
    message: str

    def __post_init__(self) -> None:
        shared_wording.check_platform_text(self.message, f"Flag {getattr(self.code, 'value', self.code)} message")


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
    not_applicable: tuple[CheckCode, ...]
    flags: tuple[Flag, ...]
    max_loss: Decimal | _Unlimited | None
    margin_required: Decimal | None
    charges_estimate: Decimal | None
    blocked_execution: BlockedExecution | None
    requires_confirmation: bool = False  # an exit that passes on unhealthy data needs the user's confirmation
    confirmation_text: str | None = None

    @property
    def blocked(self) -> bool:
        return bool(self.failures)

    @property
    def failed_codes(self) -> frozenset[CheckCode]:
        return frozenset(f.code for f in self.failures)


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
        and e.has_ref(ZERODHA)
        and eligibility.is_tradable(e.contract.id)
    }
    return tuple(sorted(strikes, key=lambda s: (abs(s - leg.strike), s))[:MAX_ALTERNATIVES])


def _contract_failure(code: CheckCode, template_id: str, number: int, leg: Leg, underlying: str,
                      alternatives: tuple[Decimal, ...]) -> CheckFailure:
    """A contract problem with the alternatives offered (never applied): the template with or without strikes."""
    value = LegValue(number, leg, underlying)
    if alternatives:
        return _fail(code, template_id + "_alternatives", leg_number=number, alternatives=alternatives, leg=value,
                     strikes=alternatives)
    return _fail(code, template_id, leg_number=number, leg=value)


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


@dataclass(frozen=True)
class ProReason:
    """Why an action needs Pro: a catalogue template id and its slots, rendered only by `render()`."""

    template_id: str
    slots: tuple[tuple[str, object], ...] = ()

    def render(self) -> UserFacingError:
        return render(self.template_id, **dict(self.slots))


PRO_REQUIRED = ProReason("gate_entitlement_pro")


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


def _worse_worst_case(active: tuple[Leg, ...], proposed: tuple[Leg, ...]) -> ProReason | None:
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
    return ProReason("gate_entitlement_worse_worst_case", (("before", b), ("after", a)))


FUTURES_ENTRY_UNKNOWN = ProReason("gate_entitlement_futures_entry_unknown")
MULTI_EXPIRY_PRO = ProReason("gate_entitlement_multi_expiry")


def pro_requirement(strategy: Strategy, ctx: ExecutionContext) -> ProReason | None:
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
        return PRO_REQUIRED
    active, proposed = ctx.active_legs, strategy.legs
    if not _reduces_only(active, proposed):
        return PRO_REQUIRED
    if ctx.active_futures_entry_known is not True and any(leg.instrument is Instrument.FUT for leg in active):
        return FUTURES_ENTRY_UNKNOWN
    before_pos, after_pos = _positions(active), _positions(proposed)
    if _same_share(before_pos, after_pos):
        return None
    if len({leg.expiry for leg in active + proposed}) > 1:
        return None if _closes_only_short_options(before_pos, after_pos) else MULTI_EXPIRY_PRO
    return _worse_worst_case(active, proposed)


def _context_failures(ctx: ExecutionContext, pro_reason: ProReason | None, strategy_id: str) -> list[CheckFailure]:
    out: list[CheckFailure] = []

    def unknown_or(value: bool | None, code: CheckCode, unknown: str, false: str) -> None:
        if value is not True:
            out.append(_fail(code, unknown if value is None else false))

    unknown_or(ctx.market_open, CheckCode.MARKET_CLOSED, "gate_market_unconfirmed", "gate_market_closed")
    if ctx.version_state not in EXECUTABLE_VERSION_STATES[ctx.action]:
        out.append(_fail(CheckCode.VERSION_NOT_EXECUTABLE, "gate_version_not_executable", state=ctx.version_state,
                         allowed=frozenset(EXECUTABLE_VERSION_STATES[ctx.action])))
    unknown_or(ctx.broker_connected, CheckCode.BROKER_NOT_CONNECTED, "gate_broker_unconfirmed",
               "gate_broker_not_connected")
    unknown_or(ctx.session_valid, CheckCode.SESSION_INVALID, "gate_session_unconfirmed", "gate_session_expired")
    if pro_reason is not None and ctx.pro_entitled is not True:
        if ctx.pro_entitled is None:
            out.append(_fail(CheckCode.ENTITLEMENT_REQUIRED, "gate_entitlement_unconfirmed"))
        else:
            out.append(CheckFailure(CheckCode.ENTITLEMENT_REQUIRED, pro_reason.render()))
    for data_input in REQUIRED_DATA_INPUTS:
        health = ctx.data_health.get(data_input)
        if health is not DataHealth.HEALTHY:
            out.append(_fail(CheckCode.DATA_UNHEALTHY, "gate_data_unhealthy", data_input=data_input, state=health))
    unknown_or(ctx.rules_valid, CheckCode.RULES_INVALID, "gate_rules_unconfirmed", "gate_rules_invalid")
    unknown_or(ctx.dependencies_satisfied, CheckCode.DEPENDENCIES_UNSATISFIED, "gate_dependencies_unconfirmed",
               "gate_dependencies_unsatisfied")
    if ctx.margin_available is None or ctx.margin_required is None:
        out.append(_fail(CheckCode.MARGIN_INSUFFICIENT, "gate_margin_unconfirmed"))
    elif ctx.margin_available < ctx.margin_required:
        out.append(_fail(CheckCode.MARGIN_INSUFFICIENT, "gate_margin_insufficient", available=ctx.margin_available,
                         required=ctx.margin_required))
    if ctx.reconciliation_blocked_strategy_ids is None:
        out.append(_fail(CheckCode.RECONCILIATION_MISMATCH, "gate_reconciliation_unknown"))
    elif strategy_id in ctx.reconciliation_blocked_strategy_ids:
        out.append(_fail(CheckCode.RECONCILIATION_MISMATCH, "gate_reconciliation_mismatch"))
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
        value = LegValue(number, leg, underlying)
        key = _key(leg.expiry, leg.instrument.value, leg.strike)
        if key in seen:
            out.append(_fail(CheckCode.DUPLICATE_LEG, "gate_duplicate_leg", leg_number=number, leg=value,
                             other=seen[key]))
        else:
            seen[key] = number
        try:
            lot = catalogue.lot_size(underlying, leg.expiry, _kind(leg))
        except ValueError:
            out.append(_fail(CheckCode.QUANTITY_INVALID, "gate_lot_size_unconfirmed", leg_number=number, leg=value))
        else:
            if leg.quantity % lot != 0:
                out.append(_fail(CheckCode.QUANTITY_INVALID, "gate_quantity_not_lots", leg_number=number, leg=value,
                                 quantity=leg.quantity, underlying=underlying, lot=lot, two_lots=2 * lot))
        if leg.expiry < today:
            out.append(_fail(CheckCode.EXPIRY_PASSED, "gate_expiry_passed", leg_number=number, leg=number,
                             contract=value, date=leg.expiry))
            continue
        matches = index.get(key, [])
        if len(matches) > 1:
            out.append(_fail(CheckCode.CONTRACT_AMBIGUOUS, "gate_contract_ambiguous", leg_number=number, leg=value))
            continue
        if not matches:
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            out.append(_contract_failure(CheckCode.CONTRACT_NOT_FOUND, "gate_contract_not_found", number, leg,
                                         underlying, alts))
            continue
        entry = matches[0]
        if not entry.currently_listed:
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            out.append(_contract_failure(CheckCode.CONTRACT_NOT_LISTED, "gate_contract_not_listed", number, leg,
                                         underlying, alts))
            continue
        if not entry.has_ref(ZERODHA):
            # REQ-054 AC-3: a contract with no Zerodha row cannot be traded at Zerodha; no symbol is guessed.
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            out.append(_contract_failure(CheckCode.CONTRACT_NOT_FOUND, "gate_contract_no_zerodha_record", number,
                                         leg, underlying, alts))
            continue
        status = eligibility.get(entry.contract.id)
        if status is None or not status.tradable:
            alts = _alternatives(leg, underlying, catalogue, eligibility)
            template_id = "gate_contract_unconfirmed" if status is None else "gate_contract_unavailable"
            out.append(_contract_failure(CheckCode.CONTRACT_NOT_ELIGIBLE, template_id, number, leg, underlying, alts))
    return out


def _risk_flags(strategy: Strategy, ctx: ExecutionContext) -> tuple[list[Flag], Decimal | _Unlimited | None]:
    flags: list[Flag] = []
    max_loss: Decimal | _Unlimited | None = None
    if ctx.action is ExecutionAction.EXIT:
        pass  # closing orders are not a strategy; their payoff says nothing about the risk left behind
    elif strategy.is_single_expiry:
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


# REQ-059 Gate decisions (SPEC CHANGE to AC-1, review MAJOR 2): an exit frees margin, closing orders are not fresh
# positions, and a user must never be stopped from getting out of risk by a rule-definition or data problem.
EXIT_NOT_REQUIRED: frozenset[CheckCode] = frozenset({
    CheckCode.MARGIN_INSUFFICIENT,
    CheckCode.CONTRACT_NOT_ELIGIBLE,
    CheckCode.RULES_INVALID,
    CheckCode.DATA_UNHEALTHY,
    CheckCode.ENTITLEMENT_REQUIRED,
})
STALE_ON_EXIT = "Prices shown may be stale — confirm to continue."


def _exit_failure(strategy: Strategy, ctx: ExecutionContext) -> CheckFailure | None:
    """Review MAJOR 1: every exit order closes or reduces a held position of the same contract, opposite side."""
    if ctx.active_legs is None:
        return _fail(CheckCode.EXIT_NOT_REDUCE_ONLY, "gate_exit_unverified")
    held = _positions(ctx.active_legs)
    opposite = {Action.BUY.value: Action.SELL.value, Action.SELL.value: Action.BUY.value}
    for (key, side), units in _positions(strategy.legs).items():
        if held.get((key, opposite[side]), 0) < units:
            return _fail(CheckCode.EXIT_NOT_REDUCE_ONLY, "gate_exit_adds_position")
    return None


def _active_legs_failure(ctx: ExecutionContext, strategy_id: str) -> CheckFailure | None:
    """Round 2 MAJOR A: supplied active legs are trusted only when their canonical hash, with this strategy's id
    and the active version id, equals the hash stored with that version."""
    if ctx.active_legs is None:
        return None
    if ctx.active_version_id is None or ctx.active_legs_hash is None or (
        active_legs_hash(strategy_id, ctx.active_version_id, ctx.active_legs) != ctx.active_legs_hash
    ):
        return _fail(CheckCode.ACTIVE_LEGS_UNVERIFIED, "gate_active_legs_unverified")
    return None


def _run_checks(
    strategy: Strategy, ctx: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry,
    strategy_id: str,
) -> tuple[
    list[CheckFailure], tuple[CheckCode, ...], tuple[CheckCode, ...], frozenset[CheckCode], list[Flag],
    Decimal | _Unlimited | None,
]:
    uses_active_legs = ctx.action is not ExecutionAction.NEW_ENTRY
    unverified = _active_legs_failure(ctx, strategy_id) if uses_active_legs else None
    trusted = dataclasses.replace(ctx, active_legs=None) if unverified else ctx  # never reason from unverified legs
    pro_reason = pro_requirement(strategy, trusted)
    failures = _context_failures(ctx, pro_reason, strategy_id)
    if unverified is not None:
        failures.append(unverified)
    if strategy_id != ctx.strategy_id:
        failures.insert(0, _fail(CheckCode.STRATEGY_MISMATCH, "gate_strategy_mismatch"))
    not_checked: tuple[CheckCode, ...] = ()
    if ctx.underlying not in SUPPORTED_UNDERLYINGS:
        failures.insert(0, _fail(CheckCode.UNDERLYING_UNSUPPORTED, "gate_underlying_unsupported",
                                 symbol=ctx.underlying))
        not_checked = _CONTRACT_CHECKS + (CheckCode.DUPLICATE_LEG,)
    else:
        failures.extend(_leg_failures(strategy, ctx, catalogue, eligibility))
    flags, max_loss = _risk_flags(strategy, ctx)

    not_applicable: frozenset[CheckCode] = frozenset()
    if ctx.action is ExecutionAction.EXIT:
        not_applicable = EXIT_NOT_REQUIRED
        if any(f.code is CheckCode.DATA_UNHEALTHY for f in failures):
            flags.append(Flag(FlagCode.DATA_STALE_ON_EXIT, STALE_ON_EXIT))
        failures = [f for f in failures if f.code not in not_applicable]
        if unverified is None:
            exit_failure = _exit_failure(strategy, ctx)
            if exit_failure is not None:
                failures.append(exit_failure)
        else:
            not_checked = not_checked + (CheckCode.EXIT_NOT_REDUCE_ONLY,)
    elif ctx.action is ExecutionAction.ADJUSTMENT:
        not_applicable = frozenset({CheckCode.EXIT_NOT_REDUCE_ONLY})
        if pro_reason is None:
            not_applicable |= {CheckCode.ENTITLEMENT_REQUIRED}
    else:
        not_applicable = frozenset({CheckCode.EXIT_NOT_REDUCE_ONLY, CheckCode.ACTIVE_LEGS_UNVERIFIED})
    not_applicable |= {CheckCode.INTERNAL_ERROR}
    failed = {f.code for f in failures}
    passed = tuple(c for c in CheckCode if c not in failed and c not in not_checked and c not in not_applicable)
    return failures, passed, not_checked, not_applicable - {CheckCode.INTERNAL_ERROR}, flags, max_loss


def check_pre_execution(
    strategy: Strategy, context: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry,
    *, strategy_id: str,
) -> SafetyResult:
    """Run every pre-execution check (REQ-059 AC-1, AC-3); block if any fails; never change ``strategy``.

    ``strategy_id`` is the id of the strategy being executed; a context built for another strategy is blocked.
    Any internal exception blocks with ``INTERNAL_ERROR`` (never a pass) and still carries the audit record.
    """
    if not isinstance(strategy, Strategy):
        raise ValueError(f"strategy must be a Strategy, got {strategy!r}")
    if not isinstance(context, ExecutionContext):
        raise ValueError(f"context must be an ExecutionContext, got {context!r}")
    if not isinstance(catalogue, Catalogue) or not isinstance(eligibility, EligibilityRegistry):
        raise ValueError("catalogue and eligibility must be a Catalogue and an EligibilityRegistry")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError(f"strategy_id must be a non-empty string, got {strategy_id!r}")

    try:
        failures, passed, not_checked, not_applicable, flags, max_loss = _run_checks(
            strategy, context, catalogue, eligibility, strategy_id
        )
    except Exception:
        logger.exception("pre-execution checks raised strategy=%s action=%s", strategy_id, context.action.value)
        failures = [_fail(CheckCode.INTERNAL_ERROR, "gate_internal_error")]
        passed, not_checked, not_applicable, flags, max_loss = (), (), frozenset(), [], None

    needs_confirmation = not failures and any(f.code is FlagCode.DATA_STALE_ON_EXIT for f in flags)
    record = None
    if failures:
        record = BlockedExecution(
            strategy_id=strategy_id, version_id=context.version_id, action=context.action.value,
            failed_codes=tuple(f.code for f in failures), reasons=tuple(f.reason for f in failures),
            at=context.as_of, actor=context.actor,
        )
    result = SafetyResult(
        failures=tuple(failures), passed=passed, not_checked=not_checked,
        not_applicable=tuple(c for c in CheckCode if c in not_applicable), flags=tuple(flags), max_loss=max_loss,
        margin_required=context.margin_required, charges_estimate=context.charges_estimate, blocked_execution=record,
        requires_confirmation=needs_confirmation, confirmation_text=STALE_ON_EXIT if needs_confirmation else None,
    )
    if result.blocked:
        logger.warning(
            "pre-execution blocked strategy=%s action=%s codes=%s", strategy_id, context.action.value,
            ",".join(f.code.value for f in result.failures),
        )
    else:
        logger.info("pre-execution passed strategy=%s action=%s", strategy_id, context.action.value)
    return result
