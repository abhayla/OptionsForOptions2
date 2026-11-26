"""ADR-330 (12): the P&L-percent check answers Met / NotMet / NotComputable only. Pure, no database.

Real case: loss 4,500 of a max loss 10,000 against a 45 % stop: 4500 >= 45 * 10000 / 100? The caller scales num by 100
(450000 / 10000 = 45.00 %), so num=450000, den=10000, limit=45 -> Met exactly at the line; 449999 -> NotMet.
"""
from __future__ import annotations

import inspect
from decimal import Decimal

from ofo.checks import pnl_percent as mod
from ofo.checks.outcome import Met, NotComputable, NotMet
from ofo.checks.pnl_percent import pnl_percent

D = Decimal


def test_ge_boundaries():
    assert isinstance(pnl_percent(D("450000"), D("10000"), D("45"), "ge"), Met)
    assert isinstance(pnl_percent(D("450001"), D("10000"), D("45"), "ge"), Met)
    assert isinstance(pnl_percent(D("449999"), D("10000"), D("45"), "ge"), NotMet)


def test_le_boundaries():
    assert isinstance(pnl_percent(D("450000"), D("10000"), D("45"), "le"), Met)
    assert isinstance(pnl_percent(D("449999"), D("10000"), D("45"), "le"), Met)
    assert isinstance(pnl_percent(D("450001"), D("10000"), D("45"), "le"), NotMet)


def test_one_third_has_no_rounding_error():
    # 100/3 = 33.333...; against limit 33.33 -> met; against 33.34 -> not met, no division is rounded
    assert isinstance(pnl_percent(D("100"), D("3"), D("33.33"), "ge"), Met)
    assert isinstance(pnl_percent(D("100"), D("3"), D("33.34"), "ge"), NotMet)


def test_absent_figures_are_not_computable_never_not_met():
    for args in ((None, D("1"), D("1")), (D("1"), None, D("1")), (D("1"), D("1"), None)):
        out = pnl_percent(*args, "ge")
        assert isinstance(out, NotComputable) and not isinstance(out, NotMet) and out.reason


def test_unreadable_and_zero_denominator_and_unknown_cmp_are_not_computable():
    assert isinstance(pnl_percent(D("NaN"), D("1"), D("1"), "ge"), NotComputable)
    assert isinstance(pnl_percent(D("1"), D("0"), D("1"), "ge"), NotComputable)
    assert isinstance(pnl_percent(D("1"), D("-5"), D("1"), "le"), NotComputable)
    assert isinstance(pnl_percent(D("1"), D("1"), D("1"), "gt"), NotComputable)


def test_no_conn_in_signature_and_no_float():
    assert not {"conn", "db", "session"} & set(inspect.signature(pnl_percent).parameters)
    assert "float" not in inspect.getsource(mod)
