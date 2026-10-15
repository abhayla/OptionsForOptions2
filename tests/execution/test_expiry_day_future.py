"""Issue #275 item 4 (W-086 minor): a FUTURE expiring today.

Basis: F-20 (the extra 2% ELM on expiry day is for short OPTIONS; a future gets no such claim); ADR-083 decision 2
(only a short OPTION leg needs the acknowledgement). The contract is the REAL SENSEX26OCTFUT row (expiry 2026-10-29,
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


@pytest.mark.parametrize("action", [Action.SELL, Action.BUY])
def test_a_future_expiring_today_warns_without_option_text_or_acknowledgement(action, cat, elig):
    r = _run(action, cat, elig)
    assert not r.blocked
    assert r.requires_confirmation is False and r.confirmation_text is None
    flags = [f for f in r.flags if f.code in EXPIRY_FLAGS]
    assert [f.code for f in flags] == [FlagCode.EXPIRY_DAY_ENTRY]
    (flag,) = flags
    assert "SENSEX26OCTFUT" in flag.message and "expires today" in flag.message
    assert "no margin offset" in flag.message and "cash-settled" in flag.message
    assert "2%" not in flag.message and "short options" not in flag.message


def test_the_same_future_a_day_earlier_is_not_flagged(cat, elig):
    r = _run(Action.SELL, cat, elig, as_of=DAY_BEFORE)
    assert {f.code for f in r.flags} & EXPIRY_FLAGS == set()
