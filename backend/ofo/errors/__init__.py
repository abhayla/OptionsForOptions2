"""Error classification and user-facing error messages (REQ-065).

Rounds 3-5 (W-024): `UserFacingError` has no public constructor. Build one with `render(template_id,
**slots)` from the fixed, CI-scanned `CATALOGUE` of `MessageTemplate`s.

Public surface:
- `ErrorClass`: the AC-1 classification enum.
- `UserFacingError`: an immutable error carrying the four required message parts (plus optional
  `external_text`); no public constructor.
- `MessageTemplate`, `CATALOGUE`: the fixed, reviewed template catalogue.
- `render`: the only way to build a `UserFacingError`.
- Slot types: `Money`, `PnLMoney`, `Int`, `Count`, `Time`, `Instrument`, `Underlying`, `Code`,
  `ExternalText` (with its closed `ExternalSource` label).
"""

from .classes import ErrorClass
from .model import UserFacingError
from .slots import (
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
from .templates import CATALOGUE, MessageTemplate, render

__all__ = [
    "ErrorClass",
    "UserFacingError",
    "MessageTemplate",
    "CATALOGUE",
    "render",
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
