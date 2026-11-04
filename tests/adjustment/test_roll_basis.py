"""ADR-243 roll basis (GC "Your adjustment settings" step 2): the basis in force (strategy plan, else user, else the
admin default "Target delta") decides where a roll places the new short. "Entry distance from spot" (REQ-046 Q255)
keeps widths and re-places the short at its entry distance from spot, snapped to a listed strike.

Core proof: the REQ-046 example - entered 353 points above spot (entry spot 23,047, short 23,400), spot now 23,300,
basis "Entry distance" -> the rolled call spread is 23,650 / 23,850. The basis is read through the ONE resolver
(``ofo.settings.layers``) with its source. Every answer state of the basis and of the entry spot has a test."""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

import pytest
from ofo.adjustment.approaches import (
    BASIS_CODES,
    ROLL_ENTRY_DISTANCE,
    ROLL_TARGET_DELTA,
    ChainRow,
    Position,
    PositionLeg,
    RollBasis,
    build_approach,
)
from ofo.settings import layers
from test_approaches import CFG, inputs, load

EXPIRY = datetime.date(2026, 11, 10)
NEXT = datetime.date(2026, 11, 17)
ENTRY_SPOT = D("23047")
SPOT = D("23300")
CFG20 = replace(CFG, target_short_delta={"weekly": D("0.20"), "monthly": D("0.20")})


def _delta(strike: int, typ: str, spot: D = SPOT) -> D:
    """A smooth made-up delta falling with distance from spot (|delta| 0.50 at spot, 0.01 per 25 points)."""
    away = (strike - spot) if typ == "CE" else (spot - strike)
    value = max(D("0.02"), D("0.50") - D(away) / D(2500)) if away >= 0 else min(D("0.98"), D("0.50") - D(away) / D(2500))
    return value if typ == "CE" else -value


def _chain(expiries=(EXPIRY,), step=50, low=22000, high=24600, with_delta=True):
    return [ChainRow(D(k), t, e, f"NIFTY{e:%y%m%d}{k}{t}", D("10.00"), D("9.95"), D("10.05"),
                     _delta(k, t) if with_delta else None)
            for e in expiries for k in range(low, high + 1, step) for t in ("CE", "PE")]


def _condor() -> Position:
    legs = (PositionLeg("BUY", "PE", D("22500"), EXPIRY, 1, D("5"), "p1"),
            PositionLeg("SELL", "PE", D("22700"), EXPIRY, 1, D("20"), "p2"),
            PositionLeg("SELL", "CE", D("23400"), EXPIRY, 1, D("20"), "c1"),
            PositionLeg("BUY", "CE", D("23600"), EXPIRY, 1, D("5"), "c2"))
    return Position("NIFTY", 65, "weekly", datetime.date(2026, 11, 5), legs)


def _basis(user: str | None = None, plan: str | None = None, entry_spot=ENTRY_SPOT, admin: D = D(1)) -> RollBasis:
    """The basis in force through the ONE resolver (as ``adjustment_check.roll_basis_of``): plan, else user, else
    admin default."""
    got = layers.resolve(layers.ROLL_BASIS, {layers.ROLL_BASIS: admin},
                         None if user is None else {layers.ROLL_BASIS: user},
                         None if plan is None else {layers.ROLL_BASIS: plan})
    return RollBasis(BASIS_CODES[got.value], got.source, entry_spot)


def _calls(built) -> list[D]:
    return sorted(x.strike for x in built.after if x.type == "CE")


def test_core_req046_example_entry_distance_rolls_the_call_spread_to_23650_23850():
    """The REQ-046 example (Q255): 23,300 + 353 = 23,653 -> 23,650 on the 50-point grid; the 200-point wing kept."""
    basis = _basis(user="2")
    assert (basis.code, basis.source) == (ROLL_ENTRY_DISTANCE, layers.SOURCE_USER)
    built = build_approach(_condor(), _chain(), SPOT, "A-05", replace(CFG20, roll_basis=basis))
    assert built.refusal is None
    assert _calls(built) == [D("23650"), D("23850")]
    assert (built.step_basis, built.step_value, built.basis_source) == (ROLL_ENTRY_DISTANCE, D("353"), "user")


def test_strategy_override_target_delta_gives_todays_delta_strike():
    """Same strategy, plan says Target delta: the 0.20-delta strike (today's result, byte-identical)."""
    position, chain = _condor(), _chain()
    today = build_approach(position, chain, SPOT, "A-05", CFG20)
    basis = _basis(user="2", plan="1")
    assert (basis.code, basis.source) == (ROLL_TARGET_DELTA, layers.SOURCE_STRATEGY)
    built = build_approach(position, chain, SPOT, "A-05", replace(CFG20, roll_basis=basis))
    assert _calls(built) == _calls(today)
    assert (built.trades, built.after, built.step_basis, built.step_value) == \
        (today.trades, today.after, "delta", D("0.20"))
    assert built.basis_source == "strategy"
    # the first strike beyond 23,400 at or under 0.20: 0.50 - (k - 23300)/2500 <= 0.20 -> k >= 24050
    assert _calls(built)[0] == D("24050")


def test_no_user_value_is_the_target_delta_default():
    basis = _basis()
    assert (basis.code, basis.source) == (ROLL_TARGET_DELTA, layers.SOURCE_DEFAULT)
    built = build_approach(_condor(), _chain(), SPOT, "A-05", replace(CFG20, roll_basis=basis))
    assert (built.step_basis, built.basis_source) == ("delta", "default")


@pytest.mark.parametrize("approach", ["A-01", "A-02", "A-04", "A-05"])
def test_entry_distance_without_a_stored_entry_spot_fails_closed_naming_the_leg(approach):
    """Never the delta rule silently: every roll approach is refused with the named reason."""
    basis = _basis(user="2", entry_spot=None)
    built = build_approach(_condor(), _chain((EXPIRY, NEXT)), SPOT, approach, replace(CFG20, roll_basis=basis))
    assert built.refusal is not None and "spot at entry is not stored" in built.refusal
    assert built.trades == () and built.refusal_message.code == "USER_INPUT_191"  # type: ignore[union-attr]


@pytest.mark.parametrize("approach", ["A-01", "A-02", "A-04", "A-05"])
def test_an_unreadable_basis_refuses_every_roll(approach):
    basis = RollBasis(None, None, ENTRY_SPOT, layers.USER_UNREADABLE)
    built = build_approach(_condor(), _chain((EXPIRY, NEXT)), SPOT, approach, replace(CFG20, roll_basis=basis))
    assert built.refusal is not None and "roll basis setting" in built.refusal


def test_a_basis_code_the_builder_does_not_know_is_refused_never_delta():
    basis = RollBasis("something_else", "user", ENTRY_SPOT)
    built = build_approach(_condor(), _chain(), SPOT, "A-05", replace(CFG20, roll_basis=basis))
    assert built.refusal is not None and "roll basis setting" in built.refusal


def test_resolver_refuses_a_basis_value_outside_the_registry():
    with pytest.raises(layers.LayerUnreadable) as exc:
        layers.resolve(layers.ROLL_BASIS, {layers.ROLL_BASIS: D(1)}, {layers.ROLL_BASIS: "3"}, None)
    assert exc.value.code == layers.USER_UNREADABLE


def test_entry_distance_put_side_and_a01_roll_in():
    """A-01 rolls the untested put in: 22,700 entered 347 below 23,047 -> 23,300 - 347 = 22,953 -> 22,950; wing 22,750."""
    basis = _basis(user="2")
    built = build_approach(_condor(), _chain(), SPOT, "A-01", replace(CFG20, roll_basis=basis))
    assert built.refusal is None
    assert sorted(x.strike for x in built.after if x.type == "PE") == [D("22750"), D("22950")]
    assert built.step_value == D("347")


def test_entry_distance_a02_moves_only_the_short_and_a04_uses_the_next_expiry_listing():
    basis = _basis(user="2")
    cfg = replace(CFG20, roll_basis=basis)
    a02 = build_approach(_condor(), _chain(), SPOT, "A-02", cfg)
    assert a02.refusal is not None  # 23,650 is beyond the 23,600 wing: A-02's own refusal, not a delta pick
    position = replace(_condor(), legs=tuple(replace(x, strike=D("23900")) if x.tradingsymbol == "c2" else x
                                             for x in _condor().legs))
    a02 = build_approach(position, _chain(), SPOT, "A-02", cfg)
    assert _calls(a02) == [D("23650"), D("23900")]
    a04 = build_approach(_condor(), _chain((EXPIRY, NEXT)), SPOT, "A-04", cfg)
    assert {x.expiry for x in a04.after if x.type == "CE"} == {NEXT} and _calls(a04) == [D("23650"), D("23850")]


def test_snapping_only_to_listed_strikes_of_the_type_and_expiry():
    """23,653 with 23,650 NOT listed: the nearest listed is 23,700 (23,600 is 53 away, 23,700 is 47); never a
    strike the listing does not hold; widths kept (wing 23,900)."""
    chain = [r if not (r.strike == D("23650") and r.type == "CE") else replace(r, listed=False) for r in _chain()]
    chain = [r for r in chain if not (r.type == "CE" and r.strike in (D("23600"),) and r.expiry == EXPIRY)] + \
        [ChainRow(D("23600"), "CE", EXPIRY, "c2", D("10.00"), D("9.95"), D("10.05"), _delta(23600, "CE"))]
    built = build_approach(_condor(), chain, SPOT, "A-05", replace(CFG20, roll_basis=_basis(user="2")))
    assert built.refusal is None and _calls(built) == [D("23700"), D("23900")]


def test_a_tie_snaps_to_the_strike_farther_from_spot():
    """Grid of 100: 23,300 + 353 = 23,653 is nearest 23,700; entry spot 23,050 -> 350 -> 23,650 ties 23,600/23,700
    -> 23,700 (farther from spot, the safer short)."""
    chain = _chain(step=100)
    built = build_approach(_condor(), chain, SPOT, "A-05",
                           replace(CFG20, roll_basis=_basis(user="2", entry_spot=D("23050"))))
    assert _calls(built) == [D("23700"), D("23900")]


@pytest.mark.parametrize("sid", ["ADJ-02"])
@pytest.mark.parametrize("approach", ["A-01", "A-02", "A-04", "A-05", "A-06"])
def test_users_who_change_nothing_get_byte_identical_rolls(sid, approach):
    """No basis read (None) and the default basis (Target delta, source default) build the same legs as today."""
    position, chain, spot = inputs(load(sid))
    today = build_approach(position, chain, spot, approach, CFG)
    default = build_approach(position, chain, spot, approach, replace(CFG, roll_basis=_basis()))
    assert replace(default, basis_source=None) == today
