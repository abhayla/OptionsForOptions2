"""ADR-330 (5): a plan's rupee level is a pure whole-trade, before-charges check. Nothing exits by itself.

Pure tests, no database. Real case: loss level Rs 400 on a trade whose P&L is -400.00 -> met; -399.95 -> not met.
Answer states: stated (Met/NotMet), absent pnl (NotComputable, never NotMet), empty level (no check), refused level.

Spec basis: ADR-330 (5) and its Q3 answer.
"""
from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from ofo.checks import pnl_amount as mod
from ofo.checks.pnl_amount import LOSS, PROFIT, Met, NotComputable, NotMet, level_of, pnl_amount

D = Decimal


def test_loss_level_met_exactly_at_level():
    assert isinstance(pnl_amount(D("400"), D("-400.00"), LOSS), Met)


def test_loss_level_not_met_one_paisa_short():
    assert isinstance(pnl_amount(D("400"), D("-399.95"), LOSS), NotMet)


def test_loss_level_met_beyond():
    assert isinstance(pnl_amount(D("400"), D("-400.05"), LOSS), Met)


def test_profit_level_boundaries():
    assert isinstance(pnl_amount(D("1000"), D("1000.00"), PROFIT), Met)
    assert isinstance(pnl_amount(D("1000"), D("999.95"), PROFIT), NotMet)
    assert isinstance(pnl_amount(D("1000"), D("-1000"), PROFIT), NotMet)


def test_pnl_none_is_not_computable_never_not_met():
    out = pnl_amount(D("400"), None, LOSS)
    assert isinstance(out, NotComputable) and not isinstance(out, NotMet) and out.reason


def test_unknown_side_is_not_computable():
    assert isinstance(pnl_amount(D("400"), D("-500"), "sideways"), NotComputable)


def test_empty_level_is_no_check():
    assert level_of("") is None and level_of(None) is None and level_of("  ") is None


@pytest.mark.parametrize("bad", ["0", "-5", "-0.01", "NaN", "Infinity", "-Infinity", "abc", "1,000"])
def test_refused_levels(bad):
    with pytest.raises(ValueError):
        level_of(bad)


def test_float_and_nan_refused_in_the_check():
    with pytest.raises(ValueError):
        pnl_amount(400.0, D("-500"), LOSS)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        pnl_amount(D("NaN"), D("-500"), LOSS)
    with pytest.raises(ValueError):
        pnl_amount(D("0"), D("-500"), LOSS)
    assert isinstance(pnl_amount(D("400"), D("NaN"), LOSS), NotComputable)
    assert isinstance(pnl_amount(D("400"), -399.0, LOSS), NotComputable)  # type: ignore[arg-type]


def test_level_of_parses_text_decimal():
    assert level_of("400") == D("400") and level_of("1000.50") == D("1000.50")


def test_module_is_pure_and_float_free():
    src = inspect.getsource(mod)
    assert "float(" not in src
    for banned in ("import datetime", "import time", "ofo_app", "sqlalchemy"):
        assert banned not in src


@pytest.mark.parametrize("bad", ["1e3", "400.005", "\uff14\uff10\uff10", "+400", "4_00", "1,000", "0x10", "400."])
def test_f8_one_parser_level_of_takes_only_the_route_pattern(bad):
    with pytest.raises(ValueError):
        level_of(bad)
