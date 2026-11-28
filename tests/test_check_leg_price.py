"""ADR-330 (12): the leg-price check answers Met / NotMet / NotComputable only; stops.crossed delegates to it.

Real case: a short leg stop at Rs 150.00 above; the leg trades 150.00 -> Met, 149.95 -> NotMet.
"""
from __future__ import annotations

import datetime
import inspect
from decimal import Decimal

from ofo.checks import leg_price as mod
from ofo.checks.leg_price import leg_price
from ofo.checks.outcome import Met, NotComputable, NotMet
from ofo.tracking import paper, stops

D = Decimal


def test_above_boundaries():
    assert isinstance(leg_price(D("150"), "above", D("150.00")), Met)
    assert isinstance(leg_price(D("150"), "above", D("150.05")), Met)
    assert isinstance(leg_price(D("150"), "above", D("149.95")), NotMet)


def test_below_boundaries():
    assert isinstance(leg_price(D("150"), "below", D("150")), Met)
    assert isinstance(leg_price(D("150"), "below", D("149.95")), Met)
    assert isinstance(leg_price(D("150"), "below", D("150.05")), NotMet)


def test_absent_price_is_not_computable_never_not_met():
    out = leg_price(D("150"), "below", None)
    assert isinstance(out, NotComputable) and not isinstance(out, NotMet) and out.reason


def test_absent_level_and_unreadable_and_unknown_direction():
    assert isinstance(leg_price(None, "above", D("1")), NotComputable)
    assert isinstance(leg_price(D("1"), "above", D("NaN")), NotComputable)
    assert isinstance(leg_price(D("1"), "up", D("1")), NotComputable)


def test_no_conn_in_signature_and_no_float():
    assert not {"conn", "db", "session"} & set(inspect.signature(leg_price).parameters)
    assert "float" not in inspect.getsource(mod)


def _price(state: str, value: Decimal | None) -> paper.Price:
    return paper.Price("X", state, value, datetime.datetime(2026, 11, 26, 10, 0, tzinfo=datetime.UTC))  # type: ignore[arg-type]


def _stop(direction: str) -> stops.Trigger:
    return stops.Trigger(1, 1, "leg_stop", direction, D("150"), contract_id=7)  # type: ignore[arg-type]


def test_crossed_equality_fires_both_directions_and_stale_never_fires():
    assert stops.crossed(_stop("above"), _price(paper.LIVE, D("150")))
    assert stops.crossed(_stop("below"), _price(paper.LIVE, D("150")))
    assert not stops.crossed(_stop("above"), _price(paper.LIVE, D("149.95")))
    # fail closed: a stale price carrying a crossing number never fires (NotComputable)
    assert not stops.crossed(_stop("above"), _price("stale", D("999")))
    assert not stops.crossed(_stop("above"), _price("missing", None))


def test_crossed_index_exit_uses_the_same_rule():
    t = stops.Trigger(2, 1, "conditional_exit", "below", D("24500"), underlying="NIFTY")
    assert stops.crossed(t, _price(paper.LIVE, D("24500")))
    assert not stops.crossed(t, _price(paper.LIVE, D("24500.05")))
