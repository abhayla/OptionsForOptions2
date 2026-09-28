"""Display without false precision; estimates labelled with assumptions (REQ-032 AC-5; ADR-008 Q15)."""
from decimal import Decimal as D

import pytest

from ofo.engine.display import (
    describe_estimate,
    estimate_line,
    format_approx_percent,
    format_approx_rupees,
    format_points,
    format_rupees,
)
from ofo.engine.estimate import estimate_now


@pytest.mark.parametrize(
    "amount, text",
    [
        (D("1719000"), "₹17,19,000.00"),
        (D("-322.50"), "−₹322.50"),
        (D("6825"), "₹6,825.00"),
        (D("999.999"), "₹1,000.00"),
        (D("123456789.005"), "₹12,34,56,789.00"),  # half-even to the paisa
        (D("0"), "₹0.00"),
    ],
)
def test_rupees_indian_grouping_to_the_paisa(amount, text):
    """AC-5: exact money shows to the paisa with Indian digit grouping (₹17,19,000.00)."""
    assert format_rupees(amount) == text


def test_estimates_have_no_false_precision():
    """AC-5: '~73%' never '73.48291%'; estimated rupees to the whole rupee; levels in points without ₹."""
    assert format_approx_percent(D("73.48291")) == "~73%"
    assert format_approx_percent(D("72.5")) == "~72%"  # half-even
    assert format_approx_percent(D("-4.6")) == "~−5%"
    assert format_approx_rupees(D("-8175.50")) == "~−₹8,176"
    assert format_approx_rupees(D("1234.49")) == "~₹1,234"
    assert format_points(D("23047.35")) == "23,047.35"
    assert format_points(D("22909")) == "22,909"


def test_estimate_line_is_labelled_with_assumptions():
    """AC-5: an estimate reads 'Estimated probability of profit: ~73%' and lists its assumptions; none is refused."""
    line = estimate_line("probability of profit", format_approx_percent(D("73.48291")), ["IV 14.2%", "10 days left"])
    assert line == "Estimated probability of profit: ~73% (estimate; assumes IV 14.2%; 10 days left)"
    with pytest.raises(ValueError, match="assumptions"):
        estimate_line("probability of profit", "~73%", [])
    with pytest.raises(ValueError, match="assumptions"):
        estimate_line("probability of profit", "~73%", ["IV 14.2%", " "])


def test_estimated_now_line_exact_text(condor_inputs):
    """AC-5: the Estimated Now result renders as a labelled, approximate line with its model, IVs, rate and time."""
    text = describe_estimate(estimate_now(condor_inputs, D("23500")), "NIFTY")
    assert text == (
        "Estimated P&L now at NIFTY 23,500: ~−₹1,009 (estimate; assumes Black-Scholes (European, no dividends) "
        "model; IV 11.7%, 10.9%, 9.3%, 10.2%; rate 6.5%; valued 2026-10-17 15:30 IST)"
    )
    for banned in ("guarantee", "you should", "best trade"):
        assert banned not in text.lower()
