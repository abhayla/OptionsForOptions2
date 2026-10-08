"""ErrorClass: the classification set from REQ-065 AC-1.

REQ-065 AC-1: "Errors are classified at least as: user input, strategy validation, market data,
broker authentication, broker eligibility, margin, order rejection, partial execution,
reconciliation mismatch, notification, entitlement/access, internal system."

Member names are the AC-1 phrases normalised to `UPPER_SNAKE_CASE` (spaces and `/` become `_`),
which is what lets `tests/errors/test_error_catalogue.py` parse the requirement text on disk and check
every listed class has a member, without hand-typing the mapping twice.
"""

from __future__ import annotations

from enum import Enum, unique


@unique
class ErrorClass(Enum):
    """One member per AC-1 error classification, plus none beyond what AC-1 lists."""

    USER_INPUT = "user input"
    STRATEGY_VALIDATION = "strategy validation"
    MARKET_DATA = "market data"
    BROKER_AUTHENTICATION = "broker authentication"
    BROKER_ELIGIBILITY = "broker eligibility"
    MARGIN = "margin"
    ORDER_REJECTION = "order rejection"
    PARTIAL_EXECUTION = "partial execution"
    RECONCILIATION_MISMATCH = "reconciliation mismatch"
    NOTIFICATION = "notification"
    ENTITLEMENT_ACCESS = "entitlement/access"
    INTERNAL_SYSTEM = "internal system"
