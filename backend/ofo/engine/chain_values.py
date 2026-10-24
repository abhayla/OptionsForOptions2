"""The extra Option Chain values of one contract: per-lot premium, intrinsic value, time value, breakeven and
breakeven %, and the engine's Greeks (W-124; REQ-087 AC-1/AC-4/AC-5, REQ-029 AC-3). Standard library plus the engine.

Copy from: none - no algochanakya row. Taken from branch build/W-124-a3-chain (PR #509, row 33-35 code; ADR-171
reuse rule: this file and its test only) with ``iv`` added to ``ChainGreeks`` for the leg picker (REQ-080 AC-2).
Money is ``Decimal`` end to end (ADR-008); the browser only draws the strings.

- intrinsic value is measured against the SPOT (the index price), labelled so on the screen: call max(S - K, 0),
  put max(K - S, 0); time value is LTP minus intrinsic and may be negative (a stale deep in-the-money price is shown
  as it is, never clamped); breakeven is K + LTP for a call and K - LTP for a put; breakeven % is
  (breakeven - S) / S x 100, signed, half-up to 0.01.
- A value whose input is missing is None (the screen draws a dash), never 0 (REQ-087 AC-5): no LTP -> every
  LTP-dependent value is None; no spot -> intrinsic, time value and breakeven % are None. A breakeven at or below zero
  (a deep put) is None: the contract cannot break even inside the index's range.
- Greeks come from the engine's own model at the live spot with the expiry's forward (ADR-056/063), never from the
  vendor's numbers: the contract's implied volatility from the engine's one IV price (``iv_price``, ADR-172: the mid
  when both sides are live and not crossed, else the LTP - the same number the outcome leg shows), then
  ``bs_greeks``. Any refusal gives no Greeks.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ofo.engine.legs import Instrument
from ofo.engine.model import expiry_model, greeks, implied_vol, iv_price
from ofo.marketdata.forward import ForwardUnavailable, parity_forward
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import HUNDREDTH, PAISE
from ofo.scenario.spot import SpotRefused, spot_reading

_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class CellValues:
    """Each field None = "not computable now" (drawn as a dash)."""

    per_lot: Decimal | None  # LTP x the contract's lot size
    intrinsic: Decimal | None
    time_value: Decimal | None
    breakeven: Decimal | None
    breakeven_pct: Decimal | None


@dataclass(frozen=True)
class ChainGreeks:
    iv: Decimal  # the engine's implied volatility as a fraction (0.1134 = 11.34 %), from the contract's price
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal


def cell_values(kind: str, strike: Decimal, ltp: Decimal | None, spot: Decimal | None, lot_size: int) -> CellValues:
    """The extra values of one option cell. ``ltp`` is the price as shown (None: no live price); ``spot`` None: none."""
    if kind not in ("CE", "PE"):
        raise ValueError(f"an option side is CE or PE, got {kind!r}")
    priced = ltp is not None and is_live_price(ltp)
    per_lot = ltp * lot_size if priced else None
    intrinsic = None
    if spot is not None and is_live_price(spot):
        intrinsic = max(spot - strike, Decimal(0)) if kind == "CE" else max(strike - spot, Decimal(0))
    breakeven = None
    if priced:
        breakeven = strike + ltp if kind == "CE" else strike - ltp
        if breakeven <= 0:
            breakeven = None
    time_value = ltp - intrinsic if priced and intrinsic is not None else None
    pct = None
    if breakeven is not None and spot is not None and is_live_price(spot):
        pct = ((breakeven - spot) / spot * _HUNDRED).quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
    return CellValues(
        per_lot=None if per_lot is None else per_lot.quantize(PAISE, rounding=ROUND_HALF_UP),
        intrinsic=None if intrinsic is None else intrinsic.quantize(PAISE, rounding=ROUND_HALF_UP),
        time_value=None if time_value is None else time_value.quantize(PAISE, rounding=ROUND_HALF_UP),
        breakeven=None if breakeven is None else breakeven.quantize(PAISE, rounding=ROUND_HALF_UP),
        breakeven_pct=pct)


def in_the_money(kind: str, strike: Decimal, spot: Decimal | None) -> bool | None:
    """REQ-087 AC-2: calls with a strike below the spot, puts with a strike above it. None without a live spot (the
    shading is then off, with the reason on the screen), never False."""
    if kind not in ("CE", "PE"):
        raise ValueError(f"an option side is CE or PE, got {kind!r}")
    if spot is None or not is_live_price(spot):
        return None
    return strike < spot if kind == "CE" else strike > spot


def chain_greeks(chain: Iterable[NormalizedQuote], spot_quote: NormalizedQuote | None, expiry: datetime.date,
                 valuation: datetime.datetime, rate: Decimal) -> Mapping[str, ChainGreeks]:
    """instrument_id -> engine Greeks for each option of the expiry whose price gives an implied volatility. Empty when
    the spot or the expiry's forward is refused; a contract the model refuses is simply left out."""
    quotes = list(chain)
    try:
        em = expiry_model(spot_reading(spot_quote), parity_forward(quotes, spot_quote, expiry, valuation, rate))
    except (SpotRefused, ForwardUnavailable, ValueError, ArithmeticError):
        return {}
    out: dict[str, ChainGreeks] = {}
    for q in quotes:
        if q.instrument_type not in (Instrument.CE, Instrument.PE) or q.strike is None or not is_live_price(q.ltp):
            continue
        try:
            vol = implied_vol(em, q.instrument_type, iv_price(q), q.strike).iv
            g = greeks(em, q.instrument_type, q.strike, vol).greeks
        except (ValueError, ArithmeticError):
            continue
        out[q.instrument_id] = ChainGreeks(vol, g.delta, g.gamma, g.theta, g.vega)
    return out
