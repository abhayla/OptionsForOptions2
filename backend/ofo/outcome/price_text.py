"""GC-UI D-PX (REQ-152 AC-2/AC-4, ADR-008): a per-unit price as the browser prints it. The one helper every reply that
carries a ``*_display`` price beside its exact value uses (the same text as the table cells' ``cell_number``)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ofo.errors.explanations import render_explanation
from ofo.money import PAISE


def price_text(value: Decimal | None) -> str | None:
    """Two decimals, half-up from the exact Decimal (REQ-152 AC-3); None -> None (the browser prints the dash)."""
    return None if value is None else render_explanation("cell_number", value=value.quantize(PAISE, rounding=ROUND_HALF_UP))  # noqa: E501 - long line kept whole
