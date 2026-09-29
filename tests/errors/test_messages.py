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


# --- Round 5 (issue #30, owner decision Q226): the round-3 verifier's exact attacks -------------
# Every expected value below is from the brief/Q226 text or hand-worked, never pasted from a run.

from ofo.errors import CATALOGUE, UserFacingError  # noqa: E402
from ofo.errors import model as model_mod  # noqa: E402


def test_attack_reference_risk_free_is_refused() -> None:
    """AC-2: round-3 attack 1a, `reference="risk-free"` in the Code slot never reaches a user."""
    with pytest.raises(ValueError):
        render("internal_system_save_failed", reference="risk-free")


def test_attack_symbol_guaranteed_profit_is_refused() -> None:
    """AC-2: round-3 attack 1b, `symbol="GUARANTEED-PROFIT"` in the Underlying slot is refused."""
    with pytest.raises(ValueError):
        render("market_data_stale", symbol="GUARANTEED-PROFIT", minutes=5)


def test_attack_you_should_buy_in_code_slot_is_refused_and_flagged() -> None:
    """AC-2: round-3 attack 1c, `you_should_buy` in a Code slot is refused, and the wording check
    itself splits `_` so the finished-text check would flag it too (second line)."""
    with pytest.raises(ValueError):
        render("internal_system_save_failed", reference="you_should_buy")
    from ofo.wording import find_advice_wording

    assert find_advice_wording("you_should_buy") != []
    assert find_advice_wording("RISK_FREE") != []


class _EvilStr(str):
    """A str whose formatting says something other than its value (a known check code)."""

    def __format__(self, spec: str) -> str:
        return "you should buy"

    def __str__(self) -> str:
        return "you should buy"


def test_attack_str_subclass_in_a_closed_slot_is_refused() -> None:
    """AC-2: a str subclass equal to a known code but formatting as advice is refused (exact type)."""
    with pytest.raises(TypeError):
        render("internal_system_save_failed", reference=_EvilStr("INTERNAL_ERROR"))
    with pytest.raises(TypeError):
        render("market_data_stale", symbol=_EvilStr("NIFTY"), minutes=5)


def test_attack_build_is_unreachable_from_outside() -> None:
    """AC-2: round-3 attack 2a. `_build` is no longer a method of the public class, the render token
    is not a module attribute, it can be claimed only once (render already holds it), and `_build`
    refuses any other token."""
    assert not hasattr(UserFacingError, "_build")
    assert not hasattr(model_mod, "_RENDER_TOKEN")
    with pytest.raises(RuntimeError):
        model_mod._claim_render_token()
    with pytest.raises(ValueError):
        model_mod._build(
            object(),
            error_class=ErrorClass.MARGIN,
            code="MARGIN_001",
            what_happened="you should buy",
            impact="b",
            what_is_blocked="c",
            next_action="d",
            external_text=None,
        )


def test_attack_object_new_instance_is_unusable() -> None:
    """AC-2: round-3 attack 2b. `object.__new__(UserFacingError)` yields an object that cannot be
    given text (every field is read-only) and refuses every read (it was never issued by render)."""
    obj = object.__new__(UserFacingError)
    with pytest.raises(AttributeError):
        object.__setattr__(obj, "what_happened", "you should buy")
    with pytest.raises(ValueError):
        _ = obj.what_happened
    with pytest.raises(ValueError):
        obj.as_dict()


def test_attack_class_new_refuses() -> None:
    """AC-2: `UserFacingError.__new__` refuses outside render."""
    with pytest.raises(TypeError):
        UserFacingError.__new__(UserFacingError)


def test_attack_subclass_with_advice_is_refused() -> None:
    """AC-2: round-3 attack 2c. A subclass carrying "you should buy" cannot be defined."""
    with pytest.raises(TypeError):

        class Evil(UserFacingError):  # noqa: F841
            what_happened = "you should buy"


def test_attack_rendered_error_is_immutable() -> None:
    """AC-2: a rendered error's text cannot be replaced afterwards."""
    error = render("user_input_lot_size", entered=0)
    with pytest.raises(AttributeError):
        error.what_happened = "you should buy"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        object.__setattr__(error, "what_happened", "you should buy")
    assert error.what_happened == "The lot size you entered (0) is not a positive whole number."


def test_attack_catalogue_is_read_only_and_render_ignores_mutated_templates() -> None:
    """AC-2: the public catalogue cannot gain a template, and forcing new text into a catalogue
    template object does not change what render() produces (render works from its own snapshot)."""
    with pytest.raises(TypeError):
        CATALOGUE["evil"] = CATALOGUE["user_input_lot_size"]  # type: ignore[index]
    template = CATALOGUE["user_input_lot_size"]
    original = template.impact
    object.__setattr__(template, "impact", "Honestly this is a winner, add more lots.")
    try:
        error = render("user_input_lot_size", entered=0)
        assert error.impact == "The strategy cannot be priced or saved with this quantity."
    finally:
        object.__setattr__(template, "impact", original)
    with pytest.raises(TypeError):
        template.slots["entered"] = Money  # type: ignore[index]


@pytest.mark.parametrize(
    "available",
    [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-5"), Decimal("1E+30")],
    ids=["nan", "snan", "inf", "-inf", "negative", "absurd"],
)
def test_attack_money_non_finite_negative_or_absurd_is_refused_not_crash(available: Decimal) -> None:
    """AC-2: round-3 attack 3. Money NaN/Infinity/negative/absurd is refused with ValueError via
    render (not rendered as "₹NaN", not an InvalidOperation crash)."""
    with pytest.raises(ValueError):
        render("margin_insufficient", available=available, required=Decimal("48000"))


def test_money_negative_zero_renders_as_zero() -> None:
    """AC-2: Decimal("-0") is zero, and is shown as ₹0, never "₹-0" (hand-worked)."""
    error = render("margin_insufficient", available=Decimal("-0"), required=Decimal("48000"))
    assert error.what_happened == "Margin available ₹0 is below the ₹48,000 this strategy needs."


def test_decimal_subclass_is_refused_for_money() -> None:
    """AC-2: a Decimal subclass can override formatting; Money needs exactly Decimal."""

    class EvilDecimal(Decimal):
        def __format__(self, spec: str) -> str:
            return "a sure thing"

    with pytest.raises(TypeError):
        Money.validate(EvilDecimal("5"))


def test_count_slots_refuse_negative_and_absurd() -> None:
    """AC-2: a count (legs, lots, minutes) is never negative, and absurd sizes are capped."""
    with pytest.raises(ValueError):
        render("partial_execution_legs", filled=-1, total=2)
    with pytest.raises(ValueError):
        render("partial_execution_legs", filled=1, total=10**12)


def test_time_zone_name_cannot_inject_text() -> None:
    """AC-2: a tz-aware datetime whose zone is NAMED with advice words renders as IST digits only
    (hand-worked: 04:30 UTC = 10:00 IST)."""
    evil_zone = datetime.timezone(datetime.timedelta(0), "you should buy GUARANTEED")
    when = datetime.datetime(2026, 9, 29, 4, 30, tzinfo=evil_zone)
    error = render("broker_authentication_session_expired", expired_at=when)
    assert error.what_happened == "Your Zerodha session expired at 29 Sep 2026, 10:00 IST."


def test_external_text_source_is_a_closed_label() -> None:
    """AC-2 / Q226: quoted text is Zerodha's or the user's own, in a labelled field; the label is a
    closed choice, never free text ("Guaranteed desk" as a source is refused)."""
    from ofo.errors.slots import ExternalSource

    with pytest.raises(TypeError):
        render("order_rejection_leg", broker_message=ExternalText(source="Guaranteed desk", text="x"))
    error = render(
        "order_rejection_leg", broker_message=ExternalText(source=ExternalSource.ZERODHA, text="RMS: margin exceeds")
    )
    assert error.external_text == "Zerodha's message: «RMS: margin exceeds»"


def test_runtime_wording_check_on_finished_text_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: render() checks the FINISHED text at runtime (second line after typed slots). A slot
    formatter that produced advice (a future bug) is refused, not shown."""
    monkeypatch.setattr(Money, "format", staticmethod(lambda value: "₹5, a safe bet"))
    with pytest.raises(ValueError, match="banned wording"):
        render("margin_insufficient", available=Decimal("5"), required=Decimal("6"))


# --- Q226 wording rule, exactly: bare-word bans plus four named exceptions ----------------------


def test_q226_named_exceptions_are_one_constant_exactly_as_the_owner_wrote_them() -> None:
    """AC-2 / Q226: the exceptions list is one named constant holding exactly the four reviewed
    exceptions, and the bare-word list is exactly the five Q226 words."""
    from ofo.wording import Q226_BARE_WORDS, Q226_NAMED_EXCEPTIONS

    assert Q226_NAMED_EXCEPTIONS == ("best bid", "best ask", "best-case", "make sure")
    assert Q226_BARE_WORDS == ("best", "sure", "safe", "guarantee*", "recommend*")


@pytest.mark.parametrize(
    "text,word",
    [
        ("This is the best way in.", "best"),
        ("Best", "best"),
        ("best_way", "best"),
        ("It is sure to rise.", "sure"),
        ("A sure-shot setup.", "sure"),
        ("This leg is safe.", "safe"),
        ("SAFE-bet", "safe"),
        ("Guaranteed", "guarantee*"),
        ("We guarantee it.", "guarantee*"),
        ("guarantees_apply", "guarantee*"),
        ("Our recommendation", "recommend*"),
        ("Recommended trade", "recommend*"),
    ],
)
def test_q226_bare_words_are_flagged_after_splitting_on_underscore_and_hyphen(text: str, word: str) -> None:
    """AC-2 / Q226: each bare word is caught, in any case, joined by `_` or `-`."""
    from ofo.wording import find_advice_wording

    assert word in find_advice_wording(text)


@pytest.mark.parametrize(
    "text",
    ["The best bid is 101.5.", "Best ask: 102.", "The best-case outcome is ₹4,000.", "Make sure your session is live.",
     "best_bid", "BEST-ASK"],
)
def test_q226_named_exceptions_pass(text: str) -> None:
    """AC-2 / Q226: the four reviewed exceptions are not flagged, whatever the joiner or case."""
    from ofo.wording import find_advice_wording

    assert find_advice_wording(text) == []


@pytest.mark.parametrize(
    "text",
    ["The best bid is best.", "Make sure it is safe.", "best-case, best trade", "make sure, sure thing"],
)
def test_q226_an_exception_covers_only_its_own_words(text: str) -> None:
    """AC-2 / Q226: an exception never whitelists a second, bare occurrence in the same text."""
    from ofo.wording import find_advice_wording

    assert find_advice_wording(text) != []


@pytest.mark.parametrize("text", ["the second-best bid", "ensure", "unsafe", "safely", "insurer", "bestow"])
def test_q226_only_whole_words_are_bare_words(text: str) -> None:
    """AC-2 / Q226 says "bare words": a word that merely contains the letters is not the bare word
    ("unsafe", "ensure", "bestow"); but a hyphen splits, so "second-best" is caught unless it is
    one of the exceptions. Hand-worked: "the second-best bid" -> tokens second, best, bid ->
    "best bid" is an exception -> clean."""
    from ofo.wording import find_advice_wording

    assert find_advice_wording(text) == []
