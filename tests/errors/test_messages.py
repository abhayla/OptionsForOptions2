"""AC-2: every user-facing error states what happened, the impact, what is blocked, next action.

Round 3 (W-024): covers the typed slot system (`ofo.errors.slots`) that `render()` validates every
value against, plus round-2's verifier-found red cases reproduced as real `render()` calls (proving
the fix holds at the render boundary, not just inside the wording scanner tested directly in
`tests/test_wording.py`).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from ofo.engine.legs import Instrument as EngineInstrument
from ofo.errors import ErrorClass, render
from ofo.errors.slots import Code, ExternalText, Instrument, Int, Money, PnLMoney, Time, Underlying


# --- Slot types: validate + format ---------------------------------------------------------------

def test_money_requires_decimal_not_str_int_float_bool() -> None:
    Money.validate(Decimal("100"))  # ok
    for bad in ("100", 100, 100.0, True):
        with pytest.raises(TypeError):
            Money.validate(bad)


def test_money_format_uses_rupee_sign_and_thousands_separator() -> None:
    assert Money.format(Decimal("41200")) == "₹41,200"


def test_money_rejects_nan_and_infinity() -> None:
    """AC-2 (W-024 round-4 fix): NaN/Infinity must be refused, not rendered as "₹NaN"/crash."""
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ValueError):
            Money.validate(bad)


def test_money_rejects_negative_amounts() -> None:
    """AC-2 (W-024 round-4 fix): every current Money slot is an amount (never a P&L), so negative is
    refused; a P&L slot uses `PnLMoney` instead."""
    with pytest.raises(ValueError):
        Money.validate(Decimal("-5"))


def test_pnlmoney_allows_negative_but_still_rejects_nan_and_infinity() -> None:
    PnLMoney.validate(Decimal("-1500"))  # ok: a real loss
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ValueError):
            PnLMoney.validate(bad)


def test_pnlmoney_format_shows_a_leading_sign_for_a_loss() -> None:
    assert PnLMoney.format(Decimal("-1500")) == "-₹1,500"
    assert PnLMoney.format(Decimal("1500")) == "₹1,500"


def test_int_requires_int_not_bool_or_float() -> None:
    Int.validate(4)  # ok
    with pytest.raises(TypeError):
        Int.validate(4.0)
    with pytest.raises(TypeError):
        Int.validate(True)


def test_time_requires_timezone_aware_datetime() -> None:
    aware = datetime.datetime(2026, 9, 29, 10, 0, tzinfo=datetime.timezone.utc)
    Time.validate(aware)  # ok
    naive = datetime.datetime(2026, 9, 29, 10, 0)
    with pytest.raises(ValueError):
        Time.validate(naive)
    with pytest.raises(TypeError):
        Time.validate("2026-09-29T10:00:00Z")


def test_instrument_requires_engine_instrument_enum() -> None:
    Instrument.validate(EngineInstrument.CE)  # ok
    with pytest.raises(TypeError):
        Instrument.validate("CE")


def test_code_is_a_closed_enum_known_check_code_or_strict_reference_id() -> None:
    """AC-2 (W-024 round-4 fix): Code is closed to known check codes / a strict `ERR-`+8-hex
    reference id — no free words, however they are joined."""
    Code.validate("MARGIN_INSUFFICIENT")  # ok: a known CheckCode value
    Code.validate("ERR-DEADBEEF")  # ok: strict reference id format
    for bad in ("this is a sentence with spaces", "ORDER-REF-001", "risk-free", "you_should_buy"):
        with pytest.raises(ValueError):
            Code.validate(bad)
    with pytest.raises(TypeError):
        Code.validate("")


def test_underlying_is_closed_to_the_catalogues_supported_symbols() -> None:
    """AC-2 (W-024 round-4 fix): the market-symbol slot is closed to the catalogue's underlyings
    (NIFTY/SENSEX) — never a free word."""
    Underlying.validate("NIFTY")  # ok
    Underlying.validate("SENSEX")  # ok
    with pytest.raises(ValueError):
        Underlying.validate("GUARANTEED-PROFIT")
    with pytest.raises(ValueError):
        Underlying.validate("BANKNIFTY")  # not in SUPPORTED_UNDERLYINGS
    with pytest.raises(TypeError):
        Underlying.validate("")


def test_external_text_requires_nonblank_source_and_text() -> None:
    ExternalText.validate(ExternalText(source="Zerodha", text="rejected"))  # ok
    with pytest.raises(ValueError):
        ExternalText.validate(ExternalText(source="", text="rejected"))
    with pytest.raises(TypeError):
        ExternalText.validate("Zerodha: rejected")


# --- Round-2 verifier red cases, reproduced against real render() calls -------------------------

def test_round2_red_case_must_is_rejected_at_the_template_level() -> None:
    """'you must buy more lots' would only ever reach a user via a catalogue template; none of the
    12 real templates contain it (proven by test_every_template_four_parts_pass_the_core_checks in
    test_error_catalogue.py), and render() offers no slot through which a caller could inject it."""
    error = render("user_input_lot_size", entered=0)
    assert "must" not in error.what_happened.lower()


def test_round2_red_case_best_strike_to_pick_pattern_is_covered_by_the_checker() -> None:
    from ofo.wording import find_advice_wording

    assert find_advice_wording("best strike to pick") == [
        "best <trade/strategy/option/choice/adjustment/strike/entry/time/pick/level>"
    ]
    assert find_advice_wording("best entry point") == [
        "best <trade/strategy/option/choice/adjustment/strike/entry/time/pick/level>"
    ]


# --- Legitimate rendered output is not flagged ----------------------------------------------------

def test_legitimate_rendered_error_has_no_advice_wording() -> None:
    from ofo.wording import find_advice_wording

    error = render(
        "margin_insufficient", available=Decimal("41200"), required=Decimal("48000")
    )
    for part in (error.what_happened, error.impact, error.what_is_blocked, error.next_action):
        assert find_advice_wording(part) == []
    assert error.what_happened == "Margin available ₹41,200 is below the ₹48,000 this strategy needs."
