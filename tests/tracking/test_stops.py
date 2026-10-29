"""GC-TP step 7a (ADR-207 (5); ADR-015; REQ-109 AC-5, AC-8): when a paper stop trigger has crossed its level.

Spec basis: ADR-207 (5) (Conditional Exit: the index crosses above / below a level; per-leg stop-loss); ADR-015
("stale is never live"): only a LIVE price can fire a trigger.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.tracking import paper
from ofo.tracking.stops import Trigger, crossed

AT = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
BELOW = Trigger(1, 7, "conditional_exit", "below", Decimal("22850.00"), underlying="NIFTY")
ABOVE = Trigger(2, 7, "leg_stop", "above", Decimal("120.00"), contract_id=11)


def live(value: str) -> paper.Price:
    return paper.Price("NSE_INDEX:1001", "live", Decimal(value), AT)


@pytest.mark.parametrize(("trigger", "price", "fires"), [
    (BELOW, "22850.05", False), (BELOW, "22850.00", True), (BELOW, "22849.95", True),
    (ABOVE, "119.95", False), (ABOVE, "120.00", True), (ABOVE, "131.40", True),
])
def test_a_live_price_at_or_beyond_the_level_fires(trigger, price, fires):
    assert crossed(trigger, live(price)) is fires


@pytest.mark.parametrize("state", ["stale", "missing", "contract_retired", "contract_delisted", "token_reassigned",
                                   "contract_missing", "exited"])
def test_a_price_that_is_not_live_never_fires_even_when_it_carries_a_crossing_number(state):
    assert crossed(BELOW, paper.Price("NSE_INDEX:1001", state, Decimal("1.00"), AT)) is False
    assert crossed(BELOW, paper.Price("NSE_INDEX:1001", state, None, None)) is False


@pytest.mark.parametrize("kwargs", [
    {"kind": "leg_stop", "underlying": "NIFTY"}, {"kind": "conditional_exit", "contract_id": 3},
    {"kind": "conditional_exit", "underlying": "NIFTY", "level": Decimal("0")},
    {"kind": "conditional_exit", "underlying": "NIFTY", "level": 22850.0},
    {"kind": "conditional_exit", "underlying": "NIFTY", "direction": "crosses"},
])
def test_a_malformed_trigger_is_refused(kwargs):
    args = {"id": 1, "strategy_id": 7, "direction": "below", "level": Decimal("1.00")} | kwargs
    with pytest.raises(ValueError):
        Trigger(**args)
