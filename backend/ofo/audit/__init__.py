"""Append-only audit log and event catalogue (REQ-064).

Out of scope here: domain-model "timeline" records (REQ-064 AC-2 also names "timeline records" as
append-only) are a separate, user-facing feature and are not built in this work item.
"""
from ofo.audit.catalogue import EVENT_SPEC_PHRASES, EventType
from ofo.audit.log import AuditChainError, AuditLog, HeadAnchor, VerificationResult
from ofo.audit.models import GENESIS_HASH, AuditEvent, PayloadValidationError

__all__ = [
    "EVENT_SPEC_PHRASES",
    "GENESIS_HASH",
    "AuditChainError",
    "AuditEvent",
    "AuditLog",
    "EventType",
    "HeadAnchor",
    "PayloadValidationError",
    "VerificationResult",
]
