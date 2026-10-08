"""Error classification and user-facing error messages (REQ-065).

Rounds 3-5 (W-024): `UserFacingError` has no public constructor. Build one with `render(template_id,
**slots)` from the fixed, CI-scanned `CATALOGUE` of `MessageTemplate`s.

Public surface:
- `ErrorClass`: the AC-1 classification enum.
- `UserFacingError`: an immutable error carrying the four required message parts (plus optional
  `external_text`); no public constructor.
- `MessageTemplate`, `CATALOGUE`: the fixed, reviewed template catalogue.
- `render`: the only way to build a `UserFacingError`.
- `UserFacing`, `user_message_of`: the marker for exceptions/results whose message is shown to a user (round 9
  part 6); the API boundary shows only their message, and the INTERNAL_SYSTEM template for anything else.
- Slot types: `Money`, `PnLMoney`, `Int`, `Count`, `Time`, `Instrument`, `Underlying`, `Code`,
  `ExternalText` (with its closed `ExternalSource` label).
"""

from ofo.errors.classes import ErrorClass
from ofo.errors.model import UserFacingError
from ofo.errors.slots import (
    Code,
    Count,
    ExternalSource,
    ExternalText,
    Instrument,
    Int,
    Money,
    PnLMoney,
    SlotType,
    Time,
    Underlying,
)
from ofo.errors.gate_slots import LegValue
from ofo.errors.templates import CATALOGUE, MessageTemplate, display_text, render
from ofo.errors.user_facing import UserFacing, user_message_of

__all__ = [
    "ErrorClass",
    "UserFacingError",
    "UserFacing",
    "user_message_of",
    "MessageTemplate",
    "CATALOGUE",
    "render",
    "display_text",
    "LegValue",
    "Money",
    "PnLMoney",
    "Int",
    "Time",
    "Instrument",
    "Underlying",
    "Code",
    "Count",
    "ExternalSource",
    "ExternalText",
    "SlotType",
]
