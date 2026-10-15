"""W-086 / REQ-056 AC-6 (ADR-083 decision 2): entering a contract on its own expiry day.

Spec basis: ADR-083 "a SHORT leg expiring that day needs the explicit acknowledgement"; REQ-056 AC-6 "elevated -> warn;
exceptional -> explicit acknowledgement"; F-20 (extra 2% ELM on short options on expiry day, no calendar benefit).

The contracts are the REAL SENSEX 2026-10-15 rows of the recorded Zerodha list (tests/fixtures/kite_ws/). The trading
date is the context clock (``as_of``) in IST, never the wall clock.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from pathlib import Path

import pytest
from execution_inputs import AS_OF, IST, all_true_context, check, closing_orders

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import ExecutionAction, FlagCode, VersionState
from ofo.instruments import Catalogue, EligibilityRegistry, EligibilityStatus, parse_instruments_csv

CSV = Path(__file__).resolve().parents[1] / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
EXPIRY = datetime.date(2026, 10, 15)
LOT = 20
DAY = datetime.datetime(2026, 10, 15, 10, 0, tzinfo=IST)
DAY_BEFORE = datetime.datetime(2026, 10, 14, 10, 0, tzinfo=IST)
EXPIRY_FLAGS = {FlagCode.EXPIRY_DAY_ENTRY, FlagCode.EXPIRY_DAY_SHORT}


@pytest.fixture(scope="module")
def cat() -> Catalogue:
    c = Catalogue()
    c.load(parse_instruments_csv(CSV))
    return c


@pytest.fixture(scope="module")
def elig(cat: Catalogue) -> EligibilityRegistry:
    r = EligibilityRegistry()
    for e in cat.all_entries():
        r.record(EligibilityStatus(e.contract.id, True, AS_OF))
    return r


def _symbol(cat: Catalogue, kind: str) -> str:
    """The real Zerodha trading symbol of the 72600 contract, read from the recorded list (no typed literal)."""
    (entry,) = [e for e in cat.all_entries() if e.contract.name == "SENSEX" and e.contract.expiry == EXPIRY
                and e.contract.instrument_type == kind and e.contract.strike == D("72600")]
    return entry.ref("zerodha").broker_symbol


def _leg(action: Action, kind: Instrument = Instrument.CE, strike: str = "72600") -> Leg:
    return Leg(action, kind, D(strike), EXPIRY, LOT, D("50.00"))


def _run(legs, cat, elig, as_of=DAY, **kw):
    ctx = all_true_context(underlying="SENSEX", as_of=as_of, **kw)
    return check(Strategy(tuple(legs)), ctx, cat, elig)


def _codes(result) -> set:
    return {f.code for f in result.flags} & EXPIRY_FLAGS


def test_sell_leg_on_its_expiry_day_requires_the_acknowledgement(cat, elig):
    r = _run([_leg(Action.SELL)], cat, elig)
    assert not r.blocked
    assert r.requires_confirmation is True
    assert FlagCode.EXPIRY_DAY_SHORT in _codes(r)
    assert "expiry-day margin" in r.confirmation_text
    assert _symbol(cat, "CE") in r.confirmation_text


def test_buy_leg_on_its_expiry_day_only_warns_and_names_the_extra_margin(cat, elig):
    r = _run([_leg(Action.BUY)], cat, elig)
    assert not r.blocked
    assert r.requires_confirmation is False
    assert r.confirmation_text is None
    assert _codes(r) == {FlagCode.EXPIRY_DAY_ENTRY}
    (flag,) = [f for f in r.flags if f.code is FlagCode.EXPIRY_DAY_ENTRY]
    assert "expiry-day margin" in flag.message and "2%" in flag.message


@pytest.mark.parametrize("action", [Action.SELL, Action.BUY])
def test_same_legs_one_day_before_expiry_get_neither(action, cat, elig):
    r = _run([_leg(action)], cat, elig, as_of=DAY_BEFORE)
    assert _codes(r) == set()
    assert r.requires_confirmation is False


def test_mixed_strategy_acknowledges_only_because_of_the_short_leg(cat, elig):
    legs = [_leg(Action.BUY, Instrument.PE), _leg(Action.SELL, Instrument.CE)]
    r = _run(legs, cat, elig)
    assert _codes(r) == {FlagCode.EXPIRY_DAY_ENTRY, FlagCode.EXPIRY_DAY_SHORT}
    assert r.requires_confirmation is True
    assert _symbol(cat, "CE") in r.confirmation_text
    assert _symbol(cat, "PE") not in r.confirmation_text


def test_date_comes_from_the_context_clock_in_ist(cat, elig):
    utc = datetime.timezone.utc
    # 23:30 UTC on 14 Oct is 05:00 IST on 15 Oct: expiry day.
    r = _run([_leg(Action.SELL)], cat, elig, as_of=datetime.datetime(2026, 10, 14, 23, 30, tzinfo=utc))
    assert FlagCode.EXPIRY_DAY_SHORT in _codes(r)
    # 18:00 UTC on 14 Oct is 23:30 IST on 14 Oct: still the day before.
    r = _run([_leg(Action.SELL)], cat, elig, as_of=datetime.datetime(2026, 10, 14, 18, 0, tzinfo=utc))
    assert _codes(r) == set()


def test_an_exit_is_not_affected(cat, elig):
    held = (_leg(Action.SELL),)
    r = _run(closing_orders(held), cat, elig, action=ExecutionAction.EXIT, active_legs=held)
    assert not r.blocked
    assert _codes(r) == set()
    assert r.requires_confirmation is False


def test_an_adjustment_selling_an_expiring_contract_needs_the_acknowledgement(cat, elig):
    held = (_leg(Action.BUY, Instrument.PE),)
    r = _run([_leg(Action.SELL)], cat, elig, action=ExecutionAction.ADJUSTMENT, active_legs=held,
             version_state=VersionState.PROPOSED)
    assert FlagCode.EXPIRY_DAY_SHORT in _codes(r)
    assert r.requires_confirmation is True


def test_a_blocked_result_does_not_ask_for_confirmation(cat, elig):
    r = _run([_leg(Action.SELL)], cat, elig, market_open=False)
    assert r.blocked and r.requires_confirmation is False


def test_an_already_expired_contract_is_blocked_and_carries_no_expiry_day_flag(cat, elig):
    past = Leg(Action.SELL, Instrument.CE, D("72600"), datetime.date(2026, 10, 8), LOT, D("50.00"))
    r = _run([past], cat, elig)
    assert r.blocked
    assert _codes(r) == set()
