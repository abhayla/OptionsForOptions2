# ruff: noqa: PLR2004 - strikes and deltas of the fixture chain
"""Live test 2026-11-06 (strategy 88): every delta-targeted roll pick lands OUT of the money.

Before the fix, A-01 on NIFTY 17 Nov (spot 24,738.2; BUY 24300 PE / SELL 24500 PE / SELL 24950 CE / BUY 25150 CE, call
side tested) walked the untested put short UP past spot into the money and refused naming "SELL NIFTY 25,600.00 PE"
(an unquoted deep-ITM strike, delta about -0.9). Rolling IN stops short of spot: a put pick stays below spot, a call
pick above it; |delta| is compared (put deltas are negative). The fixture deltas are shaped like that day's chain.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

from ofo.adjustment.approaches import NO_STRATEGY_BASIS, ChainRow, Position, PositionLeg, build_approach
from ofo.adjustment.preferences import from_values as _prefs_from
from ofo.settings import defaults as _registry_defaults

CFG = replace(_prefs_from(_registry_defaults()).approach, roll_basis=NO_STRATEGY_BASIS)
EXPIRY = datetime.date(2026, 11, 17)
TODAY = datetime.date(2026, 11, 6)
SPOT = D("24738.2")
NO_STRIKE = "No strike in the chain brings {} to the target delta."


def _sym(typ: str, k: int) -> str:
    return f"NIFTY26N17{k}{typ}"


def _put_delta(k: int) -> D | None:
    """Put deltas (negative), rising in size toward and past spot; 25,600 and above unquoted (no delta, no price)."""
    if k >= 25600:
        return None
    return -min(D("0.95"), D("0.32") + D("0.04") * (k - 24500) / 50) if k >= 24500 else \
        -(D("0.32") - D("0.03") * (24500 - k) / 50)


def _call_delta(k: int) -> D | None:
    """Call deltas (positive), mirror shape: 25,000 at 0.31; 23,650 and below unquoted."""
    if k <= 23650:
        return None
    return min(D("0.95"), D("0.31") + D("0.04") * (25000 - k) / 50) if k <= 25000 else \
        D("0.31") - D("0.03") * (k - 25000) / 50


def _chain() -> list[ChainRow]:
    rows = []
    for k in range(23000, 26501, 50):
        for typ, delta in (("PE", _put_delta(k)), ("CE", _call_delta(k))):
            priced = delta is not None
            rows.append(ChainRow(D(k), typ, EXPIRY, _sym(typ, k), D("50.00") if priced else None, None, None,
                                 None if delta is None else min(delta, D("-0.01")) if typ == "PE" else
                                 max(delta, D("0.01"))))
    return rows


def _position(*legs: tuple[str, str, int]) -> Position:
    return Position("NIFTY", 75, "weekly", TODAY, tuple(
        PositionLeg(side, typ, D(k), EXPIRY, 1, D("40.00"), _sym(typ, k)) for side, typ, k in legs))


def _short(built, typ):
    return next(x.strike for x in built.after if x.side == "SELL" and x.type == typ)


def _delta(chain, typ, k):
    return next(r.delta for r in chain if (r.type, r.strike) == (typ, k))


# ---- the live case: the untested put short is already at the target; nothing OTM between it and spot fits ----------

def test_live_case_a01_never_walks_the_put_short_past_spot():
    """Strategy 88 shape: no OTM put between 24,500 and spot reaches 0.30, so A-01 is refused with the target-delta
    reason; it never names (or picks) a put strike above spot."""
    position = _position(("BUY", "PE", 24300), ("SELL", "PE", 24500), ("SELL", "CE", 24950), ("BUY", "CE", 25150))
    built = build_approach(position, _chain(), SPOT, "A-01", CFG)
    assert built.side == "put" and built.step_basis == "delta" and built.step_value == D("0.30")
    assert built.refusal is not None and "25,600" not in built.refusal
    assert built.refusal.startswith("No strike in the chain brings Leg 2 (SELL NIFTY 24,500 PE")
    assert built.refusal.endswith("to the target delta.")
    assert built.unpriced == () and built.trades == ()


def test_mirror_live_case_a01_never_walks_the_call_short_below_spot():
    """Put side tested: the untested call short (25,000, delta 0.31) has no OTM strike nearer spot at 0.30 or under:
    refused with the target-delta reason, never a call strike below spot (23,650 is the unquoted ITM gap)."""
    position = _position(("BUY", "PE", 24450), ("SELL", "PE", 24650), ("SELL", "CE", 25000), ("BUY", "CE", 25200))
    built = build_approach(position, _chain(), SPOT, "A-01", CFG)
    assert built.side == "call" and built.step_basis == "delta"
    assert built.refusal is not None and "23,650" not in built.refusal
    assert built.refusal.startswith("No strike in the chain brings Leg 3 (SELL NIFTY 25,000 CE")
    assert built.unpriced == ()


# ---- the target found OTM -----------------------------------------------------------------------------------------

def test_a01_put_pick_is_below_spot_at_the_nearest_abs_delta():
    """Untested put short at 24,300 (delta -0.20): rolled up to 24,450 (delta -0.29, the largest |delta| at or under
    0.30), below spot; the wing moves the same 150 points."""
    position = _position(("BUY", "PE", 24100), ("SELL", "PE", 24300), ("SELL", "CE", 24850), ("BUY", "CE", 25050))
    chain = _chain()
    built = build_approach(position, chain, SPOT, "A-01", CFG)
    assert built.refusal is None, built.refusal
    new = _short(built, "PE")
    assert new == D(24450) and new < SPOT
    assert _delta(chain, "PE", new) == D("-0.29")
    assert next(x.strike for x in built.after if x.side == "BUY" and x.type == "PE") == D(24250)
    # nearest |delta| to 0.30 among the OTM puts at or under the target
    otm = [r for r in chain if r.type == "PE" and r.strike < SPOT and r.delta is not None and abs(r.delta) <= D("0.30")]
    assert min(otm, key=lambda r: D("0.30") - abs(r.delta)).strike == new


def test_mirror_a01_call_pick_is_above_spot_at_the_nearest_delta():
    """Put side tested, untested call short at 25,200 (delta 0.19): rolled down to 25,050 (0.28), above spot."""
    position = _position(("BUY", "PE", 24450), ("SELL", "PE", 24650), ("SELL", "CE", 25200), ("BUY", "CE", 25400))
    chain = _chain()
    built = build_approach(position, chain, SPOT, "A-01", CFG)
    assert built.refusal is None, built.refusal
    new = _short(built, "CE")
    assert new == D(25050) and new > SPOT
    assert _delta(chain, "CE", new) == D("0.28")
    assert next(x.strike for x in built.after if x.side == "BUY" and x.type == "CE") == D(25250)


# ---- answer states ------------------------------------------------------------------------------------------------

def test_missing_delta_inside_the_otm_range_is_named_never_read_as_zero():
    """An OTM strike between the short and the pick with no delta is a gap: named, never treated as delta 0."""
    position = _position(("BUY", "PE", 24100), ("SELL", "PE", 24300), ("SELL", "CE", 24850), ("BUY", "CE", 25050))
    chain = [replace(r, delta=None) if (r.type, r.strike) == ("PE", D(24400)) else r for r in _chain()]
    built = build_approach(position, chain, SPOT, "A-01", CFG)
    assert built.refusal is not None and "24,400" in built.refusal and built.refusal.endswith(
        "has no price, and this approach trades it.")
    assert (EXPIRY, "PE", D(24400)) in built.unpriced


def test_itm_strike_with_a_small_delta_is_never_picked():
    """Structural guard: even a chain row on the ITM side carrying a small |delta| (a bad quote) is never picked."""
    position = _position(("BUY", "PE", 24300), ("SELL", "PE", 24500), ("SELL", "CE", 24950), ("BUY", "CE", 25150))
    chain = [replace(r, delta=D("-0.10")) if (r.type, r.strike) == ("PE", D(24800)) else r for r in _chain()]
    built = build_approach(position, chain, SPOT, "A-01", CFG)
    assert built.refusal is not None and built.refusal.endswith("to the target delta.")


def test_outward_rolls_pick_otm_strikes_at_or_under_the_target():
    """A-05 / A-02 (tested call short 24,950 moved out): the pick is above spot with delta at or under 0.30."""
    position = _position(("BUY", "PE", 24300), ("SELL", "PE", 24500), ("SELL", "CE", 24950), ("BUY", "CE", 25150))
    chain = _chain()
    for aid in ("A-05", "A-02"):
        built = build_approach(position, chain, SPOT, aid, CFG)
        assert built.refusal is None, (aid, built.refusal)
        new = _short(built, "CE")
        assert new == D(25050) and new > SPOT and _delta(chain, "CE", new) == D("0.28"), aid
