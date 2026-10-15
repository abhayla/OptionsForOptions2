"""The margin gate before the Kite basket is built (W-081, REQ-055 AC-1/AC-3/AC-4, ADR-016, ADR-054).

Zerodha is the authority on margin (ADR-016): the basket is built only if the funds Zerodha reports are at least the
margin Zerodha says the planned orders need. The required figure is the basket reply's ``final.total`` (after the
spread/hedge benefit Zerodha gives a basket), not ``initial.total``: for the 15 Oct 2026 four-leg NIFTY condor that is
Rs 68,498.85 against Rs 2,96,332.80, and ``initial`` would block hedged strategies Zerodha accepts. No platform
estimate takes part in the decision (AC-3).

The basket builder CALLS `check_margin`; a `MarginVerdict` cannot be built anywhere else, so a caller cannot hand over
a passing verdict of its own. An amount that is unknown (None) blocks. Money is exact `Decimal`; a float, string, int,
NaN, infinity or negative amount raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Final

from ofo.errors import UserFacingError, render

_MINT: Final = object()  # module-private: only check_margin mints a verdict
_PAISE: Final = Decimal("0.01")


class MarginReplyError(ValueError):
    """Zerodha's basket-margin reply has no usable ``final.total``: the basket must not be built."""


def _amount(value: object, name: str) -> Decimal:
    if type(value) is not Decimal:
        raise TypeError(f"{name} must be exactly Decimal, got {type(value).__name__}")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite amount of 0 or more, got {value!r}")
    return value


@dataclass(frozen=True)
class MarginVerdict:
    """The gate's answer: `allowed`, the two amounts (None when unknown) and, when blocked, the four-part message."""

    allowed: bool
    available: Decimal | None
    required: Decimal | None
    message: UserFacingError | None
    _mint: object = None

    def __post_init__(self) -> None:
        if self._mint is not _MINT:
            raise TypeError("a MarginVerdict comes only from check_margin")


def check_margin(available: Decimal | None, required: Decimal | None) -> MarginVerdict:
    """Allowed when `available` >= `required` (equal is allowed); otherwise blocked with both amounts shown.

    Both are Zerodha's figures. None (not confirmed with Zerodha) blocks with the "could not confirm" message."""
    if available is None or required is None:
        for value, name in ((available, "available"), (required, "required")):
            if value is not None:
                _amount(value, name)  # a known amount is still validated
        return MarginVerdict(False, available, required, render("gate_margin_unconfirmed"), _mint=_MINT)
    have, need = _amount(available, "available"), _amount(required, "required")
    if have >= need:
        return MarginVerdict(True, have, need, None, _mint=_MINT)
    # Shown to the paisa, never in the user's favour: the shortfall must not display as two equal amounts.
    message = render("margin_basket_insufficient", available=have.quantize(_PAISE, rounding=ROUND_FLOOR),
                     required=need.quantize(_PAISE, rounding=ROUND_CEILING))
    return MarginVerdict(False, have, need, message, _mint=_MINT)


def required_from_basket_reply(data: Mapping[str, object]) -> Decimal:
    """The margin the basket needs: ``final.total`` of Zerodha's ``POST /margins/basket`` reply ``data``.

    The reply must have been parsed with ``parse_float=Decimal``; anything but a finite, non-negative Decimal there
    (missing keys, null, float, string, bool) raises `MarginReplyError`."""
    final = data.get("final") if isinstance(data, Mapping) else None
    total = final.get("total") if isinstance(final, Mapping) else None
    if type(total) is not Decimal and type(total) is not int:
        raise MarginReplyError("the basket margin reply has no numeric final.total")
    value = Decimal(total)  # an int (Kite prints whole totals without a point) is exact
    if not value.is_finite() or value < 0:
        raise MarginReplyError("the basket margin reply's final.total is not a finite amount of 0 or more")
    return value
