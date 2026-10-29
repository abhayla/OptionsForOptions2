"""Live defect #603 item 2 (REQ-152 AC-2 style): the builder header's index level is the server's two-decimal text, so
"22713" and "22709.5" never reach the screen (the Decimal had lost its trailing zeros)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.outcome.serialize import _level


@pytest.mark.parametrize(("level", "text"), [
    (Decimal("22713"), "22713.00"),
    (Decimal("22713.00"), "22713.00"),
    (Decimal("22709.5"), "22709.50"),
    (Decimal("22722.15"), "22722.15"),
    (None, None),
])
def test_the_index_level_is_two_decimal_text(level, text) -> None:
    assert _level(level) == text
