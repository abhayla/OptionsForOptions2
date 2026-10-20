"""ADR-140: the Execute reply's ``risk`` block and the ``accept_risk`` field, without a database (pure functions and
the request model). The route's acceptance flow is in ``test_execute_route.py`` (CI database)."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from ofo_app.routes.execute import ExecuteIn, ReviewOut, risk_out
from pydantic import ValidationError


def review(loss, unlimited=False):
    return ReviewOut.model_validate({"max_loss": None if loss is None else D(loss), "max_loss_unlimited": unlimited,
                                     "max_profit": None, "max_profit_unlimited": False})


def dump(out):
    return None if out is None else out.model_dump(mode="json")


def test_normal_carries_a_one_decimal_percent_string():
    assert dump(risk_out(review("5900.00"), D("240000.00"))) == {
        "tier": "NORMAL", "percent_of_funds": "2.5", "reason": None, "needs_acceptance": False}


def test_elevated_needs_no_acceptance():
    out = dump(risk_out(review("70000.00"), D("240000.00")))
    assert (out["tier"], out["percent_of_funds"], out["needs_acceptance"]) == ("ELEVATED", "29.2", False)


@pytest.mark.parametrize(("rev", "funds", "reason"), [
    (review(None, unlimited=True), D("240000.00"), "UNLIMITED"),
    (review("240000.01"), D("240000.00"), "ABOVE_FUNDS"),
    (review("1.00"), D("0.00"), "ABOVE_FUNDS"),
])
def test_exceptional_needs_acceptance(rev, funds, reason):
    out = dump(risk_out(rev, funds))
    assert (out["tier"], out["reason"], out["needs_acceptance"]) == ("EXCEPTIONAL", reason, True)


def test_funds_unknown_has_no_percent_and_at_least_elevated():
    out = dump(risk_out(review("5900.00"), None))
    assert (out["tier"], out["percent_of_funds"], out["needs_acceptance"]) == ("ELEVATED", None, False)


def test_unknown_loss_has_no_risk_block():
    assert risk_out(review(None), D("240000.00")) is None


def test_accept_risk_defaults_false_and_must_be_a_real_boolean():
    assert ExecuteIn.model_validate({"action": "ENTRY"}).accept_risk is False
    assert ExecuteIn.model_validate({"action": "ENTRY", "accept_risk": True}).accept_risk is True
    with pytest.raises(ValidationError):
        ExecuteIn.model_validate({"action": "ENTRY", "accept_risk": "true"})


def test_basket_withheld_only_for_an_unaccepted_exceptional_plan():
    from ofo_app.routes.execute import basket_withheld  # noqa: PLC0415

    exceptional = risk_out(review(None, unlimited=True), D("240000.00"))
    elevated = risk_out(review("70000.00"), D("240000.00"))
    assert basket_withheld(exceptional, False) is True
    assert basket_withheld(exceptional, True) is False
    assert basket_withheld(elevated, False) is False   # a flag is never needed below EXCEPTIONAL
    assert basket_withheld(elevated, True) is False
    assert basket_withheld(None, False) is False       # unknown loss (an exit): no risk gate
