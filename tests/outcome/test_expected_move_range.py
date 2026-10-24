"""REQ-034 AC-4 (W-150, row 22): the default range build_outcome returns is chosen from spot, strikes, breakevens, risk
boundaries AND the expected move.

The expected move is ExpectedMove(iv, days): iv = the IV the outcome solved for the OPTION leg whose strike is nearest
the live spot, on the nearest leg expiry (ties: the lower strike); days = calendar days from the valuation date in India
time to that expiry, at least 1. No option leg with a solved IV -> no expected move and today's range; the FROM_ENTRIES
answer (no live data) never carries one.

Real 2026-10-08 09:20:09 NIFTY frames, the 13-Oct iron condor of test_same_engine: spot 22,533.25, nearest strike
22,400 PE (133.25 away; 22,800 CE is 266.75 away), days 8-Oct -> 13-Oct = 5. The move is computed HERE in Decimal from
the leg IV the answer reports: spot x IV x sqrt(5/365), rounded up to a whole point.
"""
import datetime
from decimal import ROUND_CEILING, Decimal

import ofo.outcome.service as service_module
import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.inputs import LegInput
from ofo.engine.legs import Action, Instrument
from ofo.outcome import OutcomeState, from_entries
from ofo.scenario import levels as levels_module
from ofo.timeutil import IST
from outcome.test_from_entries import _spread, _stored
from outcome.test_same_engine import CURRENT, VALUATION, outcome_of

NEAREST = "NSE_FO:44604"  # 22400 PE, the condor leg nearest the 22,533.25 spot
FARTHEST = "NSE_FO:44632"  # 23000 CE
DAYS = 5  # 2026-10-08 -> 2026-10-13


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _hand_move(spot, iv, days):
    return (spot * iv * (Decimal(days) / Decimal(365)).sqrt()).to_integral_value(rounding=ROUND_CEILING)


def _iv(out, iid):
    return next(leg.iv for leg in out.legs if leg.instrument_id == iid)


def test_core_expected_move_from_the_nearest_leg_reaches_the_range(replayed):
    out = outcome_of(replayed)
    assert out.state is OutcomeState.COMPUTED, out.reason
    ls = out.level_set
    assert ls.current == CURRENT
    iv = _iv(out, NEAREST)
    assert iv is not None
    expected = _hand_move(CURRENT, iv, DAYS)
    print(f"spot={CURRENT} iv(22400PE)={iv} days={DAYS} move={expected} range={ls.start}..{ls.end}")
    assert ls.expected_move_points == expected
    # the farthest leg's IV gives another number on these frames (so the leg choice is really tested)
    assert _hand_move(CURRENT, _iv(out, FARTHEST), DAYS) != expected
    assert ls.start <= CURRENT - expected and ls.end >= CURRENT + expected


def test_no_solved_iv_means_no_expected_move_and_todays_range(replayed, monkeypatch):
    """Attack 2: every option leg without a solved IV -> no expected move; the range equals the one built without it."""
    monkeypatch.setattr(service_module, "_leg_iv", lambda *a, **k: None)
    calls = []
    real = levels_module.build_level_set

    def spy(model, config, **kw):
        calls.append((model, config, kw))
        return real(model, config, **kw)

    monkeypatch.setattr(service_module, "build_level_set", spy)
    out = outcome_of(replayed)
    assert out.state is OutcomeState.COMPUTED, out.reason
    assert all(leg.iv is None for leg in out.legs)
    assert out.level_set.expected_move_points is None
    (model, config, kw), = calls
    assert kw.get("expected_move") is None
    today = real(model, config)
    assert (out.level_set.start, out.level_set.end, out.level_set.levels) == (today.start, today.end, today.levels)


def test_from_entries_never_carries_an_expected_move():
    """Attack 3: no live data, no IV -> the FROM_ENTRIES level set has no expected move."""
    out = from_entries(_spread(), None, _stored(), VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    assert out.level_set.expected_move_points is None


def _leg(kind, strike, expiry, iv):
    return LegInput("NIFTY", f"NIFTY{strike}{kind.value}", Action.BUY, kind, None if kind is Instrument.FUT else
                    Decimal(strike), expiry, 65, Decimal("100"), None, None if iv is None else Decimal(iv))


NEAR, FAR = datetime.date(2026, 10, 13), datetime.date(2026, 10, 20)


@pytest.mark.parametrize("legs, expected", [
    # several expiries: the nearest one decides, even when a farther leg's strike is nearer the spot
    ([_leg(Instrument.CE, "22500", FAR, "0.20"), _leg(Instrument.PE, "22400", NEAR, "0.11"),
      _leg(Instrument.CE, "22800", NEAR, "0.13")], (Decimal("0.11"), 5)),
    # tie on distance (22,500 and 22,600 from 22,550): the lower strike
    ([_leg(Instrument.CE, "22600", NEAR, "0.14"), _leg(Instrument.PE, "22500", NEAR, "0.12")], (Decimal("0.12"), 5)),
    # an option leg without a solved IV is skipped; futures never carry one
    ([_leg(Instrument.FUT, "0", NEAR, None), _leg(Instrument.PE, "22550", NEAR, None),
      _leg(Instrument.CE, "22900", NEAR, "0.15")], (Decimal("0.15"), 5)),
    ([_leg(Instrument.FUT, "0", NEAR, None)], None),  # futures only
    ([_leg(Instrument.CE, "22500", NEAR, None)], None),  # IV not solved
])
def test_expected_move_leg_choice(legs, expected):
    valuation = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
    move = service_module._expected_move(legs, Decimal("22550"), valuation)
    assert (None if move is None else (move.iv, move.days)) == expected


def test_expected_move_days_in_india_time_at_least_one():
    """Expiry today -> 1 day; 8-Oct 23:30 IST is 18:00 UTC the same date, counted in India time."""
    legs = [_leg(Instrument.CE, "22500", datetime.date(2026, 10, 8), "0.12")]
    today = datetime.datetime(2026, 10, 8, 15, 0, tzinfo=IST)
    assert service_module._expected_move(legs, Decimal("22550"), today).days == 1
    late_utc = datetime.datetime(2026, 10, 7, 19, 0, tzinfo=datetime.UTC)  # 8-Oct 00:30 IST
    legs = [_leg(Instrument.CE, "22500", NEAR, "0.12")]
    assert service_module._expected_move(legs, Decimal("22550"), late_utc).days == DAYS

