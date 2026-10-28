"""REQ-152 / REQ-153 (GC-UI step 3b): the summary money figures arrive from the server as finished whole-rupee text.

Core: every AC-1 summary figure has a ``*_display`` string made on the server, rounded half-up from the exact Decimal,
with the exact value still in its own field; breakevens carry their signed percent from spot.
Proof: test_strategy_54_summary_in_the_reply - the numbers of the recorded live reply of strategy 54 (max profit
7152.21, max loss 5847.79, net premium 5707.00) through the real ``outcome_to_dict`` path. Number FORM only is taken
from Sensibull (S-011 / S-128 / S-241); no Sensibull number appears here. The margin figures are synthetic
(the available-funds figure is the owner's: a placeholder here).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine.display import breakeven_percent, format_signed_percent, format_whole_rupees
from ofo.errors.explanations import render_explanation
from ofo.outcome import money
from ofo.outcome.serialize import _breakeven as format_breakeven
from ofo.outcome.serialize import outcome_to_dict
from ofo.outcome.service import (
    MARGIN,
    Outcome,
    OutcomeState,
    Summary,
    margin_checked,
    margin_no_basket,
    margin_unreadable,
)

D = Decimal
M = chr(0x2212)  # U+2212, as the table money cells write a loss
TEXT = render_explanation("money_charges_label")
CHECKED_AT = datetime.datetime(2026, 10, 28, 4, 0, tzinfo=datetime.UTC)


def _summary(**kw) -> Summary:
    base = {"what_can_i_lose": TEXT, "what_can_i_make": TEXT, "where_do_i_start_losing": TEXT,
            "max_profit": D("7152.21"), "max_loss": D("5847.79"), "max_profit_unlimited": False,
            "max_loss_unlimited": False, "breakevens": (D("22687.8"),), "lower_be": D("22687.8"), "upper_be": None,
            "risk_boundaries": ()}
    base.update(kw)
    return Summary(**base)


SPOT = D("22706.8")


def _out(summary, margin=MARGIN, spot=SPOT) -> Outcome:
    return Outcome(OutcomeState.COMPUTED, "NIFTY", None, None, (), margin, spot_level=spot, summary=summary)


def _s(summary, **kw):
    return outcome_to_dict(_out(summary, **kw))["summary"]


def test_strategy_54_summary_in_the_reply():
    net = money.NetPremium(D("5707.00"), "pay", D("87.80"), TEXT, None)
    s = _s(_summary(time_value=D("-104.00"), intrinsic_value=D("6942.00"), net_premium=net))
    assert s["max_profit_display"] == "+7,152"
    assert s["max_loss_display"] == f"{M}5,848"
    assert s["net_premium"]["amount_display"] == "5,707"
    assert s["time_value_display"] == f"{M}104"
    assert s["intrinsic_value_display"] == "+6,942"
    # the exact values stay where they were
    assert (s["max_profit"], s["max_loss"], s["net_premium"]["amount"]) == ("7152.21", "5847.79", "5707.00")
    assert s["net_premium"]["per_unit"] == "87.80"  # AC-2: per-unit keeps paise, no display added to it


def test_half_up_on_the_exact_decimal():  # REQ-152 AC-3
    assert _s(_summary(max_profit=D("6025.50")))["max_profit_display"] == "+6,026"
    assert _s(_summary(max_loss=D("6975.50")))["max_loss_display"] == f"{M}6,976"
    assert _s(_summary(max_profit=D("6025.50")))["max_profit"] == "6025.50"
    assert format_whole_rupees(D("-104.50"), signed=True) == f"{M}105"  # half-up on the magnitude, a loss too
    assert format_whole_rupees(D("0.49"), signed=True) == "0"


def test_indian_grouping_and_zero_and_missing():  # AC-1, AC-4
    assert format_whole_rupees(D("189000"), signed=False) == "1,89,000"
    assert format_whole_rupees(D("12345678.4"), signed=True) == "+1,23,45,678"
    s = _s(_summary(max_profit=D("0.00"), max_loss=D("0.00")))
    assert (s["max_profit_display"], s["max_loss_display"]) == ("0", "0")  # a true zero: "0", no sign
    s = _s(_summary(max_profit=None, max_profit_unlimited=True, max_loss=None, max_loss_unlimited=True))
    assert s["max_profit_display"] is None and s["max_loss_display"] is None  # unlimited: no figure, flags stay
    assert s["max_profit_unlimited"] is True
    s = _s(_summary())
    assert s["time_value_display"] is None and s["intrinsic_value_display"] is None  # absent (None) stays absent
    absent = money.NetPremium(None, None, None, None, TEXT)
    s = _s(_summary(net_premium=absent))
    assert s["net_premium"]["amount_display"] is None and s["net_premium"]["reason"] == TEXT
    zero = money.NetPremium(D("0.00"), None, D("0.00"), TEXT, None)
    assert _s(_summary(net_premium=zero))["net_premium"]["amount_display"] == "0"
    assert _s(_summary(time_value=D("0.00")))["time_value_display"] == "0"


def test_breakeven_percent_from_spot():  # REQ-153 AC-1
    assert format_breakeven(D("22687.8"), D("22706.8")) == f"22,688 ({M}0.1%)"
    assert format_breakeven(D("22900.2"), D("22706.8")) == "22,900 (+0.9%)"
    assert format_breakeven(D("22706.8"), D("22706.8")) == "22,707 (0.0%)"  # no sign on zero
    assert format_breakeven(D("22700"), D("22706.8")) == f"22,700 ({M}0.0%)"  # F-4: -0.03% rounds to 0.0, sign stays
    assert format_breakeven(D("22687.8"), D("22698.85")) == f"22,688 ({M}0.0%)"  # -0.0487%, the recorded 17:13 case
    assert format_breakeven(D("22707.5"), D("22706.8")) == "22,708 (+0.0%)"  # +0.003% likewise
    assert format_breakeven(D("23000"), None) == "23,000"  # no spot: the level alone
    assert format_breakeven(D("23000"), D("0")) == "23,000"
    s = _s(_summary(breakevens=(D("22400"), D("23000"))))
    assert s["breakevens_display"] == [f"22,400 ({M}1.4%)", "23,000 (+1.3%)"]
    assert s["breakevens"] == ["22400", "23000"]  # same order, exact values unchanged
    assert _s(_summary(breakevens=(D("22400"),)), spot=None)["breakevens_display"] == ["22,400"]
    assert _s(_summary(breakevens=()))["breakevens_display"] == []


def test_margin_display_all_states():  # AC-1, ADR-099 states
    checked = margin_checked(D("1234567.50"), D("100000.00"), CHECKED_AT, D("1234567.50"), D("0"))
    m = outcome_to_dict(_out(_summary(), margin=checked))["margin"]
    assert m["needed_display"] == "12,34,568"
    assert m["available_display"] == "1,00,000"
    assert m["broker_needed_display"] == "12,34,568"
    assert (m["needed"], m["available"]) == ("1234567.50", "100000.00")  # exact values stay
    for margin in (MARGIN, margin_unreadable()):
        m = outcome_to_dict(_out(_summary(), margin=margin))["margin"]
        assert (m["needed_display"], m["available_display"], m["broker_needed_display"]) == (None, None, None)
        assert m["reason"]  # the existing reason is unchanged
    m = outcome_to_dict(_out(None))["margin"]
    assert m["state"] == "NOT_AVAILABLE_YET"


def test_closing_basket_zero_needed():
    closing = margin_checked(D("0"), D("100000.00"), CHECKED_AT, D("0"), D("0"))
    m = outcome_to_dict(_out(_summary(), margin=closing))["margin"]
    assert (m["needed_display"], m["broker_needed_display"]) == ("0", "0")


def test_no_basket_state_has_no_display():
    m = outcome_to_dict(_out(_summary(), margin=margin_no_basket()))["margin"]
    assert m["state"] == "NO_BASKET" and m["needed_display"] is None and m["reason"]


def test_funds_needed_is_not_built():  # REQ-142: not derivable (item 3); no field may appear by accident
    m = outcome_to_dict(_out(_summary()))["margin"]
    assert "funds_needed" not in m and "funds_needed_display" not in m


@pytest.mark.parametrize("bad", [1.5, "5", None])
def test_formatter_refuses_a_non_decimal(bad):
    with pytest.raises(ValueError):
        format_whole_rupees(bad, signed=True)


def test_percent_helpers():
    assert breakeven_percent(D("22687.8"), D("22706.8")) == D("-0.1")
    assert breakeven_percent(D("1"), None) is None
    assert format_signed_percent(D("0.04")) == "+0.0" and format_signed_percent(D("-0.04")) == f"{M}0.0"  # F-4
    assert format_signed_percent(D("0")) == "0.0" and format_signed_percent(D("-0.0")) == "0.0"  # a true zero
