"""#380-3 item 3: the exact ADR-142 lines a refused recovery action shows, from the one catalogue.

Every expected text below is copied from ADR-142 (1) and its example (₹38,000.00 / ₹52,000.00), never from running
the code; the next day uses ADR-121 (2)'s own example ("Wed 21 Oct").
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.errors.explanations import ExplanationText
from ofo.execution.recovery import (
    MarginAnswer,
    Outcome,
    RecoveryAction,
    Refusal,
    overnight_line,
    refusal_line,
)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
PLACE, CLOSE = RecoveryAction.PLACE_MISSING_LEGS, RecoveryAction.CLOSE_FILLED_LEGS
NUMBERS = RecoveryAction.USE_ZERODHA_NUMBERS


def test_adr142_open_order_line() -> None:
    out = Outcome(PLACE, refusal=Refusal.ORDER_OPEN, contracts=("NIFTY26O0623400CE",))
    assert refusal_line(out) == "An order for this contract is still open on Kite. Cancel or change it on Kite first."
    assert type(refusal_line(out)) is ExplanationText  # only the catalogue makes it


def test_adr142_margin_short_line_uses_the_engine_money_format() -> None:
    out = Outcome(PLACE, refusal=Refusal.MARGIN_SHORT)
    line = refusal_line(out, margin=MarginAnswer(D("38000.00"), D("52000.00")))
    assert line == ("Zerodha shows ₹38,000.00 available; these orders need ₹52,000.00. Add funds on Kite or close "
                    "what filled.")
    # lakh grouping (the engine formatter, ADR-142 (2)), never a western "1,50,000" mistake the other way
    assert "₹1,50,000.00" in refusal_line(out, margin=MarginAnswer(D("150000.00"), D("152000.00")))


def test_margin_short_line_without_figures_fails_closed() -> None:
    with pytest.raises(ValueError, match="margin-short"):
        refusal_line(Outcome(PLACE, refusal=Refusal.MARGIN_SHORT))
    with pytest.raises(ValueError, match="margin-short"):
        refusal_line(Outcome(PLACE, refusal=Refusal.MARGIN_SHORT), margin=MarginAnswer(None, D("1.00")))


def test_adr142_entry_order_open_line() -> None:
    assert refusal_line(Outcome(CLOSE, refusal=Refusal.ENTRY_ORDER_OPEN)) == "Cancel your open entry order on Kite first."


def test_adr142_stale_read_line() -> None:
    assert refusal_line(Outcome(CLOSE, refusal=Refusal.READ_STALE)) == (
        "Zerodha's answer is out of date. Check with Zerodha again.")


def test_adr142_shared_contract_line_only_for_several_holders() -> None:
    out = Outcome(NUMBERS, refusal=Refusal.AMBIGUOUS, contracts=("NIFTY26O0624000CE",))
    assert refusal_line(out, holders=2) == ("Several strategies hold this contract. Use Zerodha's numbers needs a "
                                            "single holder; close via a basket or manage it on Kite.")
    assert refusal_line(out, holders=1) is None  # one holder: not the shared-contract case
    assert refusal_line(Outcome(PLACE, refusal=Refusal.AMBIGUOUS), holders=2) is None  # a tag twice: not this line


@pytest.mark.parametrize("refusal", sorted(set(Refusal) - {Refusal.ORDER_OPEN, Refusal.ENTRY_ORDER_OPEN,
                                                           Refusal.READ_STALE, Refusal.MARGIN_SHORT,
                                                           Refusal.AMBIGUOUS}, key=lambda r: r.value))
def test_refusals_without_an_adr142_line_get_none(refusal: Refusal) -> None:
    """No wording is invented: ADR-142 gives six lines; every other refusal has no line (the screen shows none)."""
    assert refusal_line(Outcome(PLACE, refusal=refusal)) is None


def test_built_outcome_has_no_line() -> None:
    assert refusal_line(Outcome(PLACE)) is None


@pytest.mark.parametrize(("when", "expected"), [
    (datetime.datetime(2026, 10, 20, 15, 30, tzinfo=IST), True),   # the close itself: carried overnight
    (datetime.datetime(2026, 10, 20, 20, 0, tzinfo=IST), True),
    (datetime.datetime(2026, 10, 21, 9, 14, tzinfo=IST), True),
    (datetime.datetime(2026, 10, 21, 9, 15, tzinfo=IST), False),   # session open
    (datetime.datetime(2026, 10, 21, 15, 29, tzinfo=IST), False),
    (datetime.datetime(2026, 10, 24, 11, 0, tzinfo=IST), True),    # Saturday
])
def test_adr142_overnight_line_after_the_close(when: datetime.datetime, expected: bool) -> None:
    line = overnight_line(when, datetime.date(2026, 10, 21))
    if expected:
        assert line == ("The market is closed. This position stays open overnight; nothing can be placed before "
                        "09:15 on Wed 21 Oct.")
    else:
        assert line is None


def test_overnight_line_needs_an_aware_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        overnight_line(datetime.datetime(2026, 10, 20, 20, 0), datetime.date(2026, 10, 21))  # noqa: DTZ001
