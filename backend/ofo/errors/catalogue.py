"""CATALOGUE: one example `UserFacingError` per `ErrorClass`, in calm decision-support wording.

No real personal data: account numbers, names and identifiers below are placeholders
("your Zerodha account", "ABCDE1234F" is not used — no PAN-shaped strings appear at all).
"""

from __future__ import annotations

from .classes import ErrorClass
from .model import UserFacingError

CATALOGUE: dict[ErrorClass, UserFacingError] = {
    ErrorClass.USER_INPUT: UserFacingError(
        error_class=ErrorClass.USER_INPUT,
        code="USER_INPUT_001",
        what_happened="The lot size you entered (0) is not a positive whole number.",
        impact="The strategy cannot be priced or saved with this quantity.",
        what_is_blocked="Saving and pricing of this strategy.",
        next_action="Enter a lot size of 1 or more and try again.",
    ),
    ErrorClass.STRATEGY_VALIDATION: UserFacingError(
        error_class=ErrorClass.STRATEGY_VALIDATION,
        code="STRATEGY_VALIDATION_001",
        what_happened="This strategy has two legs on the same strike and expiry in the same direction.",
        impact="The payoff and margin shown would not match what the exchange allows.",
        what_is_blocked="Saving this strategy version.",
        next_action="Remove or change one of the duplicate legs, then save again.",
    ),
    ErrorClass.MARKET_DATA: UserFacingError(
        error_class=ErrorClass.MARKET_DATA,
        code="MARKET_DATA_001",
        what_happened="No option chain data has arrived for NIFTY in the last 5 minutes.",
        impact="Prices and Greeks on screen are stale and may not match the live market.",
        what_is_blocked="New order preparation for this instrument.",
        next_action="Wait for the data feed to reconnect, or refresh the page in a few minutes.",
    ),
    ErrorClass.BROKER_AUTHENTICATION: UserFacingError(
        error_class=ErrorClass.BROKER_AUTHENTICATION,
        code="BROKER_AUTHENTICATION_001",
        what_happened="Your Zerodha session has expired.",
        impact="Orders, positions and margin cannot be read or sent to Zerodha right now.",
        what_is_blocked="Order preparation, submission and live position tracking.",
        next_action="Log in to Zerodha again from the account page to reconnect.",
    ),
    ErrorClass.BROKER_ELIGIBILITY: UserFacingError(
        error_class=ErrorClass.BROKER_ELIGIBILITY,
        code="BROKER_ELIGIBILITY_001",
        what_happened="Your Zerodha account is not enabled for F&O segment trading.",
        impact="Options and futures orders placed here cannot be accepted by Zerodha.",
        what_is_blocked="Order submission for this strategy.",
        next_action="Enable the F&O segment in your Zerodha account, then retry.",
    ),
    ErrorClass.MARGIN: UserFacingError(
        error_class=ErrorClass.MARGIN,
        code="MARGIN_001",
        what_happened="Margin available ₹41,200 is below the ₹48,000 this strategy needs.",
        impact="Zerodha would reject this order for insufficient margin.",
        what_is_blocked="Execution of this strategy.",
        next_action="Add funds in Zerodha or reduce the quantity, then retry.",
    ),
    ErrorClass.ORDER_REJECTION: UserFacingError(
        error_class=ErrorClass.ORDER_REJECTION,
        code="ORDER_REJECTION_001",
        what_happened="Zerodha rejected one leg of this order: price outside the circuit limit.",
        impact="This leg was not placed, so the strategy is only partly submitted.",
        what_is_blocked="Further legs of this order until this one is resolved.",
        next_action="Review the rejected leg's price against the current circuit limit and resubmit it.",
    ),
    ErrorClass.PARTIAL_EXECUTION: UserFacingError(
        error_class=ErrorClass.PARTIAL_EXECUTION,
        code="PARTIAL_EXECUTION_001",
        what_happened="2 of 4 legs filled; the remaining 2 legs are still open at Zerodha.",
        impact="The strategy's current position does not match its intended shape yet.",
        what_is_blocked="Automatic adjustments and rule evaluation for this strategy.",
        next_action="Check the open legs in Zerodha and cancel or complete them manually.",
    ),
    ErrorClass.RECONCILIATION_MISMATCH: UserFacingError(
        error_class=ErrorClass.RECONCILIATION_MISMATCH,
        code="RECONCILIATION_MISMATCH_001",
        what_happened="Zerodha shows 2 lots on this leg; this platform's record shows 3 lots.",
        impact="P&L, Greeks and rule checks for this strategy cannot be trusted until this is resolved.",
        what_is_blocked="New orders and automatic rule triggers for this strategy.",
        next_action="Review the mismatch on the reconciliation screen and confirm which figure is correct.",
    ),
    ErrorClass.NOTIFICATION: UserFacingError(
        error_class=ErrorClass.NOTIFICATION,
        code="NOTIFICATION_001",
        what_happened="The WhatsApp alert for this rule trigger could not be delivered.",
        impact="You may not have seen that this rule was triggered.",
        what_is_blocked="Further WhatsApp alerts on this channel until delivery succeeds again.",
        next_action="Check the alert on this page directly, and confirm your WhatsApp number is correct.",
    ),
    ErrorClass.ENTITLEMENT_ACCESS: UserFacingError(
        error_class=ErrorClass.ENTITLEMENT_ACCESS,
        code="ENTITLEMENT_ACCESS_001",
        what_happened="Your trial period for this feature has ended.",
        impact="This feature's screens and actions are read-only.",
        what_is_blocked="Creating or editing strategies that use this feature.",
        next_action="Upgrade your plan on the billing page to regain access.",
    ),
    ErrorClass.INTERNAL_SYSTEM: UserFacingError(
        error_class=ErrorClass.INTERNAL_SYSTEM,
        code="INTERNAL_SYSTEM_001",
        what_happened="An unexpected server error occurred while saving this strategy.",
        impact="Your latest changes to this strategy were not saved.",
        what_is_blocked="Saving this strategy until the issue is resolved.",
        next_action="Try again in a few minutes; contact support if this keeps happening.",
    ),
}


def example_for(error_class: ErrorClass) -> UserFacingError:
    """Return the catalogue's example `UserFacingError` for `error_class`."""
    return CATALOGUE[error_class]
