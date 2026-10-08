"""CheckCode -> ErrorClass: every execution safety-gate check code maps to exactly one ErrorClass.

W-014 (backend/ofo/execution/safety.py) landed on main (2026-09-29, PR #24) after W-024 rounds 1-2;
this is the mapping those rounds' guard test deferred. `tests/errors/test_checkcode_map.py` asserts
the mapping is total: every `CheckCode` member has an entry, and every entry names a real member.
"""

from __future__ import annotations

from ofo.execution.safety import CheckCode

from ofo.errors.classes import ErrorClass

#: One ErrorClass per CheckCode (REQ-065 AC-1 classes). Each mapping is the class whose four-part
#: message best explains that check's failure to the user; grouped by rationale below.
CHECKCODE_TO_ERROR_CLASS: dict[CheckCode, ErrorClass] = {
    # The chosen underlying/instrument itself is not something this platform can execute.
    CheckCode.UNDERLYING_UNSUPPORTED: ErrorClass.USER_INPUT,
    CheckCode.QUANTITY_INVALID: ErrorClass.USER_INPUT,
    # The strategy/version/rules are not in an executable shape.
    CheckCode.VERSION_NOT_EXECUTABLE: ErrorClass.STRATEGY_VALIDATION,
    CheckCode.RULES_INVALID: ErrorClass.STRATEGY_VALIDATION,
    CheckCode.DUPLICATE_LEG: ErrorClass.STRATEGY_VALIDATION,
    CheckCode.EXIT_NOT_REDUCE_ONLY: ErrorClass.STRATEGY_VALIDATION,
    CheckCode.DEPENDENCIES_UNSATISFIED: ErrorClass.STRATEGY_VALIDATION,
    # Market/contract data problems.
    CheckCode.MARKET_CLOSED: ErrorClass.MARKET_DATA,
    CheckCode.DATA_UNHEALTHY: ErrorClass.MARKET_DATA,
    CheckCode.EXPIRY_PASSED: ErrorClass.MARKET_DATA,
    CheckCode.CONTRACT_NOT_FOUND: ErrorClass.MARKET_DATA,
    CheckCode.CONTRACT_AMBIGUOUS: ErrorClass.MARKET_DATA,
    CheckCode.CONTRACT_NOT_LISTED: ErrorClass.MARKET_DATA,
    # Broker session/connection problems.
    CheckCode.BROKER_NOT_CONNECTED: ErrorClass.BROKER_AUTHENTICATION,
    CheckCode.SESSION_INVALID: ErrorClass.BROKER_AUTHENTICATION,
    # The broker account is not permitted to trade this.
    CheckCode.CONTRACT_NOT_ELIGIBLE: ErrorClass.BROKER_ELIGIBILITY,
    # Not enough margin.
    CheckCode.MARGIN_INSUFFICIENT: ErrorClass.MARGIN,
    # The platform's plan/entitlement.
    CheckCode.ENTITLEMENT_REQUIRED: ErrorClass.ENTITLEMENT_ACCESS,
    # The platform's record of live legs/strategy doesn't match what should be true.
    CheckCode.ACTIVE_LEGS_UNVERIFIED: ErrorClass.RECONCILIATION_MISMATCH,
    CheckCode.STRATEGY_MISMATCH: ErrorClass.RECONCILIATION_MISMATCH,
    CheckCode.RECONCILIATION_MISMATCH: ErrorClass.RECONCILIATION_MISMATCH,
    # Everything else is our own bug.
    CheckCode.INTERNAL_ERROR: ErrorClass.INTERNAL_SYSTEM,
}


def error_class_for_check(code: CheckCode) -> ErrorClass:
    """Return the `ErrorClass` for a safety-gate `CheckCode`; raises `KeyError` if unmapped."""
    return CHECKCODE_TO_ERROR_CLASS[code]
