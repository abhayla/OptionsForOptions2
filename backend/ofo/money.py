"""The one home of the two-decimal step (ADR-008: money is exact `Decimal`, never float).

Standard library only. `tests/test_one_home_constants.py` fails when `Decimal("0.01")` is written anywhere else
under `backend/`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Final

#: One hundredth: the two-decimal step of quantities that are not rupees (index points, strikes, percentages) and the
#: 1% fraction cap of charge rates.
HUNDREDTH: Final = Decimal("0.01")
#: One paisa: the step of every rupee amount and premium.
PAISE: Final = HUNDREDTH
