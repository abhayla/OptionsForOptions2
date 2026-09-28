"""Error classification and user-facing error messages (REQ-065).

Public surface:
- `ErrorClass`: the AC-1 classification enum.
- `UserFacingError`: an immutable error carrying the four required message parts.
- `BANNED_PHRASES`: the ADR-003 advice-wording denylist, enforced at construction.
- `CATALOGUE`: one example `UserFacingError` per `ErrorClass`.
"""

from .classes import ErrorClass
from .model import BANNED_PHRASES, UserFacingError, scan_for_banned_phrases
from .catalogue import CATALOGUE, example_for

__all__ = [
    "ErrorClass",
    "UserFacingError",
    "BANNED_PHRASES",
    "scan_for_banned_phrases",
    "CATALOGUE",
    "example_for",
]
