"""Timeline entry types (REQ-040 AC-1) and trigger follow-up kinds (REQ-040 AC-4).

Every entry type named in REQ-040 AC-1 has exactly one ``EntryType`` member, and every follow-up named in AC-4 has
exactly one ``FollowUpKind`` member. ``tests/timeline/test_timeline.py`` and ``tests/timeline/test_trigger_record.py``
parse the AC texts from ``spec/requirements/REQ-040.md`` on disk and assert the sets are equal, so neither enum can
silently drop or invent a member.
"""
from __future__ import annotations

from enum import Enum


class EntryType(Enum):
    """One member per timeline entry named in REQ-040 AC-1, in the spec's order."""

    CREATED = "created"
    MODIFIED = "modified"
    VALIDATED = "validated"
    ACTIVATED = "activated"
    RULE_TRIGGERED = "rule_triggered"
    ADJUSTMENT_PROPOSED = "adjustment_proposed"
    ORDER_PREPARED = "order_prepared"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL_EXECUTION = "partial_execution"
    REJECTION = "rejection"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    EXTERNAL_BROKER_CHANGE = "external_broker_change"
    USER_ACKNOWLEDGEMENT = "user_acknowledgement"
    EXIT = "exit"
    COMPLETION = "completion"


#: The exact (lower-cased) REQ-040 AC-1 phrase each member covers.
ENTRY_SPEC_PHRASES: dict[EntryType, str] = {
    EntryType.CREATED: "created",
    EntryType.MODIFIED: "modified",
    EntryType.VALIDATED: "validated",
    EntryType.ACTIVATED: "activated",
    EntryType.RULE_TRIGGERED: "rule triggered",
    EntryType.ADJUSTMENT_PROPOSED: "adjustment proposed",
    EntryType.ORDER_PREPARED: "order prepared",
    EntryType.SUBMITTED: "submitted",
    EntryType.FILLED: "filled",
    EntryType.PARTIAL_EXECUTION: "partial execution",
    EntryType.REJECTION: "rejection",
    EntryType.RECONCILIATION_REQUIRED: "reconciliation required",
    EntryType.EXTERNAL_BROKER_CHANGE: "external broker change",
    EntryType.USER_ACKNOWLEDGEMENT: "user acknowledgement",
    EntryType.EXIT: "exit",
    EntryType.COMPLETION: "completion",
}


class FollowUpKind(Enum):
    """What followed a trigger (REQ-040 AC-4). The first four and the last are yes/no; the broker report is text."""

    ALERT_GENERATED = "alert_generated"
    ORDER_PREPARED = "order_prepared"
    CONFIRMATION_REQUIRED = "confirmation_required"
    EXECUTED = "executed"
    BROKER_REPORTED = "broker_reported"
    RECONCILIATION_SUCCEEDED = "reconciliation_succeeded"

    @property
    def is_yes_no(self) -> bool:
        return self is not FollowUpKind.BROKER_REPORTED


#: The exact (lower-cased) REQ-040 AC-4 phrase each member covers.
FOLLOW_UP_SPEC_PHRASES: dict[FollowUpKind, str] = {
    FollowUpKind.ALERT_GENERATED: "alert generated",
    FollowUpKind.ORDER_PREPARED: "order prepared",
    FollowUpKind.CONFIRMATION_REQUIRED: "confirmation required",
    FollowUpKind.EXECUTED: "executed",
    FollowUpKind.BROKER_REPORTED: "what the broker reported",
    FollowUpKind.RECONCILIATION_SUCCEEDED: "whether reconciliation succeeded",
}

assert set(ENTRY_SPEC_PHRASES) == set(EntryType), "every entry type must have a spec phrase"
assert set(FOLLOW_UP_SPEC_PHRASES) == set(FollowUpKind), "every follow-up kind must have a spec phrase"
