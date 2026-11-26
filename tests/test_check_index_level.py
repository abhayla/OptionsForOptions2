"""ADR-330 (12): the index-level check answers Met / NotMet / NotComputable only. Pure, no database.

Real case: NIFTY exit level 24500 above; price 24500.00 -> Met (a level, not an edge); 24499.95 -> NotMet.
"""
from __future__ import annotations

import inspect
from decimal import Decimal

from ofo.checks import index_level as mod
from ofo.checks.index_level import index_level
from ofo.checks.outcome import Met, NotComputable, NotMet
from ofo.checks.pnl_amount import Met as AmountMet

D = Decimal


def test_above_met_at_equality_and_beyond_not_met_short():
    assert isinstance(index_level(D("24500"), "above", D("24500.00")), Met)
    assert isinstance(index_level(D("24500"), "above", D("24500.05")), Met)
    assert isinstance(index_level(D("24500"), "above", D("24499.95")), NotMet)


def test_below_met_at_equality_and_beyond_not_met_short():
    assert isinstance(index_level(D("24500"), "below", D("24500")), Met)
    assert isinstance(index_level(D("24500"), "below", D("24499.95")), Met)
    assert isinstance(index_level(D("24500"), "below", D("24500.05")), NotMet)


def test_absent_price_is_not_computable_never_not_met():
    out = index_level(D("24500"), "above", None)
    assert isinstance(out, NotComputable) and not isinstance(out, NotMet) and out.reason


def test_absent_level_is_not_computable():
    assert isinstance(index_level(None, "above", D("1")), NotComputable)


def test_unreadable_values_are_not_computable():
    assert isinstance(index_level(D("24500"), "above", D("NaN")), NotComputable)
    assert isinstance(index_level(D("Infinity"), "below", D("1")), NotComputable)


def test_unknown_direction_is_not_computable():
    assert isinstance(index_level(D("1"), "sideways", D("1")), NotComputable)


def test_one_answer_type_shared_with_pnl_amount():
    assert AmountMet is Met


def test_no_conn_clock_or_float_in_the_signature():
    params = inspect.signature(index_level).parameters
    assert not {"conn", "db", "session"} & set(params)
    assert "float" not in inspect.getsource(mod)
