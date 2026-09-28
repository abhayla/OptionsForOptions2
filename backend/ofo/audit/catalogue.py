"""Audit event-type catalogue (REQ-064 AC-1, including the ADR-029 identity events).

Every event named in REQ-064 AC-1's text has exactly one member here, and every member here maps
back to exactly one phrase from that text. ``tests/audit/test_catalogue.py`` parses the AC-1 text
programmatically and asserts the two sets are equal, so this catalogue cannot silently drop or add
an event without a test failing.
"""
from __future__ import annotations

from enum import Enum


class EventType(Enum):
    """One member per audited event named in REQ-064 AC-1."""

    # General actions (REQ-064 AC-1, first clause)
    STRATEGY_CHANGED = "strategy_changed"
    VERSION_CREATED = "version_created"
    RULE_EVALUATED = "rule_evaluated"
    TRIGGER_VALUE_RECORDED = "trigger_value_recorded"
    USER_APPROVAL_RECORDED = "user_approval_recorded"
    ORDER_PREPARED = "order_prepared"
    ORDER_SUBMITTED = "order_submitted"
    BROKER_RESPONSE_RECORDED = "broker_response_recorded"
    EXECUTION_RECORDED = "execution_recorded"
    RECONCILIATION_RECORDED = "reconciliation_recorded"
    EXTERNAL_BROKER_CHANGE_DETECTED = "external_broker_change_detected"
    ENTITLEMENT_CHANGED = "entitlement_changed"
    ADMIN_CHANGE_RECORDED = "admin_change_recorded"
    SECURITY_EVENT_RECORDED = "security_event_recorded"

    # Identity events (ADR-029, T1 #272 s27)
    PLATFORM_ACCOUNT_CREATED = "platform_account_created"
    GOOGLE_IDENTITY_ADDED = "google_identity_added"
    GOOGLE_IDENTITY_CHANGED = "google_identity_changed"
    MOBILE_VERIFIED = "mobile_verified"
    ZERODHA_CLIENT_ID_ASSOCIATED = "zerodha_client_id_associated"
    ZERODHA_SESSION_AUTHENTICATED = "zerodha_session_authenticated"
    ZERODHA_SESSION_EXPIRED = "zerodha_session_expired"
    TRIAL_STARTED = "trial_started"
    TRIAL_EXPIRED = "trial_expired"
    DIRECT_CUSTOMER_ELIGIBILITY_GRANTED = "direct_customer_eligibility_granted"
    DIRECT_CUSTOMER_ELIGIBILITY_REVOKED = "direct_customer_eligibility_revoked"
    REFERRAL_REWARD_GRANTED = "referral_reward_granted"
    SUBSCRIPTION_STARTED = "subscription_started"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    EMAIL_CHANGED = "email_changed"
    ZERODHA_ASSOCIATION_TRANSFERRED = "zerodha_association_transferred"
    TRANSFER_SENT_TO_ADMIN_REVIEW = "transfer_sent_to_admin_review"
    ACCOUNT_DELETED = "account_deleted"
    ANTI_ABUSE_RESTRICTION_TRIGGERED = "anti_abuse_restriction_triggered"


#: Maps each catalogue member to the exact (lower-cased) REQ-064 AC-1 phrase it covers, so the
#: AC-1 text can be checked against the catalogue word for word. See test_catalogue.py.
EVENT_SPEC_PHRASES: dict[EventType, str] = {
    EventType.STRATEGY_CHANGED: "strategy changes",
    EventType.VERSION_CREATED: "version creation",
    EventType.RULE_EVALUATED: "rule evaluation",
    EventType.TRIGGER_VALUE_RECORDED: "trigger values",
    EventType.USER_APPROVAL_RECORDED: "user approvals",
    EventType.ORDER_PREPARED: "order preparation",
    EventType.ORDER_SUBMITTED: "order submission",
    EventType.BROKER_RESPONSE_RECORDED: "broker responses",
    EventType.EXECUTION_RECORDED: "execution",
    EventType.RECONCILIATION_RECORDED: "reconciliation",
    EventType.EXTERNAL_BROKER_CHANGE_DETECTED: "external broker changes",
    EventType.ENTITLEMENT_CHANGED: "entitlement changes",
    EventType.ADMIN_CHANGE_RECORDED: "admin changes",
    EventType.SECURITY_EVENT_RECORDED: "security events",
    EventType.PLATFORM_ACCOUNT_CREATED: "platform account created",
    EventType.GOOGLE_IDENTITY_ADDED: "google identity added",
    EventType.GOOGLE_IDENTITY_CHANGED: "google identity changed",
    EventType.MOBILE_VERIFIED: "mobile verified",
    EventType.ZERODHA_CLIENT_ID_ASSOCIATED: "zerodha client id associated",
    EventType.ZERODHA_SESSION_AUTHENTICATED: "zerodha session authenticated",
    EventType.ZERODHA_SESSION_EXPIRED: "zerodha session expired",
    EventType.TRIAL_STARTED: "trial started",
    EventType.TRIAL_EXPIRED: "trial expired",
    EventType.DIRECT_CUSTOMER_ELIGIBILITY_GRANTED: "direct-customer eligibility granted",
    EventType.DIRECT_CUSTOMER_ELIGIBILITY_REVOKED: "direct-customer eligibility revoked",
    EventType.REFERRAL_REWARD_GRANTED: "referral reward granted",
    EventType.SUBSCRIPTION_STARTED: "subscription started",
    EventType.SUBSCRIPTION_EXPIRED: "subscription expired",
    EventType.EMAIL_CHANGED: "email changed",
    EventType.ZERODHA_ASSOCIATION_TRANSFERRED: "zerodha association transferred",
    EventType.TRANSFER_SENT_TO_ADMIN_REVIEW: "transfer sent to admin review",
    EventType.ACCOUNT_DELETED: "account deleted",
    EventType.ANTI_ABUSE_RESTRICTION_TRIGGERED: "anti-abuse restriction triggered",
}

assert set(EVENT_SPEC_PHRASES) == set(EventType), "every catalogue member must have a spec phrase"
