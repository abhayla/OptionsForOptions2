"""Issue #275 item 4 (W-086 minor): a FUTURE expiring today.

Basis: F-20 (the extra 2% ELM on expiry day is for short OPTIONS; a future gets no such claim); ADR-083 decision 2
(a SHORT leg expiring that day needs the explicit acknowledgement; it does not limit that to options). The contract is the REAL SENSEX26OCTFUT row (expiry 2026-10-29,
lot 20) of the recorded instrument-list slice (tests/fixtures/instruments/).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from execution_inputs import FIXTURE, IST, all_true_context, check

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import FlagCode
from ofo.instruments import Catalogue, EligibilityRegistry, EligibilityStatus, parse_instruments_csv

FUT_EXPIRY = datetime.date(2026, 10, 29)
DAY = datetime.datetime(2026, 10, 29, 10, 0, tzinfo=IST)
DAY_BEFORE = datetime.datetime(2026, 10, 28, 10, 0, tzinfo=IST)
EXPIRY_FLAGS = {FlagCode.EXPIRY_DAY_ENTRY, FlagCode.EXPIRY_DAY_SHORT}


@pytest.fixture(scope="module")
def cat() -> Catalogue:
    c = Catalogue()
    c.load(parse_instruments_csv(FIXTURE))
    return c


@pytest.fixture(scope="module")
def elig(cat: Catalogue) -> EligibilityRegistry:
    r = EligibilityRegistry()
    for e in cat.all_entries():
        r.record(EligibilityStatus(e.contract.id, True, DAY))
    return r


def _run(action: Action, cat, elig, as_of=DAY):
    leg = Leg(action, Instrument.FUT, None, FUT_EXPIRY, 20, D("75600.00"))
    return check(Strategy((leg,)), all_true_context(underlying="SENSEX", as_of=as_of), cat, elig)


def test_a_long_future_expiring_today_only_warns():
    r = _run(Action.BUY, CAT, ELIG)
    assert not r.blocked and r.requires_confirmation is False and r.confirmation_text is None
    (flag,) = [f for f in r.flags if f.code in EXPIRY_FLAGS]
    assert flag.code is FlagCode.EXPIRY_DAY_ENTRY
    assert "SENSEX26OCTFUT" in flag.message and "no margin offset" in flag.message and "cash-settled" in flag.message
    assert "2%" not in flag.message and "short options" not in flag.message


def test_a_short_future_expiring_today_needs_the_acknowledgement_without_the_option_claim():
    r = _run(Action.SELL, CAT, ELIG)
    assert not r.blocked and r.requires_confirmation is True
    (flag,) = [f for f in r.flags if f.code in EXPIRY_FLAGS]
    assert flag.code is FlagCode.EXPIRY_DAY_SHORT_FUTURE
    text = r.confirmation_text
    assert "SENSEX26OCTFUT" in text and "cash-settled" in text and "no margin offset" in text
    assert "2%" not in text and "short options" not in text and "calendar" not in text
    assert text.count("Confirm to continue.") == 1 and text.endswith("Confirm to continue.")


def test_short_options_and_short_futures_share_one_confirm_sentence():
    from ofo.execution.safety import Flag, _confirmation_text
    from ofo.errors.explanations import render_explanation
    flags = [Flag(FlagCode.EXPIRY_DAY_SHORT, render_explanation("flag_expiry_day_short", symbol="AAA1CE"), ("AAA1CE",)),
             Flag(FlagCode.EXPIRY_DAY_SHORT, render_explanation("flag_expiry_day_short", symbol="AAA1PE"), ("AAA1PE",)),
             Flag(FlagCode.EXPIRY_DAY_SHORT_FUTURE,
                  render_explanation("flag_expiry_day_future_short", symbol="AAAFUT"), ("AAAFUT",))]
    text = _confirmation_text(flags)
    assert text.count("Confirm to continue.") == 1
    assert "AAA1CE, AAA1PE" in text and "AAAFUT" in text
    assert text.count("an extra 2% on short options") == 1


def test_the_same_future_a_day_earlier_is_not_flagged(cat, elig):
    r = _run(Action.SELL, cat, elig, as_of=DAY_BEFORE)
    assert {f.code for f in r.flags} & EXPIRY_FLAGS == set()
