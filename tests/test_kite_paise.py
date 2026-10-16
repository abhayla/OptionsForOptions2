"""ADR-099/ADR-101: `kite_paise` rounds one Kite money figure HALF-UP to the paisa; only exact Decimal/int go in.

Expected values are worked by hand (a paisa is 0.01; half-up sends a tie away from zero).
"""
from decimal import Decimal

import pytest
from ofo.money import kite_paise


@pytest.mark.parametrize(("raw", "expected"), [
    (Decimal("68498.85000000001"), "68498.85"),  # Kite's float tail above: dropped
    (Decimal("68498.84999999999"), "68498.85"),  # ... and below: rounds up to the same paisa
    (Decimal("0.005"), "0.01"),  # a tie goes up (half-up)
    (Decimal("0.0049999"), "0.00"),
    (Decimal("-214.5"), "-214.50"),  # a closing basket stays negative here; the gate floors it to 0 later
    (68499, "68499.00"),  # Kite prints a whole total without a point
    (Decimal("2073.5"), "2073.50"),
])
def test_kite_paise_rounds_half_up_to_the_paisa(raw: object, expected: str) -> None:
    result = kite_paise(raw)  # type: ignore[arg-type]
    assert type(result) is Decimal and str(result) == expected


@pytest.mark.parametrize("bad", [68498.85, "68498.85", True, None, [1]])
def test_kite_paise_refuses_anything_but_decimal_or_int(bad: object) -> None:
    with pytest.raises(TypeError):
        kite_paise(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_kite_paise_refuses_a_non_finite_figure(bad: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        kite_paise(bad)


def test_kite_paise_never_returns_negative_zero() -> None:
    """Tier A round 3 MINOR: -1e-13 rounds to the paisa as -0.00; the API must never show "-0.00"."""
    result = kite_paise(Decimal("-0.0000000000001"))
    assert str(result) == "0.00"


def test_kite_paise_too_large_is_a_value_error_and_the_gate_fails_closed() -> None:
    """Tier A round 3 MINOR: 1e30 cannot be held at the paisa; it must not escape as decimal.InvalidOperation."""
    from ofo.execution.margin_gate import MarginReplyError, _final_total  # noqa: PLC0415

    with pytest.raises(ValueError, match="too large"):
        kite_paise(Decimal("1E+30"))
    with pytest.raises(MarginReplyError):
        _final_total({"final": {"total": Decimal("1E+30")}})
