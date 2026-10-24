"""REQ-034 AC-4 (W-150, row 22): the default range build_outcome returns is chosen from spot, strikes, breakevens, risk
boundaries AND the expected move.

The expected move is ExpectedMove(ATM IV, days) (REQ-027 Q254): ATM IV = the mean of the CE and PE IVs at the strike
nearest the nearest leg expiry's parity forward (REQ-106 AC-1); days = calendar days from the valuation date in India
time to that expiry, at least 1. ATM IV not solved -> no expected move and today's range; the FROM_ENTRIES answer (no
live data) never carries one.

Real 2026-10-08 09:20:09 NIFTY frames, 13-Oct expiry: spot 22,533.25, forward 22,529.17, ATM strike 22,550, CE IV
0.124691, PE IV 0.125116, mean 0.1249035, days 5, move 330 - computed HERE by hand from the two quotes.
"""
import dataclasses
import datetime
from decimal import ROUND_CEILING, Decimal

import ofo.outcome.service as service_module
import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.inputs import LegInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import expiry_model, implied_vol
from ofo.marketdata.forward import mid_price
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, from_entries, read_snapshot
from ofo.rules.inputs import DataHealth
from ofo.scenario import levels as levels_module
from ofo.scenario.config import ScenarioConfig
from ofo.scenario.spot import spot_reading
from ofo.timeutil import IST
from outcome.test_from_entries import _spread, _stored
from outcome.test_same_engine import CONDOR, CURRENT, RATE, VALUATION, outcome_of

NEAREST = "NSE_FO:44604"  # 22400 PE, the condor leg nearest the 22,533.25 spot
FARTHEST = "NSE_FO:44632"  # 23000 CE
DAYS = 5  # 2026-10-08 -> 2026-10-13
NEAR, FAR = datetime.date(2026, 10, 13), datetime.date(2026, 10, 20)


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


def _atm_by_hand(provider, expiry, fwd=None):
    """REQ-106 AC-1 written out: the strike of the expiry's chain nearest its parity forward (ties: the lower), the CE
    and the PE IV solved by the engine from mid (sound bid/ask) else LTP, and their mean."""
    snap = read_snapshot(provider, "NIFTY", [iid for iid, *_ in CONDOR], VALUATION, RATE)
    fwd = fwd or snap.forwards[expiry]
    chain = [q for q in provider.option_chain_snapshot("NIFTY", expiry)
             if q.instrument_type in (Instrument.CE, Instrument.PE) and q.strike is not None]
    strike = min({q.strike for q in chain}, key=lambda k: (abs(k - fwd.forward), k))
    em = expiry_model(spot_reading(snap.spot), fwd, underlying="NIFTY")
    ivs = []
    for kind in (Instrument.CE, Instrument.PE):
        q = next(x for x in chain if x.strike == strike and x.instrument_type is kind)
        price = mid_price(q.bid, q.ask) if q.bid and q.ask and q.ask >= q.bid else q.ltp
        ivs.append(implied_vol(em, kind, price, strike).iv)
    return fwd.forward, strike, ivs[0], ivs[1], (ivs[0] + ivs[1]) / 2


def test_core_expected_move_is_the_atm_iv_move(replayed):
    """Core: build_outcome's move = spot x ATM IV x sqrt(days/365), rounded up; ATM IV per REQ-106 AC-1."""
    out = outcome_of(replayed)
    assert out.state is OutcomeState.COMPUTED, out.reason
    ls = out.level_set
    assert ls.current == CURRENT
    forward, strike, ce_iv, pe_iv, atm = _atm_by_hand(replayed, NEAR)
    expected = _hand_move(CURRENT, atm, DAYS)
    print(f"spot={CURRENT} forward={forward} atm_strike={strike} ce_iv={ce_iv} pe_iv={pe_iv} mean={atm} "
          f"days={DAYS} move={expected} range={ls.start}..{ls.end}")
    assert ls.expected_move_points == expected
    # the nearest leg's IV (the old rule) gives another number on these frames, so the IV basis is really tested
    assert _hand_move(CURRENT, _iv(out, NEAREST), DAYS) != expected


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


def _leg(kind, strike, expiry):
    return LegInput("NIFTY", f"NIFTY{strike}{kind.value}", Action.BUY, kind, None if kind is Instrument.FUT else
                    Decimal(strike), expiry, 65, Decimal("100"), None, None)


def _strategy(provider, legs):
    return StrategyDefinition("NIFTY", tuple(
        PlannedLeg(iid, act, 1, provider.book.get(iid, VALUATION).ltp, VALUATION) for iid, act in legs))


def _build(provider, definition, **kw):
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in definition.legs], VALUATION, RATE)
    return build_outcome(definition, snap, VALUATION, **kw)


ATM_PE = "NSE_FO:44615"  # 22550 PE, 13-Oct (CE is NSE_FO:44614): the strike nearest the 22,529.17 forward
ATM_MOVE = Decimal("330")  # 22,533.25 x 0.1249035 x sqrt(5/365), rounded up (the Core test computes it by hand)
WING = [("NSE_FO:44595", Action.SELL), ("NSE_FO:44632", Action.SELL)]  # 22200 PE / 23000 CE


def test_strangle_far_from_atm_gets_the_atm_move_not_its_wing_iv(replayed):
    """Attack 2: the nearest leg (22200 PE, 333.25 from spot) has a skewed wing IV; the move is still the ATM one."""
    out = _build(replayed, _strategy(replayed, WING))
    assert out.state is OutcomeState.COMPUTED, out.reason
    wing_iv = _iv(out, "NSE_FO:44595")
    print(f"wing iv={wing_iv} wing move={_hand_move(CURRENT, wing_iv, DAYS)} "
          f"atm move={out.level_set.expected_move_points}")
    assert _hand_move(CURRENT, wing_iv, DAYS) != ATM_MOVE
    assert out.level_set.expected_move_points == ATM_MOVE


def test_atm_strike_is_nearest_the_forward_not_the_spot(replayed):
    """REQ-106 AC-1: with the forward at 22,510 the ATM strike is 22,500 although the spot (22,533.25) is nearest
    22,550 - the forward decides."""
    snap = read_snapshot(replayed, "NIFTY", [iid for iid, *_ in CONDOR], VALUATION, RATE)
    fwd = dataclasses.replace(snap.forwards[NEAR], forward=Decimal("22510"))
    _, strike, ce_iv, pe_iv, mean = _atm_by_hand(replayed, NEAR, fwd)
    assert strike == Decimal("22500")
    got = service_module.atm_iv(dataclasses.replace(snap, forwards={NEAR: fwd}), NEAR)
    _, _, _, _, at_22550 = _atm_by_hand(replayed, NEAR)
    print(f"forward 22510: strike={strike} ce={ce_iv} pe={pe_iv} mean={mean} got={got}")
    assert got == mean and mean != at_22550


def _edit(q, **kw):
    return dataclasses.replace(q, **kw) if q.instrument_id == ATM_PE else q


@pytest.mark.parametrize("change", [
    lambda q: q,  # control: both ATM quotes usable -> the move
    lambda q: None if q.instrument_id == ATM_PE else q,  # PE quote missing
    lambda q: _edit(q, ltp=Decimal(0), bid=None, ask=None),  # a zero last price is no price
    lambda q: _edit(q, health=DataHealth.UNHEALTHY),  # an unusable quote
    lambda q: _edit(q, ltp=Decimal("0.05"), bid=None, ask=None),  # below intrinsic-free value: IV not solved
    lambda q: None,  # no chain at all
], ids=["control", "pe_missing", "pe_zero", "pe_unhealthy", "pe_unsolvable", "no_chain"])
def test_one_atm_side_unusable_means_no_move(replayed, change):
    """Attack 3: either ATM IV missing / unusable / unsolved, or no chain -> no move (the range is then today's)."""
    snap = read_snapshot(replayed, "NIFTY", [iid for iid, *_ in CONDOR], VALUATION, RATE)
    chains = {e: tuple(x for x in (change(q) for q in c) if x is not None) for e, c in snap.chains.items()}
    move = service_module._expected_move([_leg(Instrument.CE, "22800", NEAR)],
                                         dataclasses.replace(snap, chains=chains), VALUATION)
    if chains[NEAR] == snap.chains[NEAR]:  # only the control leaves the chain as read
        assert move is not None and move.points(CURRENT) == ATM_MOVE
    else:
        assert move is None


def test_refused_forward_means_no_move(replayed):
    """Attack 3: no forward for the nearest expiry -> no move (build_outcome itself refuses such an answer)."""
    snap = read_snapshot(replayed, "NIFTY", [iid for iid, *_ in CONDOR], VALUATION, RATE)
    assert service_module._expected_move([_leg(Instrument.CE, "22800", NEAR)],
                                         dataclasses.replace(snap, forwards={}), VALUATION) is None
    assert service_module._expected_move([], snap, VALUATION) is None


def test_nearest_expiry_decides_and_days_count_in_india_time(monkeypatch):
    """Several expiries: the nearest leg expiry's ATM IV and days; expiry today -> 1 day; India-time date."""
    asked = []
    monkeypatch.setattr(service_module, "atm_iv", lambda snap, expiry, shared=None, known=None: asked.append(expiry)
                        or Decimal("0.12"))
    legs = [_leg(Instrument.CE, "22500", FAR), _leg(Instrument.FUT, "0", NEAR), _leg(Instrument.PE, "22400", FAR)]
    move = service_module._expected_move(legs, None, VALUATION)
    assert (asked, move.iv, move.days) == ([NEAR], Decimal("0.12"), DAYS)
    today = datetime.datetime(2026, 10, 8, 15, 0, tzinfo=IST)
    assert service_module._expected_move([_leg(Instrument.CE, "22500", VALUATION.date())], None, today).days == 1
    late_utc = datetime.datetime(2026, 10, 7, 19, 0, tzinfo=datetime.UTC)  # 8-Oct 00:30 IST
    assert service_module._expected_move([_leg(Instrument.CE, "22500", NEAR)], None, late_utc).days == DAYS


NARROW = ScenarioConfig("NIFTY", Decimal("100"), Decimal("100"), Decimal("0"), 2, 200)  # the default, no half-width


@pytest.mark.parametrize("legs, config, before, after", [
    ([("NSE_FO:44604", Action.BUY)], NARROW, ("22100", "22800"), ("22000", "23100")),  # long 22400 PE
    ([("NSE_FO:44624", Action.BUY)], NARROW, ("22300", "23100"), ("22000", "23100")),  # long 22800 CE
    ([("NSE_FO:44604", Action.BUY)], None, ("21500", "23500"), ("21500", "23500")),  # default config: unchanged
    (WING, None, ("21500", "23500"), ("21500", "23500")),
], ids=["narrow_long_pe", "narrow_long_ce", "default_long_pe", "default_wing"])
def test_the_move_widens_the_range_on_build_outcome(replayed, monkeypatch, legs, config, before, after):  # noqa: PLR0913
    """Attack 4: on build_outcome, a narrow config's range is widened by the ATM move (spot +/- 330 plus 2 steps);
    the default config's range (its 1,000-point half-width already covers it) is unchanged."""
    d = _strategy(replayed, legs)
    kw = {} if config is None else {"config": config}
    with_move = _build(replayed, d, **kw).level_set
    monkeypatch.setattr(service_module, "_expected_move", lambda *a, **k: None)
    without = _build(replayed, d, **kw).level_set
    print(f"{legs} before={without.start}..{without.end} after={with_move.start}..{with_move.end}")
    assert with_move.expected_move_points == ATM_MOVE and without.expected_move_points is None
    assert (without.start, without.end) == tuple(Decimal(x) for x in before)
    assert (with_move.start, with_move.end) == tuple(Decimal(x) for x in after)
